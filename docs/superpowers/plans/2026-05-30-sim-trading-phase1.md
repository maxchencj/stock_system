# 模拟仓交易系统 Phase 1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个能跑通的模拟仓最小系统：基于自选股，用 MACD/均线共振策略自动监控买卖点，触发后全自动在模拟账户成交，并推送到独立 Telegram Bot（@mcStockMessage_bot）。

**Architecture:** 新建 `modules/sim_trading/` 模块，与现有代码零耦合，仅复用 `data/data_service.py`（K线/指标）、`config/settings.py`（配置）、`core/scheduler.py`（定时任务）、`notify/notifier.py`（TG 底层 `TelegramNotifier`）。账户状态持久化为 `data/sim_account.json`。Phase 1 不含 AI 层、缠论、回测、RSI——这些在 Phase 2-5 单独成计划。本期信号通过"双指标共振"过滤误报，仓位用静态规则（固定单笔 10%、总仓上限 80%、单股上限 20%）。

**Tech Stack:** Python 3.9+, pandas, APScheduler, requests, pytest（本期为新模块引入单元测试）。

**说明：** 仓库现有代码无 pytest，仅用 `--test-*` 脚本手动验证。本计划为新模块的纯逻辑（账户算术、策略信号、成交计算）引入 pytest 单测（这些是纯函数，最适合 TDD），集成层用 `main.py --test-sim` 烟雾验证。

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `modules/sim_trading/__init__.py` | 包标识（空） |
| `modules/sim_trading/account/__init__.py` | 子包标识（空） |
| `modules/sim_trading/account/account.py` | 账户持久化、现金/净值/仓位比、成交执行（建仓/加仓/减仓/平仓） |
| `modules/sim_trading/strategy/__init__.py` | 子包标识（空） |
| `modules/sim_trading/strategy/signals.py` | MACD 金叉/死叉、均线突破、双指标共振判断（纯函数，输入 DataFrame 输出信号） |
| `modules/sim_trading/signal_engine.py` | 信号主控：扫描自选股 → 共振判断 → 风控 → 自动成交 → 推送 |
| `modules/sim_trading/sim_notifier.py` | 专用推送：封装第三个 TelegramNotifier，格式化成交/风险消息 |
| `config/settings.py` | 修改：新增 `SimTradingConfig`（bot token/chat_id、初始资金、仓位参数） |
| `core/scheduler.py` | 修改：注册盘中每5分钟信号扫描任务 |
| `main.py` | 修改：新增 `--test-sim` 烟雾测试入口 |
| `tests/__init__.py` | 测试包标识（空） |
| `tests/test_sim_account.py` | 账户算术单测 |
| `tests/test_sim_signals.py` | 策略信号单测 |
| `requirements.txt` | 修改：新增 pytest |
| `.env` | 用户手动配置：SIM_TELEGRAM_TOKEN / SIM_TELEGRAM_CHAT_ID |

---

## 数据结构契约（贯穿全计划）

**`data/sim_account.json`：**
```json
{
  "initial_capital": 100000,
  "cash": 100000,
  "positions": {
    "603993": {
      "name": "洛阳钼业",
      "shares": 1300,
      "cost_price": 9.20,
      "buy_date": "2026-05-30"
    }
  },
  "trade_history": [
    {
      "date": "2026-05-30 10:35", "action": "buy",
      "code": "603993", "name": "洛阳钼业",
      "shares": 1300, "price": 9.20, "amount": 11960,
      "signal": "MACD金叉+均线多头", "realized_pnl": 0
    }
  ]
}
```

**信号字典（`signals.py` 输出，`signal_engine` 消费）：**
```python
{
    "code": "603993",
    "action": "buy",          # "buy" | "sell" | "hold"
    "reasons": ["MACD金叉", "均线多头排列"],  # 触发的指标列表
    "price": 9.20,            # 最新收盘价
}
```

**成交结果字典（`account.execute` 返回，`sim_notifier` 消费）：**
```python
{
    "ok": True,
    "action": "buy",          # "buy" | "sell" | "skip"
    "code": "603993", "name": "洛阳钼业",
    "shares": 1300, "price": 9.20, "amount": 11960,
    "realized_pnl": 0.0,      # 卖出时的已实现盈亏，买入为0
    "cash_after": 88040.0,
    "position_ratio_after": 0.12,
    "reason": "",             # skip 时填原因（如"现金不足"）
}
```

---

