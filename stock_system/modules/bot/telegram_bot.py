"""
Telegram Bot 双向交互模块
支持命令：/watchlist /add /remove /research /brief /status /help
仅响应配置的 chat_id，防止未授权访问
"""
import asyncio
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config.settings import config
from utils.logger import logger

WATCHLIST_FILE = Path(__file__).parent.parent.parent / "data" / "watchlist.json"
US_WATCHLIST_FILE = Path(__file__).parent.parent.parent / "data" / "us_watchlist.json"

ALLOWED_CHAT_ID = int(config.notify.telegram_chat_id or 0)


# ─────────────────── 工具函数 ───────────────────

def _is_a_share(code: str) -> bool:
    return code.isdigit() and len(code) == 6 and code[0] in ("0", "3", "6")


def _is_us_stock(code: str) -> bool:
    return code.isalpha() and 1 <= len(code) <= 5


def _load_json(path: Path) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {"stocks": {}}


def _save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_a_stock_name(code: str) -> str:
    try:
        import baostock as bs
        lg = bs.login()
        bs_code = f"sh.{code}" if code.startswith("6") else f"sz.{code}"
        rs = bs.query_stock_basic(code=bs_code)
        row = rs.get_row_data()
        bs.logout()
        return row[1] if row and len(row) > 1 else code
    except Exception:
        return code


def _get_us_stock_name(symbol: str) -> str:
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info
        return info.get("longName", symbol)
    except Exception:
        return symbol


def _auth(update: Update) -> bool:
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return False
    return True


