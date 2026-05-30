"""
模拟仓专用推送：第三个 Telegram Bot（@mcStockMessage_bot）。
复用 notify.notifier.TelegramNotifier 底层，仅做消息格式化。
"""
from typing import Dict
from config.settings import config
from notify.notifier import TelegramNotifier
from utils.logger import logger


class SimNotifier:
    def __init__(self):
        self.tg = TelegramNotifier(
            token=config.sim_trading.telegram_token,
            chat_id=config.sim_trading.telegram_chat_id,
        )

    def send_trade(self, result: Dict, signal: Dict, total_value: float):
        """成交后推送。result: account.execute 返回；signal: 含 reasons。"""
        if not self.tg.enabled:
            logger.warning("模拟仓 Telegram Bot 未配置，跳过推送")
            return False
        if not result.get("ok"):
            return False

        is_buy = result["action"] == "buy"
        head = "✅ 模拟仓已买入" if is_buy else "✅ 模拟仓已卖出"
        reasons = "、".join(signal.get("reasons", [])) or "策略信号"
        lines = [
            head, "",
            f"📌 {result['name']}（{result['code']}）",
            "━━━━━━━━━━━━━━━━━━",
            f"📊 触发信号：{reasons}",
            f"💰 成交：{'买入' if is_buy else '卖出'} {result['shares']}股 "
            f"@ {result['price']:.2f}，金额 {result['amount']:.0f}",
        ]
        if not is_buy:
            lines.append(f"📈 已实现盈亏：{result['realized_pnl']:+.0f}")
        lines += [
            f"📊 成交后仓位：{result['position_ratio_after']*100:.0f}%",
            f"💵 账户：现金 {result['cash_after']:.0f} / 总资产 {total_value:.0f}",
        ]
        return self.tg.send("\n".join(lines))

    def send_skip_log(self, result: Dict):
        """成交被跳过时仅记日志，不推送（避免噪音）。"""
        logger.info(f"模拟仓跳过 {result.get('code')}: {result.get('reason')}")


sim_notifier = SimNotifier()
