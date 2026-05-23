"""
因子计算层 - 多因子打分
支持：动量因子 / 质量因子 / 技术因子
数据来源：baostock（历史K线 + 财务季报）
"""
from datetime import datetime, timedelta
from typing import Dict, Optional
import pandas as pd

from utils.logger import logger


def _bs_login():
    import baostock as bs
    bs.login()
    return bs


def _to_bs_code(code: str) -> str:
    return f"sh.{code}" if code.startswith("6") else f"sz.{code}"


# ─────────────────── 价格历史 ───────────────────

def get_price_history(code: str, days: int = 130) -> Optional[pd.DataFrame]:
    """获取历史日K（收盘价/换手率），返回 DataFrame(date, close, turn)"""
    try:
        import baostock as bs
        bs.login()
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days + 50)).strftime("%Y-%m-%d")
        rs = bs.query_history_k_data_plus(
            _to_bs_code(code),
            "date,close,turn,volume",
            start_date=start, end_date=end,
            frequency="d", adjustflag="3"
        )
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
        bs.logout()
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["date", "close", "turn", "volume"])
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["turn"] = pd.to_numeric(df["turn"], errors="coerce")
        df = df.dropna(subset=["close"]).tail(days)
        return df.reset_index(drop=True)
    except Exception as e:
        logger.debug(f"获取价格历史失败({code}): {e}")
        return None


# ─────────────────── 动量因子 ───────────────────

def calc_momentum(df: pd.DataFrame) -> Dict:
    """计算多周期动量因子"""
    if df is None or len(df) < 21:
        return {}
    closes = df["close"].values
    result = {}
    for period, key in [(20, "mom20"), (60, "mom60"), (120, "mom120")]:
        if len(closes) >= period + 1:
            ret = (closes[-1] / closes[-period - 1] - 1) * 100
            result[key] = round(ret, 3)
    return result


# ─────────────────── 技术因子 ───────────────────

def calc_technical(df: pd.DataFrame) -> Dict:
    """计算技术因子：均线方向 / 换手率均值"""
    if df is None or len(df) < 21:
        return {}
    closes = df["close"].values
    result = {}

    # MA方向得分：价格在MA上方 = 正分
    for period in [20, 60]:
        if len(closes) >= period:
            ma = closes[-period:].mean()
            result[f"above_ma{period}"] = 1.0 if closes[-1] > ma else -1.0

    # 均线多头排列（MA20 > MA60）
    if len(closes) >= 60:
        ma20 = closes[-20:].mean()
        ma60 = closes[-60:].mean()
        result["ma_bullish"] = 1.0 if ma20 > ma60 else -1.0

    # 20日平均换手率（流动性 + 活跃度）
    if "turn" in df.columns:
        turn_series = df["turn"].dropna().values
        if len(turn_series) >= 10:
            result["avg_turn20"] = round(float(turn_series[-20:].mean()), 3)

    return result


# ─────────────────── 质量因子 ───────────────────

def calc_quality(code: str) -> Dict:
    """从 baostock 获取最新季度财务因子（ROE/净利率/增速/负债率）"""
    try:
        import baostock as bs
        bs.login()
        bs_code = _to_bs_code(code)

        year = datetime.now().year
        month = datetime.now().month
        # 使用上一季度（保守，避免未公布数据）
        quarter = (month - 1) // 3
        if quarter == 0:
            quarter = 4
            year -= 1

        result = {}

        # 利润指标
        rs = bs.query_profit_data(code=bs_code, year=year, quarter=quarter)
        if rs.error_code == "0":
            row = rs.get_row_data()
            if row:
                d = dict(zip(rs.fields, row))
                result["roe"] = float(d.get("roeAvg") or 0)
                result["net_margin"] = float(d.get("npMargin") or 0)

        # 成长指标
        rs2 = bs.query_growth_data(code=bs_code, year=year, quarter=quarter)
        if rs2.error_code == "0":
            row2 = rs2.get_row_data()
            if row2:
                d2 = dict(zip(rs2.fields, row2))
                result["yoy_profit"] = float(d2.get("YOYNI") or 0)

        # 资产负债
        rs3 = bs.query_balance_data(code=bs_code, year=year, quarter=quarter)
        if rs3.error_code == "0":
            row3 = rs3.get_row_data()
            if row3:
                d3 = dict(zip(rs3.fields, row3))
                result["debt_ratio"] = float(d3.get("liabilityToAsset") or 0)

        bs.logout()
        return result
    except Exception as e:
        logger.debug(f"质量因子获取失败({code}): {e}")
        return {}


# ─────────────────── 综合因子打分 ───────────────────

def score_stock(code: str) -> Optional[Dict]:
    """
    计算单只股票的原始因子值（不含标准化）
    返回 dict 供 screener 做截面标准化
    """
    df = get_price_history(code, days=130)
    mom = calc_momentum(df)
    tech = calc_technical(df)
    qual = calc_quality(code)

    # 如果关键数据缺失，直接跳过
    if not mom.get("mom20") and not qual.get("roe"):
        return None

    return {
        "code": code,
        # 动量
        "mom20": mom.get("mom20", 0),
        "mom60": mom.get("mom60", 0),
        "mom120": mom.get("mom120", 0),
        # 技术
        "above_ma20": tech.get("above_ma20", 0),
        "ma_bullish": tech.get("ma_bullish", 0),
        "avg_turn20": tech.get("avg_turn20", 1.0),
        # 质量
        "roe": qual.get("roe", 0),
        "net_margin": qual.get("net_margin", 0),
        "yoy_profit": qual.get("yoy_profit", 0),
        "debt_ratio": qual.get("debt_ratio", 0.5),  # 低负债率更好（后续取反）
    }
