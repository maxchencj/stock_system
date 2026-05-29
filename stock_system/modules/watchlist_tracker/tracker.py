"""
自选股每日跟踪模块
交易日晚8:30推送每日行情+技术分析+AI研判
周末推送周度回顾
A股 → A股Bot | 美股 → mcDolphin Bot
"""
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger

WATCHLIST_FILE = Path(__file__).parent.parent.parent / "data" / "watchlist.json"
US_WATCHLIST_FILE = Path(__file__).parent.parent.parent / "data" / "us_watchlist.json"


# ─────────────────── 工具函数 ───────────────────

def _is_weekend() -> bool:
    return datetime.now().weekday() >= 5


def _week_range() -> str:
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    return f"{monday.strftime('%m/%d')}—{friday.strftime('%m/%d')}"


def _load_watchlist(path: Path) -> Dict[str, str]:
    """读取自选股文件，返回 {code: name}"""
    try:
        with open(path) as f:
            data = json.load(f)
        return {code: info["name"] for code, info in data.get("stocks", {}).items()}
    except Exception as e:
        logger.warning(f"读取自选股文件失败 {path}: {e}")
        return {}


# ─────────────────── baostock 历史K线 ───────────────────

def _get_history_baostock(code: str, days: int = 90) -> pd.DataFrame:
    """通过 baostock 获取A股历史K线（前复权）"""
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != '0':
            logger.warning(f"baostock登录失败: {lg.error_msg}")
            return pd.DataFrame()

        bs_code = f"sh.{code}" if code.startswith("6") else f"sz.{code}"
        start = (datetime.now() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")

        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume",
            start_date=start, end_date=end,
            frequency="d", adjustflag="2"  # 前复权
        )
        rows = []
        while rs.error_code == '0' and rs.next():
            rows.append(rs.get_row_data())
        bs.logout()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        df = df[df["close"] != ""].copy()
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date").tail(days).reset_index(drop=True)

    except Exception as e:
        logger.warning(f"baostock获取{code}历史数据失败: {e}")
        return pd.DataFrame()


# ─────────────────── 消息面：公告 + 个股新闻 ───────────────────

def _fetch_stock_news(code: str, ts_code: str) -> str:
    """获取个股最近公告和新闻，返回格式化字符串"""
    items = []

    # 1. Tushare 公告（anns_d）
    try:
        import tushare as ts
        pro = ts.pro_api(os.getenv("TUSHARE_TOKEN", ""))
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
        anns = pro.anns_d(ts_code=ts_code, start_date=start, end_date=end,
                          fields="ann_date,title")
        if anns is not None and not anns.empty:
            for _, row in anns.head(4).iterrows():
                items.append(f"[公告 {row['ann_date']}] {row['title']}")
    except Exception as e:
        logger.debug(f"获取公告失败 {ts_code}: {e}")

    # 2. 东方财富 个股新闻
    try:
        url = (
            f"https://np-anotice-stock.eastmoney.com/api/security/ann"
            f"?sr=-1&page_size=5&page_index=1&ann_type=A"
            f"&client_source=web&stock_list={code}"
        )
        resp = requests.get(url, timeout=6,
                            headers={"User-Agent": "Mozilla/5.0"})
        data = resp.json().get("data", {}).get("list", [])
        for item in data[:3]:
            title = item.get("title", "")
            date  = item.get("notice_date", "")[:10]
            if title:
                items.append(f"[公告 {date}] {title}")
    except Exception:
        pass

    # 3. 新浪财经 个股新闻
    try:
        url = f"https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2513&k={code}&num=5&page=1"
        resp = requests.get(url, timeout=6,
                            headers={"User-Agent": "Mozilla/5.0"})
        news_list = resp.json().get("result", {}).get("data", [])
        for n in news_list[:3]:
            title = n.get("title", "")
            ctime = n.get("ctime", "")[:10]
            if title:
                items.append(f"[新闻 {ctime}] {title}")
    except Exception:
        pass

    if not items:
        return "暂无近期公告/新闻"

    # 去重
    seen, unique = set(), []
    for it in items:
        key = it[10:]  # 去掉日期前缀再去重
        if key not in seen:
            seen.add(key)
            unique.append(it)
    return "\n".join(unique[:6])


# ─────────────────── 技术指标计算 ───────────────────

