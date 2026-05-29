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


# 无关内容过滤关键词
_NOISE_KEYWORDS = [
    "广告", "招聘", "培训", "理财产品", "开户", "佣金", "手续费",
    "配资", "炒股软件", "股票推荐群", "微信扫码", "公众号",
    "点击查看", "更多详情", "阅读全文", "查看更多",
    "娱乐", "明星", "综艺", "体育", "足球", "篮球",
]

# 高价值财经关键词（至少含其一才保留）
_FINANCE_KEYWORDS = [
    "股市", "A股", "港股", "美股", "纳斯达克", "上证", "深证", "创业板",
    "央行", "美联储", "政策", "货币", "利率", "通胀", "CPI", "PPI", "GDP",
    "财报", "业绩", "净利润", "营收", "分红", "回购", "增持", "减持",
    "板块", "行业", "资金", "北向", "外资", "融资", "并购",
    "IPO", "新股", "科技", "新能源", "半导体", "医药", "消费",
    "原油", "黄金", "大宗", "汇率", "人民币", "美元",
]


def _is_quality_news(title: str, intro: str = "") -> bool:
    """过滤无关新闻，保留高价值财经内容"""
    text = title + intro
    # 含噪声词直接过滤
    if any(kw in text for kw in _NOISE_KEYWORDS):
        return False
    # 标题太短过滤
    if len(title) < 8:
        return False
    # 含财经关键词保留，否则也保留（不过于激进）
    return True


# ─────────────────── 新闻抓取 ───────────────────

def _fetch_cn_news(max_items: int = 20) -> List[str]:
    """抓取中文财经新闻（新浪财经双源 + 质量过滤）"""
    items = []

    # 源1：新浪财经 A股新闻 JSON API
    try:
        r = requests.get(
            "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=30&page=1",
            headers=_HEADERS, timeout=10
        )
        data = r.json().get("result", {}).get("data", [])
        for item in data:
            title = item.get("title", "").strip()
            intro = _clean_html(item.get("intro", ""))[:120]
            if title and _is_quality_news(title, intro):
                items.append(f"{title}{'：' + intro if intro else ''}")
    except Exception as e:
        logger.warning(f"新浪A股新闻抓取失败: {e}")

    # 源2：新浪财经 RSS（补充财经要闻）
    if len(items) < 10:
        try:
            import feedparser
            feed = feedparser.parse("http://rss.sina.com.cn/news/china/focus15.xml")
            existing_titles = {i.split("：")[0] for i in items}
            for entry in feed.entries[:15]:
                title = entry.get("title", "").strip()
                if title and title not in existing_titles and _is_quality_news(title):
                    items.append(title)
        except Exception as e:
            logger.warning(f"新浪RSS抓取失败: {e}")

    logger.info(f"获取中文财经新闻 {len(items)} 条（已过滤噪声）")
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

def _get_overnight_market() -> str:
    """
    获取隔夜全市场数据：
      - 美股三大指数 + VIX
      - 亚太（日经、恒生、韩综）
      - 大宗商品（WTI原油、黄金、铜）
      - 美元指数 / 离岸人民币
    返回带具体点位和涨跌幅的格式化字符串。
    """
    try:
        import yfinance as yf

        groups = {
            "美股": [
                ("^GSPC",  "标普500"),
                ("^IXIC",  "纳斯达克"),
                ("^DJI",   "道琼斯"),
                ("^VIX",   "VIX恐慌指数"),
            ],
            "亚太": [
                ("^N225",  "日经225"),
                ("^HSI",   "恒生指数"),
                ("^KS11",  "韩国综合"),
            ],
            "大宗商品": [
                ("CL=F",   "WTI原油($/桶)"),
                ("GC=F",   "黄金($/盎司)"),
                ("HG=F",   "铜($/磅)"),
            ],
            "外汇": [
                ("DX-Y.NYB", "美元指数"),
                ("CNH=X",    "离岸人民币"),
            ],
        }

        lines = []
        for group, symbols in groups.items():
            group_lines = []
            for sym, name in symbols:
                try:
                    hist = yf.Ticker(sym).history(period="2d")
                    if len(hist) < 2:
                        continue
                    prev = float(hist["Close"].iloc[-2])
                    last = float(hist["Close"].iloc[-1])
                    chg  = round((last - prev) / prev * 100, 2)
                    sign = "+" if chg >= 0 else ""
                    arrow = "↑" if chg > 0 else ("↓" if chg < 0 else "→")
                    import math
                    if math.isnan(last) or math.isnan(chg):
                        continue
                    group_lines.append(
                        f"  {name} {last:.2f}  {arrow}{sign}{chg}%"
                    )
                except Exception:
                    pass
            if group_lines:
                lines.append(f"[{group}]")
                lines.extend(group_lines)

        return "\n".join(lines) if lines else "  数据获取失败"
    except Exception as e:
        logger.warning(f"获取隔夜市场数据失败: {e}")
        return "  数据获取失败"