## Task 1: 创建包骨架与配置

**Files:**
- Create: `modules/sim_trading/__init__.py`（空）
- Create: `modules/sim_trading/account/__init__.py`（空）
- Create: `modules/sim_trading/strategy/__init__.py`（空）
- Modify: `config/settings.py`（新增 `SimTradingConfig` 并挂到 `SystemConfig`）
- Modify: `requirements.txt`（新增 pytest）

- [ ] **Step 1: 创建三个空包文件**

```bash
mkdir -p modules/sim_trading/account modules/sim_trading/strategy
touch modules/sim_trading/__init__.py
touch modules/sim_trading/account/__init__.py
touch modules/sim_trading/strategy/__init__.py
```

- [ ] **Step 2: 在 `config/settings.py` 新增配置类**

在 `USStockConfig` 之后、`SystemConfig` 之前插入：

```python
@dataclass
class SimTradingConfig:
    """模拟仓交易配置"""
    telegram_token: str = os.getenv("SIM_TELEGRAM_TOKEN", "")
    telegram_chat_id: str = os.getenv("SIM_TELEGRAM_CHAT_ID", "")
    enabled: bool = True
    initial_capital: float = 100000.0   # 初始资金10万
    per_trade_pct: float = 0.10         # 单笔建仓占总资产比例
    max_total_position: float = 0.80    # 总仓位上限
    max_single_position: float = 0.20   # 单股仓位上限
```

- [ ] **Step 3: 挂到 `SystemConfig`**

在 `SystemConfig` 类中 `us_stock` 字段下方新增：

```python
    sim_trading: SimTradingConfig = field(default_factory=SimTradingConfig)
```

- [ ] **Step 4: 在 `requirements.txt` 末尾新增**

```
pytest
```

- [ ] **Step 5: 验证配置可加载**

Run: `cd stock_system && python3 -c "from config.settings import config; print(config.sim_trading.initial_capital, config.sim_trading.per_trade_pct)"`
Expected: 输出 `100000.0 0.1`

- [ ] **Step 6: Commit**

```bash
git add modules/sim_trading config/settings.py requirements.txt
git commit -m "feat(sim): 模拟仓包骨架与配置"
```

---

## Task 2: 账户成交核心（建仓/加仓）

**Files:**
- Create: `modules/sim_trading/account/account.py`
- Create: `tests/__init__.py`（空）
- Create: `tests/test_sim_account.py`

- [ ] **Step 1: 写失败测试 `tests/test_sim_account.py`**

```python
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
```

- [ ] **Step 2: 运行验证失败**

Run: `cd stock_system && touch tests/__init__.py && python3 -m pytest tests/test_sim_account.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'modules.sim_trading.account.account'`

- [ ] **Step 3: 实现 `modules/sim_trading/account/account.py`**

```python
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

    def _record(self, action, code, name, shares, price, amount, sig, pnl):
        self.trade_history.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "action": action, "code": code, "name": name,
            "shares": shares, "price": round(price, 4),
            "amount": round(amount, 2), "signal": sig,
            "realized_pnl": round(pnl, 2),
        })
```

- [ ] **Step 4: 运行验证通过**

Run: `cd stock_system && python3 -m pytest tests/test_sim_account.py -v`
Expected: 3 passed（`_sell` 尚未实现，本任务测试不涉及卖出）

- [ ] **Step 5: Commit**

```bash
git add modules/sim_trading/account/account.py tests/
git commit -m "feat(sim): 账户建仓/加仓与持久化"
```

---

## Task 3: 账户卖出/平仓

**Files:**
- Modify: `modules/sim_trading/account/account.py`（新增 `_sell`）
- Modify: `tests/test_sim_account.py`（新增卖出测试）

- [ ] **Step 1: 追加失败测试到 `tests/test_sim_account.py`**

```python
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
```

- [ ] **Step 2: 运行验证失败**

Run: `cd stock_system && python3 -m pytest tests/test_sim_account.py -v -k sell`
Expected: FAIL，`_sell` 未实现（`execute` 调用到不存在的方法 → AttributeError）

- [ ] **Step 3: 在 `account.py` 新增 `_sell` 方法（放在 `_buy` 之后）**

```python
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
```

- [ ] **Step 4: 运行验证全部通过**

Run: `cd stock_system && python3 -m pytest tests/test_sim_account.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add modules/sim_trading/account/account.py tests/test_sim_account.py
git commit -m "feat(sim): 账户卖出/平仓与已实现盈亏"
```

