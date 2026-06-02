"""
每日复盘 - 交易日 21:00 自动生成
数据源：全部 Tushare（不依赖 AKShare）
  - 大盘指数：腾讯 Finance
  - 名称映射：stock_basic（每日缓存一次）
  - 涨跌幅排名：daily
  - 涨跌停统计：limit_list_d（有积分时），否则从 daily 推算
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger

_DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _is_excluded_board(ts_code: str) -> bool:
    """排除创业板（300/301）和科创板（688/689）"""
    c = ts_code.split(".")[0]
    return c.startswith("300") or c.startswith("301") or \
           c.startswith("688") or c.startswith("689")


def _get_pro():
    import tushare as ts
    return ts.pro_api(os.getenv("TUSHARE_TOKEN", ""))


# ─── 名称映射（每日缓存）────────────────────────────────────────
def _get_name_map(pro, today: str) -> Dict[str, str]:
    """从 stock_basic 获取 ts_code->name，结果写文件缓存当天复用"""
    cache = _DATA_DIR / "stock_basic_cache.csv"
    if cache.exists():
        first_line = cache.open().readline().strip()
        if first_line == f"# date={today}":
            import pandas as pd
            df = pd.read_csv(cache, comment="#")
            return dict(zip(df["ts_code"], df["name"]))

    basic = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")
    with cache.open("w") as f:
        f.write(f"# date={today}\n")
        basic.to_csv(f, index=False)
    return dict(zip(basic["ts_code"], basic["name"]))


# ─── 大盘指数 ──────────────────────────────────────────────────
def _fetch_market_summary() -> Dict:
    try:
        import requests
        symbols = {"sh000001": "上证", "sz399001": "深证",
                   "sz399006": "创业板", "sh000016": "上证50"}
        codes = ",".join(f"s_{c}" for c in symbols)
        resp = requests.get(f"http://qt.gtimg.cn/q={codes}", timeout=8)
        resp.encoding = "gbk"
        indices = {}
        for line in resp.text.strip().split("\n"):
            parts = line.split("~")
            if len(parts) < 6:
                continue
            for code, name in symbols.items():
                if code in line:
                    try:
                        indices[name] = {"price": float(parts[3]), "pct": float(parts[5])}
                    except Exception:
                        pass
        return indices
    except Exception as e:
        logger.warning(f"获取大盘数据失败: {e}")
        return {}


# ─── 涨跌停统计 ────────────────────────────────────────────────
def _fetch_limit_stats(pro, today: str, daily_df) -> Dict:
    """
    优先用 limit_list_d（含行业/连板）；
    限频时从 daily 推算涨跌停家数，行业/连板显示为空。
    """
    try:
        fields = "ts_code,name,industry,pct_chg,limit_times"
        zt_df = pro.limit_list_d(trade_date=today, limit_type="U", fields=fields)
        dt_df = pro.limit_list_d(trade_date=today, limit_type="D", fields=fields)

        for df in [zt_df, dt_df]:
            if df is not None and not df.empty:
                df.drop(df[df["ts_code"].apply(_is_excluded_board)].index, inplace=True)

        zt_count = len(zt_df) if zt_df is not None else 0
        dt_count = len(dt_df) if dt_df is not None else 0
        lian = int((zt_df["limit_times"] >= 2).sum()) if zt_df is not None and not zt_df.empty else 0
        sectors = zt_df["industry"].value_counts().head(3).index.tolist() \
            if zt_df is not None and not zt_df.empty else []
        return {"zt": zt_count, "dt": dt_count, "lian": lian, "sectors": sectors}

    except Exception:
        # 降级：从 daily 推算（排除创业板/科创板）
        if daily_df is not None and not daily_df.empty:
            d = daily_df[~daily_df["ts_code"].apply(_is_excluded_board)]
            zt = int((d["pct_chg"] >= 9.9).sum())
            dt = int((d["pct_chg"] <= -9.9).sum())
        else:
            zt = dt = 0
        return {"zt": zt, "dt": dt, "lian": 0, "sectors": []}


# ─── 涨跌幅排名 ────────────────────────────────────────────────
def _fetch_top_stocks(pro, today: str, name_map: Dict) -> Dict:
    """
    Tushare daily + stock_basic 名称缓存
    排除创业板/科创板，过滤新股首日（>30%）
    """
    try:
        daily = pro.daily(trade_date=today, fields="ts_code,close,pct_chg")
        if daily is None or daily.empty:
            return {}

        daily = daily[~daily["ts_code"].apply(_is_excluded_board)].copy()
        daily = daily[daily["close"] > 0]
        daily["pct_chg"] = daily["pct_chg"].astype(float)
        daily = daily[(daily["pct_chg"] <= 30) & (daily["pct_chg"] >= -30)]

        daily["is_zt"] = daily["pct_chg"] >= 9.9
        daily["is_dt"] = daily["pct_chg"] <= -9.9
        daily["name"] = daily["ts_code"].map(name_map).fillna(
            daily["ts_code"].str.split(".").str[0]
        )

        cols = ["ts_code", "name", "close", "pct_chg", "is_zt", "is_dt"]
        return {
            "up":   daily[daily["pct_chg"] >= 9.9].sort_values("pct_chg", ascending=False)[cols].to_dict("records"),
            "down": daily.nsmallest(10, "pct_chg")[cols].to_dict("records"),
            "daily_df": daily,
        }
    except Exception as e:
        logger.warning(f"获取涨跌榜失败: {e}")
        return {}


# ─── AI 分析（分批）──────────────────────────────────────────────
def _ai_batch_reasons(stocks: List[Dict]) -> Dict[str, str]:
    """为一批涨停股生成上涨原因，返回 {name: reason}"""
    stock_list = "\n".join(f"{s['name']}|?" for s in stocks)
    prompt = f"""请为以下今日涨停的A股股票逐一生成上涨原因（15-25字，说明具体催化剂和逻辑）：