def _calc_indicators(df: pd.DataFrame) -> Optional[Dict]:
    """计算多维技术指标（MA/MACD/RSI/KDJ/布林/量能）"""
    if df.empty or len(df) < 26:
        return None
    try:
        close  = df["close"].astype(float)
        high   = df["high"].astype(float)
        low    = df["low"].astype(float)
        volume = df["volume"].astype(float)
        n      = len(close)

        # ── 均线
        ma5  = close.rolling(5).mean().iloc[-1]
        ma10 = close.rolling(10).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1] if n >= 60 else None

        current = float(close.iloc[-1])
        ma_pos = (
            "三线多头" if current > ma5 > ma10 > ma20
            else "三线空头" if current < ma5 < ma10 < ma20
            else "多空交织"
        )

        # ── MACD (12,26,9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif   = ema12 - ema26
        dea   = dif.ewm(span=9, adjust=False).mean()
        bar   = 2 * (dif - dea)
        cross = ""
        if dif.iloc[-2] < dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]:
            cross = "金叉"
        elif dif.iloc[-2] > dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]:
            cross = "死叉"

        # ── RSI (14)
        delta    = close.diff()
        avg_gain = delta.where(delta > 0, 0.0).ewm(com=13, min_periods=14).mean()
        avg_loss = (-delta.where(delta < 0, 0.0)).ewm(com=13, min_periods=14).mean()
        rsi = round(float((100 - 100 / (1 + avg_gain / avg_loss.replace(0, 1e-10))).iloc[-1]), 1)

        # ── KDJ (9,3,3)
        low9  = low.rolling(9).min()
        high9 = high.rolling(9).max()
        rsv   = (close - low9) / (high9 - low9 + 1e-9) * 100
        k     = rsv.ewm(com=2, adjust=False).mean()
        d     = k.ewm(com=2, adjust=False).mean()
        j     = 3 * k - 2 * d
        kdj_k = round(float(k.iloc[-1]), 1)
        kdj_d = round(float(d.iloc[-1]), 1)
        kdj_j = round(float(j.iloc[-1]), 1)

        # ── 布林带 (20,2)
        bb_mid   = close.rolling(20).mean()
        bb_std   = close.rolling(20).std()
        bb_upper = float((bb_mid + 2 * bb_std).iloc[-1])
        bb_lower = float((bb_mid - 2 * bb_std).iloc[-1])
        bb_mid_v = float(bb_mid.iloc[-1])
        bb_pos   = (current - bb_lower) / (bb_upper - bb_lower + 1e-9)

        # ── 量能分析
        vol_ma5  = float(volume.rolling(5).mean().iloc[-1])
        vol_ma20 = float(volume.rolling(20).mean().iloc[-1])
        vol_ratio_5  = round(float(volume.iloc[-1]) / vol_ma5, 2)  if vol_ma5  > 0 else 1.0
        vol_ratio_20 = round(float(volume.iloc[-1]) / vol_ma20, 2) if vol_ma20 > 0 else 1.0
        vol_trend = (
            "放量" if vol_ratio_5 >= 1.5
            else "缩量" if vol_ratio_5 <= 0.7
            else "平量"
        )

        # ── 近期支撑/压力（20日区间）
        support    = round(float(low.tail(20).min()), 2)
        resistance = round(float(high.tail(20).max()), 2)

        return {
            "current": round(current, 2),
            "ma5":  round(ma5, 2), "ma10": round(ma10, 2),
            "ma20": round(ma20, 2),
            "ma60": round(ma60, 2) if ma60 else None,
            "ma_pos": ma_pos,
            "macd_dif": round(float(dif.iloc[-1]), 4),
            "macd_dea": round(float(dea.iloc[-1]), 4),
            "macd_bar": round(float(bar.iloc[-1]), 4),
            "macd_cross": cross,
            "rsi": rsi,
            "kdj_k": kdj_k, "kdj_d": kdj_d, "kdj_j": kdj_j,
            "bb_upper": round(bb_upper, 2),
            "bb_mid":   round(bb_mid_v, 2),
            "bb_lower": round(bb_lower, 2),
            "bb_pos":   round(bb_pos, 2),
            "vol_ratio_5": vol_ratio_5,
            "vol_ratio_20": vol_ratio_20,
            "vol_trend": vol_trend,
            "support": support, "resistance": resistance,
        }
    except Exception as e:
        logger.warning(f"技术指标计算失败: {e}")
        return None


# ─────────────────── K线形态描述 ───────────────────

