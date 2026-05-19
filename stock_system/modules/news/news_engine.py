"""
财经新闻模块
早报 8:15：隔夜市场 + 政策要闻 + 行业新闻 + 自选股关联
晚报 20:15：今日复盘 + 重要公告 + 自选股关联 + 明日预告
A股新闻 → A股Bot | 美股新闻 → mcDolphin Bot
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import requests

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger

WATCHLIST_FILE = Path(__file__).parent.parent.parent / "data" / "watchlist.json"
US_WATCHLIST_FILE = Path(__file__).parent.parent.parent / "data" / "us_watchlist.json"

_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


# ─────────────────── 工具函数 ───────────────────

def _load_watchlist(path: Path) -> Dict[str, str]:
    try:
        with open(path) as f:
            data = json.load(f)
        return {code: info["name"] for code, info in data.get("stocks", {}).items()}
    except Exception:
        return {}


def _clean_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text).strip()


# ─────────────────── 新闻抓取 ───────────────────

def _fetch_cn_news(max_items: int = 20) -> List[str]:
    """抓取中文财经新闻（新浪财经双源）"""
    items = []

    # 源1：新浪财经 A股新闻 JSON API
    try:
        r = requests.get(
            "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=20&page=1",
            headers=_HEADERS, timeout=10
        )
        data = r.json().get("result", {}).get("data", [])
        for item in data:
            title = item.get("title", "").strip()
            intro = _clean_html(item.get("intro", ""))[:100]
            if title:
                items.append(f"{title}{'：' + intro if intro else ''}")
    except Exception as e:
        logger.warning(f"新浪A股新闻抓取失败: {e}")

    # 源2：新浪财经 RSS（补充财经要闻）
    if len(items) < 10:
        try:
            import feedparser
            feed = feedparser.parse("http://rss.sina.com.cn/news/china/focus15.xml")
            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                if title and title not in [i.split("：")[0] for i in items]:
                    items.append(title)
        except Exception as e:
            logger.warning(f"新浪RSS抓取失败: {e}")

    logger.info(f"获取中文财经新闻 {len(items)} 条")
    return items[:max_items]


def _fetch_us_news(max_items: int = 20) -> List[str]:
    """抓取英文美股新闻（Yahoo Finance + CNBC 双源）"""
    import feedparser
    items = []

    sources = [
        ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
        ("CNBC", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
        ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ]

    for name, url in sources:
        if len(items) >= max_items:
            break
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                summary = _clean_html(entry.get("summary", ""))[:100]
                if title:
                    items.append(f"{title}{'  ' + summary if summary else ''}")
        except Exception as e:
            logger.warning(f"{name} RSS抓取失败: {e}")

    logger.info(f"获取英文财经新闻 {len(items)} 条")
    return items[:max_items]


# ─────────────────── 市场数据 ───────────────────

def _get_us_indices() -> str:
    """获取美股+亚太指数表现（字符串格式）"""
    try:
        import yfinance as yf
        symbols = [("^GSPC", "标普500"), ("^IXIC", "纳斯达克"), ("^DJI", "道琼斯"),
                   ("^N225", "日经225"), ("^HSI", "恒生指数")]
        lines = []
        for sym, name in symbols:
            try:
                hist = yf.Ticker(sym).history(period="2d")
                if len(hist) >= 2:
                    prev = float(hist["Close"].iloc[-2])
                    last = float(hist["Close"].iloc[-1])
                    chg = round((last - prev) / prev * 100, 2)
                    sign = "+" if chg > 0 else ""
                    icon = "🔴" if chg > 0 else "🟢" if chg < 0 else "⚪"
                    lines.append(f"  {icon} {name} {sign}{chg}%")
            except Exception:
                pass
        return "\n".join(lines) if lines else "  数据获取失败"
    except Exception as e:
        logger.warning(f"获取美股指数失败: {e}")
        return "  数据获取失败"


def _get_a_indices() -> str:
    """获取A股指数收盘数据（腾讯财经）"""
    try:
        codes = "sh000001,sz399001,sz399006"
        url = f"https://qt.gtimg.cn/q={codes}"
        r = requests.get(url, headers={**_HEADERS, "Referer": "https://finance.qq.com/"}, timeout=10)
        r.encoding = "gbk"
        names = {"000001": "上证指数", "399001": "深证成指", "399006": "创业板指"}
        lines = []
        for line in r.text.strip().split("\n"):
            if '=""' in line or not line.strip():
                continue
            try:
                p = line.split('"')[1].split("~")
                if len(p) < 5:
                    continue
                code = p[2]
                price = float(p[3])
                prev = float(p[4])
                chg = round((price - prev) / prev * 100, 2) if prev else 0
                sign = "+" if chg > 0 else ""
                icon = "🔴" if chg > 0 else "🟢" if chg < 0 else "⚪"
                name = names.get(code, code)
                lines.append(f"  {icon} {name} {price:.2f} ({sign}{chg}%)")
            except Exception:
                pass
        return "\n".join(lines) if lines else "  数据获取失败"
    except Exception as e:
        logger.warning(f"获取A股指数失败: {e}")
        return "  数据获取失败"


def _get_us_premarket() -> str:
    """获取美股盘前数据"""
    try:
        import yfinance as yf
        symbols = [("^GSPC", "标普500"), ("^IXIC", "纳斯达克"), ("^DJI", "道琼斯")]
        lines = []
        for sym, name in symbols:
            try:
                ticker = yf.Ticker(sym)
                hist = ticker.history(period="1d", prepost=True)
                if not hist.empty:
                    last = float(hist["Close"].iloc[-1])
                    lines.append(f"  {name} 最新: {last:.2f}")
            except Exception:
                pass
        return "\n".join(lines) if lines else "  盘前数据暂无"
    except Exception as e:
        logger.warning(f"获取盘前数据失败: {e}")
        return "  盘前数据暂无"


# ─────────────────── AI 生成 ───────────────────

def _ai_brief(system_prompt: str, user_prompt: str) -> str:
    return ai_engine._call(system_prompt, user_prompt, max_tokens=1000)


def _build_watchlist_context(watchlist: Dict[str, str]) -> str:
    if not watchlist:
        return "暂无自选股"
    return "、".join([f"{name}({code})" for code, name in watchlist.items()])


# ═══════════════════════════════════════════════════════
#  A股新闻引擎
# ═══════════════════════════════════════════════════════

class AShareNewsEngine:

    def push_morning(self):
        """A股早报 8:15"""
        logger.info("生成A股早报...")
        try:
            us_data = _get_us_indices()
            cn_news = _fetch_cn_news()
            watchlist = _load_watchlist(WATCHLIST_FILE)
            wl_ctx = _build_watchlist_context(watchlist)
            date_str = datetime.now().strftime("%m/%d")

            system_prompt = "你是专业的A股财经分析师，擅长撰写简洁有料的每日财经早报。"
            user_prompt = f"""请根据以下信息，生成今日A股财经早报（{date_str}）：