格式：股票名称|原因
{stock_list}"""
    raw = ai_engine._call(
        "你是资深A股复盘分析师，擅长归纳个股涨停逻辑。",
        prompt, max_tokens=1500
    )
    result = {}
    for line in raw.splitlines():
        line = line.strip().lstrip("- 0123456789.")
        if "|" in line:
            parts = line.split("|", 1)
            name = parts[0].strip()
            reason = parts[1].strip().lstrip("?").strip() or "—"
            if name:
                result[name] = reason
    return result


def _ai_summaries(indices: Dict, stats: Dict, down_list: List[Dict]) -> str:
    """生成跌幅原因 + 涨/跌停总结 + 今日总结 + 次日关注"""
    idx_str = "  ".join(f"{k} {v['pct']:+.2f}%" for k, v in indices.items()) \
        if indices else "数据获取失败"
    sec_str = " · ".join(stats.get("sectors", [])) or "无"
    down_stock_list = "\n".join(f"{s['name']}|?" for s in down_list)

    prompt = f"""今日A股复盘（已排除创业板/科创板）：

大盘：{idx_str}
涨停{stats.get('zt',0)}家 / 跌停{stats.get('dt',0)}家 / 连板{stats.get('lian',0)}家
热点行业：{sec_str}

请严格按以下格式输出，不要改变标签名称：

【跌幅个股原因】
格式：股票名称|原因（15-25字，说明具体下跌原因）
{down_stock_list}

【涨停总结】2-3句话概括今日涨停板块分布和核心驱动
【跌停总结】2-3句话概括今日跌停主要原因和板块特征
【今日总结】市场情绪及核心逻辑（60字以内）
【次日关注】重点方向和操作建议（60字以内）"""

    return ai_engine._call(
        "你是资深A股复盘分析师，擅长归纳当日市场主线并给出次日操作建议。",
        prompt, max_tokens=2000
    )


def _ai_zt_recommend(up_list: List[Dict], stats: Dict) -> List[Dict]:
    """从今日所有涨停股中 AI 精选 5 只次日跟进标的"""
    if not up_list:
        return []
    sec_str = " · ".join(stats.get("sectors", [])) or "无"
    stock_names = "\n".join(f"{s['name']} {s['pct_chg']:+.1f}%" for s in up_list)

    prompt = f"""今日主板涨停股共 {len(up_list)} 只，热点板块：{sec_str}