def _get_us_indices() -> str:
    """兼容旧调用，委托给新函数"""
    return _get_overnight_market()


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
    return ai_engine._call(system_prompt, user_prompt, max_tokens=2500)


def _build_watchlist_context(watchlist: Dict[str, str]) -> str:
    if not watchlist:
        return "暂无自选股"
    return "、".join([f"{name}({code})" for code, name in watchlist.items()])


# ═══════════════════════════════════════════════════════
#  A股新闻引擎
# ═══════════════════════════════════════════════════════

class AShareNewsEngine:

    def push_morning(self):
        """A股综合早报 8:00 — 隔夜全市场 + 精选要闻 + 自选股关联 + 三指数开盘研判"""
        logger.info("生成A股综合早报...")
        try:
            overnight = _get_overnight_market()
            cn_news   = _fetch_cn_news(max_items=30)
            watchlist = _load_watchlist(WATCHLIST_FILE)
            date_str  = datetime.now().strftime("%Y-%m-%d")

            wl_lines = [f"{name}（{code}）" for code, name in watchlist.items()]
            wl_section = (
                "\n【自选股列表】\n" + "、".join(wl_lines)
                if wl_lines else ""
            )

            news_block = "\n".join(f"- {n}" for n in cn_news)

            system_prompt = (
                "你是资深A股策略研究员。所有判断必须来自提供的实际数据，"
                "禁止添加数据中不存在的事实或无依据的主观猜测。"
                "风格：专业、精准、有逻辑链条，避免套话。"
            )
            user_prompt = f"""根据以下真实数据，生成今日A股综合早报（{date_str}）：

【隔夜全市场数据（含具体点位和涨跌幅）】
{overnight}

【候选财经新闻（待筛选，原始条目）】
{news_block}
{wl_section}

━━ 输出格式要求（严格遵守，尽量详尽，不设字数上限）━━

▍隔夜市场
逐一列出美股三大指数、VIX、亚太指数、大宗商品（原油/黄金/铜）、美元指数的具体收盘点位和涨跌幅。
提炼隔夜 2-3 个核心驱动因素（需引用具体数据支撑）。
最后一句说明外盘整体对今日A股开盘情绪的传导方向（偏多/偏空/分化）。

▍精选要闻（严格筛选，8-10 条，越充分越好）
保留标准：政策法规落地、宏观数据发布（PMI/CPI/利率等）、产业链重大事件、龙头公司业绩/公告、重要机构观点。
删除：情绪性标题、无量化依据的预测、娱乐财经、与A股板块无直接关联的境外事件。
每条格式（编号 + 标签换行 + 内容，条目之间空一行）：
① 板块标签
具体事实 + 对A股相关板块的影响逻辑（40字以内）

② 板块标签
具体事实 + 对A股相关板块的影响逻辑（40字以内）
……以此类推

▍自选股关联（仅当要闻与自选股所属行业/产业链有直接关联时输出，否则省略整段）
写明：哪条新闻 → 影响哪个业务环节 → 对股价的预判方向，尽量具体。

▍开盘研判
分三个指数各一行，每行引用上方具体数字或事件作为依据：
上证指数：[偏多/偏空/震荡]——[具体依据]
深证成指：[偏多/偏空/震荡]——[具体依据]
创业板指：[偏多/偏空/震荡]——[具体依据]"""

            content = _ai_brief(system_prompt, user_prompt)
            if not content:
                return

            msg = (
                f"📰 A股早报  {date_str}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"{content}"
            )
            notifier.telegram.send(msg)
            logger.info("A股综合早报推送完成")
        except Exception as e:
            logger.error(f"A股综合早报失败: {e}", exc_info=True)

    def push_evening(self):
        """已合并至早报，保留此方法供历史调用兼容，不再执行任何操作。"""
        logger.info("晚报已合并至早报，跳过")


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
