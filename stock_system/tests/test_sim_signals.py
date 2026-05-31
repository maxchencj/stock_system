import pandas as pd
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
    # 69根价格极低(≈1) → EMA12≈EMA26≈1,DIF≈DEA≈0
    # 最后一根暴涨到100 → EMA12跳升远快于EMA26 → DIF从≈0一跃为正(金叉)
    # MA: 最后一根100 >> MA20(≈5.95) >> MA60(≈1) → 均线多头
    closes = [1.0] * 69 + [100.0]
    sig = generate_signal("603993", "测试股", _df_from_closes(closes))
    assert sig["action"] == "buy"
    assert len(sig["reasons"]) >= 2
    assert sig["price"] == closes[-1]


def test_downtrend_triggers_sell():
    # 69根价格极高(≈100) → EMA12≈EMA26≈100,DIF≈DEA≈0
    # 最后一根暴跌到1 → EMA12跌得远快于EMA26 → DIF从≈0一跃为负(死叉)
    # MA: 最后一根1 << MA20(≈95) → 跌破均线
    closes = [100.0] * 69 + [1.0]
    sig = generate_signal("603993", "测试股", _df_from_closes(closes))
    assert sig["action"] == "sell"
    assert len(sig["reasons"]) >= 2


def test_flat_returns_hold():
    # 价格全程不变 → DIF=DEA=0无交叉，价格=MA20=MA60无多空方向 → hold
    closes = [10.0] * 70
    sig = generate_signal("603993", "测试股", _df_from_closes(closes))
    assert sig["action"] == "hold"


def test_insufficient_data_returns_hold():
    sig = generate_signal("603993", "测试股", _df_from_closes([10, 11, 12]))
    assert sig["action"] == "hold"