def _describe_candles(df: pd.DataFrame, n: int = 5) -> str:
    """描述最近 n 根K线的形态特征"""
    if df.empty or len(df) < n:
        return "K线数据不足"
    try:
        recent = df.tail(n).reset_index(drop=True)
        lines = []
        for _, row in recent.iterrows():
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            body  = abs(c - o)
            total = h - l if h > l else 1e-9
            upper_shadow = h - max(o, c)
            lower_shadow = min(o, c) - l
            body_ratio   = body / total

            direction = "阳线" if c >= o else "阴线"
            if body_ratio < 0.1:
                shape = "十字星"
            elif body_ratio > 0.7:
                shape = f"实体{direction}"
            elif upper_shadow / total > 0.4:
                shape = "上影线长"
            elif lower_shadow / total > 0.4:
                shape = "下影线长（锤子）" if direction == "阳线" else "下影线长"
            else:
                shape = direction

            chg = (c - o) / o * 100
            date_str = str(row.get("date", ""))[:10]
            lines.append(f"{date_str}  {shape}  {chg:+.2f}%  高{h:.2f}/低{l:.2f}/收{c:.2f}")
        return "\n".join(lines)
    except Exception as e:
        return f"K线描述失败: {e}"


# ─────────────────── AI 全方位研判 ───────────────────

def _ai_analysis(name: str, code: str, quote: Dict, ind: Optional[Dict],
                 is_weekly: bool = False, weekly_data: str = "",
                 news_text: str = "", candle_text: str = "") -> str:
    system_prompt = (
        "你是资深A股研究员，擅长多维度综合分析：消息面解读、技术形态研判、"
        "K线过程解析、量价关系研究，并能给出可操作的具体建议。请用中文输出。"
    )

    if is_weekly:
        user_prompt = f"""请对以下股票进行本周总结分析：

股票：{name}（{code}）
本周数据：
{weekly_data}

请按以下格式输出（400字以内）：

【本周回顾】价格走势、涨跌幅度、成交量变化（2-3句）

【技术面】当前趋势判断、关键指标状态（2-3句）

【下周展望】关键支撑/压力位、可能的走势方向（2-3句）

【持仓建议】持股/减仓/观望/关注买入 + 一句理由"""

    else:
        ind_text = ""
        if ind:
            ma60_str = f"  MA60={ind['ma60']}" if ind.get("ma60") else ""
            ind_text = f"""
技术指标：
  均线：MA5={ind['ma5']}  MA10={ind['ma10']}  MA20={ind['ma20']}{ma60_str}  ({ind['ma_pos']})
  MACD：DIF={ind['macd_dif']}  DEA={ind['macd_dea']}  柱={ind['macd_bar']}  {ind['macd_cross'] or '无金死叉'}
  RSI(14)：{ind['rsi']}
  KDJ：K={ind['kdj_k']}  D={ind['kdj_d']}  J={ind['kdj_j']}
  布林带：上轨{ind['bb_upper']}  中轨{ind['bb_mid']}  下轨{ind['bb_lower']}  位置{ind['bb_pos']:.0%}
  量能：相对5日均量×{ind['vol_ratio_5']}（{ind['vol_trend']}）  相对20日均量×{ind['vol_ratio_20']}
  支撑区：{ind['support']}  压力区：{ind['resistance']}"""

        user_prompt = f"""请对以下股票进行今日全方位跟踪分析：

股票：{name}（{code}）

今日行情：
  收盘价：{quote.get('price', 'N/A')}  涨跌幅：{quote.get('change_pct', 0):+.2f}%
  最高：{quote.get('high', 'N/A')}  最低：{quote.get('low', 'N/A')}  开盘：{quote.get('open', 'N/A')}
  量比：{quote.get('volume_ratio', 0):.2f}  换手率：{quote.get('turnover_rate', 0):.2f}%
{ind_text}

近期K线（最近5日）：
{candle_text}

近期消息/公告：
{news_text}

请严格按以下格式输出，每段2-3句，总计500字以内：

【消息面】解读近期公告/新闻对股价的影响，无消息则说明基本面背景

【K线过程】描述近5日K线走势节奏、量价配合、今日K线形态含义

【技术面】均线多空判断、MACD/KDJ/RSI/布林带综合研判，当前处于什么阶段

【涨跌原因】结合消息面和技术面，分析今日涨跌的核心驱动

【持仓建议】明确给出 持有/减仓/观望/买入 + 核心逻辑（一句话）

【明日关注】给出2个具体价位：关键支撑位 和 突破确认位"""

    return ai_engine._call(system_prompt, user_prompt, max_tokens=900)


# ═══════════════════════════════════════════════════════
#  A股自选股跟踪
# ═══════════════════════════════════════════════════════

