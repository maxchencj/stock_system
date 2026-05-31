"""
模拟仓策略信号（Phase 1）：MACD 金叉/死叉 + 均线突破，双指标共振才触发。
纯函数：输入日K DataFrame，输出信号字典。
"""
from typing import Dict, List
import pandas as pd


def _macd(close: pd.Series, fast=12, slow=26, signal=9):
    exp1 = close.ewm(span=fast, adjust=False).mean()
    exp2 = close.ewm(span=slow, adjust=False).mean()
    dif = exp1 - exp2
    dea = dif.ewm(span=signal, adjust=False).mean()
    return dif, dea


def _macd_cross(close: pd.Series) -> str:
    """返回 'golden' | 'death' | ''（看最后两根 DIF-DEA 关系变化）"""
    dif, dea = _macd(close)
    if len(dif) < 2:
        return ""
    prev = dif.iloc[-2] - dea.iloc[-2]
    cur = dif.iloc[-1] - dea.iloc[-1]
    if prev <= 0 < cur:
        return "golden"
    if prev >= 0 > cur:
        return "death"
    return ""


def _ma_state(close: pd.Series) -> str:
    """均线状态：'bull'（价>MA20且MA20>MA60）| 'bear'（价<MA20或MA20<MA60）| ''"""
    if len(close) < 60:
        return ""
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1]
    price = close.iloc[-1]
    if price > ma20 and ma20 > ma60:
        return "bull"
    if price < ma20 or ma20 < ma60:
        return "bear"
    return ""


def generate_signal(code: str, name: str, df: pd.DataFrame) -> Dict:
    """生成共振信号。数据不足或无共振返回 action='hold'。"""
    base = {"code": code, "name": name, "action": "hold", "reasons": [],
            "price": float(df["close"].iloc[-1]) if len(df) else 0.0}
    if df is None or len(df) < 120:
        return base

    close = df["close"].astype(float)
    cross = _macd_cross(close)
    ma = _ma_state(close)
    reasons: List[str] = []

    # 买入共振：MACD金叉 + 均线多头
    if cross == "golden" and ma == "bull":
        reasons = ["MACD金叉", "均线多头排列"]
        base["action"] = "buy"
    # 卖出共振：MACD死叉 + 均线空头
    elif cross == "death" and ma == "bear":
        reasons = ["MACD死叉", "跌破均线"]
        base["action"] = "sell"

    base["reasons"] = reasons
    base["price"] = float(close.iloc[-1])
    return base
