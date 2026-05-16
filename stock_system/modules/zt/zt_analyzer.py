"""
每日涨停分析 - 涨停股池 + DeepSeek AI 原因分析
"""
import json
import akshare as ak
import pandas as pd
from datetime import datetime
from typing import Dict, List
from collections import Counter

from ai.analysis_engine import ai_engine
from utils.logger import logger


class ZTAnalyzer:

    def run_daily_analysis(self) -> Dict:
        """获取今日涨停股并 AI 分析"""
        date_str = datetime.now().strftime("%Y%m%d")
        logger.info(f"开始涨停分析，日期: {date_str}")
        try:
            df = ak.stock_zt_pool_em(date=date_str)
            if df is None or df.empty:
                return {"status": "no_data", "date": date_str}

            logger.info(f"今日涨停 {len(df)} 只")

            # 连板股（≥2板）
            multi_df = df[df["连板数"] >= 2].sort_values("连板数", ascending=False)

            # 板块分布
            sector_counts = Counter(df["所属行业"].tolist())
            top_sectors = sector_counts.most_common(8)

            # 传给 AI 的摘要数据（控制 token）
            summary = self._build_summary(df, multi_df, top_sectors)
            ai_analysis = self._ai_analyze(summary, date_str)

            return {
                "status": "success",
                "date": date_str,
                "total": len(df),
                "multi_board": multi_df.head(10).to_dict("records"),
                "top_sectors": top_sectors,
                "all_stocks": df[["代码","名称","连板数","所属行业","首次封板时间","炸板次数"]].to_dict("records"),
                "ai_analysis": ai_analysis,
            }
        except Exception as e:
            logger.error(f"涨停分析失败: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    def _build_summary(self, df: pd.DataFrame, multi_df: pd.DataFrame,
                       top_sectors: list) -> Dict:
        """构建给 AI 的精简摘要"""
        return {
            "total_zt": len(df),
            "top_sectors": [{"行业": s, "数量": c} for s, c in top_sectors],
            "multi_board_stocks": [
                {
                    "名称": r["名称"], "代码": r["代码"],
                    "连板数": int(r["连板数"]), "涨停统计": r["涨停统计"],
                    "所属行业": r["所属行业"],
                    "首次封板时间": r["首次封板时间"],
                    "最后封板时间": r["最后封板时间"],
                    "炸板次数": int(r["炸板次数"]),
                    "封板资金(万)": round(r["封板资金"] / 10000, 0),
                    "流通市值(亿)": round(r["流通市值"] / 1e8, 2),
                }
                for _, r in multi_df.head(15).iterrows()
            ],
            "single_board_sample": [
                {"名称": r["名称"], "所属行业": r["所属行业"],
                 "首次封板时间": r["首次封板时间"], "炸板次数": int(r["炸板次数"])}
                for _, r in df[df["连板数"] == 1].head(20).iterrows()
            ],
        }

    def _ai_analyze(self, summary: Dict, date_str: str) -> str:
        system_prompt = """你是顶级的A股涨停板研究员，有超过10年的复盘经验。
擅长通过涨停数据识别市场主线、板块联动逻辑、龙头效应和情绪传导路径。
分析要有深度、有逻辑，给出明确的操作参考。"""

        user_prompt = f"""今日（{date_str}）A股涨停数据如下：

{json.dumps(summary, ensure_ascii=False, indent=2)}

请按以下结构进行详细分析：

【一、今日市场情绪】
涨停家数、情绪强弱、与近期对比。

【二、主线题材解析】
逐一分析今日最强的2-3个板块，说明：
- 为什么今天这个板块涨停？（政策/消息/资金/技术面）
- 板块内龙头是哪只？
- 是第几次爆发？持续性如何？

【三、连板龙头精析】
对连板数≥3的个股逐一点评：涨停逻辑、封板强度（首次封板时间/炸板次数）、是否值得跟进。

【四、明日预判】
- 哪个板块最可能继续？理由是什么？
- 哪些连板股有望继续？
- 需要回避的风险点？

要求：分析详细深入，800字左右，像一份专业的晚间复盘报告。"""

        return ai_engine._call(system_prompt, user_prompt, max_tokens=4096)

    def format_report(self, data: Dict) -> str:
        """格式化推送内容"""
        if data.get("status") == "no_data":
            return ""  # 非交易日或数据未出，不推送
        if data.get("status") == "error":
            return f"❌ 涨停分析失败: {data.get('error')}"

        date = data["date"]
        total = data["total"]
        top_sectors = data["top_sectors"]
        multi = data["multi_board"]

        lines = [
            f"🔴 今日涨停复盘  {date[:4]}-{date[4:6]}-{date[6:]}",
            f"━━━━━━━━━━━━━━━━",
            f"涨停家数：{total} 只",
            "",
        ]

        # 热门板块
        if top_sectors:
            lines.append("🔥 热门板块")
            for sector, count in top_sectors[:6]:
                lines.append(f"  {sector}  {count}只")
            lines.append("")

        # 连板龙头
        if multi:
            lines.append("🚀 连板龙头")
            for r in multi[:8]:
                zb = int(r.get("连板数", 1))
                name = r.get("名称", "")
                code = r.get("代码", "")
                stat = r.get("涨停统计", "")
                industry = r.get("所属行业", "")
                zb_str = "🔥" * min(zb, 5) if zb >= 3 else f"{zb}板"
                lines.append(f"  {zb_str} {name}({code})  {industry}  [{stat}]")
            lines.append("")

        # AI 分析（去掉 Markdown 符号避免 Telegram 解析报错）
        ai = data.get("ai_analysis", "")
        if ai:
            import re
            ai = ai.replace("**", "").replace("__", "").replace("```", "")
            ai = re.sub(r"^#{1,4}\s*", "", ai, flags=re.MULTILINE)
            lines.append("🤖 AI 分析")
            lines.append(ai)

        return "\n".join(lines)


zt_analyzer = ZTAnalyzer()
