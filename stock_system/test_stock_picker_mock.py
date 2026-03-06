#!/usr/bin/env python3
"""
选股功能测试（使用模拟数据）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from notify.notifier import notifier
from datetime import datetime

def test_with_mock_data():
    """使用模拟数据测试选股推送"""
    print("=" * 60)
    print("📊 选股功能测试（模拟数据）")
    print("=" * 60)

    # 模拟选股结果
    mock_report = f"""
📊 【每日选股报告 {datetime.now().strftime('%Y-%m-%d')}】
扫描时间: {datetime.now().strftime('%H:%M:%S')}
候选股票: 5 只

🎯 AI精选推荐:

1. [600519] 贵州茅台 | 评分:88 | 强烈推荐
   📌 买入逻辑:
      • 技术面：MACD金叉，均线多头排列
      • 量能：成交量温和放大，量比2.3
      • 趋势：突破60日均线，上升趋势确立
   🛡️ 止损: 1850 | 目标: 2100 | 持仓周期: 1-2周

2. [000001] 平安银行 | 评分:82 | 推荐
   📌 买入逻辑:
      • 技术面：RSI从超卖区反弹，KDJ金叉
      • 估值：PE仅8倍，处于历史低位
      • 板块：银行板块资金流入明显
   🛡️ 止损: 12.5 | 目标: 15.0 | 持仓周期: 2-4周

3. [300750] 宁德时代 | 评分:79 | 推荐
   📌 买入逻辑:
      • 基本面：新能源车销量持续增长
      • 技术面：回调至20日均线获得支撑
      • 资金面：主力资金连续3日净流入
   🛡️ 止损: 180 | 目标: 220 | 持仓周期: 1-3周

🌐 市场研判:
大盘震荡上行，成交量温和放大。消费、新能源板块表现活跃，
建议关注低估值蓝筹和成长性标的。

🔥 重点关注板块: 消费、新能源、银行

📝 总结:
今日市场情绪回暖，个股活跃度提升。推荐标的均具备良好的
技术形态和基本面支撑，建议分批建仓，严格止损。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ 风险提示: 本报告仅供参考，不构成投资建议。
股市有风险，投资需谨慎！
    """

    print("\n生成的选股报告:")
    print(mock_report)
    print("\n" + "=" * 60)

    # 发送推送
    print("\n正在发送推送到微信...")
    try:
        success = notifier.pushplus.send(
            "📊 每日选股报告（测试）",
            mock_report
        )
        if success:
            print("✅ 推送成功！请检查您的微信")
            print("\n💡 这是一个模拟数据的测试推送")
            print("   明天交易时间会推送真实的选股数据")
        else:
            print("❌ 推送失败")
    except Exception as e:
        print(f"❌ 推送异常: {e}")

    print("=" * 60)

if __name__ == "__main__":
    test_with_mock_data()
