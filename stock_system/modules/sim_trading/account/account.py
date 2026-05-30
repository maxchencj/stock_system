"""
模拟仓账户：持久化、现金/持仓/仓位比、成交执行（建仓/加仓/减仓/平仓）
全自动成交，无真实下单。数据文件 data/sim_account.json
"""
import json
import math
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import threading

from utils.logger import logger

_LOCK = threading.Lock()


class SimAccount:
    def __init__(self, store_path: str, initial_capital: float,
                 per_trade_pct: float, max_total: float, max_single: float):
        self.store_path = Path(store_path)
        self.initial_capital = initial_capital
        self.per_trade_pct = per_trade_pct
        self.max_total = max_total
        self.max_single = max_single
        self.cash = initial_capital
        self.positions: Dict[str, Dict] = {}
        self.trade_history = []
        self._load()

    def _load(self):
        if self.store_path.exists():
            try:
                data = json.loads(self.store_path.read_text(encoding="utf-8"))
                self.initial_capital = data.get("initial_capital", self.initial_capital)
                self.cash = data.get("cash", self.initial_capital)
                self.positions = data.get("positions", {})
                self.trade_history = data.get("trade_history", [])
            except Exception as e:
                logger.warning(f"加载模拟账户失败，使用空账户: {e}")

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "initial_capital": self.initial_capital,
            "cash": round(self.cash, 2),
            "positions": self.positions,
            "trade_history": self.trade_history,
        }
        self.store_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def total_value(self, prices: Dict[str, float]) -> float:
        """总资产 = 现金 + 持仓市值（持仓用传入价，缺失则用成本价）"""
        mv = 0.0
        for code, pos in self.positions.items():
            px = prices.get(code) or pos["cost_price"]
            mv += px * pos["shares"]
        return self.cash + mv

    def position_ratio(self, prices: Dict[str, float]) -> float:
        tv = self.total_value(prices)
        if tv <= 0:
            return 0.0
        return 1.0 - self.cash / tv

    def execute(self, signal: Dict, prices: Dict[str, float]) -> Dict:
        """根据信号成交。signal: {code,name,action,price}; prices: code→现价"""
        with _LOCK:
            action = signal["action"]
            if action == "buy":
                return self._buy(signal, prices)
            if action == "sell":
                return self._sell(signal, prices)
            return {"ok": False, "action": "skip", "code": signal.get("code"),
                    "reason": f"未知动作 {action}"}

    def _buy(self, signal: Dict, prices: Dict[str, float]) -> Dict:
        code, name, price = signal["code"], signal["name"], signal["price"]
        tv = self.total_value(prices)
        target_amount = self.per_trade_pct * tv

        # 单股上限约束：当前该股市值 + 本次买入 不得超过 max_single * tv
        cur_mv = self.positions.get(code, {}).get("shares", 0) * price
        room_single = self.max_single * tv - cur_mv
        # 总仓位上限约束
        room_total = self.max_total * tv - (tv - self.cash)
        target_amount = min(target_amount, room_single, room_total, self.cash)

        if target_amount <= 0:
            return {"ok": False, "action": "skip", "code": code, "name": name,
                    "reason": "仓位已满或现金不足"}

        shares = math.floor(target_amount / price / 100) * 100
        if shares < 100:
            return {"ok": False, "action": "skip", "code": code, "name": name,
                    "reason": "现金不足以买入100股"}

        amount = shares * price
        self.cash -= amount
        if code in self.positions:
            pos = self.positions[code]
            total_shares = pos["shares"] + shares
            pos["cost_price"] = round(
                (pos["cost_price"] * pos["shares"] + amount) / total_shares, 4)
            pos["shares"] = total_shares
        else:
            self.positions[code] = {
                "name": name, "shares": shares,
                "cost_price": round(price, 4),
                "buy_date": datetime.now().strftime("%Y-%m-%d"),
            }
        self._record("buy", code, name, shares, price, amount,
                     signal.get("signal", ""), 0.0)
        self._save()
        return {"ok": True, "action": "buy", "code": code, "name": name,
                "shares": shares, "price": price, "amount": round(amount, 2),
                "realized_pnl": 0.0, "cash_after": round(self.cash, 2),
                "position_ratio_after": round(self.position_ratio(prices), 4),
                "reason": ""}

    def _sell(self, signal: Dict, prices: Dict[str, float]) -> Dict:
        code, name, price = signal["code"], signal["name"], signal["price"]
        pos = self.positions.get(code)
        if not pos or pos["shares"] <= 0:
            return {"ok": False, "action": "skip", "code": code, "name": name,
                    "reason": "无持仓可卖"}
        shares = pos["shares"]
        amount = shares * price
        realized = (price - pos["cost_price"]) * shares
        self.cash += amount
        del self.positions[code]
        self._record("sell", code, name, shares, price, amount,
                     signal.get("signal", ""), realized)
        self._save()
        return {"ok": True, "action": "sell", "code": code, "name": name,
                "shares": shares, "price": price, "amount": round(amount, 2),
                "realized_pnl": round(realized, 2), "cash_after": round(self.cash, 2),
                "position_ratio_after": round(self.position_ratio(prices), 4),
                "reason": ""}

    def _record(self, action, code, name, shares, price, amount, sig, pnl):
        self.trade_history.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "action": action, "code": code, "name": name,
            "shares": shares, "price": round(price, 4),
            "amount": round(amount, 2), "signal": sig,
            "realized_pnl": round(pnl, 2),
        })
