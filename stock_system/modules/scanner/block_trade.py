"""
大宗交易监控 - 每日盘后推送折价/溢价大宗交易，判断主力动向
每个交易日 19:30 推送 → A股Bot
"""
from datetime import datetime, timedelta
from typing import List, Dict

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger


def _fetch_block_trades() -> List[Dict]:
    """获取近期大宗交易数据（按频次+折溢价筛选）"""
    try:
        import akshare as ak
        df = ak.stock_dzjy_hygtj()
        if df is None or df.empty:
            return []

        # 过滤：最近上榜日在近3个交易日内
        today = datetime.now()
        cutoff = (today - timedelta(days=5)).strftime("%Y-%m-%d")

        result = []
        for _, row in df.iterrows():
            last_date = str(row.get("最近上榜日", ""))
            if last_date < cutoff:
                continue
            discount = float(row.get("折溢率", 0) or 0)
            result.append({
                "code": str(row.get("证券代码", "")),
                "name": str(row.get("证券简称", "")),
                "price": float(row.get("最新价", 0) or 0),
                "pct": float(row.get("涨跌幅", 0) or 0),
                "last_date": last_date,
                "total_count": int(row.get("上榜次数-总计", 0) or 0),
                "premium_count": int(row.get("上榜次数-溢价", 0) or 0),
                "discount_count": int(row.get("上榜次数-折价", 0) or 0),
                "total_amount": float(row.get("总成交额", 0) or 0),
                "discount_rate": discount,
                "ret_1d": float(row.get("上榜日后平均涨跌幅-1日", 0) or 0),
                "ret_5d": float(row.get("上榜日后平均涨跌幅-5日", 0) or 0),
                "ret_10d": float(row.get("上榜日后平均涨跌幅-10日", 0) or 0),
            })

        # 按折溢率分组，折价（负）和溢价（正）各取Top5
        discounts = sorted([r for r in result if r["discount_rate"] < -0.03],
                          key=lambda x: x["discount_rate"])[:5]
        premiums = sorted([r for r in result if r["discount_rate"] > 0.03],
                         key=lambda x: x["discount_rate"], reverse=True)[:5]
        return discounts + premiums
    except Exception as e:
        logger.warning(f"获取大宗交易数据失败: {e}")
        return []


def _ai_block_analysis(trades: List[Dict]) -> str:
    if not trades:
        return "暂无数据"

    system_prompt = "你是专业的A股大宗交易分析师，擅长从大宗交易折溢价判断主力意图。"
    trade_str = "\n".join([
        f"  {t['name']}({t['code']}): 折溢率{t['discount_rate']*100:+.1f}%，"
        f"上榜{t['total_count']}次，历史上榜后5日均涨{t['ret_5d']:+.1f}%"
        for t in trades[:8]
    ])

    user_prompt = f"""今日近期大宗交易数据（折价为负，溢价为正）：

{trade_str}

请用150字以内分析：
【折价大宗】大幅折价说明什么？是筹码转移还是机构减持信号？
【溢价大宗】溢价成交背后的资金动机是什么？
【操作提示】哪类大宗交易值得跟踪？关注什么信号？"""

    return ai_engine._call(system_prompt, user_prompt, max_tokens=400)


class BlockTradeMonitor:

    def run_daily_push(self):
        logger.info("执行大宗交易监控")
        trades = _fetch_block_trades()
        if not trades:
            logger.info("近期无显著大宗交易，跳过推送")
            return

        discounts = [t for t in trades if t["discount_rate"] < 0]
        premiums = [t for t in trades if t["discount_rate"] > 0]
        ai_text = _ai_block_analysis(trades)

        def fmt(t):
            sign = "🔴折" if t["discount_rate"] < 0 else "🟢溢"
            return (f"  {sign}{abs(t['discount_rate'])*100:.1f}%  "
                    f"{t['name']}({t['code']})  {t['last_date']}")

        discount_str = "\n".join([fmt(t) for t in discounts]) or "  暂无"
        premium_str = "\n".join([fmt(t) for t in premiums]) or "  暂无"

        msg = (
            f"💹 大宗交易监控 — {datetime.now().strftime('%m/%d')}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📉 折价大宗（可能减持/筹码转移）\n{discount_str}\n\n"
            f"📈 溢价大宗（可能建仓/战略配置）\n{premium_str}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{ai_text}"
        )
        notifier.telegram.send(msg)
        logger.info(f"大宗交易监控已推送，共{len(trades)}条记录")


block_trade_monitor = BlockTradeMonitor()
