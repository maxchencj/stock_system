"""
全市场异动扫描 - 每日收盘后分析涨停结构与市场热点
每个交易日 15:45 推送 → A股Bot
数据来源：AKShare 涨停池（连板、首板、行业分布）
"""
from collections import Counter
from datetime import datetime
from typing import Dict, List

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger


def _fetch_zt_pool() -> List[Dict]:
    """获取今日涨停池"""
    try:
        import akshare as ak
        today = datetime.now().strftime("%Y%m%d")
        df = ak.stock_zt_pool_em(date=today)
        if df is None or df.empty:
            return []
        result = []
        for _, row in df.iterrows():
            result.append({
                "code": str(row.get("代码", "")),
                "name": str(row.get("名称", "")),
                "pct": float(row.get("涨跌幅", 0)),
                "amount": float(row.get("成交额", 0)) / 1e8,
                "seal_amount": float(row.get("封板资金", 0)) / 1e8,
                "first_seal": str(row.get("首次封板时间", "")),
                "consecutive": int(row.get("连板数", 1)),
                "industry": str(row.get("所属行业", "")),
            })
        return result
    except Exception as e:
        logger.warning(f"获取涨停池失败: {e}")
        return []


def _fetch_strong_pool() -> List[Dict]:
    """获取强势股池（高换手、高位股）"""
    try:
        import akshare as ak
        today = datetime.now().strftime("%Y%m%d")
        df = ak.stock_zt_pool_strong_em(date=today)
        if df is None or df.empty:
            return []
        result = []
        for _, row in df.iterrows():
            result.append({
                "code": str(row.get("代码", "")),
                "name": str(row.get("名称", "")),
                "pct": float(row.get("涨跌幅", 0)),
                "industry": str(row.get("所属行业", "")),
            })
        return result[:10]
    except Exception as e:
        logger.warning(f"获取强势股池失败: {e}")
        return []


def _analyze_zt_structure(zt_list: List[Dict]) -> Dict:
    """分析涨停结构"""
    if not zt_list:
        return {}

    total = len(zt_list)
    first_board = [s for s in zt_list if s["consecutive"] == 1]
    multi_board = [s for s in zt_list if s["consecutive"] > 1]
    high_board = [s for s in zt_list if s["consecutive"] >= 3]

    # 行业分布
    industries = [s["industry"] for s in zt_list if s["industry"]]
    industry_count = Counter(industries).most_common(5)

    # 早盘封板（9:30-10:00）
    early_seal = [s for s in zt_list if s["first_seal"] and s["first_seal"] < "10:00:00"]

    # 最大封板资金
    top_seal = sorted(zt_list, key=lambda x: x["seal_amount"], reverse=True)[:3]

    return {
        "total": total,
        "first_board": len(first_board),
        "multi_board": len(multi_board),
        "high_board": len(high_board),
        "top_industries": industry_count,
        "early_seal": len(early_seal),
        "top_seal_stocks": top_seal,
        "avg_consecutive": round(sum(s["consecutive"] for s in zt_list) / total, 1),
    }


def _ai_scanner_analysis(structure: Dict, strong: List[Dict]) -> str:
    system_prompt = "你是专业的A股游资和板块研究员，擅长解读涨停板结构和市场赚钱效应。"
    top_ind = "、".join([f"{k}({v}只)" for k, v in structure.get("top_industries", [])])
    top_seal = "、".join([f"{s['name']}({s['seal_amount']:.1f}亿)" for s in structure.get("top_seal_stocks", [])])
    strong_str = "、".join([s["name"] for s in strong[:5]])

    user_prompt = f"""今日涨停板结构数据：

涨停总数：{structure.get('total', 0)} 只
首板：{structure.get('first_board', 0)} 只 | 连板：{structure.get('multi_board', 0)} 只 | 3板+：{structure.get('high_board', 0)} 只
平均连板数：{structure.get('avg_consecutive', 0)}
早盘封板（10点前）：{structure.get('early_seal', 0)} 只
热点行业：{top_ind or '暂无'}
封板资金最大：{top_seal or '暂无'}
强势股：{strong_str or '暂无'}

请用200字以内输出：
【市场赚钱效应】高/中/低，说明原因
【热点板块】主要资金聚集板块及持续性判断
【操作建议】明日关注方向（首板还是连板？追板还是等回调？）"""

    return ai_engine._call(system_prompt, user_prompt, max_tokens=500)


class MarketScanner:

    def run_daily_scan(self):
        logger.info("执行全市场异动扫描")
        zt_list = _fetch_zt_pool()
        strong_list = _fetch_strong_pool()

        if not zt_list:
            logger.info("今日无涨停数据，跳过扫描")
            return

        structure = _analyze_zt_structure(zt_list)
        ai_text = _ai_scanner_analysis(structure, strong_list)

        # 热点行业格式化
        industry_str = "\n".join(
            [f"  {k} {v}只" for k, v in structure.get("top_industries", [])]
        ) or "  暂无"

        # 高连板股
        high_board = [s for s in zt_list if s["consecutive"] >= 3]
        high_str = "、".join([f"{s['name']}({s['consecutive']}板)" for s in high_board[:5]]) or "暂无"

        msg = (
            f"🔍 全市场异动扫描 — {datetime.now().strftime('%m/%d')}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🔴 涨停 {structure.get('total', 0)} 只\n"
            f"  首板 {structure.get('first_board', 0)} | "
            f"连板 {structure.get('multi_board', 0)} | "
            f"3板+ {structure.get('high_board', 0)}\n\n"
            f"🏭 热点行业\n{industry_str}\n\n"
            f"🚀 高位连板\n  {high_str}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{ai_text}"
        )
        notifier.telegram.send(msg)
        logger.info(f"全市场异动扫描已推送，涨停{structure.get('total',0)}只")


market_scanner = MarketScanner()
