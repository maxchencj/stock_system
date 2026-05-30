import pandas as pd
import numpy as np
from modules.sim_trading.strategy.signals import generate_signal


def _df_from_closes(closes):
    n = len(closes)
    return pd.DataFrame({
        "date": [f"2026-01-{i+1:02d}" for i in range(n)],
        "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes,
        "volume": [1000] * n,
    })


def test_uptrend_triggers_buy():
    # 先跌后稳步上涨 → 触发 MACD 金叉 + 均线多头
    closes = ([12 - i * 0.15 for i in range(35)]      # 持续下跌压低DIF
              + [6 + i * 0.05 for i in range(34)]      # 缓涨使DIF接近DEA
              + [6 + 34 * 0.05 + 1.5])                 # 末根跳涨触发金叉
    sig = generate_signal("603993", "测试股", _df_from_closes(closes))
    assert sig["action"] == "buy"
    assert len(sig["reasons"]) >= 2  # 双指标共振
    assert sig["price"] == closes[-1]


def test_downtrend_triggers_sell():
    # 先涨后持续下跌 → MACD 死叉 + 跌破均线
    closes = ([6 + i * 0.15 for i in range(35)]       # 持续上涨抬高DIF
              + [12 - i * 0.05 for i in range(34)]     # 缓跌使DIF接近DEA
              + [12 - 34 * 0.05 - 1.5])                # 末根跳跌触发死叉
    sig = generate_signal("603993", "测试股", _df_from_closes(closes))
    assert sig["action"] == "sell"
    assert len(sig["reasons"]) >= 2


def test_choppy_returns_hold():
    # 横盘震荡，无共振 → hold
    closes = [10 + (0.1 if i % 2 == 0 else -0.1) for i in range(70)]
    sig = generate_signal("603993", "测试股", _df_from_closes(closes))
    assert sig["action"] == "hold"


def test_insufficient_data_returns_hold():
    sig = generate_signal("603993", "测试股", _df_from_closes([10, 11, 12]))
    assert sig["action"] == "hold"
