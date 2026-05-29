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
            "up":   daily.nlargest(50, "pct_chg")[cols].to_dict("records"),
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

    prompt = f"""今日A股复盘（已排除创业板/科创板）：

【大盘指数】{idx_str}
【涨跌停】涨停{stats.get('zt',0)}家 / 跌停{stats.get('dt',0)}家 / 连板{stats.get('lian',0)}家
【涨停热点行业】{sec_str}
【涨幅榜Top10】{up_brief}
【跌幅榜Top5】{dn_brief}
【今日涨停股】{"、".join(zt_names[:15]) or "无"}
【今日跌停股】{"、".join(dt_names[:10]) or "无"}

请输出以下四段分析（每段80字以内）：
【今日总结】市场整体情绪（强/弱/分化）及核心逻辑
【涨停原因】今日主板涨停股的共性原因，哪些是主线，哪些是题材炒作
【跌停原因】今日主板跌停股的共性原因或个股逻辑
【次日关注】明天重点方向，给出具体板块"""

    return ai_engine._call(
        "你是资深A股复盘分析师，擅长归纳当日市场主线并给出次日操作建议。",
        prompt, max_tokens=800
    )


# ─── 主推送 ────────────────────────────────────────────────────
class DailyReview:

    def run_daily_push(self):
        logger.info("执行每日复盘")
        today = datetime.now().strftime("%Y%m%d")
        pro   = _get_pro()

        indices   = _fetch_market_summary()
        name_map  = _get_name_map(pro, today)
        top_stocks = _fetch_top_stocks(pro, today, name_map)
        stats     = _fetch_limit_stats(pro, today, top_stocks.get("daily_df"))
        ai_text   = _ai_review(indices, stats, top_stocks)

        sec_str = " · ".join(stats.get("sectors", [])) or "—"
        zt, dt, lian = stats.get("zt", 0), stats.get("dt", 0), stats.get("lian", 0)
        up_list   = top_stocks.get("up", [])
        down_list = top_stocks.get("down", [])

        # 大盘：两行
        idx_lines = "\n".join(
            f"  {name}  {d['price']:.2f}  {d['pct']:+.2f}%"
            for name, d in indices.items()
        ) if indices else "  数据获取中..."

        # 涨幅：Top10 带百分比 + 剩余涨停只列名字（5个/行）
        top10_lines = "\n".join(
            f"  {i+1:2d}. {s['name']}  {s['pct_chg']:+.2f}%{'🔒' if s['is_zt'] else ''}"
            for i, s in enumerate(up_list[:10])
        ) if up_list else "  暂无数据"

        rest_zt = [s["name"] for s in up_list[10:] if s["is_zt"]]
        rest_near = [
            f"{s['name']} {s['pct_chg']:+.1f}%"
            for s in up_list[10:] if not s["is_zt"]
        ]
        rest_lines = ""
        if rest_zt:
            rows = [" · ".join(rest_zt[i:i+5]) for i in range(0, len(rest_zt), 5)]
            rest_lines += f"\n  其余涨停（{len(rest_zt)}只）：\n" + "\n".join(f"  {r}" for r in rows)
        if rest_near:
            rest_lines += "\n  近涨停：" + "  ".join(rest_near)

        # 跌幅：每行两只
        down_lines = "\n".join(
            f"  {s['name']}  {s['pct_chg']:+.2f}%{'🔒' if s['is_dt'] else ''}"
            for s in down_list
        ) if down_list else "  暂无数据"

        # 消息1：行情数据
        msg1 = (
            f"📋 每日复盘 — {datetime.now().strftime('%Y-%m-%d')}\n"
            f"（主板 + 北交所 | 已排除创业板/科创板）\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📊 大盘指数\n{idx_lines}\n\n"
            f"📈 涨停 {zt}家  跌停 {dt}家  连板 {lian}家\n"
            f"🔥 热点板块：{sec_str}\n\n"
            f"🏆 涨幅前50（Top10详情）\n{top10_lines}{rest_lines}\n\n"
            f"💔 跌幅前10\n{down_lines}"
        )

        # 消息2：AI 分析（单独发送，不被行情数据稀释）
        msg2 = f"━━━━━━━━━━━━━━━━\n{ai_text}"

        notifier.telegram.send(msg1)
        notifier.telegram.send(msg2)
        logger.info("每日复盘已推送")


daily_review = DailyReview()