完整涨停列表：
{stock_names}

请从中精选 5 只最具次日跟进价值的涨停股，优先考虑：
① 首板（资金初次关注，情绪催化空间大）
② 所在板块有明确主题催化（政策/业绩/行业事件）
③ 非退市/ST/问题股
④ 有量能配合

请严格按以下格式输出，每行一只：

【涨停精选】
格式：股票名称|入选理由（40-60字，说明涨停催化剂、板块地位和次日跟进逻辑）|风险提示（20字以内）
股票1|?|?
股票2|?|?
股票3|?|?
股票4|?|?
股票5|?|?"""

    raw = ai_engine._call(
        "你是资深A股涨停板策略分析师，擅长判断涨停股次日跟进价值。",
        prompt, max_tokens=2000
    )

    import re as _re
    section = _re.search(r"【涨停精选】(.+?)$", raw, _re.S)
    lines_raw = section.group(1).strip().splitlines() if section else raw.splitlines()

    result = []
    for line in lines_raw:
        line = line.strip().lstrip("- 0123456789.")
        if "|" in line:
            parts = line.split("|")
            name   = parts[0].strip()
            reason = parts[1].strip().lstrip("?").strip() if len(parts) > 1 else "—"
            risk   = parts[2].strip().lstrip("?").strip() if len(parts) > 2 else "—"
            if name and reason and reason != "?":
                result.append({"name": name, "reason": reason, "risk": risk})
        if len(result) >= 5:
            break
    return result


# ─── 多维技术选股 ────────────────────────────────────────────────
def _fetch_stock_picks(pro, today: str, name_map: Dict) -> List[Dict]:
    """
    五维技术分析从全市场选 5 只适合开仓的股票：
      1. 趋势维度 — MA5/10/20 多头排列
      2. MACD 维度 — DIF/DEA 金叉或红柱扩张
      3. RSI 维度  — RSI(14) 处于强势区（45-65）
      4. 布林维度  — 价格在中轨附近，带宽合理
      5. 量能维度  — 量比 ≥ 1.5，换手率 1-15%
    初筛：涨幅前100（不依赖 daily_basic，避免接口偶发失败导致全空）
    """
    import pandas as pd
    import time
    from datetime import timedelta

    try:
        # ── Step 1: 今日全市场快照，按涨幅取前100
        daily_today = pro.daily(
            trade_date=today,
            fields="ts_code,open,high,low,close,vol,amount,pct_chg"
        )
        if daily_today is None or daily_today.empty:
            return []

        df = daily_today.copy()
        df = df[~df["ts_code"].apply(_is_excluded_board)].copy()
        df["pct_chg"] = df["pct_chg"].astype(float)
        df["amount"]  = pd.to_numeric(df["amount"], errors="coerce").fillna(0)

        # 初筛：价格 ≥ 5，涨幅适中（不追涨停、不跌停），有成交
        df = df[
            (df["close"] >= 5) &
            (df["pct_chg"].between(-3, 9)) &
            (df["amount"] > 0)
        ].copy()

        if df.empty:
            return []

        # 涨幅前100作为候选池
        candidates = df.nlargest(100, "pct_chg")["ts_code"].tolist()

        # ── Step 1.5: 批量获取今日资金流向（主力 = 大单 + 超大单，一次调用）
        mf_map = {}
        try:
            mf_df = pro.moneyflow(
                trade_date=today,
                fields="ts_code,buy_lg_amount,sell_lg_amount,buy_elg_amount,sell_elg_amount"
            )
            if mf_df is not None and not mf_df.empty:
                for _, mf_row in mf_df.iterrows():
                    elg = float(mf_row.get("buy_elg_amount") or 0) - float(mf_row.get("sell_elg_amount") or 0)
                    lg  = float(mf_row.get("buy_lg_amount")  or 0) - float(mf_row.get("sell_lg_amount")  or 0)
                    mf_map[mf_row["ts_code"]] = elg + lg
        except Exception as e:
            logger.warning(f"资金流向获取失败，跳过资金维度: {e}")

        # ── Step 2: 逐股历史数据 + 技术指标计算
        start_date = (
            datetime.strptime(today, "%Y%m%d") - timedelta(days=100)
        ).strftime("%Y%m%d")

        results = []
        for ts_code in candidates:
            try:
                time.sleep(0.15)  # 避免100次连续调用触发Tushare频率限制
                hist = pro.daily(
                    ts_code=ts_code, start_date=start_date, end_date=today,
                    fields="trade_date,open,high,low,close,vol"
                )
                if hist is None or len(hist) < 20:
                    continue
                hist = hist.sort_values("trade_date").reset_index(drop=True)

                close = hist["close"].astype(float)
                vol   = hist["vol"].astype(float)
                n     = len(close)

                # 均线
                ma5  = close.rolling(5).mean().iloc[-1]
                ma10 = close.rolling(10).mean().iloc[-1]
                ma20 = close.rolling(20).mean().iloc[-1]
                ma60 = close.rolling(60).mean().iloc[-1] if n >= 60 else None
                curr = close.iloc[-1]

                # MACD (12, 26, 9)
                ema12 = close.ewm(span=12, adjust=False).mean()
                ema26 = close.ewm(span=26, adjust=False).mean()
                dif   = ema12 - ema26
                dea   = dif.ewm(span=9, adjust=False).mean()
                bar   = (dif - dea) * 2
                dif_now, dea_now   = dif.iloc[-1], dea.iloc[-1]
                dif_prev, dea_prev = dif.iloc[-2], dea.iloc[-2]

                # RSI (14)
                delta = close.diff()
                up = delta.clip(lower=0).rolling(14).mean()
                dn = (-delta.clip(upper=0)).rolling(14).mean()
                rsi = float((100 - 100 / (1 + up / dn.replace(0, 1e-9))).iloc[-1])

                # 布林带 (20, 2)
                bb_mid = close.rolling(20).mean()
                bb_std = close.rolling(20).std()
                bb_up  = (bb_mid + 2 * bb_std).iloc[-1]
                bb_lo  = (bb_mid - 2 * bb_std).iloc[-1]
                bb_pos = (curr - bb_lo) / (bb_up - bb_lo + 1e-9)  # 0=下轨 1=上轨

                # 量能 (相对 5 日均量)
                vm5         = vol.rolling(5).mean().iloc[-1]
                vol_ratio_c = float(vol.iloc[-1] / vm5) if vm5 > 0 else 1.0

                # ── 五维评分
                score   = 0
                signals = []

                # 1. 趋势维度 (30分)
                if curr > ma20:
                    score += 10; signals.append("价格站上MA20")
                if ma5 > ma10:
                    score += 10; signals.append("MA5>MA10")
                if ma10 > ma20:
                    score += 10; signals.append("MA多头排列")

                # 2. MACD 维度 (30分)
                if dif_now > dea_now and dif_prev <= dea_prev:
                    score += 30; signals.append("MACD今日金叉")
                elif dif_now > dea_now:
                    if bar.iloc[-1] > bar.iloc[-2]:
                        score += 20; signals.append("MACD红柱扩张")
                    else:
                        score += 10; signals.append("MACD多头区")
                elif dif_now > dif_prev and dif_now < 0:
                    score += 8; signals.append("MACD底部反转")

                # 3. RSI 维度 (20分)
                if 45 <= rsi <= 62:
                    score += 20; signals.append(f"RSI强势区({rsi:.0f})")
                elif 35 <= rsi < 45:
                    score += 15; signals.append(f"RSI超卖回升({rsi:.0f})")
                elif 62 < rsi <= 70:
                    score += 10; signals.append(f"RSI动能充足({rsi:.0f})")

                # 4. 布林维度 (10分)
                if 0.3 <= bb_pos <= 0.65:
                    score += 10; signals.append("布林中轨共振")
                elif bb_pos < 0.2:
                    score += 5; signals.append("布林下轨支撑")

                # 5. 量能维度 (10分)
                if vol_ratio_c >= 2.0:
                    score += 10; signals.append(f"量比{vol_ratio_c:.1f}倍放量")
                elif vol_ratio_c >= 1.5:
                    score += 7; signals.append(f"量比{vol_ratio_c:.1f}温和放量")

                # 6. 资金维度 (20分)
                mf_net = mf_map.get(ts_code)
                if mf_net is not None:
                    if mf_net > 5000:
                        score += 20; signals.append(f"主力净流入{mf_net/10000:.1f}亿")
                    elif mf_net > 1000:
                        score += 15; signals.append(f"主力净流入{mf_net:.0f}万")
                    elif mf_net > 0:
                        score +=  8; signals.append(f"主力小幅净流入{mf_net:.0f}万")

                row = df[df["ts_code"] == ts_code].iloc[0]
                results.append({
                    "ts_code":  ts_code,
                    "name":     name_map.get(ts_code, ts_code.split(".")[0]),
                    "price":    round(curr, 2),
                    "pct_chg":  round(float(row["pct_chg"]), 2),
                    "ma5":      round(ma5, 2),
                    "ma10":     round(ma10, 2),
                    "ma20":     round(ma20, 2),
                    "rsi":      round(rsi, 1),
                    "macd_tag": "金叉" if (dif_now > dea_now and dif_prev <= dea_prev)
                                else ("多头" if dif_now > dea_now else "空头"),
                    "vol_ratio":   round(vol_ratio_c, 2),
                    "bb_pos":      round(bb_pos, 2),
                    "turnover":    round(float(row.get("turnover_rate") or 0), 2),
                    "score":       score,
                    "signals":     signals,
                })
            except Exception as e:
                logger.debug(f"技术分析 {ts_code} 失败: {e}")
                continue

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:5]

    except Exception as e:
        logger.warning(f"多维选股失败: {e}")
        return []


def _ai_picks_analysis(picks: List[Dict]) -> List[str]:
    """对 5 只精选股票生成 AI 开仓逻辑（买入理由 + 止损参考 + 风险提示）"""
    if not picks:
        return []

    stock_list = ""
    for p in picks:
        sig_str = " / ".join(p["signals"])
        stock_list += (
            f"{p['name']}（{p['ts_code']}）"
            f" 现价{p['price']} 涨跌{p['pct_chg']:+.2f}%"
            f" MA5={p['ma5']} MA10={p['ma10']} MA20={p['ma20']}"
            f" RSI={p['rsi']} MACD={p['macd_tag']}"
            f" 量比={p['vol_ratio']} 换手={p['turnover']}%"
            f" 技术信号：{sig_str}\n"
        )

    stocks_with_ma = "\n".join(
        f"{p['name']}（MA20={p['ma20']}）|?|?" for p in picks
    )
    prompt = f"""以下是今日技术面评分最高的 5 只A股，请逐一分析：

