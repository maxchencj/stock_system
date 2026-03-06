"""
主程序入口
股票智能分析系统 - 启动脚本
"""
import sys
import signal
import argparse
from threading import Thread

from config.settings import config
from core.scheduler import scheduler
from modules.monitor.monitor import monitor
from web.app import start_web_server
from utils.logger import logger


class StockSystem:
    """股票智能分析系统主类"""

    def __init__(self):
        self.web_thread = None

    def start(self, enable_web: bool = True, enable_scheduler: bool = True, enable_monitor: bool = False):
        """启动系统"""
        logger.info("=" * 60)
        logger.info("🚀 股票智能分析系统启动中...")
        logger.info("=" * 60)

        # 启动定时任务调度器
        if enable_scheduler:
            scheduler.start()

        # 启动监控模块
        if enable_monitor:
            monitor.start()

        # 启动Web服务（在独立线程）
        if enable_web:
            self.web_thread = Thread(target=start_web_server, daemon=True)
            self.web_thread.start()
            logger.info(f"Web Dashboard: http://{config.web.host}:{config.web.port}")

        logger.info("=" * 60)
        logger.info("✅ 系统启动完成")
        logger.info("=" * 60)
        logger.info("按 Ctrl+C 停止系统")

    def stop(self):
        """停止系统"""
        logger.info("=" * 60)
        logger.info("🛑 系统停止中...")
        scheduler.stop()
        monitor.stop()
        logger.info("✅ 系统已停止")
        logger.info("=" * 60)


def signal_handler(sig, frame):
    """信号处理（Ctrl+C）"""
    logger.info("\n收到停止信号，正在关闭系统...")
    system.stop()
    sys.exit(0)


# 全局实例
system = StockSystem()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="股票智能分析系统")
    parser.add_argument("--no-web", action="store_true", help="不启动Web服务")
    parser.add_argument("--no-scheduler", action="store_true", help="不启动定时任务")
    parser.add_argument("--enable-monitor", action="store_true", help="启动时开启监控")
    parser.add_argument("--test-picker", action="store_true", help="测试选股模块")
    parser.add_argument("--test-sector", action="store_true", help="测试板块分析")
    args = parser.parse_args()

    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 测试模式
    if args.test_picker:
        logger.info("测试模式: 选股模块")
        from modules.stock_picker.picker import stock_picker
        result = stock_picker.run_daily_scan()
        report = stock_picker.format_daily_report(result)
        print("\n" + "=" * 60)
        print(report)
        print("=" * 60)
        return

    if args.test_sector:
        logger.info("测试模式: 板块分析")
        from modules.sector.analyzer import sector_analyzer
        result = sector_analyzer.run_daily_analysis()
        report = sector_analyzer.format_daily_report(result)
        print("\n" + "=" * 60)
        print(report)
        print("=" * 60)
        return

    # 正常启动（监控模块默认开启）
    system.start(
        enable_web=not args.no_web,
        enable_scheduler=not args.no_scheduler,
        enable_monitor=True
    )

    # 保持主线程运行
    try:
        while True:
            signal.pause()
    except AttributeError:
        # Windows 不支持 signal.pause()
        import time
        while True:
            time.sleep(1)


if __name__ == "__main__":
    main()
