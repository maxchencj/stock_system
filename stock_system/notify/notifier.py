"""
通知层 - PushPlus微信 + Telegram Bot
"""
import requests
from typing import Dict, Optional
from config.settings import config
from utils.logger import logger


class PushPlusNotifier:
    """PushPlus 微信推送"""

    def __init__(self):
        self.token = config.notify.pushplus_token
        self.enabled = config.notify.pushplus_enabled and bool(self.token)
        self.api_url = "http://www.pushplus.plus/send"

    def send(self, title: str, content: str, template: str = "txt") -> bool:
        """发送推送"""
        if not self.enabled:
            logger.debug("PushPlus未启用")
            return False

        try:
            data = {
                "token": self.token,
                "title": title,
                "content": content,
                "template": template
            }
            resp = requests.post(self.api_url, json=data, timeout=10)
            if resp.status_code == 200 and resp.json().get("code") == 200:
                logger.info(f"PushPlus推送成功: {title}")
                return True
            else:
                logger.error(f"PushPlus推送失败: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"PushPlus推送异常: {e}")
            return False


class TelegramNotifier:
    """Telegram Bot 推送"""

    def __init__(self):
        self.token = config.notify.telegram_token
        self.chat_id = config.notify.telegram_chat_id
        self.enabled = config.notify.telegram_enabled and bool(self.token) and bool(self.chat_id)
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send(self, message: str, parse_mode: str = "Markdown") -> bool:
        """发送消息"""
        if not self.enabled:
            logger.debug("Telegram未启用")
            return False

        try:
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode
            }
            resp = requests.post(self.api_url, json=data, timeout=10)
            if resp.status_code == 200:
                logger.info("Telegram推送成功")
                return True
            else:
                logger.error(f"Telegram推送失败: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Telegram推送异常: {e}")
            return False


class NotificationService:
    """统一通知服务"""

    def __init__(self):
        self.pushplus = PushPlusNotifier()
        self.telegram = TelegramNotifier()

    def send_all(self, title: str, content: str):
        """发送到所有启用的通知渠道"""
        self.pushplus.send(title, content)
        self.telegram.send(f"**{title}**\n\n{content}")

    def send_daily_picks(self, report: str):
        """发送每日选股报告"""
        self.send_all("📊 每日选股报告", report)

    def send_sector_report(self, report: str):
        """发送板块分析报告"""
        self.send_all("📈 板块分析日报", report)

    def send_monitor_alert(self, stock_info: Dict):
        """发送监控预警（支持多维度信号格式化）"""
        code = stock_info.get("code", "")
        name = stock_info.get("name", "")
        price = stock_info.get("price", 0)
        signals = stock_info.get("signals", [])
        buy_count = stock_info.get("buy_count", 0)
        sell_count = stock_info.get("sell_count", 0)

        # 标题根据信号方向
        if buy_count > sell_count:
            title = f"🟢 买入信号 [{code}] {name}"
        elif sell_count > buy_count:
            title = f"🔴 卖出信号 [{code}] {name}"
        else:
            title = f"⚡ 监控预警 [{code}] {name}"

        lines = [
            f"股票: [{code}] {name}",
            f"现价: {price:.2f}",
            f"涨跌幅: {stock_info.get('change_pct', 0):.2f}%",
            f"量比: {stock_info.get('volume_ratio', 0):.2f}",
        ]
        turnover = stock_info.get("turnover_rate", 0)
        if turnover:
            lines.append(f"换手率: {turnover:.2f}%")

        # 按信号类型分组展示
        buy_signals = [s for s in signals if s.get("signal") == "buy"]
        sell_signals = [s for s in signals if s.get("signal") == "sell"]
        alert_signals = [s for s in signals if s.get("signal") == "alert"]

        if buy_signals:
            lines.append("")
            lines.append(f"--- 买入信号({len(buy_signals)}) ---")
            for sig in buy_signals:
                icon = "!!" if sig.get("urgency") == "high" else ""
                lines.append(f"  {icon} {sig.get('reason')}")
                detail = sig.get("detail", {})
                if detail.get("fractal_type") == "bottom":
                    lines.append(f"     止损参考: {detail.get('stop_loss', '-')}")

        if sell_signals:
            lines.append("")
            lines.append(f"--- 卖出信号({len(sell_signals)}) ---")
            for sig in sell_signals:
                icon = "!!" if sig.get("urgency") == "high" else ""
                lines.append(f"  {icon} {sig.get('reason')}")

        if alert_signals:
            lines.append("")
            lines.append(f"--- 异动提醒({len(alert_signals)}) ---")
            for sig in alert_signals:
                lines.append(f"  {sig.get('reason')}")

        # 信号共振提示
        if len(signals) >= 3:
            lines.append("")
            lines.append(f"*** 多信号共振({len(signals)}个信号)，请重点关注 ***")

        # AI分析
        ai_analysis = stock_info.get("ai_analysis")
        if ai_analysis:
            lines.append("")
            lines.append("--- AI智能分析 ---")
            lines.append(f"信号有效性: {ai_analysis.get('confidence', '未知')}")
            lines.append(f"建议操作: {ai_analysis.get('action', '观察')}")
            lines.append(f"分析: {ai_analysis.get('analysis', '')}")
            if ai_analysis.get("entry_price"):
                lines.append(f"介入价: {ai_analysis['entry_price']}")
            if ai_analysis.get("stop_loss"):
                lines.append(f"止损价: {ai_analysis['stop_loss']}")
            if ai_analysis.get("target_price"):
                lines.append(f"目标价: {ai_analysis['target_price']}")

        content = "\n".join(lines)
        self.send_all(title, content)

    def send_morning_brief(self, brief: str):
        """发送市场早报"""
        self.send_all("🌅 市场早报", brief)


# 单例
notifier = NotificationService()
