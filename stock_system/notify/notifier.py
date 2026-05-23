"""
通知层 - PushPlus微信 + Telegram Bot
"""
import time
import sqlite3
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from config.settings import config
from utils.logger import logger

# ── 推送历史 SQLite ──────────────────────────────────────
_DB_PATH = Path(__file__).parent.parent / "data" / "push_history.db"


def _init_db():
    con = sqlite3.connect(_DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS push_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT    NOT NULL,
            bot       TEXT    NOT NULL,
            preview   TEXT    NOT NULL,
            success   INTEGER NOT NULL DEFAULT 1
        )
    """)
    con.commit()
    con.close()


def _log_push(bot: str, message: str, success: bool):
    try:
        _init_db()
        preview = message.replace("\n", " ")[:100]
        con = sqlite3.connect(_DB_PATH)
        con.execute(
            "INSERT INTO push_history(ts, bot, preview, success) VALUES (?,?,?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bot, preview, 1 if success else 0)
        )
        con.commit()
        con.close()
    except Exception as e:
        logger.warning(f"记录推送历史失败: {e}")


def get_push_history(limit: int = 10) -> list:
    """返回最近 limit 条推送记录"""
    try:
        _init_db()
        con = sqlite3.connect(_DB_PATH)
        rows = con.execute(
            "SELECT ts, bot, preview, success FROM push_history ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        con.close()
        return [{"ts": r[0], "bot": r[1], "preview": r[2], "success": bool(r[3])} for r in rows]
    except Exception:
        return []


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

    def __init__(self, token: str = "", chat_id: str = ""):
        self.token = token or config.notify.telegram_token
        self.chat_id = chat_id or config.notify.telegram_chat_id
        self.enabled = bool(self.token) and bool(self.chat_id)
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send(self, message: str, parse_mode: str = "") -> bool:
        """发送消息，超过 4096 字符自动分段，失败最多重试 2 次（间隔 30s）"""
        if not self.enabled:
            logger.debug("Telegram未启用")
            return False

        chunks = self._split(message)
        all_ok = True
        for chunk in chunks:
            ok = self._send_with_retry(chunk, parse_mode)
            all_ok = all_ok and ok

        bot_name = "A股Bot" if self.token == config.notify.telegram_token else "US Bot"
        _log_push(bot_name, message, all_ok)
        return all_ok

    def _send_with_retry(self, text: str, parse_mode: str = "", max_retry: int = 2) -> bool:
        data = {"chat_id": self.chat_id, "text": text}
        if parse_mode:
            data["parse_mode"] = parse_mode
        for attempt in range(max_retry + 1):
            try:
                resp = requests.post(self.api_url, json=data, timeout=10)
                if resp.status_code == 200:
                    logger.info("Telegram推送成功")
                    return True
                logger.warning(f"Telegram推送失败(第{attempt+1}次): {resp.text[:100]}")
            except Exception as e:
                logger.warning(f"Telegram推送异常(第{attempt+1}次): {e}")
            if attempt < max_retry:
                time.sleep(30)
        logger.error("Telegram推送重试耗尽，放弃")
        return False

    @staticmethod
    def _split(text: str, limit: int = 4000) -> list:
        """按段落切割长消息，每段不超过 limit 字符"""
        if len(text) <= limit:
            return [text]
        chunks, current = [], ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > limit:
                if current:
                    chunks.append(current.rstrip())
                current = line + "\n"
            else:
                current += line + "\n"
        if current.strip():
            chunks.append(current.rstrip())
        return chunks


class USNotificationService:
    """美股专用通知服务（第二个 Telegram Bot）"""

    def __init__(self):
        self.telegram = TelegramNotifier(
            token=config.us_stock.telegram_token,
            chat_id=config.us_stock.telegram_chat_id,
        )

    def send(self, message: str) -> bool:
        if not self.telegram.enabled:
            logger.warning("美股 Telegram Bot 未配置，跳过推送")
            return False
        return self.telegram.send(message)


class NotificationService:
    """统一通知服务"""

    def __init__(self):
        self.pushplus = PushPlusNotifier()
        self.telegram = TelegramNotifier()
        self.us = USNotificationService()

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
