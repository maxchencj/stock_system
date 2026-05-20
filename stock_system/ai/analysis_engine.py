"""
AI 分析引擎 - 使用 DeepSeek API (OpenAI 兼容)
综合研判 + 报告生成
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from openai import OpenAI

from config.settings import config
from utils.logger import logger

_USAGE_FILE = Path(__file__).parent.parent / "data" / "api_usage.json"


def _record_tokens(prompt_tokens: int, completion_tokens: int):
    """记录 API token 用量到 data/api_usage.json"""
    try:
        _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(_USAGE_FILE) as f:
                usage = json.load(f)
        except Exception:
            usage = {"daily": {}, "total": {"calls": 0, "total_tokens": 0}}

        today = datetime.now().strftime("%Y-%m-%d")
        day = usage.setdefault("daily", {}).setdefault(today, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        day["calls"] += 1
        day["prompt_tokens"] += prompt_tokens
        day["completion_tokens"] += completion_tokens
        day["total_tokens"] += prompt_tokens + completion_tokens

        total = usage.setdefault("total", {"calls": 0, "total_tokens": 0})
        total["calls"] += 1
        total["total_tokens"] += prompt_tokens + completion_tokens

        with open(_USAGE_FILE, "w") as f:
            json.dump(usage, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"记录API用量失败: {e}")


class AIAnalysisEngine:
    """DeepSeek AI 分析引擎"""

    def __init__(self):
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
        self.client = OpenAI(
            api_key=config.ai.api_key,
            base_url=base_url
        )
        logger.info(f"AI 引擎已连接 DeepSeek: {base_url}")
        self.model = config.ai.model

    def _call(self, system_prompt: str, user_prompt: str,
               max_tokens: int = None, as_json: bool = False) -> str:
        """调用 DeepSeek API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens or config.ai.max_tokens,
                temperature=config.ai.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            # 记录 token 用量
            if response.usage:
                _record_tokens(response.usage.prompt_tokens, response.usage.completion_tokens)

            text = response.choices[0].message.content.strip()
            if as_json:
                # 提取JSON内容
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
            return text
        except Exception as e:
            logger.error(f"AI 调用失败: {e}")
            return ""

    # ─────────────────── 选股分析 ───────────────────
    def analyze_stock_picks(self, stocks_data: List[Dict]) -> Dict:
        """
        对筛选出的候选股票进行 AI 精选分析
        返回最终推荐列表+理由
        """
        system_prompt = """你是一位专业的A股量化分析师，擅长技术分析和基本面分析。
请根据提供的股票数据，从候选股中精选出最具潜力的投资标的。
分析需客观、专业，指出具体的买入逻辑和风险点。
输出必须是合法的JSON格式。"""

        stocks_json = json.dumps(stocks_data, ensure_ascii=False, indent=2)
        user_prompt = f"""以下是今日候选股票数据（已经过量化初步筛选）：

{stocks_json}

请对这些股票进行深度分析，输出JSON格式：
{{
  "top_picks": [
    {{
      "code": "股票代码",
      "name": "股票名称",
      "score": 85,
      "recommendation": "强烈推荐/推荐/谨慎推荐",
      "buy_reason": "买入逻辑（3-5点）",
      "risk_warning": "风险提示",
      "target_price": "目标价位",
      "stop_loss": "止损价位",
      "hold_period": "建议持仓周期"
    }}
  ],
  "market_outlook": "整体市场研判",
  "sector_focus": ["重点关注板块"],
  "summary": "今日选股总结"
}}

精选不超过5只，要求有明确的技术形态支撑。"""

        result = self._call(system_prompt, user_prompt, as_json=True)
        try:
            return json.loads(result)
        except Exception:
            logger.error(f"解析选股AI结果失败: {result[:200]}")
            return {"top_picks": [], "summary": result}

    # ─────────────────── 监控信号分析 ───────────────────
    def analyze_monitor_signal(self, stock_info: Dict, signal_type: str) -> Dict:
        """
        分析监控触发的买卖信号
        signal_type: 'buy' | 'sell' | 'alert'
        """
        system_prompt = """你是A股交易信号分析专家。
根据股票的实时数据和技术指标，对触发的交易信号进行快速研判。
输出简洁、可执行的建议，必须是JSON格式。"""

        user_prompt = f"""股票信号触发通知：

信号类型: {signal_type}
股票数据:
{json.dumps(stock_info, ensure_ascii=False, indent=2)}

请快速研判并输出JSON：
{{
  "signal_valid": true/false,
  "confidence": "高/中/低",
  "action": "立即操作/观察等待/忽略",
  "analysis": "信号分析（100字内）",
  "entry_price": "建议介入价位",
  "stop_loss": "止损价位",
  "take_profit": "止盈价位",
  "urgency": "紧急/普通"
}}"""

        result = self._call(system_prompt, user_prompt, max_tokens=800, as_json=True)
        try:
            return json.loads(result)
        except Exception:
            return {"signal_valid": False, "analysis": result, "confidence": "低"}

    # ─────────────────── 板块分析 ───────────────────
    def analyze_sectors(self, sector_data: List[Dict], money_flow: List[Dict]) -> Dict:
        """
        板块轮动分析 + 资金流向研判
        """
        system_prompt = """你是A股板块轮动分析专家，熟悉各行业板块的轮动规律和资金流向特征。
请结合板块表现和资金流向，判断当前市场热点和下一步轮动方向。
输出必须是合法的JSON格式。"""

        user_prompt = f"""今日板块行情数据：
{json.dumps(sector_data[:20], ensure_ascii=False, indent=2)}

资金流向数据：
{json.dumps(money_flow[:10], ensure_ascii=False, indent=2)}

请分析并输出JSON：
{{
  "hot_sectors": [
    {{
      "name": "板块名",
      "reason": "强势原因",
      "sustainability": "持续性评估",
      "representative_stocks": ["龙头股1", "龙头股2"]
    }}
  ],
  "rotation_signal": "轮动方向判断",
  "money_flow_analysis": "资金流向分析",
  "avoid_sectors": ["需要回避的板块"],
  "tomorrow_focus": ["明日重点关注板块"],
  "daily_report": "今日板块分析日报（200字）"
}}"""

        result = self._call(system_prompt, user_prompt, as_json=True)
        try:
            return json.loads(result)
        except Exception:
            logger.error(f"解析板块AI结果失败: {result[:200]}")
            return {"daily_report": result}

    # ─────────────────── 个股深度分析 ───────────────────
    def deep_analyze_stock(self, code: str, name: str,
                            kline_data: List[Dict], indicators: Dict,
                            money_flow: Optional[Dict] = None) -> str:
        """
        个股深度分析报告（完整版）
        """
        system_prompt = """你是专业的A股研究员，善于综合技术分析、资金面、市场情绪进行全面研判。
请生成专业、深入的个股分析报告，文字流畅，有理有据。"""

        kline_str = json.dumps(kline_data[-30:], ensure_ascii=False) if kline_data else "暂无"
        flow_str = json.dumps(money_flow, ensure_ascii=False) if money_flow else "暂无"

        user_prompt = f"""请对 [{code}] {name} 进行深度分析：

近30日K线数据（最新）:
{kline_str}

技术指标:
{json.dumps(indicators, ensure_ascii=False, indent=2)}

资金流向:
{flow_str}

请生成完整分析报告，包含：
1. 📊 技术面分析（趋势、均线、MACD、RSI、KDJ等）
2. 💰 资金面分析（主力资金动向）
3. 🎯 操作建议（买入/持有/卖出，附价位）
4. ⚠️ 风险提示
5. 📈 后市展望

报告字数800-1200字，专业且易懂。"""

        return self._call(system_prompt, user_prompt, max_tokens=2000)

    # ─────────────────── 市场早报 ───────────────────
    def generate_morning_brief(self, market_data: Dict) -> str:
        """生成每日市场早报"""
        system_prompt = """你是专业的A股市场播报员，每日为投资者提供简洁、有价值的市场早报。
语言简练，重点突出，500字以内。"""

        user_prompt = f"""请根据以下数据生成今日市场早报：

市场数据:
{json.dumps(market_data, ensure_ascii=False, indent=2)}

早报格式：
【今日市场早报 - {market_data.get('date', '今日')}】

📌 市场概况：...
🔥 热点板块：...
💡 今日关注：...
⚠️ 风险提示：...
🎯 操作策略：..."""

        return self._call(system_prompt, user_prompt, max_tokens=1000)


# 单例
ai_engine = AIAnalysisEngine()
