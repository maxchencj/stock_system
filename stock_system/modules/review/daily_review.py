"""
每日复盘模板 - 交易日 21:00 自动生成当日复盘
数据源：全部使用 Tushare（不依赖 AKShare）
  - 大盘指数：腾讯 Finance
  - 涨停/跌停统计 + 名称：Tushare limit_list_d
  - 全市场涨跌幅排名：Tushare daily
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


def _get_pro():
    import tushare as ts
    return ts.pro_api(os.getenv("TUSHARE_TOKEN", ""))


def _fetch_market_summary() -> Dict:
    """大盘指数（腾讯 Finance）"""
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
        # s_xxx 简化接口格式: exchange~名称~代码~现价~涨跌额~涨跌幅~...
        indices = {}
        for line in resp.text.strip().split("\n"):
            if "~" not in line:
                continue
            parts = line.split("~")
            if len(parts) < 6:
                continue
            for code, name in symbols.items():
                if code in line:
                    try:
                        indices[name] = {
                            "price": float(parts[3]),
                            "pct": float(parts[5]),
                        }
                    except Exception:
                        pass
        return indices
    except Exception as e:
        logger.warning(f"获取大盘数据失败: {e}")
        return {}


def _fetch_limit_data(today: str) -> Dict:
    """
    用 Tushare limit_list_d 获取涨停/跌停数据
    返回：涨停列表、跌停列表、统计数字
    """
    try:
        pro = _get_pro()
        fields = "ts_code,name,industry,close,pct_chg,limit_times,open_times,first_time"

        zt_df = pro.limit_list_d(trade_date=today, limit_type="U", fields=fields)
        dt_df = pro.limit_list_d(trade_date=today, limit_type="D", fields=fields)

        zt_df = zt_df if zt_df is not None else __import__("pandas").DataFrame()
        dt_df = dt_df if dt_df is not None else __import__("pandas").DataFrame()

        # 过滤创业板 / 科创板
        if not zt_df.empty:
            zt_df = zt_df[~zt_df["ts_code"].apply(_is_excluded_board)].copy()
        if not dt_df.empty:
            dt_df = dt_df[~dt_df["ts_code"].apply(_is_excluded_board)].copy()

        # 统计
        zt_count = len(zt_df)
        dt_count = len(dt_df)
        lian_count = 0
        top_sectors: List[str] = []
        if not zt_df.empty:
            if "limit_times" in zt_df.columns:
                lian_count = int((zt_df["limit_times"] >= 2).sum())
            if "industry" in zt_df.columns:
                top_sectors = zt_df["industry"].value_counts().head(3).index.tolist()

        return {
            "zt_df": zt_df,
            "dt_df": dt_df,
            "zt": zt_count,
            "dt": dt_count,
            "lian": lian_count,
            "sectors": top_sectors,
        }
    except Exception as e:
        logger.warning(f"获取涨跌停数据失败: {e}")
        import pandas as pd
        return {"zt_df": pd.DataFrame(), "dt_df": pd.DataFrame(),
                "zt": 0, "dt": 0, "lian": 0, "sectors": []}


def _fetch_top_stocks(today: str, zt_df, dt_df) -> Dict:
    """
    涨幅前50 / 跌幅前10（主板 + 北交所，排除创业板/科创板）
    价格数据来自 Tushare daily，名称来自 limit_list_d（涨跌停股有名称，其余显示代码）
    过滤新股首日（涨幅 > 30%）
    """
    try:
        pro = _get_pro()
        daily = pro.daily(trade_date=today, fields="ts_code,close,pct_chg")
        if daily is None or daily.empty:
            return {}

        # 名称映射：仅涨停/跌停股有名称，其余用 6 位代码
        name_map: Dict[str, str] = {}
        for df in [zt_df, dt_df]:
            if not df.empty and "name" in df.columns:
                name_map.update(dict(zip(df["ts_code"], df["name"])))

        daily = daily[~daily["ts_code"].apply(_is_excluded_board)].copy()
        daily = daily[daily["close"] > 0]
        daily["pct_chg"] = daily["pct_chg"].astype(float)
        # 过滤新股首日 / 长期停牌复牌（涨跌幅超 ±30%）
        daily = daily[(daily["pct_chg"] <= 30) & (daily["pct_chg"] >= -30)]

        daily["is_zt"] = daily["pct_chg"] >= 9.9
        daily["is_dt"] = daily["pct_chg"] <= -9.9
        daily["name"] = daily["ts_code"].map(name_map).fillna(
            daily["ts_code"].str.split(".").str[0]
        )

        cols = ["ts_code", "name", "close", "pct_chg", "is_zt", "is_dt"]
        top_up   = daily.nlargest(50, "pct_chg")[cols].to_dict("records")
        top_down = daily.nsmallest(10, "pct_chg")[cols].to_dict("records")
        return {"up": top_up, "down": top_down}

    except Exception as e:
        logger.warning(f"获取涨跌榜失败: {e}")
        return {}


def _ai_review(indices: Dict, limit_data: Dict, top_stocks: Dict) -> str:
    system_prompt = (
        "你是资深A股复盘分析师，擅长从涨停跌停个股中归纳当日市场主线，"
        "并给出次日操作建议。"
    )

    idx_str = "  ".join(
        f"{k} {v['pct']:+.2f}%" for k, v in indices.items()
    ) if indices else "数据获取失败"

    sec_str = "、".join(limit_data.get("sectors", [])) or "无"

    up_list   = top_stocks.get("up", [])
    down_list = top_stocks.get("down", [])

    zt_names = [s["name"] for s in up_list if s.get("is_zt")]
    dt_names = [s["name"] for s in down_list if s.get("is_dt")]

    up_brief = "  ".join(
        f"{s['name']}{s['pct_chg']:+.1f}%{'🔒' if s['is_zt'] else ''}"
        for s in up_list[:10]
    ) or "无"
    down_brief = "  ".join(
        f"{s['name']}{s['pct_chg']:+.1f}%{'🔒' if s['is_dt'] else ''}"
        for s in down_list[:5]
    ) or "无"

    user_prompt = f"""今日A股复盘数据（已排除创业板/科创板）：

