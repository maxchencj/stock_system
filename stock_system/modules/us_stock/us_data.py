"""
美股数据服务 - 基于 yfinance
"""
import json
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from utils.logger import logger

INDICES = {
    "S&P 500": "^GSPC",
    "纳斯达克": "^IXIC",
    "道琼斯": "^DJI",
    "恐慌指数VIX": "^VIX",
}

# 热门美股筛选池
US_STOCK_POOL = [
    # 科技
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "NFLX", "AMD", "INTC",
    "ORCL", "CRM", "ADBE", "QCOM", "AVGO", "MU", "AMAT", "PLTR", "SNOW", "ARM",
    # 金融
    "JPM", "BAC", "GS", "MS", "V", "MA", "PYPL", "COIN",
    # 医疗
    "JNJ", "UNH", "PFE", "LLY", "AMGN", "MRNA",
    # 消费
    "WMT", "COST", "HD", "MCD", "SBUX", "NKE",
    # 能源/工业
    "XOM", "CVX", "BA", "CAT", "GE",
    # 中概股
    "BABA", "PDD", "JD", "BIDU", "NIO", "XPEV", "LI", "FUTU",
]

WATCHLIST_PATH = "data/us_watchlist.json"


def load_us_watchlist() -> List[str]:
    """加载美股自选股列表"""
    try:
        with open(WATCHLIST_PATH) as f:
            data = json.load(f)
        return list(data.get("stocks", {}).keys())
    except Exception as e:
        logger.warning(f"加载美股自选股失败: {e}")
        return []


def get_quotes(symbols: List[str]) -> pd.DataFrame:
    """批量获取实时行情"""
    if not symbols:
        return pd.DataFrame()
    try:
        tickers = yf.Tickers(" ".join(symbols))
        rows = []
        for sym in symbols:
            try:
                t = tickers.tickers[sym]
                fi = t.fast_info
                prev_close = fi.previous_close or 0
                price = fi.last_price or 0
                change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0
                rows.append({
                    "symbol": sym,
                    "price": round(price, 2),
                    "prev_close": round(prev_close, 2),
                    "change_pct": round(change_pct, 2),
                    "high": round(fi.day_high or 0, 2),
                    "low": round(fi.day_low or 0, 2),
                    "volume": int(fi.three_month_average_volume or 0),
                    "market_cap": fi.market_cap or 0,
                })
            except Exception:
                continue
        return pd.DataFrame(rows)
    except Exception as e:
        logger.error(f"获取美股行情失败: {e}")
        return pd.DataFrame()


def get_market_indices() -> Dict:
    """获取主要指数数据"""
    result = {}
    for name, symbol in INDICES.items():
        try:
            t = yf.Ticker(symbol)
            fi = t.fast_info
            prev = fi.previous_close or 0
            price = fi.last_price or 0
            change_pct = ((price - prev) / prev * 100) if prev else 0
            result[name] = {
                "symbol": symbol,
                "price": round(price, 2),
                "change_pct": round(change_pct, 2),
                "prev_close": round(prev, 2),
            }
        except Exception as e:
            logger.warning(f"获取指数 {name} 失败: {e}")
    return result


def get_top_movers(pool: List[str] = None, top_n: int = 10) -> Dict:
    """从股票池中获取涨跌幅最大的股票"""
    pool = pool or US_STOCK_POOL
    df = get_quotes(pool)
    if df.empty:
        return {"gainers": [], "losers": []}
    df = df[df["price"] > 0]
    gainers = df.nlargest(top_n, "change_pct").to_dict("records")
    losers = df.nsmallest(top_n, "change_pct").to_dict("records")
    return {"gainers": gainers, "losers": losers}


def get_premarket_movers(pool: List[str] = None) -> List[Dict]:
    """获取盘前异动股票（涨跌幅超过2%）"""
    pool = pool or US_STOCK_POOL[:30]
    movers = []
    for sym in pool:
        try:
            info = yf.Ticker(sym).info
            pre_price = info.get("preMarketPrice") or 0
            prev_close = info.get("previousClose") or 0
            if pre_price and prev_close:
                change_pct = (pre_price - prev_close) / prev_close * 100
                if abs(change_pct) >= 2.0:
                    movers.append({
                        "symbol": sym,
                        "name": info.get("shortName", sym),
                        "pre_price": round(pre_price, 2),
                        "prev_close": round(prev_close, 2),
                        "change_pct": round(change_pct, 2),
                    })
        except Exception:
            continue
    return sorted(movers, key=lambda x: abs(x["change_pct"]), reverse=True)


def get_earnings_calendar(symbols: List[str]) -> List[Dict]:
    """获取股票财报日期（未来30天内）"""
    upcoming = []
    today = datetime.now().date()
    deadline = today + timedelta(days=30)
    for sym in symbols:
        try:
            cal = yf.Ticker(sym).calendar
            if cal is None:
                continue
            # calendar 可能是 dict 或 DataFrame
            if isinstance(cal, dict):
                earnings_date = cal.get("Earnings Date")
                if earnings_date:
                    if hasattr(earnings_date, '__iter__') and not isinstance(earnings_date, str):
                        earnings_date = list(earnings_date)[0]
                    ed = pd.Timestamp(earnings_date).date()
                    if today <= ed <= deadline:
                        upcoming.append({"symbol": sym, "earnings_date": str(ed)})
            elif isinstance(cal, pd.DataFrame) and not cal.empty:
                for col in ["Earnings Date", "earnings_date"]:
                    if col in cal.columns:
                        ed = pd.Timestamp(cal[col].iloc[0]).date()
                        if today <= ed <= deadline:
                            upcoming.append({"symbol": sym, "earnings_date": str(ed)})
                        break
        except Exception:
            continue
    return sorted(upcoming, key=lambda x: x["earnings_date"])
