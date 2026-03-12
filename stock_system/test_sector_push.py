"""
测试板块轮动分析推送 - Telegram
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from modules.sector.analyzer import sector_analyzer
from notify.notifier import notifier
from utils.logger import logger


def test_sector_push():
    """测试板块分析推送"""
    print("=" * 60)
    print("测试板块轮动分析推送")
    print("=" * 60)

    # 1. 执行板块分析
    print("\n" + "-" * 60)
    print("步骤1: 执行板块分析...")
    print("-" * 60)

    try:
        result = sector_analyzer.run_daily_analysis()

        if result.get("status") != "success":
            print(f"✗ 板块分析失败: {result.get('status')}")
            if result.get("error"):
                print(f"  错误: {result['error']}")
            return

        print(f"✓ 板块分析完成")
        print(f"  分析板块数: {len(result.get('sectors', []))}")
        print(f"  资金流向数: {len(result.get('money_flow', []))}")
        print(f"  耗时: {result.get('elapsed_seconds', 0)}秒")

    except Exception as e:
        print(f"✗ 板块分析异常: {e}")
        import traceback
        traceback.print_exc()
        return

    # 2. 格式化报告
    print("\n" + "-" * 60)
    print("步骤2: 格式化报告...")
    print("-" * 60)

    try:
        report = sector_analyzer.format_daily_report(result)
        print("✓ 报告格式化完成\n")
        print("报告内容预览:")
        print(report)

    except Exception as e:
        print(f"✗ 格式化报告失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 3. 推送到 Telegram
    print("\n" + "-" * 60)
    print("步骤3: 推送到 Telegram...")
    print("-" * 60)

    try:
        if not notifier.telegram.enabled:
            print("✗ Telegram 未启用")
            print(f"  Token: {'已配置' if notifier.telegram.token else '未配置'}")
            print(f"  Chat ID: {'已配置' if notifier.telegram.chat_id else '未配置'}")
            return

        success = notifier.telegram.send(report)

        if success:
            print("✓ Telegram 推送成功！")
        else:
            print("✗ Telegram 推送失败，请检查日志")

    except Exception as e:
        print(f"✗ 推送失败: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    test_sector_push()
