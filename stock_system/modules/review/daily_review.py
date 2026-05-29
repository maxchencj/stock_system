"""
每日复盘模板 - 交易日 21:00 自动生成当日复盘
推送内容：大盘指数 / 涨幅前50 / 跌幅前10（排除创业板/科创板）/ 涨跌停原因分析
推送频率：交易日 21:00 → Telegram
"""
import os
from datetime import datetime
from typing import Dict, List

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger


# 创业板：300xxx / 301xxx，科创板：688xxx / 689xxx
def _is_excluded_board(ts_code: str) -> bool:
    code = ts_code.split(".")[0]
    return (
        code.startswith("300")
        or code.startswith("301")
        or code.startswith("688")
        or code.startswith("689")
    )


def _get_tushare_pro():
    import tushare as ts
    token = os.getenv("TUSHARE_TOKEN", "")
    return ts.pro_api(token)


def _fetch_market_summary() -> Dict:
    """大盘指数（腾讯Finance）"""
    try:
        import requests
        symbols = {
            "sh000001": "上证",
            "sz399001": "深证",
            "sz399006": "创业板",
            "sh000016": "上证50",
        }
        codes = ",".join(f"s_{c}" for c in symbols)
        resp = requests.get(f"http://qt.gtimg.cn/q={codes}", timeout=8)
        resp.encoding = "gbk"
        indices = {}
        for line in resp.text.strip().split("\n"):
            if "~" not in line:
                continue
            parts = line.split("~")
            if len(parts) < 35:
                continue
            for code, name in symbols.items():
                if code in line:
                    try:
                        indices[name] = {
                            "price": float(parts[3]),
                            "pct": float(parts[32]),
                        }
                    except Exception:
                        pass
        return indices
    except Exception as e:
        logger.warning(f"获取大盘数据失败: {e}")
        return {}


def _fetch_limit_stats() -> Dict:
    """涨跌停统计（AKShare）"""
    try:
        import akshare as ak
        today = datetime.now().strftime("%Y%m%d")
        zt_df = ak.stock_zt_pool_em(date=today)
        dt_df = ak.stock_zt_pool_dtgc_em(date=today)
        zt_count = len(zt_df) if zt_df is not None else 0
        dt_count = len(dt_df) if dt_df is not None else 0

        lian_count = 0
        top_sectors = []
        if zt_df is not None and not zt_df.empty:
            if "连板数" in zt_df.columns:
                lian_count = int((zt_df["连板数"] >= 2).sum())
            if "所属行业" in zt_df.columns:
                top_sectors = zt_df["所属行业"].value_counts().head(3).index.tolist()
        return {"zt": zt_count, "dt": dt_count, "lian": lian_count, "sectors": top_sectors}
    except Exception as e:
        logger.warning(f"获取涨跌停数据失败: {e}")
        return {"zt": 0, "dt": 0, "lian": 0, "sectors": []}


def _fetch_top_stocks() -> Dict:
    """
    用 Tushare 获取今日涨幅前50 / 跌幅前10
    排除创业板（300xxx/301xxx）和科创板（688xxx/689xxx）
    同时标记涨停/跌停股
    """
    try:
        import pandas as pd
        pro = _get_tushare_pro()
        today = datetime.now().strftime("%Y%m%d")

        # 日行情
        daily = pro.daily(trade_date=today, fields="ts_code,close,pct_chg,vol,amount")
        if daily is None or daily.empty:
            return {}

        # 股票基本信息（名称）
        basic = pro.stock_basic(
            exchange="", list_status="L", fields="ts_code,name"
        )
        df = daily.merge(basic, on="ts_code", how="left")

        # 过滤创业板 / 科创板
        df = df[~df["ts_code"].apply(_is_excluded_board)].copy()

        # 过滤无效（停牌、ST 等）
        df = df[df["close"] > 0]
        df["pct_chg"] = df["pct_chg"].astype(float)

        # 涨停线 ≈ 9.9%，跌停线 ≈ -9.9%（北交所 ±30% 不计）
        df["is_zt"] = df["pct_chg"] >= 9.9
        df["is_dt"] = df["pct_chg"] <= -9.9

        cols = ["ts_code", "name", "close", "pct_chg", "is_zt", "is_dt"]
        top_up   = df.nlargest(50, "pct_chg")[cols].to_dict("records")
        top_down = df.nsmallest(10, "pct_chg")[cols].to_dict("records")

        return {"up": top_up, "down": top_down}

    except Exception as e:
        logger.warning(f"Tushare 涨跌榜获取失败: {e}")
        return {}


