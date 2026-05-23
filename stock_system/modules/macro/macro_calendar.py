"""
宏观经济日历 - 每周一 8:45 推送本周重要经济数据发布计划
A股Bot + mcDolphin Bot
"""
from datetime import datetime, timedelta
from typing import List, Dict

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger


# 固定重要月度事件（每月固定时间窗口）
MONTHLY_EVENTS = [
    # 中国数据
    {"name": "中国CPI/PPI", "source": "国家统计局", "window": "每月10日前后", "market": "A"},
    {"name": "中国社融/M2", "source": "央行", "window": "每月10日前后", "market": "A"},
    {"name": "中国进出口数据", "source": "海关总署", "window": "每月10日前后", "market": "A"},
    {"name": "中国GDP（季度）", "source": "国家统计局", "window": "每季度中旬", "market": "A"},
    {"name": "PMI制造业/服务业", "source": "统计局+财新", "window": "每月1日前后", "market": "A"},
    # 美国数据
    {"name": "非农就业", "source": "美国劳工部", "window": "每月第一个周五", "market": "US"},
    {"name": "美国CPI", "source": "美国劳工部", "window": "每月10日前后", "market": "US"},
    {"name": "美联储FOMC决议", "source": "美联储", "window": "每6-8周一次", "market": "US"},
    {"name": "美国GDP（季度初值）", "source": "商务部", "window": "每季度末月最后一周", "market": "US"},
    {"name": "美国PCE通胀", "source": "商务部", "window": "每月最后一周", "market": "US"},
]


def _get_week_range() -> tuple:
    today = datetime.now()
    # 本周一到周日
    mon = today - timedelta(days=today.weekday())
    sun = mon + timedelta(days=6)
    return mon, sun


def _build_weekly_context() -> str:
    """构建本周宏观背景"""
    mon, sun = _get_week_range()
    week_str = f"{mon.strftime('%m月%d日')}～{sun.strftime('%m月%d日')}"
    month = mon.month
    day = mon.day

    # 判断本月可能发生的重要事件
    events_this_week = []

    # PMI 一般在月初
    if 1 <= day <= 5:
        events_this_week.append("📊 本周可能发布：PMI制造业/服务业（国家统计局+财新）")

    # CPI/PPI/社融 一般10号前后
    if 7 <= day <= 15:
        events_this_week.append("📊 本周可能发布：中国CPI/PPI、M2/社融、进出口数据")
        events_this_week.append("📊 本周可能发布：美国CPI")

    # 非农一般第一个周五
    if 1 <= day <= 7:
        events_this_week.append("🇺🇸 本周可能发布：美国非农就业数据（周五）")

    # PCE 月末
    if 22 <= day <= 31:
        events_this_week.append("🇺🇸 本周可能发布：美国PCE通胀、GDP季度终值")

    event_str = "\n".join(events_this_week) if events_this_week else "本周暂无固定重要数据窗口"

    return f"本周日期：{week_str}\n\n{event_str}"


def _ai_macro_preview(week_context: str) -> str:
    system_prompt = "你是专业的宏观经济分析师，同时熟悉A股和美股市场。请用中文输出。"
    user_prompt = f"""请基于以下信息，生成本周宏观经济日历简报：

{week_context}

固定关注事项（每周）：
- A股：政策动向、外资流向、汇率变化
- 美股：美联储官员讲话、科技股财报（财报季期间）
- 全球：大宗商品（油价/金价）、地缘风险

请输出（总计250字以内）：
【本周关键数据】列出2-3个最值得关注的数据/事件及发布时间
【A股影响】对A股可能的影响方向
【美股影响】对美股可能的影响方向
【策略建议】本周操作上需要注意的宏观风险点"""

    return ai_engine._call(system_prompt, user_prompt, max_tokens=600)


class MacroCalendar:

    def run_weekly_push(self):
        logger.info("执行宏观经济日历推送")
        week_context = _build_weekly_context()
        ai_text = _ai_macro_preview(week_context)

        mon, sun = _get_week_range()
        msg = (
            f"📅 宏观经济日历\n"
            f"本周 {mon.strftime('%m/%d')}～{sun.strftime('%m/%d')}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{ai_text}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💡 常规关注：PMI(月初) / CPI(月中) / 非农(第1个周五) / FOMC(每6-8周)"
        )
        notifier.telegram.send(msg)
        notifier.us.send(msg)
        logger.info("宏观经济日历已推送")


macro_calendar = MacroCalendar()