class AShareWatchlistTracker:

    def run(self):
        stocks = _load_watchlist(WATCHLIST_FILE)
        if not stocks:
            logger.info("A股自选股列表为空，跳过跟踪")
            return

        if _is_weekend():
            self._push_weekly_review(stocks)
        else:
            self._push_daily(stocks)

    def _push_daily(self, stocks: Dict[str, str]):
        logger.info(f"开始A股自选股每日跟踪，共{len(stocks)}只")
        from data.data_service import market_service

        codes = list(stocks.keys())
        quotes_df = market_service.get_realtime_quotes(codes)

        for code, name in stocks.items():
            try:
                row = quotes_df[quotes_df["code"] == code]
                if row.empty:
                    logger.warning(f"{name}({code}) 未获取到行情")
                    continue
                quote = row.iloc[0].to_dict()

                # ts_code 格式 (603993 → 603993.SH)
                ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"

                hist         = _get_history_baostock(code)
                ind          = _calc_indicators(hist)
                candle_text  = _describe_candles(hist)
                news_text    = _fetch_stock_news(code, ts_code)

                analysis = _ai_analysis(
                    name, code, quote, ind,
                    news_text=news_text, candle_text=candle_text
                )

                chg  = quote.get("change_pct", 0)
                icon = "🔴" if chg > 0 else "🟢" if chg < 0 else "⚪"
                sign = "+" if chg > 0 else ""

                msg = (
                    f"📊 自选股跟踪  {name}（{code}）\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"{icon} 收盘 {quote.get('price', 'N/A')}  "
                    f"{sign}{chg:.2f}%  "
                    f"量比 {quote.get('volume_ratio', 0):.2f}  "
                    f"换手 {quote.get('turnover_rate', 0):.2f}%\n\n"
                    f"{analysis}"
                )
                notifier.telegram.send(msg)
                logger.info(f"已推送A股跟踪: {name}({code})")
                time.sleep(3)

            except Exception as e:
                logger.error(f"A股{name}({code})跟踪失败: {e}", exc_info=True)

    def _push_weekly_review(self, stocks: Dict[str, str]):
        logger.info(f"开始A股自选股周度回顾，共{len(stocks)}只")
        from data.data_service import market_service

        codes = list(stocks.keys())
        quotes_df = market_service.get_realtime_quotes(codes)

        for code, name in stocks.items():
            try:
                hist = _get_history_baostock(code, days=10)
                if hist.empty:
                    continue

                week_high = round(hist["high"].max(), 2)
                week_low = round(hist["low"].min(), 2)
                week_open = round(hist["open"].iloc[0], 2)
                week_close = round(hist["close"].iloc[-1], 2)
                week_chg = round((week_close - week_open) / week_open * 100, 2)
                sign = "+" if week_chg > 0 else ""

                ind = _calc_indicators(_get_history_baostock(code))

                weekly_summary = (
                    f"周期间：{_week_range()}\n"
                    f"周开盘：{week_open}  周收盘：{week_close}\n"
                    f"周涨跌：{sign}{week_chg}%  周高：{week_high}  周低：{week_low}"
                )
                if ind:
                    weekly_summary += (
                        f"\nMA5={ind['ma5']} MA10={ind['ma10']} MA20={ind['ma20']} ({ind['ma_position']})"
                        f"\nRSI={ind['rsi']}  MACD={ind['macd_dif']}/{ind['macd_dea']}"
                    )

                analysis = _ai_analysis(name, code, {}, ind, is_weekly=True, weekly_data=weekly_summary)

                icon = "🔴" if week_chg > 0 else "🟢" if week_chg < 0 else "⚪"
                msg = (
                    f"📊 周度回顾  {name}（{code}）\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"{icon} 本周{sign}{week_chg}%  "
                    f"高{week_high} / 低{week_low}\n\n"
                    f"{analysis}"
                )
                notifier.telegram.send(msg)
                logger.info(f"已推送A股周报: {name}({code})")
                time.sleep(3)

            except Exception as e:
                logger.error(f"A股{name}({code})周报失败: {e}", exc_info=True)


# ═══════════════════════════════════════════════════════
#  美股自选股跟踪
# ═══════════════════════════════════════════════════════