{stock_list}
请严格按以下格式逐股输出，不要改变标签名称：

【开仓精选】
格式：股票名称|开仓逻辑|参考止损

要求：
- 开仓逻辑：50-80字，详细说明①当前技术形态 ②入场理由 ③上涨空间预判，例如"MACD今日金叉，DIF上穿DEA，MA5>MA10>MA20多头排列，RSI从超卖区回升至52，量比1.8倍温和放量确认趋势，前期压力位20元附近，若突破可看至22元"
- 参考止损：必须给出具体止损价格数字，格式为"跌破X.XX止损"（X.XX为MA20下方1-2%的具体数值，不能只写"跌破MA20止损"）

{stocks_with_ma}"""

    raw = ai_engine._call(
        "你是专业A股技术分析师，擅长多维度技术分析和精准入场时机判断。",
        prompt, max_tokens=2500
    )
    # 按顺序解析：找到所有含 | 的行，按位置对应股票（不依赖名称匹配）
    import re as _re
    section = _re.search(r"【开仓精选】(.+?)$", raw, _re.S)
    lines_raw = section.group(1).strip().splitlines() if section else raw.splitlines()

    parsed = []
    for line in lines_raw:
        line = line.strip().lstrip("- 0123456789.")
        if "|" in line:
            parts = line.split("|")
            logic = parts[1].strip().lstrip("?").strip() if len(parts) > 1 else "—"
            stop  = parts[2].strip().lstrip("?").strip() if len(parts) > 2 else "—"
            if logic and logic != "?":
                parsed.append({"logic": logic or "—", "stop": stop or "—"})

    result = []
    for i, p in enumerate(picks):
        item = parsed[i] if i < len(parsed) else {"logic": "—", "stop": "—"}
        result.append(item)
    return result


# ─── 主推送 ────────────────────────────────────────────────────
class DailyReview:

    def run_daily_push(self):
        import re as _re

        logger.info("执行每日复盘")
        today    = datetime.now().strftime("%Y%m%d")
        date_str = datetime.now().strftime("%Y-%m-%d")
        pro      = _get_pro()

        indices    = _fetch_market_summary()
        name_map   = _get_name_map(pro, today)
        top_stocks = _fetch_top_stocks(pro, today, name_map)
        stats      = _fetch_limit_stats(pro, today, top_stocks.get("daily_df"))
        picks      = _fetch_stock_picks(pro, today, name_map)

        zt, dt, lian = stats.get("zt", 0), stats.get("dt", 0), stats.get("lian", 0)
        sec_str      = " · ".join(stats.get("sectors", [])) or "—"
        up_list      = top_stocks.get("up", [])
        down_list    = top_stocks.get("down", [])

        md_path = str(_DATA_DIR / f"review_{date_str}.md")

        # ── Phase 0: 写文件头（大盘 + 涨跌停统计）
        idx_table = "| 指数 | 收盘 | 涨跌幅 |\n|------|-----:|------:|\n"
        for name, d in indices.items():
            arrow = "▲" if d["pct"] >= 0 else "▼"
            idx_table += f"| {name} | {d['price']:.2f} | {arrow} {d['pct']:+.2f}% |\n"

        header = f"""# 📋 每日复盘 — {date_str}