【隔夜美股及亚太指数】
{us_data}

【今日财经新闻】（从中筛选3-5条最相关A股市场的）
{chr(10).join(f'- {n}' for n in cn_news)}

【我的A股自选股】
{wl_ctx}

请按以下格式输出（300字以内，简洁有料）：

🌏 隔夜市场
（美股和亚太市场关键表现，1-2句，说明对今日A股的影响方向）

📋 今日要闻
（3-4条精选新闻，每条一行，格式：• 内容）

⭐ 自选股关联
（如有新闻涉及自选股所在行业/供应链，重点标注；无则写"暂无直接关联消息"）

💡 开盘研判
（一句话：今日A股整体情绪偏多/偏空/中性，关注哪个方向）"""

            content = _ai_brief(system_prompt, user_prompt)
            if not content:
                return

            msg = (
                f"📰 A股早报  {date_str} 08:15\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"{content}"
            )
            notifier.telegram.send(msg)
            logger.info("A股早报推送完成")
        except Exception as e:
            logger.error(f"A股早报失败: {e}", exc_info=True)

    def push_evening(self):
        """A股晚报 20:15"""
        logger.info("生成A股晚报...")
        try:
            a_data = _get_a_indices()
            cn_news = _fetch_cn_news()
            watchlist = _load_watchlist(WATCHLIST_FILE)
            wl_ctx = _build_watchlist_context(watchlist)
            date_str = datetime.now().strftime("%m/%d")

            system_prompt = "你是专业的A股财经分析师，擅长撰写每日收盘后的市场复盘简报。"
            user_prompt = f"""请根据以下信息，生成今日A股财经晚报（{date_str}）：

【今日A股指数收盘】
{a_data}

