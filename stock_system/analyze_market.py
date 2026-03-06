"""
大盘分析脚本 - 分析本周走势及下周预判
"""
import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

import akshare as ak
from datetime import datetime, timedelta
import json
from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger


def get_market_data():
    """获取大盘数据"""
    try:
        # 获取上证指数近期数据
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")

        logger.info(f"获取上证指数数据: {start_date} - {end_date}")
        sh_index = ak.stock_zh_index_daily(symbol="sh000001")

        # 获取最近30天数据
        recent_data = sh_index.tail(30).copy()

        # 转换日期为字符串
        if 'date' in recent_data.columns:
            recent_data['date'] = recent_data['date'].astype(str)

        # 计算本周数据（最近5个交易日）
        week_data = sh_index.tail(5).copy()
        if 'date' in week_data.columns:
            week_data['date'] = week_data['date'].astype(str)

        latest = recent_data.iloc[-1].to_dict()

        return {
            "recent_30days": recent_data.to_dict('records'),
            "this_week": week_data.to_dict('records'),
            "latest": latest
        }
    except Exception as e:
        logger.error(f"获取大盘数据失败: {e}")
        return None


def analyze_market_trend(market_data):
    """AI分析大盘走势"""
    system_prompt = """你是资深的A股市场分析师，擅长技术分析和趋势研判。
请根据上证指数的K线数据，分析本周市场表现，并对下周走势做出预判。
分析要专业、客观，有理有据。"""

    week_data = market_data["this_week"]
    recent_data = market_data["recent_30days"]
    latest = market_data["latest"]

    user_prompt = f"""请分析上证指数走势：

【最新行情】
日期: {latest.get('date', 'N/A')}
收盘: {latest.get('close', 'N/A')}
涨跌幅: {latest.get('pct_chg', 'N/A')}%
成交量: {latest.get('volume', 'N/A')}
成交额: {latest.get('amount', 'N/A')}

【本周数据（最近5个交易日）】
{json.dumps(week_data, ensure_ascii=False, indent=2)}

【近30日数据】
{json.dumps(recent_data[-10:], ensure_ascii=False, indent=2)}

请生成完整的市场分析报告，包含：

📊 **本周市场回顾**
- 本周大盘整体表现（涨跌幅、成交量变化）
- 关键技术位分析（支撑位、压力位）
- 市场情绪判断（多空力量对比）

📈 **技术面分析**
- 均线系统（5日、10日、20日、60日均线）
- 成交量分析（量价配合情况）
- 技术指标（MACD、RSI等，如果能从数据推断）

🔮 **下周走势预判**
- 大盘方向预测（看多/看空/震荡）
- 关键点位预测（支撑位、压力位）
- 概率评估（上涨/下跌/震荡的概率）

💡 **操作建议**
- 仓位建议（重仓/半仓/轻仓/空仓）
- 板块建议（重点关注哪些板块）
- 风险提示

⚠️ **风险因素**
- 需要关注的风险点
- 可能的黑天鹅事件

报告要求：
1. 数据驱动，有理有据
2. 语言专业但易懂
3. 字数1000-1500字
4. 结论明确，可操作性强
"""

    logger.info("正在调用AI分析大盘...")
    result = ai_engine._call(system_prompt, user_prompt, max_tokens=3000)
    return result


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("📊 开始分析本周大盘走势及下周预判")
    logger.info("=" * 80)

    # 1. 获取市场数据
    market_data = get_market_data()
    if not market_data:
        logger.error("无法获取市场数据，分析终止")
        return

    logger.info(f"✅ 成功获取市场数据")
    logger.info(f"   最新收盘: {market_data['latest'].get('close', 'N/A')}")
    logger.info(f"   涨跌幅: {market_data['latest'].get('pct_chg', 'N/A')}%")

    # 2. AI分析
    analysis = analyze_market_trend(market_data)

    # 3. 输出报告
    print("\n" + "=" * 80)
    print("📊 大盘分析报告")
    print("=" * 80)
    print(analysis)
    print("=" * 80)

    # 4. 推送报告
    logger.info("正在推送分析报告...")
    notifier.send_all("📊 本周大盘分析及下周预判", analysis)
    logger.info("✅ 推送完成")

    logger.info("✅ 分析完成")


if __name__ == "__main__":
    main()