---

## Task 4: 策略信号（MACD + 均线 + 共振）

**Files:**
- Create: `modules/sim_trading/strategy/signals.py`
- Create: `tests/test_sim_signals.py`

- [ ] **Step 1: 写失败测试 `tests/test_sim_signals.py`**

```python
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
    closes = [10 - i * 0.1 for i in range(30)] + [7 + i * 0.25 for i in range(40)]
    sig = generate_signal("603993", "测试股", _df_from_closes(closes))
    assert sig["action"] == "buy"
    assert len(sig["reasons"]) >= 2  # 双指标共振
    assert sig["price"] == closes[-1]


def test_downtrend_triggers_sell():
    # 先涨后持续下跌 → MACD 死叉 + 跌破均线
    closes = [7 + i * 0.25 for i in range(40)] + [17 - i * 0.3 for i in range(30)]
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
```

- [ ] **Step 2: 运行验证失败**

Run: `cd stock_system && python3 -m pytest tests/test_sim_signals.py -v`
Expected: FAIL，`ModuleNotFoundError: ...strategy.signals`

- [ ] **Step 3: 实现 `modules/sim_trading/strategy/signals.py`**

```python
"""
模拟仓策略信号（Phase 1）：MACD 金叉/死叉 + 均线突破，双指标共振才触发。
纯函数：输入日K DataFrame，输出信号字典。复用 data_service 的指标算法（此处内联以保持模块独立）。
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
    if df is None or len(df) < 60:
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
```

- [ ] **Step 4: 运行验证通过**

Run: `cd stock_system && python3 -m pytest tests/test_sim_signals.py -v`
Expected: 4 passed
（若 `test_uptrend_triggers_buy` 或 `test_downtrend_triggers_sell` 未触发，因金叉/死叉只看最后一根：调整测试数据让交叉恰好落在末根——见 Step 5 兜底）

- [ ] **Step 5: 若交叉时点未落末根，修正测试数据（仅在 Step 4 失败时执行）**

把 `test_uptrend_triggers_buy` 的 closes 改为构造末根金叉：
```python
    closes = ([12 - i * 0.15 for i in range(35)]      # 持续下跌压低DIF
              + [6 + i * 0.05 for i in range(34)]      # 缓涨使DIF接近DEA
              + [6 + 34 * 0.05 + 1.5])                 # 末根跳涨触发金叉
```
对称地为 `test_downtrend_triggers_sell` 构造末根死叉。重跑 Step 4 直至通过。

- [ ] **Step 6: Commit**

```bash
git add modules/sim_trading/strategy/signals.py tests/test_sim_signals.py
git commit -m "feat(sim): MACD+均线双指标共振策略信号"
```

---

## Task 5: 专用 Telegram 推送

**Files:**
- Create: `modules/sim_trading/sim_notifier.py`

- [ ] **Step 1: 实现 `modules/sim_trading/sim_notifier.py`**

```python
"""
模拟仓专用推送：第三个 Telegram Bot（@mcStockMessage_bot）。
复用 notify.notifier.TelegramNotifier 底层，仅做消息格式化。
"""
from typing import Dict
from config.settings import config
from notify.notifier import TelegramNotifier
from utils.logger import logger


class SimNotifier:
    def __init__(self):
        self.tg = TelegramNotifier(
            token=config.sim_trading.telegram_token,
            chat_id=config.sim_trading.telegram_chat_id,
        )

    def send_trade(self, result: Dict, signal: Dict, total_value: float):
        """成交后推送。result: account.execute 返回；signal: 含 reasons。"""
        if not self.tg.enabled:
            logger.warning("模拟仓 Telegram Bot 未配置，跳过推送")
            return False
        if not result.get("ok"):
            return False

        is_buy = result["action"] == "buy"
        head = "✅ 模拟仓已买入" if is_buy else "✅ 模拟仓已卖出"
        reasons = "、".join(signal.get("reasons", [])) or "策略信号"
        lines = [
            head, "",
            f"📌 {result['name']}（{result['code']}）",
            "━━━━━━━━━━━━━━━━━━",
            f"📊 触发信号：{reasons}",
            f"💰 成交：{'买入' if is_buy else '卖出'} {result['shares']}股 "
            f"@ {result['price']:.2f}，金额 {result['amount']:.0f}",
        ]
        if not is_buy:
            lines.append(f"📈 已实现盈亏：{result['realized_pnl']:+.0f}")
        lines += [
            f"📊 成交后仓位：{result['position_ratio_after']*100:.0f}%",
            f"💵 账户：现金 {result['cash_after']:.0f} / 总资产 {total_value:.0f}",
        ]
        return self.tg.send("\n".join(lines))

    def send_skip_log(self, result: Dict):
        """成交被跳过时仅记日志，不推送（避免噪音）。"""
        logger.info(f"模拟仓跳过 {result.get('code')}: {result.get('reason')}")


sim_notifier = SimNotifier()
```

