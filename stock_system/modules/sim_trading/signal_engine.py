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
