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
            "up":   daily.nlargest(100, "pct_chg")[cols].to_dict("records"),
            "down": daily.nsmallest(10, "pct_chg")[cols].to_dict("records"),
            "daily_df": daily,
        }
    except Exception as e:
        logger.warning(f"获取涨跌榜失败: {e}")
        return {}


# ─── AI 分析 ───────────────────────────────────────────────────
def _ai_review(indices: Dict, stats: Dict, top_stocks: Dict) -> str:
    idx_str = "  ".join(f"{k} {v['pct']:+.2f}%" for k, v in indices.items()) \
        if indices else "数据获取失败"
    sec_str = " · ".join(stats.get("sectors", [])) or "无"

    up_list   = top_stocks.get("up", [])
    down_list = top_stocks.get("down", [])

    zt_names = [s["name"] for s in up_list   if s.get("is_zt")]
    dt_names = [s["name"] for s in down_list if s.get("is_dt")]
    up_brief  = "  ".join(f"{s['name']}{s['pct_chg']:+.1f}%" for s in up_list[:10])   or "无"
    dn_brief  = "  ".join(f"{s['name']}{s['pct_chg']:+.1f}%" for s in down_list[:5])  or "无"

    up_stock_list  = "\n".join(f"{s['name']}|?" for s in up_list)
    down_stock_list = "\n".join(f"{s['name']}|?" for s in down_list)

    prompt = f"""今日A股复盘（已排除创业板/科创板）：

大盘：{idx_str}
涨停{stats.get('zt',0)}家 / 跌停{stats.get('dt',0)}家 / 连板{stats.get('lian',0)}家
热点行业：{sec_str}

请严格按以下格式输出，不要改变标签名称：

【涨幅个股原因】
格式：股票名称|原因（15-25字，说明具体催化剂和上涨逻辑，如"受国家电网智能化改造招标消息刺激，电力设备板块集体拉升"、"公司发布业绩预增公告，净利润同比增长超150%"）
{up_stock_list}

【跌幅个股原因】
格式：股票名称|原因（15-25字，说明具体下跌原因，如"半年报预告显示业绩大幅亏损，主力资金出逃"、"面板行业景气度持续下行，产品价格跌破成本线"）
{down_stock_list}

【涨停总结】2-3句话概括今日涨停板块分布和核心驱动
【跌停总结】2-3句话概括今日跌停主要原因和板块特征
【今日总结】市场情绪及核心逻辑（60字以内）
【次日关注】重点方向和操作建议（60字以内）"""

    return ai_engine._call(
        "你是资深A股复盘分析师，擅长归纳当日市场主线并给出次日操作建议。",
        prompt, max_tokens=6000
    )


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

    prompt = f"""以下是今日技术面评分最高的 5 只A股，请逐一分析：

{stock_list}
请严格按以下格式逐股输出，不要改变标签名称：

【开仓精选】
格式：股票名称|开仓逻辑（25-35字，说明核心技术信号和入场理由）|参考止损（如"跌破MA20止损"或具体价格区间）
{chr(10).join(p['name'] + '|?|?' for p in picks)}"""

    raw = ai_engine._call(
        "你是专业A股技术分析师，擅长多维度技术分析和精准入场时机判断。",
        prompt, max_tokens=1200
    )
    # 解析每行
    import re as _re
    section = _re.search(r"【开仓精选】(.+?)$", raw, _re.S)
    lines_raw = section.group(1).strip().splitlines() if section else raw.splitlines()

    analysis = {}
    for line in lines_raw:
        line = line.strip().lstrip("- 0123456789.")
        if "|" in line:
            parts = line.split("|")
            name = parts[0].strip()
            logic = parts[1].strip().lstrip("?").strip() if len(parts) > 1 else "—"
            stop  = parts[2].strip().lstrip("?").strip() if len(parts) > 2 else "—"
            if name:
                analysis[name] = (logic, stop)

    result = []
    for p in picks:
        logic, stop = analysis.get(p["name"], ("—", "—"))
        result.append({"logic": logic, "stop": stop})
    return result