def _ai_review(indices: Dict, limit_stats: Dict, top_stocks: Dict) -> str:
    system_prompt = (
        "你是资深A股复盘分析师，擅长从涨停跌停个股中归纳当日市场主线，"
        "并给出次日操作建议。"
    )

    idx_str = "  ".join(
        f"{k} {v['pct']:+.2f}%" for k, v in indices.items()
    ) if indices else "数据获取失败"

    sec_str = "、".join(limit_stats.get("sectors", [])) or "无"

    up_list   = top_stocks.get("up", [])
    down_list = top_stocks.get("down", [])

    # 涨停股列表（用于让AI分析原因）
    zt_names = [s["name"] for s in up_list if s.get("is_zt")]
    dt_names = [s["name"] for s in down_list if s.get("is_dt")]

    # 涨幅前10用于prompt（节省token）
    up_brief = "  ".join(
        f"{s['name']}{s['pct_chg']:+.1f}%{'🔒' if s['is_zt'] else ''}"
        for s in up_list[:10]
    ) or "无"
    down_brief = "  ".join(
        f"{s['name']}{s['pct_chg']:+.1f}%{'🔒' if s['is_dt'] else ''}"
        for s in down_list[:5]
    ) or "无"

    zt_str = "、".join(zt_names[:15]) if zt_names else "无"
    dt_str = "、".join(dt_names[:10]) if dt_names else "无"

    user_prompt = f"""今日A股复盘数据（已排除创业板/科创板）：

【大盘指数】{idx_str}
【涨跌停】涨停{limit_stats.get('zt', 0)}家 / 跌停{limit_stats.get('dt', 0)}家 / 连板{limit_stats.get('lian', 0)}家
【涨停热点行业】{sec_str}
【涨幅榜Top10（主板+北交所）】{up_brief}
【跌幅榜Top5（主板+北交所）】{down_brief}
【今日涨停股（主板）】{zt_str}
【今日跌停股（主板）】{dt_str}

请输出以下四段分析（每段80字以内，直接写内容，不要加markdown标题）：

【今日总结】市场整体情绪（强/弱/分化）及核心逻辑
【涨停原因】今日主板涨停股的共性原因，哪些是主线，哪些是题材炒作
【跌停原因】今日主板跌停股的共性原因或个股逻辑
【次日关注】明天重点方向（反弹/追板/观望），给出具体板块"""

    return ai_engine._call(system_prompt, user_prompt, max_tokens=600)


class DailyReview:

    def run_daily_push(self):
        logger.info("执行每日复盘")
        indices    = _fetch_market_summary()
        limit_stats = _fetch_limit_stats()
        top_stocks  = _fetch_top_stocks()

        ai_text = _ai_review(indices, limit_stats, top_stocks)

        # 大盘指数
        if indices:
            idx_lines = "\n".join(
                f"  {name}: {d['price']:.2f}  {d['pct']:+.2f}%"
                for name, d in indices.items()
            )
        else:
            idx_lines = "  数据获取中..."

        # 涨幅榜 Top50（每行: 序号 名称 涨跌幅，涨停加🔒）
        up_list = top_stocks.get("up", [])
        if up_list:
            up_lines = "\n".join(
                f"  {i+1:2d}. {s['name']}  {s['pct_chg']:+.2f}%{'🔒' if s['is_zt'] else ''}"
                for i, s in enumerate(up_list)
            )
        else:
            up_lines = "  暂无数据"

        # 跌幅榜 Top10
        down_list = top_stocks.get("down", [])
        if down_list:
            down_lines = "\n".join(
                f"  {i+1:2d}. {s['name']}  {s['pct_chg']:+.2f}%{'🔒' if s['is_dt'] else ''}"
                for i, s in enumerate(down_list)
            )
        else:
            down_lines = "  暂无数据"

        sec_str = "  ".join(limit_stats.get("sectors", [])) or "无"
        zt = limit_stats.get("zt", 0)
        dt = limit_stats.get("dt", 0)
        lian = limit_stats.get("lian", 0)

        msg = (
            f"📋 每日复盘 — {datetime.now().strftime('%Y-%m-%d')}\n"
            f"（主板 + 北交所，已排除创业板/科创板）\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📊 大盘指数\n{idx_lines}\n\n"
            f"📈 今日涨跌停\n"
            f"  涨停: {zt}家  跌停: {dt}家  连板: {lian}家\n"
            f"  热点行业: {sec_str}\n\n"
            f"🏆 涨幅榜 Top50\n{up_lines}\n\n"
            f"💔 跌幅榜 Top10\n{down_lines}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{ai_text}"
        )
        notifier.telegram.send(msg)
        logger.info("每日复盘已推送")


daily_review = DailyReview()
