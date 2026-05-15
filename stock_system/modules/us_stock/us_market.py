"""
美股大盘日报 + 盘前异动预警 + 财报日提醒
"""
import json
from datetime import datetime
from typing import Dict, List

from ai.analysis_engine import ai_engine
from modules.us_stock.us_data import (
    get_market_indices, get_premarket_movers,
    get_earnings_calendar, load_us_watchlist, US_STOCK_POOL
)
from utils.logger import logger


class USMarketAnalyzer:

    # ── 大盘日报 ──────────────────────────────────────────────
    def run_daily_report(self) -> Dict:
        """美股收盘后大盘日报"""
        logger.info("生成美股大盘日报...")
        try:
            indices = get_market_indices()
            if not indices:
                return {"status": "error", "error": "指数数据获取失败"}

            ai_summary = self._ai_market_summary(indices)
            return {"status": "success", "indices": indices, "ai_summary": ai_summary,
                    "date": datetime.now().strftime("%Y-%m-%d")}
        except Exception as e:
            logger.error(f"大盘日报失败: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    def _ai_market_summary(self, indices: Dict) -> str:
        system_prompt = "你是美股市场分析师，用简洁中文总结今日美股表现，200字以内。"
        user_prompt = f"今日美股指数数据：\n{json.dumps(indices, ensure_ascii=False, indent=2)}\n\n请生成简洁的收盘总结，包括：市场整体走势、主要驱动因素、明日关注点。"
        return ai_engine._call(system_prompt, user_prompt, max_tokens=600)

    def format_daily_report(self, data: Dict) -> str:
        if data.get("status") != "success":
            return f"❌ 大盘日报失败: {data.get('error')}"

        lines = [
            f"🌐 美股大盘日报  {data.get('date', '')}",
            "━━━━━━━━━━━━━━━━",
            "",
        ]
        for name, info in data.get("indices", {}).items():
            pct = info.get("change_pct", 0)
            icon = "🔴" if pct > 0 else ("🟢" if pct < 0 else "⚪")
            sign = "+" if pct > 0 else ""
            lines.append(f"{icon} {name}  {sign}{pct:.2f}%  {info.get('price', 0):,.2f}")

        summary = data.get("ai_summary", "")
        if summary:
            lines += ["", "📝 AI 市场点评", summary]

        return "\n".join(lines)

    # ── 盘前异动预警 ──────────────────────────────────────────
    def run_premarket_alert(self) -> Dict:
        """盘前异动预警（涨跌幅 ≥ 2%）"""
        logger.info("检查美股盘前异动...")
        try:
            watchlist = load_us_watchlist()
            pool = list(set(watchlist + US_STOCK_POOL[:20]))
            movers = get_premarket_movers(pool)
            return {"status": "success", "movers": movers,
                    "time": datetime.now().strftime("%H:%M")}
        except Exception as e:
            logger.error(f"盘前预警失败: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    def format_premarket_alert(self, data: Dict) -> str:
        if data.get("status") != "success":
            return f"❌ 盘前预警失败: {data.get('error')}"
        movers = data.get("movers", [])
        if not movers:
            return ""  # 无异动不推送

        lines = [
            f"⚡ 美股盘前异动  {data.get('time', '')}",
            "━━━━━━━━━━━━━━━━",
            "",
        ]
        for m in movers[:8]:
            pct = m["change_pct"]
            icon = "🔴" if pct > 0 else "🟢"
            sign = "+" if pct > 0 else ""
            lines.append(f"{icon} {m['symbol']}  {sign}{pct:.2f}%  盘前: ${m['pre_price']:.2f}")
            if m.get("name") and m["name"] != m["symbol"]:
                lines[-1] = f"{icon} {m['symbol']} ({m['name']})  {sign}{pct:.2f}%  盘前: ${m['pre_price']:.2f}"
        return "\n".join(lines)

    # ── 财报日提醒 ────────────────────────────────────────────
    def run_earnings_check(self) -> Dict:
        """检查自选股未来30天内的财报日"""
        logger.info("检查美股财报日历...")
        try:
            watchlist = load_us_watchlist()
            if not watchlist:
                return {"status": "success", "upcoming": []}
            upcoming = get_earnings_calendar(watchlist)
            return {"status": "success", "upcoming": upcoming}
        except Exception as e:
            logger.error(f"财报日检查失败: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    def format_earnings_alert(self, data: Dict) -> str:
        upcoming = data.get("upcoming", [])
        if not upcoming:
            return ""  # 无财报不推送

        lines = ["📅 财报日提醒（未来30天）", "━━━━━━━━━━━━━━━━", ""]
        for item in upcoming:
            days = (datetime.strptime(item["earnings_date"], "%Y-%m-%d").date()
                    - datetime.now().date()).days
            tag = "⚠️ 明天" if days == 1 else (f"  {days}天后" if days > 1 else "  今天")
            lines.append(f"{tag}  {item['symbol']}  财报日: {item['earnings_date']}")
        return "\n".join(lines)


us_market = USMarketAnalyzer()