> 主板 + 北交所　|　已排除创业板 / 科创板

---

## 📊 大盘指数

{idx_table}
---

> 涨停 **{zt}** 家　跌停 **{dt}** 家　连板 **{lian}** 家　热点：{sec_str}

---

## 🏆 今日涨停股（主板 + 北交所，共 {len(up_list)} 只）

| # | 股票 | 涨跌幅 | 原因 |
|--:|------|------:|------|
"""
        with open(md_path, "w", encoding="utf-8-sig") as f:
            f.write(header)

        # ── Phase 1..N: 分批 AI 生成涨停原因，追加写行
        import time as _time
        BATCH_SIZE = 30
        all_up_reasons: Dict[str, str] = {}
        for batch_idx in range(0, len(up_list), BATCH_SIZE):
            batch = up_list[batch_idx: batch_idx + BATCH_SIZE]
            batch_no = batch_idx // BATCH_SIZE + 1
            logger.info(f"涨停原因批次 {batch_no}，共 {len(batch)} 只")
            batch_reasons: Dict[str, str] = {}
            for attempt in range(3):
                try:
                    batch_reasons = _ai_batch_reasons(batch)
                    if batch_reasons:
                        break
                    logger.warning(f"批次 {batch_no} 第 {attempt+1} 次返回空，重试")
                except Exception as e:
                    logger.warning(f"批次 {batch_no} 第 {attempt+1} 次失败: {e}")
                _time.sleep(3)
            all_up_reasons.update(batch_reasons)

            with open(md_path, "a", encoding="utf-8-sig") as f:
                for i, s in enumerate(batch):
                    reason = batch_reasons.get(s["name"], "—")
                    f.write(f"| {batch_idx + i + 1} | {s['name']} | {s['pct_chg']:+.2f}% | {reason} |\n")

        # ── Phase N+1: AI 生成总结 + 跌幅原因
        logger.info("生成涨/跌停总结及跌幅原因")
        try:
            summary_text = _ai_summaries(indices, stats, down_list)
        except Exception as e:
            logger.warning(f"总结 AI 调用失败: {e}")
            summary_text = ""

        def _extract(tag: str, text: str, fallback: str = "—") -> str:
            m = _re.search(rf"【{tag}】(.+?)(?=【|$)", text, _re.S)
            return m.group(1).strip() if m else fallback

        def _parse_down_reasons(text: str) -> Dict[str, str]:
            section = _extract("跌幅个股原因", text, "")
            result: Dict[str, str] = {}
            for line in section.splitlines():
                line = line.strip().lstrip("- ")
                if "|" in line:
                    parts = line.split("|", 1)
                    name   = parts[0].strip()
                    reason = parts[1].strip().lstrip("?").strip() or "—"
                    if name:
                        result[name] = reason
            return result

        down_reasons = _parse_down_reasons(summary_text)
        zt_summary   = _extract("涨停总结",  summary_text)
        dt_summary   = _extract("跌停总结",  summary_text)
        summary      = _extract("今日总结",  summary_text)
        next_focus   = _extract("次日关注",  summary_text)

        down_table = "| # | 股票 | 涨跌幅 | 原因 |\n|--:|------|------:|------|\n"
        for i, s in enumerate(down_list):
            reason = down_reasons.get(s["name"], "—")
            down_table += f"| {i+1} | {s['name']} | {s['pct_chg']:+.2f}% | {reason} |\n"

        with open(md_path, "a", encoding="utf-8-sig") as f:
            f.write(f"\n**涨停总结**：{zt_summary}\n\n---\n\n")
            f.write(f"## 💔 跌幅前 10\n\n{down_table}\n")
            f.write(f"**跌停总结**：{dt_summary}\n\n---\n\n")
            f.write(f"## 🤖 今日总结\n\n{summary}\n\n")
            f.write(f"## 📌 次日关注\n\n{next_focus}\n\n---\n\n")

        # ── Phase N+2a: 涨停精选5只
        logger.info("生成涨停精选推荐")
        try:
            zt_picks = _ai_zt_recommend(up_list, stats)
        except Exception as e:
            logger.warning(f"涨停精选 AI 调用失败: {e}")
            zt_picks = []

        if zt_picks:
            zt_picks_block = "| # | 股票 | 入选理由 | 风险提示 |\n"
            zt_picks_block += "|--:|------|---------|--------|\n"
            for i, p in enumerate(zt_picks):
                zt_picks_block += f"| {i+1} | {p['name']} | {p['reason']} | {p['risk']} |\n"
        else:
            zt_picks_block = "_涨停精选数据获取失败_"

        with open(md_path, "a", encoding="utf-8-sig") as f:
            f.write(f"## 🚀 涨停精选（5只，次日跟进参考）\n\n{zt_picks_block}\n\n---\n\n")

        # ── Phase N+2b: 技术选股精选5只
        picks_ai = _ai_picks_analysis(picks)
        if picks:
            picks_block = "| # | 股票 | 现价 | 涨跌幅 | 技术信号 | 开仓逻辑 | 参考止损 |\n"
            picks_block += "|--:|------|-----:|------:|---------|---------|--------|\n"
            for i, (p, ai) in enumerate(zip(picks, picks_ai or [{}] * len(picks))):
                sig   = " · ".join(p["signals"][:3])
                logic = ai.get("logic", "—") if isinstance(ai, dict) else "—"
                stop  = ai.get("stop",  "—") if isinstance(ai, dict) else "—"
                picks_block += (
                    f"| {i+1} | {p['name']} | {p['price']} "
                    f"| {p['pct_chg']:+.2f}% | {sig} | {logic} | {stop} |\n"
                )
        else:
            picks_block = "_选股数据获取失败_"

        with open(md_path, "a", encoding="utf-8-sig") as f:
            f.write(f"## 🎯 今日开仓精选（5只）\n\n{picks_block}\n\n")
            f.write("> 技术评分维度：趋势（MA多头）/ MACD（金叉/扩张）/ RSI（45-65）/ 布林（中轨共振）/ 量能（量比≥1.5）\n")

        # ── Phase End: 推送
        caption = f"📋 每日复盘 {date_str}　涨停{zt}家 跌停{dt}家"
        notifier.telegram.send_document(md_path, caption=caption)
        logger.info(f"每日复盘已推送，涨停 {len(up_list)} 只，分 {(len(up_list) + BATCH_SIZE - 1) // BATCH_SIZE} 批处理")


daily_review = DailyReview()