【大盘指数】{idx_str}
【涨跌停】涨停{limit_data.get('zt', 0)}家 / 跌停{limit_data.get('dt', 0)}家 / 连板{limit_data.get('lian', 0)}家
【涨停热点行业】{sec_str}
【涨幅榜Top10（主板+北交所）】{up_brief}
【跌幅榜Top5（主板+北交所）】{down_brief}
【今日涨停股（主板）】{"、".join(zt_names[:15]) or "无"}
【今日跌停股（主板）】{"、".join(dt_names[:10]) or "无"}

请输出以下四段分析（每段80字以内）：
【今日总结】市场整体情绪（强/弱/分化）及核心逻辑
【涨停原因】今日主板涨停股的共性原因，哪些是主线，哪些是题材炒作
【跌停原因】今日主板跌停股的共性原因或个股逻辑
【次日关注】明天重点方向，给出具体板块"""

    return ai_engine._call(system_prompt, user_prompt, max_tokens=600)


class DailyReview:

    def run_daily_push(self):
        logger.info("执行每日复盘")
        today = datetime.now().strftime("%Y%m%d")

        indices    = _fetch_market_summary()
        limit_data = _fetch_limit_data(today)
        top_stocks = _fetch_top_stocks(today, limit_data["zt_df"], limit_data["dt_df"])
        ai_text    = _ai_review(indices, limit_data, top_stocks)

        # 大盘指数：单行紧凑
        idx_line = "  ".join(
            f"{name} {d['price']:.0f}（{d['pct']:+.2f}%）"
            for name, d in indices.items()
        ) if indices else "数据获取中..."

        # 涨跌停行
        sec_str = " · ".join(limit_data.get("sectors", [])) or "—"
        zt, dt, lian = limit_data.get("zt", 0), limit_data.get("dt", 0), limit_data.get("lian", 0)

        # 股票榜：每行 3 只，格式 "名称+涨跌幅🔒"
        def _rows(stocks: list, per_row: int = 3) -> str:
            if not stocks:
                return "  暂无数据"
            items = [
                f"{s['name']} {s['pct_chg']:+.1f}%{'🔒' if s.get('is_zt') or s.get('is_dt') else ''}"
                for s in stocks
            ]
            lines = []
            for i in range(0, len(items), per_row):
                lines.append("  " + "   ".join(items[i:i + per_row]))
            return "\n".join(lines)

        up_list   = top_stocks.get("up", [])
        down_list = top_stocks.get("down", [])

        msg = (
            f"📋 每日复盘 — {datetime.now().strftime('%Y-%m-%d')}\n"
            f"（主板 + 北交所 | 已排除创业板/科创板）\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📊 {idx_line}\n\n"
            f"📈 涨停 {zt}家  跌停 {dt}家  连板 {lian}家\n"
            f"🔥 热点板块：{sec_str}\n\n"
            f"🏆 涨幅前50\n{_rows(up_list)}\n\n"
            f"💔 跌幅前10\n{_rows(down_list)}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{ai_text}"
        )
        notifier.telegram.send(msg)
        logger.info("每日复盘已推送")


daily_review = DailyReview()
