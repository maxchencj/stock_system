#!/usr/bin/env python3
"""
PushPlus 推送测试脚本（详细版）
"""
import os
import requests
from datetime import datetime

# 从环境变量读取 token
PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN", "c01431a12ea64a30ad71954c2442cc9a").strip()

def test_pushplus_direct():
    """直接调用 PushPlus API 测试"""
    print("=" * 60)
    print("📱 测试 PushPlus 微信推送（直接调用 API）")
    print("=" * 60)
    print(f"Token: {PUSHPLUS_TOKEN[:10]}...{PUSHPLUS_TOKEN[-10:]}")
    print()

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

    # PushPlus API
    api_url = "http://www.pushplus.plus/send"
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "txt"
    }

    try:
        print("正在发送推送...")
        response = requests.post(api_url, json=data, timeout=10)
        print(f"HTTP 状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        print()

        if response.status_code == 200:
            result = response.json()
            if result.get("code") == 200:
                print("✅ 推送成功！请检查您的微信")
                print()
                print("💡 提示:")
                print("   • 打开微信，查找 'pushplus推送加' 公众号")
                print("   • 应该会收到一条测试消息")
                return True
            else:
                print(f"❌ 推送失败: {result.get('msg', '未知错误')}")
                print()
                print("💡 可能的原因:")
                print("   1. Token 不正确")
                print("   2. 未关注 PushPlus 公众号")
                print("   3. Token 已过期")
                return False
        else:
            print(f"❌ HTTP 请求失败: {response.status_code}")
            return False

    except requests.exceptions.Timeout:
        print("❌ 请求超时，请检查网络连接")
        return False
    except Exception as e:
        print(f"❌ 推送异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        print("=" * 60)

if __name__ == "__main__":
    test_pushplus_direct()