# ─── 主推送 ────────────────────────────────────────────────────
class DailyReview:

    def run_daily_push(self):
        logger.info("执行每日复盘")
        today = datetime.now().strftime("%Y%m%d")
        pro   = _get_pro()

        indices    = _fetch_market_summary()
        name_map   = _get_name_map(pro, today)
        top_stocks = _fetch_top_stocks(pro, today, name_map)
        stats      = _fetch_limit_stats(pro, today, top_stocks.get("daily_df"))
        picks      = _fetch_stock_picks(pro, today, name_map)
        ai_text    = _ai_review(indices, stats, top_stocks)
        picks_ai   = _ai_picks_analysis(picks)

        sec_str = " · ".join(stats.get("sectors", [])) or "—"
        zt, dt, lian = stats.get("zt", 0), stats.get("dt", 0), stats.get("lian", 0)
        up_list   = top_stocks.get("up", [])
        down_list = top_stocks.get("down", [])
        date_str  = datetime.now().strftime("%Y-%m-%d")

        # ── 解析 AI 各段
        import re as _re
        def _extract(tag: str, text: str, fallback: str = "—") -> str:
            m = _re.search(rf"【{tag}】(.+?)(?=【|$)", text, _re.S)
            return m.group(1).strip() if m else fallback

        def _parse_stock_reasons(tag: str, text: str) -> dict:
            """解析【tag】段落中 '股票名|原因' 格式，返回 {name: reason}"""
            section = _extract(tag, text, "")
            result = {}
            for line in section.splitlines():
                line = line.strip().lstrip("- ").strip()
                if "|" in line:
                    parts = line.split("|", 1)
                    name = parts[0].strip()
                    reason = parts[1].strip().lstrip("?").strip() or "—"
                    if name:
                        result[name] = reason
            return result

        up_reasons  = _parse_stock_reasons("涨幅个股原因", ai_text)
        down_reasons = _parse_stock_reasons("跌幅个股原因", ai_text)
        zt_summary  = _extract("涨停总结", ai_text)
        dt_summary  = _extract("跌停总结", ai_text)
        summary     = _extract("今日总结", ai_text)
        next_focus  = _extract("次日关注", ai_text)

        # ── 大盘表格
        idx_table = "| 指数 | 收盘 | 涨跌幅 |\n|------|-----:|------:|\n"
        for name, d in indices.items():
            arrow = "▲" if d["pct"] >= 0 else "▼"
            idx_table += f"| {name} | {d['price']:.2f} | {arrow} {d['pct']:+.2f}% |\n"

        # ── 涨幅榜：全部 50 只，带原因列
        up_table = "| # | 股票 | 涨跌幅 | 原因 |\n|--:|------|------:|------|\n"
        for i, s in enumerate(up_list):
            reason = up_reasons.get(s["name"], "—")
            up_table += f"| {i+1} | {s['name']} | {s['pct_chg']:+.2f}% | {reason} |\n"

        rest_block = ""  # 不再需要单独的其余涨停列表

        # ── 跌幅榜：全部 10 只，带原因列
        down_table = "| # | 股票 | 涨跌幅 | 原因 |\n|--:|------|------:|------|\n"
        for i, s in enumerate(down_list):
            reason = down_reasons.get(s["name"], "—")
            down_table += f"| {i+1} | {s['name']} | {s['pct_chg']:+.2f}% | {reason} |\n"

        # ── 精选股票表格
        picks_block = ""
        if picks:
            picks_block = "| # | 股票 | 现价 | 涨跌幅 | 技术信号 | 开仓逻辑 | 参考止损 |\n"
            picks_block += "|--:|------|-----:|------:|---------|---------|--------|\n"
            for i, (p, ai) in enumerate(zip(picks, picks_ai or [{}] * len(picks))):
                sig = " · ".join(p["signals"][:3])  # 最多展示3个信号
                logic = ai.get("logic", "—") if isinstance(ai, dict) else "—"
                stop  = ai.get("stop", "—")  if isinstance(ai, dict) else "—"
                picks_block += (
                    f"| {i+1} | {p['name']} | {p['price']} "
                    f"| {p['pct_chg']:+.2f}% | {sig} | {logic} | {stop} |\n"
                )

        # ── 组装 Markdown 文档
        md = f"""# 📋 每日复盘 — {date_str}

> 主板 + 北交所　|　已排除创业板 / 科创板

---

## 📊 大盘指数

{idx_table}
---

## 🏆 涨幅前 100

{up_table}{rest_block}

**涨停总结**：{zt_summary}

---

## 💔 跌幅前 10

{down_table}

**跌停总结**：{dt_summary}

---

## 🤖 今日总结

{summary}

## 📌 次日关注

{next_focus}

---

## 🎯 今日开仓精选（5只）

{picks_block if picks_block else "_选股数据获取失败_"}

> 技术评分维度：趋势（MA多头）/ MACD（金叉/扩张）/ RSI（45-65）/ 布林（中轨共振）/ 量能（量比≥1.5）
"""

        # 写入临时文件并发送
        md_path = str(_DATA_DIR / f"review_{date_str}.md")
        with open(md_path, "w", encoding="utf-8-sig") as f:
            f.write(md)

        caption = f"📋 每日复盘 {date_str}　涨停{zt}家 跌停{dt}家"
        notifier.telegram.send_document(md_path, caption=caption)
        logger.info("每日复盘 md 文件已推送")


daily_review = DailyReview()