- [ ] **Step 2: 验证可导入（无 token 时不报错）**

Run: `cd stock_system && python3 -c "from modules.sim_trading.sim_notifier import sim_notifier; print('enabled=', sim_notifier.tg.enabled)"`
Expected: 输出 `enabled= False`（未配置 token），无异常

- [ ] **Step 3: Commit**

```bash
git add modules/sim_trading/sim_notifier.py
git commit -m "feat(sim): 模拟仓专用Telegram推送"
```

---

## Task 6: 信号引擎（扫描 → 成交 → 推送）

**Files:**
- Create: `modules/sim_trading/signal_engine.py`

- [ ] **Step 1: 实现 `modules/sim_trading/signal_engine.py`**

```python
"""
模拟仓信号引擎：扫描自选股 → 共振信号 → 全自动成交 → 推送。
被定时任务每5分钟调用。交易日/休市判断由调用方或本模块入口保证。
"""
import json
from pathlib import Path
from typing import Dict, List

from config.settings import config
from data.data_service import market_service
from modules.sim_trading.account.account import SimAccount
from modules.sim_trading.strategy.signals import generate_signal
from modules.sim_trading.sim_notifier import sim_notifier
from utils.logger import logger

_WATCHLIST_FILE = Path(__file__).parent.parent.parent / "data" / "watchlist.json"
_ACCOUNT_FILE = Path(__file__).parent.parent.parent / "data" / "sim_account.json"


def _load_watchlist() -> Dict[str, str]:
    """返回 {code: name}。兼容 watchlist.json 的 stocks 字典结构。"""
    try:
        data = json.loads(_WATCHLIST_FILE.read_text(encoding="utf-8"))
        stocks = data.get("stocks", {})
        if isinstance(stocks, dict):
            return {c: (v.get("name", "") if isinstance(v, dict) else "")
                    for c, v in stocks.items()}
        if isinstance(stocks, list):
            return {c: "" for c in stocks}
    except Exception as e:
        logger.warning(f"读取自选股失败: {e}")
    return {}


class SignalEngine:
    def __init__(self):
        self.account = SimAccount(
            store_path=str(_ACCOUNT_FILE),
            initial_capital=config.sim_trading.initial_capital,
            per_trade_pct=config.sim_trading.per_trade_pct,
            max_total=config.sim_trading.max_total_position,
            max_single=config.sim_trading.max_single_position,
        )

    def scan_once(self) -> List[Dict]:
        """扫描一轮自选股，对共振信号自动成交并推送。返回成交结果列表。"""
        watchlist = _load_watchlist()
        if not watchlist:
            logger.info("模拟仓：自选股为空，跳过扫描")
            return []

        # 第一遍：取每只股的日K（一次取齐，复用于估值与信号判断）
        klines = {}   # code -> DataFrame
        prices = {}   # code -> 最新收盘价
        for code in watchlist:
            try:
                df = market_service.get_history(code, period="daily")
                if df is None or df.empty or "close" not in df.columns:
                    continue
                klines[code] = df
                prices[code] = float(df["close"].iloc[-1])
            except Exception as e:
                logger.warning(f"模拟仓取K线失败 {code}: {e}")

        # 持仓股若取价失败，用成本价兜底计入估值
        for code, pos in self.account.positions.items():
            if code not in prices:
                prices[code] = pos["cost_price"]

        # 第二遍：生成信号并成交
        results = []
        for code, name in watchlist.items():
            df = klines.get(code)
            if df is None:
                continue
            try:
                sig = generate_signal(code, name or code, df)
                if sig["action"] == "hold":
                    continue
                # 卖出信号仅对已持仓股有效
                if sig["action"] == "sell" and code not in self.account.positions:
                    continue
                sig["signal"] = "、".join(sig["reasons"])
                result = self.account.execute(sig, prices)
                if result.get("ok"):
                    tv = self.account.total_value(prices)
                    sim_notifier.send_trade(result, sig, tv)
                    logger.info(f"模拟仓成交 {result['action']} {code} {result['shares']}股")
                else:
                    sim_notifier.send_skip_log(result)
                results.append(result)
            except Exception as e:
                logger.error(f"模拟仓处理 {code} 失败: {e}", exc_info=True)
        return results


signal_engine = SignalEngine()
```

