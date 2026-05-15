"""
美股自选股盘中实时价格推送
"""
from datetime import datetime
from typing import List

from modules.us_stock.us_data import get_quotes, load_us_watchlist
from utils.logger import logger


class USStockMonitor:

    def run_realtime_push(self) -> str:
        """推送自选美股实时价格，返回格式化消息"""
        watchlist = load_us_watchlist()
        if not watchlist:
            logger.warning("美股自选股为空，跳过推送")
            return ""

        df = get_quotes(watchlist)
        if df.empty:
            logger.warning("美股行情获取失败")
            return ""

        df = df.sort_values("change_pct", ascending=False)
        now = datetime.now().strftime("%m/%d %H:%M")
        lines = [f"📡 美股自选  {now}", "━━━━━━━━━━━━━━━━", ""]

        for _, row in df.iterrows():
            pct = row["change_pct"]
            icon = "🔴" if pct > 0 else ("🟢" if pct < 0 else "⚪")
            sign = "+" if pct > 0 else ""
            lines.append(f"{icon} {row['symbol']}")
            lines.append(f"   ${row['price']:.2f}  {sign}{pct:.2f}%  "
                         f"H: ${row['high']:.2f}  L: ${row['low']:.2f}")
            lines.append("")

        logger.info(f"美股实时行情推送，共 {len(df)} 只")
        return "\n".join(lines)


us_monitor = USStockMonitor()
