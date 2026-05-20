"""
打新提醒模块
每天 18:00 检查次日申购新股，推送 AI 分析
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from notify.notifier import notifier
from utils.logger import logger

IPO_LOG_FILE = Path(__file__).parent.parent.parent / "data" / "ipo_log.json"


def _load_log() -> dict:
    try:
        with open(IPO_LOG_FILE) as f:
            return json.load(f)
    except Exception:
        return {"notified": []}


def _save_log(data: dict):
    IPO_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(IPO_LOG_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _fetch_upcoming_ipos() -> list:
    """获取近期新股申购信息（含今日 + 明日申购）"""
    try:
        import akshare as ak
        df = ak.stock_ipo_ths()
        if df is None or df.empty:
            return []

        # 申购日期格式为 "05-20 周三" 或 "2026-05-18"，统一提取 MM-DD 匹配
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%m-%d")
        today = datetime.now().strftime("%m-%d")
        target_mmdd = {today, tomorrow}

        results = []
        for _, row in df.iterrows():
            sub_date = str(row.get("申购日期", ""))
            if not any(d in sub_date for d in target_mmdd):
                continue
            # 过滤掉已有中签率（已过申购期）的记录
            lottory = str(row.get("中签率（%）", ""))
            if lottory and lottory not in ("-", "", "nan"):
                continue
            results.append({
                "name": str(row.get("股票简称", "")),
                "code": str(row.get("股票代码", "")),
                "issue_price": str(row.get("发行价格", "未知")),
                "pe_ratio": str(row.get("发行市盈率", "未知")),
                "industry_pe": str(row.get("行业市盈率", "未知")),
                "max_apply": str(row.get("申购上限（万股）", "未知")),
                "sub_date": sub_date,
            })
        return results
    except Exception as e:
        logger.warning(f"获取新股申购数据失败: {e}")
        return []


def _ai_ipo_analysis(ipo: dict) -> str:
    """AI 分析新股是否值得申购"""
    try:
        from ai.analysis_engine import ai_engine
        system_prompt = (
            "你是专业的A股打新分析师。根据新股基本信息，分析上市后表现预期，给出申购建议。"
            "分析简洁有力，重点关注：发行价合理性、行业景气度、市盈率水平。"
        )
        user_prompt = f"""请分析以下新股是否值得申购：

股票名称: {ipo['name']}
股票代码: {ipo['code']}
发行价格: {ipo['issue_price']} 元
发行市盈率: {ipo['pe_ratio']}（行业市盈率: {ipo.get('industry_pe', '未知')}）
申购上限: {ipo.get('max_apply', '未知')} 万股
申购日期: {ipo['sub_date']}

输出格式（总计250字以内）：
【行业分析】...
【估值判断】...
【申购建议】推荐申购 / 谨慎申购 / 不建议申购
【预期首日涨幅】X%～Y%
【风险提示】..."""

        return ai_engine._call(system_prompt, user_prompt, max_tokens=500)
    except Exception as e:
        logger.error(f"IPO AI分析失败: {e}")
        return "（AI分析暂时不可用）"


class IPOReminder:
    """打新提醒"""

    def run_daily_check(self):
        """检查并推送打新提醒"""
        logger.info("执行打新提醒检查")
        ipos = _fetch_upcoming_ipos()
        if not ipos:
            logger.info("近期无新股申购")
            return

        log = _load_log()
        notified = set(log.get("notified", []))
        today = datetime.now().strftime("%Y-%m-%d")
        pushed = False

        for ipo in ipos:
            key = f"{ipo['code']}_{today}"
            if key in notified:
                continue

            analysis = _ai_ipo_analysis(ipo)
            msg = (
                f"🔔 打新提醒\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"📋 {ipo['name']}（{ipo['code']}）\n"
                f"💰 发行价：{ipo['issue_price']} 元\n"
                f"📊 发行市盈率：{ipo['pe_ratio']}（行业：{ipo.get('industry_pe','未知')}）\n"
                f"📈 申购上限：{ipo.get('max_apply','未知')} 万股\n"
                f"📅 申购日期：{ipo['sub_date']}\n\n"
                f"{analysis}"
            )
            notifier.telegram.send(msg)
            notified.add(key)
            pushed = True
            logger.info(f"打新提醒已推送: {ipo['name']}({ipo['code']})")

        if pushed:
            log["notified"] = list(notified)
            _save_log(log)


ipo_reminder = IPOReminder()