【今日财经新闻】（从中筛选3-5条最相关A股市场的）
{chr(10).join(f'- {n}' for n in cn_news)}

【我的A股自选股】
{wl_ctx}

请按以下格式输出（300字以内）：

📊 今日A股复盘
（大盘走势一句话总结，成交量和情绪判断）

📋 今日要闻
（3-4条精选新闻，格式：• 内容）

⭐ 自选股关联
（如有新闻涉及自选股所在行业/供应链，重点标注；无则写"暂无直接关联消息"）

🔮 明日关注
（一句话：明日值得关注的板块或事件）"""

            content = _ai_brief(system_prompt, user_prompt)
            if not content:
                return

            msg = (
                f"📰 A股晚报  {date_str} 20:15\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"{content}"
            )
            notifier.telegram.send(msg)
            logger.info("A股晚报推送完成")
        except Exception as e:
            logger.error(f"A股晚报失败: {e}", exc_info=True)


# ═══════════════════════════════════════════════════════
#  美股新闻引擎
# ═══════════════════════════════════════════════════════

class USNewsEngine:

    def push_morning(self):
        """美股早报 8:15（今晚美股开盘前预热）"""
        logger.info("生成美股早报...")
        try:
            us_data = _get_us_indices()
            us_news = _fetch_us_news()
            watchlist = _load_watchlist(US_WATCHLIST_FILE)
            wl_ctx = _build_watchlist_context(watchlist)
            date_str = datetime.now().strftime("%m/%d")

            system_prompt = "You are a professional US stock market analyst. Respond in Chinese."
            user_prompt = f"""请根据以下信息，生成今日美股财经早报（{date_str}），请用中文输出：

【昨日美股及亚太指数】
{us_data}

【今日英文财经新闻】（从中筛选3-5条最相关美股市场的）
{chr(10).join(f'- {n}' for n in us_news)}

【我的美股自选股】
{wl_ctx}

请按以下格式输出（300字以内）：

📊 昨日美股复盘
（三大指数表现，领涨/领跌板块，一句话总结）

📋 今日要闻
（3-4条精选新闻，中文翻译后输出，格式：• 内容）

⭐ 自选股关联
（如有新闻涉及自选股所在行业/业务，重点标注；无则写"暂无直接关联消息"）

💡 今晚关注
（一句话：今晚美股开盘值得关注的方向或事件）"""

            content = _ai_brief(system_prompt, user_prompt)
            if not content:
                return

            msg = (
                f"📰 美股早报  {date_str} 08:15\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"{content}"
            )
            notifier.us.send(msg)
            logger.info("美股早报推送完成")
        except Exception as e:
            logger.error(f"美股早报失败: {e}", exc_info=True)

    def push_evening(self):
        """美股晚报 20:15（距美股开盘约1-1.5小时）"""
        logger.info("生成美股晚报...")
        try:
            premarket = _get_us_premarket()
            us_news = _fetch_us_news()
            watchlist = _load_watchlist(US_WATCHLIST_FILE)
            wl_ctx = _build_watchlist_context(watchlist)
            date_str = datetime.now().strftime("%m/%d")

            system_prompt = "You are a professional US stock market analyst. Respond in Chinese."
            user_prompt = f"""请根据以下信息，生成今日美股财经晚报（{date_str}），请用中文输出：

【美股盘前数据】
{premarket}

【今日英文财经新闻】（从中筛选3-5条最相关美股市场的）
{chr(10).join(f'- {n}' for n in us_news)}

【我的美股自选股】
{wl_ctx}

请按以下格式输出（300字以内）：

📊 盘前动态
（盘前指数方向，主要驱动因素，一句话）

📋 今日要闻
（3-4条精选新闻，中文翻译后输出，格式：• 内容）

⭐ 自选股关联
（如有新闻涉及自选股所在行业/业务，重点标注；无则写"暂无直接关联消息"）

💡 今晚开盘策略
（一句话：今晚美股关注哪个板块或方向）"""

            content = _ai_brief(system_prompt, user_prompt)
            if not content:
                return

            msg = (
                f"📰 美股晚报  {date_str} 20:15\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"{content}"
            )
            notifier.us.send(msg)
            logger.info("美股晚报推送完成")
        except Exception as e:
            logger.error(f"美股晚报失败: {e}", exc_info=True)


a_news = AShareNewsEngine()
us_news = USNewsEngine()