# ─────────────────── 命令处理 ───────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    await update.message.reply_text(
        "👋 股票助手已就绪\n\n"
        "/watchlist — 查看自选股\n"
        "/add <代码> — 添加自选股\n"
        "/remove <代码> — 删除自选股\n"
        "/research <代码> — 生成研报\n"
        "/brief — 立即推送今日简报\n"
        "/status — 系统状态\n"
        "/help — 帮助"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    a_data = _load_json(WATCHLIST_FILE)
    us_data = _load_json(US_WATCHLIST_FILE)

    lines = ["📋 当前自选股\n"]
    lines.append("🇨🇳 A股：")
    a_stocks = a_data.get("stocks", {})
    if a_stocks:
        for code, info in a_stocks.items():
            lines.append(f"  {info['name']}（{code}）")
    else:
        lines.append("  暂无")

    lines.append("\n🇺🇸 美股：")
    us_stocks = us_data.get("stocks", {})
    if us_stocks:
        for code, info in us_stocks.items():
            lines.append(f"  {info['name']}（{code}）")
    else:
        lines.append("  暂无")

    await update.message.reply_text("\n".join(lines))


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    if not context.args:
        await update.message.reply_text("用法：/add <股票代码>\n示例：/add 600519  或  /add NVDA")
        return

    code = context.args[0].upper().strip()
    await update.message.reply_text(f"🔍 查询 {code} 中...")

    if _is_a_share(code):
        name = _get_a_stock_name(code)
        data = _load_json(WATCHLIST_FILE)
        if code in data["stocks"]:
            await update.message.reply_text(f"⚠️ {name}（{code}）已在A股自选股中")
            return
        data["stocks"][code] = {"name": name, "added_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        _save_json(WATCHLIST_FILE, data)
        await update.message.reply_text(f"✅ 已添加 {name}（{code}）到A股自选股")
        logger.info(f"Bot: 添加A股自选股 {name}({code})")

    elif _is_us_stock(code):
        name = _get_us_stock_name(code)
        data = _load_json(US_WATCHLIST_FILE)
        if code in data["stocks"]:
            await update.message.reply_text(f"⚠️ {name}（{code}）已在美股自选股中")
            return
        data["stocks"][code] = {"name": name, "added_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        _save_json(US_WATCHLIST_FILE, data)
        await update.message.reply_text(f"✅ 已添加 {name}（{code}）到美股自选股")
        logger.info(f"Bot: 添加美股自选股 {name}({code})")

    else:
        await update.message.reply_text("❌ 无法识别股票代码\nA股：6位数字（如 600519）\n美股：1-5位字母（如 NVDA）")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    if not context.args:
        await update.message.reply_text("用法：/remove <股票代码>\n示例：/remove 600519  或  /remove NVDA")
        return

    code = context.args[0].upper().strip()

    # 先查A股
    a_data = _load_json(WATCHLIST_FILE)
    if code in a_data["stocks"]:
        name = a_data["stocks"][code]["name"]
        del a_data["stocks"][code]
        _save_json(WATCHLIST_FILE, a_data)
        await update.message.reply_text(f"✅ 已从A股自选股移除 {name}（{code}）")
        logger.info(f"Bot: 移除A股自选股 {name}({code})")
        return

    # 再查美股
    us_data = _load_json(US_WATCHLIST_FILE)
    if code in us_data["stocks"]:
        name = us_data["stocks"][code]["name"]
        del us_data["stocks"][code]
        _save_json(US_WATCHLIST_FILE, us_data)
        await update.message.reply_text(f"✅ 已从美股自选股移除 {name}（{code}）")
        logger.info(f"Bot: 移除美股自选股 {name}({code})")
        return

    await update.message.reply_text(f"❌ 未找到 {code}，请检查代码是否正确")


async def cmd_research(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    if not context.args:
        await update.message.reply_text("用法：/research <股票代码>\n示例：/research 600519  或  /research NVDA")
        return

    code = context.args[0].upper().strip()
    await update.message.reply_text(f"📚 正在生成 {code} 研报，约需 20-30 秒...")

    def _do_research():
        try:
            if _is_a_share(code):
                import pandas as pd
                from modules.research.research_engine import AShareResearch
                r = AShareResearch()
                name = _get_a_stock_name(code)
                row = pd.Series({"代码": code, "名称": name, "总市值": 0, "市盈率-动态": 0, "市净率": 0})
                report = r._generate_report(row)
                from notify.notifier import notifier
                msg = f"📚 A股研报  {name}（{code}）\n━━━━━━━━━━━━━━━━\n{report}"
                notifier.telegram.send(msg)
            elif _is_us_stock(code):
                from modules.research.research_engine import USResearch
                r = USResearch()
                report = r._generate_report(code)
                cn_name = r._extract_cn_name(report)
                import yfinance as yf
                name = yf.Ticker(code).info.get("longName", code)
                display = f"{cn_name}·{name}" if cn_name else name
                from notify.notifier import notifier
                msg = f"📚 美股研报  {display}（{code}）\n━━━━━━━━━━━━━━━━\n{report}"
                notifier.us.send(msg)
            else:
                from notify.notifier import notifier
                notifier.telegram.send(f"❌ 无法识别股票代码：{code}")
        except Exception as e:
            logger.error(f"Bot research失败: {e}", exc_info=True)

    threading.Thread(target=_do_research, daemon=True).start()


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    hour = datetime.now().hour
    await update.message.reply_text("📰 正在生成简报，稍候推送...")

    def _do_brief():
        try:
            from modules.news.news_engine import a_news, us_news
            if hour < 14:
                a_news.push_morning()
                us_news.push_morning()
            else:
                a_news.push_evening()
                us_news.push_evening()
        except Exception as e:
            logger.error(f"Bot brief失败: {e}", exc_info=True)

    threading.Thread(target=_do_brief, daemon=True).start()


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    try:
        from core.scheduler import scheduler as sch
        jobs = sch.scheduler.get_jobs()
        a_data = _load_json(WATCHLIST_FILE)
        us_data = _load_json(US_WATCHLIST_FILE)

        # API用量
        usage_file = Path(__file__).parent.parent.parent / "data" / "api_usage.json"
        today_tokens = 0
        if usage_file.exists():
            with open(usage_file) as f:
                usage = json.load(f)
            today = datetime.now().strftime("%Y-%m-%d")
            today_tokens = usage.get("daily", {}).get(today, {}).get("total_tokens", 0)

        lines = [
            "🟢 系统运行正常",
            f"",
            f"📋 定时任务：{len(jobs)} 个已注册",
            f"🇨🇳 A股自选股：{len(a_data.get('stocks', {}))} 只",
            f"🇺🇸 美股自选股：{len(us_data.get('stocks', {}))} 只",
            f"🤖 今日API消耗：{today_tokens:,} tokens",
            f"⏰ 当前时间：{datetime.now().strftime('%H:%M:%S')}",
        ]
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ 状态获取失败: {e}")


# ─────────────────── 启动函数 ───────────────────

def start_bot():
    """在后台线程启动 Telegram Bot"""
    token = config.notify.telegram_token
    if not token:
        logger.warning("未配置 TELEGRAM_TOKEN，Bot 不启动")
        return

    def _run():
        async def _main():
            app = Application.builder().token(token).build()
            app.add_handler(CommandHandler("start", cmd_start))
            app.add_handler(CommandHandler("help", cmd_help))
            app.add_handler(CommandHandler("watchlist", cmd_watchlist))
            app.add_handler(CommandHandler("wl", cmd_watchlist))
            app.add_handler(CommandHandler("add", cmd_add))
            app.add_handler(CommandHandler("remove", cmd_remove))
            app.add_handler(CommandHandler("research", cmd_research))
            app.add_handler(CommandHandler("brief", cmd_brief))
            app.add_handler(CommandHandler("status", cmd_status))

            logger.info("Telegram Bot 已启动，等待指令...")
            async with app:
                await app.start()
                await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
                await asyncio.Event().wait()  # 永久运行

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_main())
        except Exception as e:
            logger.error(f"Telegram Bot 异常停止: {e}")

    t = threading.Thread(target=_run, daemon=True, name="TelegramBot")
    t.start()
    logger.info("Telegram Bot 线程已启动")
