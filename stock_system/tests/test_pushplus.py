#!/usr/bin/env python3
"""
PushPlus 推送测试脚本
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from notify.notifier import notifier
from datetime import datetime

def test_pushplus():
    """测试 PushPlus 推送"""
    print("=" * 60)
    print("📱 测试 PushPlus 微信推送...")
    print("=" * 60)

    # 测试消息
    title = "🎉 股票智能分析系统 - 测试推送"
    content = f"""
【系统测试消息】

✅ 您的股票智能分析系统已成功启动！

📊 系统信息:
• 启动时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
• Web Dashboard: http://localhost:8888
• AI 引擎: Claude (Anthropic)
• 数据源: AKShare

🎯 功能模块:
✓ 每日选股扫描
✓ 实时监控预警
✓ 板块轮动分析
✓ 微信推送通知

📅 定时任务:
• 市场早报: 每日 08:00
• 每日选股: 每日 08:30
• 板块分析: 每日 17:00

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

如果您收到这条消息，说明推送功能正常！

系统将在每个交易日自动为您推送分析报告。

祝投资顺利！📈
    """

    # 发送推送
    try:
        success = notifier.pushplus.send(title, content)
        if success:
            print("✅ 推送成功！请检查您的微信")
            print("💡 提示: 如果没收到，请检查:")
            print("   1. PushPlus token 是否正确")
            print("   2. 是否关注了 PushPlus 公众号")
            print("   3. 网络连接是否正常")
        else:
            print("❌ 推送失败，请检查日志")
    except Exception as e:
        print(f"❌ 推送异常: {e}")

    print("=" * 60)

if __name__ == "__main__":
    test_pushplus()
