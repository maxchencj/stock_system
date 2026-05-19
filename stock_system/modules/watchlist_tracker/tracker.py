"""
自选股每日跟踪模块
交易日晚8:30推送每日行情+技术分析+AI研判
周末推送周度回顾
A股 → A股Bot | 美股 → mcDolphin Bot
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

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


# ─────────────────── 技术指标计算 ───────────────────

def _calc_indicators(df: pd.DataFrame) -> Optional[Dict]:
    """计算技术指标，返回最新一行的关键数值"""
    if df.empty or len(df) < 26:
        return None
    try:
        close = df["close"]

        # 均线
        ma5 = close.rolling(5).mean().iloc[-1]
        ma10 = close.rolling(10).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd_dif = round(dif.iloc[-1], 4)
        macd_dea = round(dea.iloc[-1], 4)
        macd_bar = round(2 * (dif.iloc[-1] - dea.iloc[-1]), 4)
        # 判断金叉死叉（最近两日DIF与DEA的相对位置变化）
        cross = ""
        if len(dif) >= 2:
            if dif.iloc[-2] < dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]:
                cross = "金叉"
            elif dif.iloc[-2] > dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]:
                cross = "死叉"

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=13, min_periods=14).mean()
        avg_loss = loss.ewm(com=13, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-10)
        rsi = round((100 - 100 / (1 + rs)).iloc[-1], 1)

        # 近期支撑/压力（20日最低/最高）
        support = round(df["low"].tail(20).min(), 2)
        resistance = round(df["high"].tail(20).max(), 2)

        current = round(close.iloc[-1], 2)
        ma_position = (
            "三线多头" if current > ma5 > ma10 > ma20
            else "三线空头" if current < ma5 < ma10 < ma20
            else "多空交织"
        )

        return {
            "ma5": round(ma5, 2), "ma10": round(ma10, 2), "ma20": round(ma20, 2),
            "ma_position": ma_position,
            "macd_dif": macd_dif, "macd_dea": macd_dea, "macd_bar": macd_bar,
            "macd_cross": cross,
            "rsi": rsi,
            "support": support, "resistance": resistance,
        }
    except Exception as e:
        logger.warning(f"技术指标计算失败: {e}")
        return None


# ─────────────────── AI 研判 ───────────────────

def _ai_analysis(name: str, code: str, quote: Dict, ind: Optional[Dict],
                 is_weekly: bool = False, weekly_data: str = "") -> str:
    system_prompt = "你是专业的股票分析师，擅长结合技术面和基本面给出简洁实用的投资建议。请用中文输出。"

    if is_weekly:
        user_prompt = f"""请对以下股票进行本周总结分析：

股票：{name}（{code}）
本周数据：
{weekly_data}

请按以下格式输出（300字以内）：

【本周回顾】价格走势、涨跌幅度、成交量变化（2-3句）

【技术面】当前趋势判断、关键指标状态（2-3句）

【下周展望】关键支撑/压力位、可能的走势方向（2-3句）

【持仓建议】持股/减仓/观望/关注买入 + 一句理由"""
    else:
        ind_text = ""
        if ind:
            ind_text = f"""
技术指标：
  均线：MA5={ind['ma5']}  MA10={ind['ma10']}  MA20={ind['ma20']}  ({ind['ma_position']})
  MACD：DIF={ind['macd_dif']}  DEA={ind['macd_dea']}  柱={ind['macd_bar']}  {ind['macd_cross']}
  RSI：{ind['rsi']}
  近期支撑：{ind['support']}  压力：{ind['resistance']}"""

        user_prompt = f"""请对以下股票进行今日跟踪分析：

股票：{name}（{code}）
今日行情：
  收盘价：{quote.get('price', 'N/A')}  涨跌幅：{quote.get('change_pct', 0):+.2f}%
  量比：{quote.get('volume_ratio', 0):.2f}  换手率：{quote.get('turnover_rate', 0):.2f}%
  最高：{quote.get('high', 'N/A')}  最低：{quote.get('low', 'N/A')}{ind_text}

请按以下格式输出（250字以内）：

【技术面】均线位置、MACD/RSI状态、趋势判断（2-3句）

【今日解读】今日量价关系、异动点评（1-2句）

【持仓建议】持股/减仓/观望/关注买入 + 一句核心理由

【明日关注】一个具体的关键价位或信号"""

    return ai_engine._call(system_prompt, user_prompt, max_tokens=600)


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

                hist = _get_history_baostock(code)
                ind = _calc_indicators(hist)

                analysis = _ai_analysis(name, code, quote, ind)

                change_icon = "🔴" if quote.get("change_pct", 0) > 0 else "🟢" if quote.get("change_pct", 0) < 0 else "⚪"
                sign = "+" if quote.get("change_pct", 0) > 0 else ""

                msg = (
                    f"📊 自选股跟踪  {name}（{code}）\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"{change_icon} 收盘 {quote.get('price', 'N/A')}  "
                    f"{sign}{quote.get('change_pct', 0):.2f}%  "
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