class USWatchlistTracker:

    def run(self):
        stocks = _load_watchlist(US_WATCHLIST_FILE)
        if not stocks:
            logger.info("美股自选股列表为空，跳过跟踪")
            return

        if _is_weekend():
            self._push_weekly_review(stocks)
        else:
            self._push_daily(stocks)

    def _get_yf_data(self, symbol: str) -> tuple[Dict, pd.DataFrame]:
        """获取美股行情和历史数据"""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="3mo")
            if hist.empty:
                return {}, pd.DataFrame()

            hist = hist.reset_index()
            hist.columns = [c.lower() for c in hist.columns]
            hist = hist.rename(columns={"stock splits": "splits"})

            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else latest
            price = round(float(latest["close"]), 2)
            prev_close = round(float(prev["close"]), 2)
            change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
            volume = int(latest["volume"])
            avg_volume = int(hist["volume"].tail(20).mean())
            volume_ratio = round(volume / avg_volume, 2) if avg_volume else 0

            quote = {
                "price": price,
                "change_pct": change_pct,
                "high": round(float(latest["high"]), 2),
                "low": round(float(latest["low"]), 2),
                "volume": volume,
                "volume_ratio": volume_ratio,
                "turnover_rate": 0,
            }
            return quote, hist[["date", "open", "high", "low", "close", "volume"]]

        except Exception as e:
            logger.warning(f"yfinance获取{symbol}失败: {e}")
            return {}, pd.DataFrame()

    def _push_daily(self, stocks: Dict[str, str]):
        logger.info(f"开始美股自选股每日跟踪，共{len(stocks)}只")

        for symbol, name in stocks.items():
            try:
                quote, hist = self._get_yf_data(symbol)
                if not quote:
                    logger.warning(f"{symbol} 未获取到行情")
                    continue

                ind = _calc_indicators(hist)
                analysis = _ai_analysis(name, symbol, quote, ind)

                change_icon = "🔴" if quote.get("change_pct", 0) > 0 else "🟢" if quote.get("change_pct", 0) < 0 else "⚪"
                sign = "+" if quote.get("change_pct", 0) > 0 else ""

                msg = (
                    f"📊 自选股跟踪  {name}（{symbol}）\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"{change_icon} 收盘 ${quote.get('price', 'N/A')}  "
                    f"{sign}{quote.get('change_pct', 0):.2f}%  "
                    f"量比 {quote.get('volume_ratio', 0):.2f}\n\n"
                    f"{analysis}"
                )
                notifier.us.send(msg)
                logger.info(f"已推送美股跟踪: {symbol}")
                time.sleep(3)

            except Exception as e:
                logger.error(f"美股{symbol}跟踪失败: {e}", exc_info=True)

    def _push_weekly_review(self, stocks: Dict[str, str]):
        logger.info(f"开始美股自选股周度回顾，共{len(stocks)}只")

        for symbol, name in stocks.items():
            try:
                _, hist = self._get_yf_data(symbol)
                if hist.empty:
                    continue

                week_data = hist.tail(7)
                week_open = round(float(week_data["open"].iloc[0]), 2)
                week_close = round(float(week_data["close"].iloc[-1]), 2)
                week_high = round(float(week_data["high"].max()), 2)
                week_low = round(float(week_data["low"].min()), 2)
                week_chg = round((week_close - week_open) / week_open * 100, 2) if week_open else 0
                sign = "+" if week_chg > 0 else ""

                ind = _calc_indicators(hist)

                weekly_summary = (
                    f"周期间：{_week_range()}\n"
                    f"周开盘：${week_open}  周收盘：${week_close}\n"
                    f"周涨跌：{sign}{week_chg}%  周高：${week_high}  周低：${week_low}"
                )
                if ind:
                    weekly_summary += (
                        f"\nMA5={ind['ma5']} MA10={ind['ma10']} MA20={ind['ma20']} ({ind['ma_position']})"
                        f"\nRSI={ind['rsi']}  MACD={ind['macd_dif']}/{ind['macd_dea']}"
                    )

                analysis = _ai_analysis(name, symbol, {}, ind, is_weekly=True, weekly_data=weekly_summary)

                icon = "🔴" if week_chg > 0 else "🟢" if week_chg < 0 else "⚪"
                msg = (
                    f"📊 周度回顾  {name}（{symbol}）\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"{icon} 本周{sign}{week_chg}%  "
                    f"高${week_high} / 低${week_low}\n\n"
                    f"{analysis}"
                )
                notifier.us.send(msg)
                logger.info(f"已推送美股周报: {symbol}")
                time.sleep(3)

            except Exception as e:
                logger.error(f"美股{symbol}周报失败: {e}", exc_info=True)


a_tracker = AShareWatchlistTracker()
us_tracker = USWatchlistTracker()
