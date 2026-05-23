"""
北向资金深度追踪 - 每个交易日 17:15 推送
沪深股通合计净流入 + 近5日趋势 + AI解读 → A股Bot
"""
import math
from datetime import datetime
from typing import List, Optional

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger


def _get_north_history(days: int = 7) -> List[dict]:
    """获取最近N日北向资金数据（沪股通+深股通合计）"""
    try:
        import akshare as ak
        import pandas as pd

        result = {}
        for sym in ["沪股通", "深股通"]:
            df = ak.stock_hsgt_hist_em(symbol=sym)
            if df is None or df.empty:
                continue
            df = df.tail(days).copy()
            for _, row in df.iterrows():
                date = str(row["日期"])[:10]
                val = row["当日成交净买额"]
                if val is None or (isinstance(val, float) and math.isnan(val)):
                    continue
                result[date] = result.get(date, 0) + float(val)

        if not result:
            return []

        sorted_days = sorted(result.items())
        return [
            {"date": d, "net_flow": round(v / 1e8, 2)}
            for d, v in sorted_days
        ]
    except Exception as e:
        logger.warning(f"获取北向历史数据失败: {e}")
        return []


def _ai_north_analysis(history: List[dict]) -> str:
    if not history:
        return "数据暂缺"

    system_prompt = "你是专业的A股外资资金流向分析师。请简洁分析北向资金动向。"
    flow_str = "\n".join(
        [f"  {d['date']}: {d['net_flow']:+.2f}亿元" for d in history]
    )
    total = sum(d["net_flow"] for d in history)
    consecutive_in = 0
    for d in reversed(history):
        if d["net_flow"] > 0:
            consecutive_in += 1
        else:
            break

    user_prompt = f"""北向资金近期数据：
{flow_str}

区间合计：{total:+.2f}亿元
连续净流入天数：{consecutive_in} 天

请用150字以内输出：
【资金趋势】流入/流出/震荡，判断当前外资态度
【信号意义】当前北向行为对A股意味着什么
【后续预判】短期北向资金方向研判"""

    return ai_engine._call(system_prompt, user_prompt, max_tokens=350)


class NorthFlowTracker:

    def run_daily_push(self):
        logger.info("执行北向资金深度追踪")
        history = _get_north_history(days=7)

        if not history:
            logger.info("北向资金数据暂缺，跳过推送")
            return

        today_flow = history[-1]["net_flow"] if history else 0
        week_total = sum(d["net_flow"] for d in history)
        consecutive_in = 0
        for d in reversed(history):
            if d["net_flow"] > 0:
                consecutive_in += 1
            else:
                break

        ai_text = _ai_north_analysis(history)

        # 近5日趋势图（文字版）
        trend_lines = []
        for d in history[-5:]:
            bar = "▲" if d["net_flow"] > 0 else "▼"
            trend_lines.append(f"  {d['date'][5:]} {bar} {d['net_flow']:+.1f}亿")
        trend_str = "\n".join(trend_lines)

        flow_emoji = "🟢" if today_flow > 0 else "🔴"
        msg = (
            f"🌏 北向资金追踪 — {datetime.now().strftime('%m/%d')}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{flow_emoji} 今日净流入：{today_flow:+.2f}亿元\n"
            f"📅 近7日合计：{week_total:+.2f}亿元\n"
            f"🔄 连续净流入：{consecutive_in} 天\n\n"
            f"📈 近5日趋势\n{trend_str}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{ai_text}"
        )
        notifier.telegram.send(msg)
        logger.info(f"北向资金追踪已推送，今日:{today_flow:+.2f}亿")


north_flow_tracker = NorthFlowTracker()
