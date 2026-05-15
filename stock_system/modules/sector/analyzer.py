"""
板块分析模块 - 31个一级板块 + 资金流向 + 轮动追踪 + 每日报告
"""
from datetime import datetime
from typing import Dict, List
import pandas as pd

from config.settings import config
from data.data_service import sector_service, money_flow_service
from ai.analysis_engine import ai_engine
from utils.logger import logger


class SectorAnalysisModule:
    """板块分析模块"""

    def __init__(self):
        self.cfg = config.sector

    def run_daily_analysis(self) -> Dict:
        """
        执行每日板块分析
        流程: 获取板块行情 → 资金流向 → AI轮动分析 → 生成报告
        """
        logger.info("=" * 50)
        logger.info("开始每日板块分析...")
        start_time = datetime.now()

        result = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "analysis_time": start_time.strftime("%H:%M:%S"),
            "sectors": [],
            "money_flow": [],
            "ai_analysis": {},
            "status": "success"
        }

        try:
            # Step 1: 获取板块实时行情
            logger.info("Step1: 获取板块行情...")
            sector_df = sector_service.get_sector_realtime()
            if sector_df.empty:
                result["status"] = "no_data"
                return result

            # 标准化列名
            col_map = {
                "板块名称": "name", "板块代码": "code",
                "最新价": "price", "涨跌幅": "change_pct",
                "总市值": "market_cap", "换手率": "turnover_rate",
                "上涨家数": "up_count", "下跌家数": "down_count",
                "领涨股票": "leader_stock", "领涨股票涨跌幅": "leader_change_pct"
            }
            sector_df = sector_df.rename(columns={k: v for k, v in col_map.items() if k in sector_df.columns})

            # 数值转换
            for col in ["price", "change_pct", "market_cap", "turnover_rate"]:
                if col in sector_df.columns:
                    sector_df[col] = pd.to_numeric(sector_df[col], errors="coerce")

            # 按涨跌幅排序
            if "change_pct" in sector_df.columns:
                sector_df = sector_df.sort_values("change_pct", ascending=False)

            result["sectors"] = sector_df.head(30).to_dict("records")
            logger.info(f"获取板块 {len(sector_df)} 个")

            # Step 2: 获取资金流向
            logger.info("Step2: 获取资金流向...")
            flow_df = money_flow_service.get_sector_money_flow()
            if not flow_df.empty:
                flow_col_map = {
                    "行业": "sector", "净额": "today_flow",
                    "行业-涨跌幅": "change_pct", "流入资金": "inflow",
                    "流出资金": "outflow", "领涨股": "top_stock",
                    "公司家数": "company_count"
                }
                flow_df = flow_df.rename(columns={k: v for k, v in flow_col_map.items() if k in flow_df.columns})
                result["money_flow"] = flow_df.head(20).to_dict("records")
                logger.info(f"获取资金流向 {len(flow_df)} 条")

            # Step 3: AI轮动分析
            logger.info("Step3: AI板块轮动分析...")
            sector_data = result["sectors"][:20]
            money_data = result["money_flow"][:10]
            result["ai_analysis"] = ai_engine.analyze_sectors(sector_data, money_data)

            elapsed = (datetime.now() - start_time).total_seconds()
            result["elapsed_seconds"] = round(elapsed, 1)
            logger.info(f"板块分析完成，耗时 {elapsed:.1f}s")

        except Exception as e:
            logger.error(f"板块分析异常: {e}", exc_info=True)
            result["status"] = "error"
            result["error"] = str(e)

        return result

    def format_daily_report(self, analysis_result: Dict) -> str:
        """格式化每日板块报告（用于推送）"""
        date = analysis_result.get("date", "今日")
        ai_analysis = analysis_result.get("ai_analysis", {})
        sectors = analysis_result.get("sectors", [])

        lines = [
            f"📈 【板块分析日报 {date}】",
            f"分析时间: {analysis_result.get('analysis_time', '')}",
            ""
        ]

        # 涨幅榜
        if sectors:
            lines.append("🔥 涨幅榜 TOP5:")
            for i, sec in enumerate(sectors[:5], 1):
                name = sec.get("name", "")
                change = sec.get("change_pct", 0)
                leader = sec.get("leader_stock", "")
                lines.append(f"{i}. {name} +{change:.2f}% | 龙头: {leader}")
            lines.append("")

        # AI热点板块
        hot_sectors = ai_analysis.get("hot_sectors", [])
        if hot_sectors:
            lines.append("🎯 AI识别热点板块:")
            for i, hot in enumerate(hot_sectors, 1):
                lines.append(f"{i}. {hot.get('name')}")
                lines.append(f"   📌 {hot.get('reason')}")
                lines.append(f"   🔮 持续性: {hot.get('sustainability')}")
                if hot.get("representative_stocks"):
                    lines.append(f"   🏆 龙头: {', '.join(hot['representative_stocks'][:3])}")
                lines.append("")

        # 轮动信号
        if ai_analysis.get("rotation_signal"):
            lines.append(f"🔄 轮动信号: {ai_analysis['rotation_signal']}")
            lines.append("")

        # 资金流向
        if ai_analysis.get("money_flow_analysis"):
            lines.append(f"💰 资金流向: {ai_analysis['money_flow_analysis']}")
            lines.append("")

        # 明日关注
        if ai_analysis.get("tomorrow_focus"):
            lines.append(f"📅 明日关注: {', '.join(ai_analysis['tomorrow_focus'])}")
            lines.append("")

        # 日报总结
        if ai_analysis.get("daily_report"):
            lines.append(f"📝 {ai_analysis['daily_report']}")

        return "\n".join(lines)

    def get_sector_stocks(self, sector_name: str) -> List[Dict]:
        """获取板块成分股"""
        try:
            df = sector_service.get_sector_stocks(sector_name)
            if df.empty:
                return []
            return df.to_dict("records")
        except Exception as e:
            logger.error(f"获取{sector_name}成分股失败: {e}")
            return []


# 单例
sector_analyzer = SectorAnalysisModule()
