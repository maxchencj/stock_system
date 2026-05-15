"""
美股每日热门推荐 - DeepSeek AI 精选
"""
import json
from datetime import datetime
from typing import Dict, List

from ai.analysis_engine import ai_engine
from modules.us_stock.us_data import get_top_movers, US_STOCK_POOL
from utils.logger import logger


class USStockPicker:

    def run_daily_picks(self) -> Dict:
        """每日热门美股推荐主流程"""
        logger.info("开始美股每日热门推荐...")
        try:
            movers = get_top_movers(US_STOCK_POOL, top_n=15)
            gainers = movers.get("gainers", [])
            losers = movers.get("losers", [])

            if not gainers:
                return {"status": "error", "error": "未获取到行情数据"}

            candidates = gainers[:10] + losers[:5]
            ai_result = self._ai_analyze(candidates)

            return {
                "status": "success",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "gainers": gainers[:5],
                "losers": losers[:3],
                "ai_picks": ai_result,
            }
        except Exception as e:
            logger.error(f"美股推荐失败: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    def _ai_analyze(self, candidates: List[Dict]) -> Dict:
        system_prompt = """你是专业的美股分析师，熟悉纳斯达克和纽交所市场。
根据今日涨跌数据，精选最具关注价值的股票，给出简洁的理由。
必须输出合法JSON。"""

        user_prompt = f"""今日美股涨跌数据：
{json.dumps(candidates, indent=2)}

请精选3-5只最值得关注的股票，输出JSON：
{{
  "picks": [
    {{
      "symbol": "代码",
      "name": "公司名",
      "change_pct": 涨跌幅,
      "reason": "关注理由（50字内）",
      "direction": "看多/看空/观察"
    }}
  ],
  "market_sentiment": "今日美股整体情绪（一句话）",
  "key_theme": "今日主线题材"
}}"""

        result = ai_engine._call(system_prompt, user_prompt, max_tokens=1000, as_json=True)
        try:
            return json.loads(result)
        except Exception:
            return {"picks": [], "market_sentiment": result}

    def format_report(self, data: Dict) -> str:
        """格式化推送内容"""
        if data.get("status") != "success":
            return f"❌ 美股推荐失败: {data.get('error')}"

        ai = data.get("ai_picks", {})
        date = data.get("date", "今日")
        lines = [
            f"🇺🇸 美股热门推荐  {date}",
            "━━━━━━━━━━━━━━━━",
            "",
        ]

        sentiment = ai.get("market_sentiment", "")
        theme = ai.get("key_theme", "")
        if sentiment:
            lines.append(f"📊 市场情绪：{sentiment}")
        if theme:
            lines.append(f"🔥 今日主线：{theme}")
        lines.append("")

        for pick in ai.get("picks", []):
            pct = pick.get("change_pct", 0)
            icon = "🔴" if pct > 0 else "🟢"
            direction_icon = {"看多": "⬆️", "看空": "⬇️", "观察": "👀"}.get(pick.get("direction"), "")
            lines.append(f"{icon} {pick.get('symbol')}  {'+' if pct > 0 else ''}{pct:.2f}%  {direction_icon}")
            lines.append(f"   {pick.get('reason', '')}")
            lines.append("")

        if data.get("gainers"):
            lines.append("📈 今日涨幅榜 TOP5")
            for s in data["gainers"][:5]:
                lines.append(f"  {s['symbol']}  +{s['change_pct']:.2f}%  ${s['price']:.2f}")
        lines.append("")
        if data.get("losers"):
            lines.append("📉 今日跌幅榜 TOP3")
            for s in data["losers"][:3]:
                lines.append(f"  {s['symbol']}  {s['change_pct']:.2f}%  ${s['price']:.2f}")

        return "\n".join(lines)


us_picker = USStockPicker()