> **数据源说明**：`market_service.get_history(code, period="daily")` 基于 AKShare，默认返回近365天日K，列含 `date/open/close/high/low/volume`，按日期升序；无需传 `days`，60日均线数据量充足。

- [ ] **Step 2: 验证可导入**

Run: `cd stock_system && python3 -c "from modules.sim_trading.signal_engine import signal_engine; print('ok, positions=', len(signal_engine.account.positions))"`
Expected: 输出 `ok, positions= 0`（全新账户），无异常

- [ ] **Step 3: Commit**

```bash
git add modules/sim_trading/signal_engine.py
git commit -m "feat(sim): 信号引擎扫描+自动成交+推送"
```

---

## Task 7: 接入定时任务

**Files:**
- Modify: `core/scheduler.py`（新增任务注册 + 任务方法）

- [ ] **Step 1: 在 `core/scheduler.py` 的 `start()` 方法中注册任务**

定时任务全部在 `start()` 方法体内用 `self.scheduler.add_job(...)` 注册（本仓库没有独立的 `_register_jobs` 方法）。在 `start()` 末尾的 `# ── Phase 3：数据增强` 注释行之后、`self.scheduler.start()` 之前插入（与现有"实时行情推送"任务的分时段写法保持一致，避开 11:30 后与 11:35-11:59 的午休时段噪音）：

```python
        # ── 模拟仓信号扫描（交易时段，每5分钟）──────────────
        self.scheduler.add_job(
            self.sim_signal_task,
            CronTrigger(hour="9", minute="30,35,40,45,50,55", day_of_week="mon-fri"),
            id="sim_0930", name="模拟仓信号(09:30-09:55)", replace_existing=True
        )
        self.scheduler.add_job(
            self.sim_signal_task,
            CronTrigger(hour="10", minute="0,5,10,15,20,25,30,35,40,45,50,55", day_of_week="mon-fri"),
            id="sim_1000", name="模拟仓信号(10:00-10:55)", replace_existing=True
        )
        self.scheduler.add_job(
            self.sim_signal_task,
            CronTrigger(hour="11", minute="0,5,10,15,20,25,30", day_of_week="mon-fri"),
            id="sim_1100", name="模拟仓信号(11:00-11:30)", replace_existing=True
        )
        self.scheduler.add_job(
            self.sim_signal_task,
            CronTrigger(hour="13,14", minute="0,5,10,15,20,25,30,35,40,45,50,55", day_of_week="mon-fri"),
            id="sim_pm", name="模拟仓信号(13:00-14:55)", replace_existing=True
        )
```

- [ ] **Step 2: 在 `core/scheduler.py` 新增任务方法（放在 `realtime_market_push_task` 之后，类的任务函数区内）**

```python
    def sim_signal_task(self):
        """模拟仓信号扫描（盘中每5分钟）"""
        try:
            from modules.sim_trading.signal_engine import signal_engine
            signal_engine.scan_once()
        except Exception as e:
            logger.error(f"模拟仓信号任务失败: {e}", exc_info=True)
        return
```

- [ ] **Step 3: 验证导入与注册无语法错误**

`start()` 末尾会调用 `self.scheduler.start()` 并 `_print_jobs()`，不便在脚本里安全调用。改为验证模块可导入、方法存在：

Run: `cd stock_system && python3 -c "from core.scheduler import TaskScheduler; assert hasattr(TaskScheduler, 'sim_signal_task'); print('ok')"`
Expected: 输出 `ok`，无异常

启动系统后，日志 `_print_jobs()` 输出应包含 `sim_0930 / sim_1000 / sim_1100 / sim_pm` 四个任务。

- [ ] **Step 4: Commit**

```bash
git add core/scheduler.py
git commit -m "feat(sim): 接入盘中每5分钟信号扫描定时任务"
```

---

## Task 8: 烟雾测试入口与文档

**Files:**
- Modify: `main.py`（新增 `--test-sim` 参数与分支）
- Modify: `stock_system/CLAUDE.md`（新增模拟仓模块说明）

