import json
from pathlib import Path
from modules.sim_trading.account.account import SimAccount


def _new_account(tmp_path) -> SimAccount:
    f = tmp_path / "sim_account.json"
    return SimAccount(store_path=str(f), initial_capital=100000.0,
                      per_trade_pct=0.10, max_total=0.80, max_single=0.20)


def test_fresh_account_starts_full_cash(tmp_path):
    acc = _new_account(tmp_path)
    assert acc.cash == 100000.0
    assert acc.positions == {}
    assert acc.total_value({}) == 100000.0


def test_buy_deducts_cash_and_rounds_to_100_shares(tmp_path):
    acc = _new_account(tmp_path)
    # 目标金额 = 10% * 100000 = 10000；价 9.20 → floor(10000/9.20/100)*100 = 1000股
    r = acc.execute({"code": "603993", "name": "洛阳钼业",
                     "action": "buy", "price": 9.20}, prices={"603993": 9.20})
    assert r["ok"] is True
    assert r["action"] == "buy"
    assert r["shares"] == 1000
    assert r["amount"] == 9200.0
    assert acc.cash == 90800.0
    assert acc.positions["603993"]["shares"] == 1000
    assert acc.positions["603993"]["cost_price"] == 9.20


def test_buy_again_averages_cost(tmp_path):
    acc = _new_account(tmp_path)
    acc.execute({"code": "603993", "name": "洛阳钼业", "action": "buy", "price": 10.0},
                prices={"603993": 10.0})   # 10%*100000=10000 → 1000股 @10
    # 再次买入，价12：目标 10%*当前总资产
    acc.execute({"code": "603993", "name": "洛阳钼业", "action": "buy", "price": 12.0},
                prices={"603993": 12.0})
    pos = acc.positions["603993"]
    assert pos["shares"] > 1000
    # 加权成本介于10与12之间
    assert 10.0 < pos["cost_price"] < 12.0


def test_sell_closes_position_and_realizes_pnl(tmp_path):
    acc = _new_account(tmp_path)
    acc.execute({"code": "603993", "name": "洛阳钼业", "action": "buy", "price": 10.0},
                prices={"603993": 10.0})   # 1000股 @10，成本10000
    shares = acc.positions["603993"]["shares"]
    cash_after_buy = acc.cash
    r = acc.execute({"code": "603993", "name": "洛阳钼业", "action": "sell", "price": 12.0},
                    prices={"603993": 12.0})
    assert r["ok"] is True
    assert r["action"] == "sell"
    assert r["shares"] == shares
    # 已实现盈亏 = (12-10)*shares
    assert r["realized_pnl"] == round((12.0 - 10.0) * shares, 2)
    assert "603993" not in acc.positions
    assert acc.cash == round(cash_after_buy + 12.0 * shares, 2)


def test_sell_nonexistent_position_skips(tmp_path):
    acc = _new_account(tmp_path)
    r = acc.execute({"code": "000001", "name": "平安银行", "action": "sell", "price": 10.0},
                    prices={"000001": 10.0})
    assert r["ok"] is False
    assert r["action"] == "skip"
