"""
测试实时行情推送 - 腾讯数据源 + Telegram
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime
from data.data_service import market_service
from notify.notifier import notifier
from utils.logger import logger


def test_realtime_push():
    """测试实时行情推送"""
    print("=" * 60)
    print("测试实时行情推送（腾讯数据源 + Telegram）")
    print("=" * 60)

    # 1. 读取关注列表
    watchlist_file = "data/watchlist.txt"
    watch_codes = []

    try:
        if os.path.exists(watchlist_file):
            with open(watchlist_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # 只取代码部分，去掉注释
                        code = line.split('#')[0].strip()
                        if code:
                            watch_codes.append(code)
            print(f"\n✓ 读取关注列表: {len(watch_codes)} 只股票")
            print(f"  股票代码: {', '.join(watch_codes)}")
        else:
            print(f"\n✗ 关注列表文件不存在: {watchlist_file}")
            # 使用默认列表
            watch_codes = ["600519", "601318", "000858", "600036", "300750"]
            print(f"  使用默认列表: {', '.join(watch_codes)}")
    except Exception as e:
        print(f"\n✗ 读取关注列表失败: {e}")
        return

    # 2. 从腾讯获取实时行情
    print("\n" + "-" * 60)
    print("步骤1: 从腾讯财经获取实时行情...")
    print("-" * 60)

    try:
        df = market_service.get_realtime_quotes(watch_codes)

        if df.empty:
            print("✗ 未获取到数据")
            return

        print(f"✓ 成功获取 {len(df)} 只股票的实时行情\n")

        # 显示数据
        for _, row in df.iterrows():
            code = row.get('code', '')
            name = row.get('name', '')
            price = row.get('price', 0)
            change_pct = row.get('change_pct', 0)
            volume_ratio = row.get('volume_ratio', 0)

            sign = "+" if change_pct > 0 else ""
            print(f"  {name}({code}): {price:.2f}  {sign}{change_pct:.2f}%  量比:{volume_ratio:.2f}")

    except Exception as e:
        print(f"✗ 获取行情数据失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 3. 格式化推送内容
    print("\n" + "-" * 60)
    print("步骤2: 格式化推送内容...")
    print("-" * 60)

    try:
        now = datetime.now()
        lines = [
            f"⏰ {now.strftime('%H:%M')} 实时行情测试",
            f"━━━━━━━━━━━━━━━━",
            ""
        ]

        # 按涨跌幅排序
        df = df.sort_values('change_pct', ascending=False)

        for _, row in df.iterrows():
            code = row.get('code', '')
            name = row.get('name', '')
            price = row.get('price', 0)
            change_pct = row.get('change_pct', 0)
            volume_ratio = row.get('volume_ratio', 0)

            # 涨跌标识
            if change_pct > 0:
                icon = "🔴"
                sign = "+"
            elif change_pct < 0:
                icon = "🟢"
                sign = ""
            else:
                icon = "⚪"
                sign = ""

            lines.append(f"{icon} {name}({code})")
            lines.append(f"   价格: {price:.2f}  {sign}{change_pct:.2f}%")
            if volume_ratio > 0:
                lines.append(f"   量比: {volume_ratio:.2f}")
            lines.append("")

        report = "\n".join(lines)
        print("✓ 推送内容格式化完成\n")
        print("推送内容预览:")
        print(report)

    except Exception as e:
        print(f"✗ 格式化内容失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 4. 推送到 Telegram
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
    test_realtime_push()