- [ ] **Step 1: 在 `main.py` 的 argparse 区新增参数**

在其它 `--test-*` 之后：
```python
    parser.add_argument("--test-sim", action="store_true", help="测试模拟仓信号扫描")
```

- [ ] **Step 2: 在 `main.py` 的分支调度区新增处理**

参照现有 `--test-*` 分支写法（在调用 `args.test_xxx` 的同一段落）：
```python
    if args.test_sim:
        from modules.sim_trading.signal_engine import signal_engine
        results = signal_engine.scan_once()
        print(f"模拟仓扫描完成，成交 {len([r for r in results if r.get('ok')])} 笔")
        print(f"当前持仓 {len(signal_engine.account.positions)} 只，"
              f"现金 {signal_engine.account.cash:.0f}")
        return
```
（若 `main()` 非函数 return 结构，按现有分支用 `sys.exit(0)` 或对应方式收尾——以文件中已有 `--test-picker` 分支为准复制结构）

- [ ] **Step 3: 运行烟雾测试**

Run: `cd stock_system && python3 main.py --test-sim`
Expected: 输出"模拟仓扫描完成，成交 N 笔"与持仓/现金信息，无异常堆栈（自选股当前仅1只洛阳钼业，多数情况成交0笔属正常）

- [ ] **Step 4: 在 `stock_system/CLAUDE.md` 的"核心模块说明"末尾新增小节**

```markdown
### 8. 模拟仓交易模块 (`modules/sim_trading/`)

**职责**: 基于自选股，MACD+均线共振策略自动监控买卖点，全自动模拟成交，推送独立 TG Bot

**关键文件**:
- `account/account.py`: 账户持久化、建/加/减/平仓、加权成本、仓位比
- `strategy/signals.py`: MACD金叉死叉 + 均线突破双指标共振（纯函数）
- `signal_engine.py`: 扫描自选股 → 风控 → 自动成交 → 推送
- `sim_notifier.py`: 第三个 Telegram Bot 推送

**数据文件**: `data/sim_account.json`（账户状态）
**配置**: `config.sim_trading`（初始10万、单笔10%、总仓80%、单股20%）
**环境变量**: `SIM_TELEGRAM_TOKEN` / `SIM_TELEGRAM_CHAT_ID`
**定时任务**: 盘中每5分钟扫描（sim_0930 / sim_1000 / sim_1100 / sim_pm）
**测试**: `python main.py --test-sim`；单测 `pytest tests/test_sim_*.py`

**待实施（后续 Phase）**: AI研判层、缠论策略、回测系统、RSI+KDJ、动态仓位
```

- [ ] **Step 5: 更新 .gitignore 忽略账户数据**

确认 `.gitignore` 含 `stock_system/data/sim_account.json`（若无则添加，与现有 portfolio.json 同处理）：
```
stock_system/data/sim_account.json
```

- [ ] **Step 6: Commit**

```bash
git add main.py stock_system/CLAUDE.md .gitignore
git commit -m "feat(sim): 烟雾测试入口、模块文档、忽略账户数据"
```

---

## 验收标准（Phase 1 完成定义）

1. `pytest tests/test_sim_account.py tests/test_sim_signals.py -v` 全部通过
2. `python main.py --test-sim` 正常跑完，无异常堆栈
3. 配置 `SIM_TELEGRAM_TOKEN` / `SIM_TELEGRAM_CHAT_ID` 后，手动触发一次有成交的扫描，`@mcStockMessage_bot` 收到格式化成交消息
4. `data/sim_account.json` 正确记录现金、持仓、加权成本、交易历史
5. 调度器启动后能看到 `sim_0930 / sim_1000 / sim_1100 / sim_pm` 四个任务注册

---

## Phase 1 范围说明（明确不做的事）

- ❌ AI 研判层（Phase 2）：本期用静态规则，不调用 Claude
- ❌ 缠论策略（Phase 3）：本期仅 MACD + 均线
- ❌ 回测系统（Phase 4）：本期信号无历史胜率附注
- ❌ RSI+KDJ（Phase 5）
- ❌ 动态仓位（市场状态调节）：本期固定单笔 10%
- ❌ 止损/回撤自动保护：本期不含（Phase 2 随风控模块加入）
- ❌ 加仓/减仓信号：本期信号只产出 buy（首次建仓）/ sell（清仓），不产生 add/reduce
