"""
模拟持仓追踪 - 记录研报推荐建仓价，每日跟踪盈亏
数据文件: data/portfolio.json
每周日 20:00 推送周度绩效报告 → A股Bot
Bot命令: /portfolio(/pf) 查看持仓  /close CODE 平仓
"""
import json
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

import threading

from notify.notifier import notifier
from utils.logger import logger

_PORTFOLIO_FILE = Path(__file__).parent.parent.parent / "data" / "portfolio.json"
_MAX_POSITIONS = 20  # 最多同时持有
_LOCK = threading.Lock()  # 防止并发写覆盖


def _load() -> Dict:
    if _PORTFOLIO_FILE.exists():
        try:
            with open(_PORTFOLIO_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"positions": {}, "history": []}


def _save(data: Dict):
    _PORTFOLIO_FILE.parent.mkdir(exist_ok=True)
    with open(_PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_price(code: str) -> Optional[float]:
    """腾讯Finance获取实时价格"""
    try:
        prefix = "sh" if code.startswith("6") else "sz"
        url = f"http://qt.gtimg.cn/q={prefix}{code}"
        resp = requests.get(url, timeout=6)
        resp.encoding = "gbk"
        parts = resp.text.split("~")
        if len(parts) > 3:
            return float(parts[3])
    except Exception:
        pass
    return None


class PortfolioTracker:

    def add_position(self, code: str, name: str, buy_price: float,
                     source: str = "研报推荐") -> bool:
        """建仓（研报推送时自动调用）"""
        with _LOCK:
            return self._add_position_locked(code, name, buy_price, source)

    def _add_position_locked(self, code: str, name: str, buy_price: float,
                             source: str) -> bool:
        data = _load()
        positions = data["positions"]
        if code in positions:
            return False  # 已持有
        if len(positions) >= _MAX_POSITIONS:
            logger.warning(f"模拟持仓已满({_MAX_POSITIONS}只)，跳过 {code}")
            return False
        positions[code] = {
            "name": name,
            "code": code,
            "buy_price": buy_price,
            "buy_date": datetime.now().strftime("%Y-%m-%d"),
            "source": source,
        }
        _save(data)
        logger.info(f"模拟建仓: {name}({code}) @ {buy_price:.2f}")
        return True

    def close_position(self, code: str) -> Optional[Dict]:
        """平仓，返回盈亏记录"""
        with _LOCK:
            return self._close_position_locked(code)

    def _close_position_locked(self, code: str) -> Optional[Dict]:
        data = _load()
        pos = data["positions"].pop(code, None)
        if not pos:
            return None
        sell_price = _get_price(code) or pos["buy_price"]
        pnl = (sell_price - pos["buy_price"]) / pos["buy_price"] * 100
        record = {
            **pos,
            "sell_price": sell_price,
            "sell_date": datetime.now().strftime("%Y-%m-%d"),
            "pnl_pct": round(pnl, 2),
        }
        data["history"].append(record)
        # 只保留最近 200 条历史
        data["history"] = data["history"][-200:]
        _save(data)
        logger.info(f"模拟平仓: {pos['name']}({code}) 盈亏{pnl:+.2f}%")
        return record

    def get_positions_text(self) -> str:
        """格式化当前持仓，供Bot查询"""
        data = _load()
        positions = data["positions"]
        if not positions:
            return "当前无模拟持仓"
        lines = [f"📂 模拟持仓 ({len(positions)}只) — {datetime.now().strftime('%m/%d %H:%M')}"]
        lines.append("━━━━━━━━━━━━━━━━")
        total_pnl = 0
        count = 0
        for code, pos in positions.items():
            cur = _get_price(code)
            if cur:
                pnl = (cur - pos["buy_price"]) / pos["buy_price"] * 100
                total_pnl += pnl
                count += 1
                icon = "🔴" if pnl >= 0 else "🟢"
                lines.append(
                    f"{icon} {pos['name']}({code})\n"
                    f"   建仓:{pos['buy_price']:.2f}  现价:{cur:.2f}  "
                    f"盈亏:{pnl:+.2f}%  {pos['buy_date']}"
                )
            else:
                lines.append(
                    f"⚪ {pos['name']}({code})  建仓:{pos['buy_price']:.2f}  "
                    f"(价格获取失败)  {pos['buy_date']}"
                )
        if count > 0:
            lines.append(f"━━━━━━━━━━━━━━━━")
            lines.append(f"平均盈亏: {total_pnl/count:+.2f}%")
        return "\n".join(lines)

    def run_weekly_report(self):
        """每周日 20:00 推送周度绩效"""
        logger.info("执行模拟持仓周报")
        data = _load()
        positions = data["positions"]
        history = data["history"]

        # 统计近30条平仓历史
        recent = history[-30:] if history else []
        if recent:
            wins = [r for r in recent if r["pnl_pct"] > 0]
            win_rate = len(wins) / len(recent) * 100
            avg_pnl = sum(r["pnl_pct"] for r in recent) / len(recent)
        else:
            win_rate = 0
            avg_pnl = 0

        # 当前持仓盈亏
        open_lines = []
        for code, pos in positions.items():
            cur = _get_price(code)
            if cur:
                pnl = (cur - pos["buy_price"]) / pos["buy_price"] * 100
                icon = "🔴" if pnl >= 0 else "🟢"
                open_lines.append(f"  {icon} {pos['name']} {pnl:+.2f}%")

        # 近期平仓
        closed_lines = []
        for r in sorted(recent, key=lambda x: x["sell_date"], reverse=True)[:5]:
            icon = "🔴" if r["pnl_pct"] >= 0 else "🟢"
            closed_lines.append(f"  {icon} {r['name']} {r['pnl_pct']:+.2f}%  ({r['sell_date']})")

        open_str = "\n".join(open_lines) or "  无持仓"
        closed_str = "\n".join(closed_lines) or "  暂无记录"

        msg = (
            f"📊 模拟持仓周报 — {datetime.now().strftime('%Y-%m-%d')}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📈 历史胜率: {win_rate:.1f}%  平均盈亏: {avg_pnl:+.2f}%  (近{len(recent)}笔)\n\n"
            f"🗂 当前持仓 ({len(positions)}只)\n{open_str}\n\n"
            f"✅ 近期平仓\n{closed_str}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💡 以上为AI研报推荐的模拟持仓，仅供参考，不构成投资建议"
        )
        notifier.telegram.send(msg)
        logger.info("模拟持仓周报已推送")


portfolio_tracker = PortfolioTracker()
