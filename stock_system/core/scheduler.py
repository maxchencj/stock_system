"""
定时任务调度器 - APScheduler
每日选股、板块分析、定时推送
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

from config.settings import config
from modules.stock_picker.picker import stock_picker
from modules.sector.analyzer import sector_analyzer
from notify.notifier import notifier
from utils.logger import logger


class TaskScheduler:
    """定时任务调度器"""

    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self.running = False

    def start(self):
        """启动调度器"""
        if self.running:
            logger.warning("调度器已在运行")
            return

        # 每日选股任务（交易日早上8:30）
        self.scheduler.add_job(
            self.daily_stock_pick_task,
            CronTrigger(hour=8, minute=30, day_of_week="mon-fri"),
            id="daily_stock_pick",
            name="每日选股",
            replace_existing=True
        )

        # 板块分析任务（交易日下午5:00）
        self.scheduler.add_job(
            self.daily_sector_analysis_task,
            CronTrigger(hour=17, minute=0, day_of_week="mon-fri"),
            id="daily_sector_analysis",
            name="板块分析",
            replace_existing=True
        )

        # 市场早报（每天早上8:00，包括周末）
        self.scheduler.add_job(
            self.morning_brief_task,
            CronTrigger(hour=8, minute=0),
            id="morning_brief",
            name="市场早报",
            replace_existing=True
        )

        self.scheduler.start()
        self.running = True
        logger.info("定时任务调度器已启动")
        self._print_jobs()

    def stop(self):
        """停止调度器"""
        if not self.running:
            return
        self.scheduler.shutdown()
        self.running = False
        logger.info("定时任务调度器已停止")

    def _print_jobs(self):
        """打印所有任务"""
        jobs = self.scheduler.get_jobs()
        logger.info(f"已注册定时任务 {len(jobs)} 个:")
        for job in jobs:
            logger.info(f"  - {job.name} (ID: {job.id}) | 下次运行: {job.next_run_time}")

    # ─────────────────── 任务函数 ───────────────────

    def daily_stock_pick_task(self):
        """每日选股任务"""
        logger.info("=" * 60)
        logger.info("执行定时任务: 每日选股")
        try:
            result = stock_picker.run_daily_scan()
            if result.get("status") == "success":
                report = stock_picker.format_daily_report(result)
                notifier.send_daily_picks(report)
                logger.info("每日选股任务完成，已推送报告")
            else:
                logger.warning(f"选股任务状态异常: {result.get('status')}")
        except Exception as e:
            logger.error(f"每日选股任务失败: {e}", exc_info=True)

    def daily_sector_analysis_task(self):
        """板块分析任务"""
        logger.info("=" * 60)
        logger.info("执行定时任务: 板块分析")
        try:
            result = sector_analyzer.run_daily_analysis()
            if result.get("status") == "success":
                report = sector_analyzer.format_daily_report(result)
                notifier.send_sector_report(report)
                logger.info("板块分析任务完成，已推送报告")
            else:
                logger.warning(f"板块分析状态异常: {result.get('status')}")
        except Exception as e:
            logger.error(f"板块分析任务失败: {e}", exc_info=True)

    def morning_brief_task(self):
        """市场早报任务"""
        logger.info("=" * 60)
        logger.info("执行定时任务: 市场早报")
        try:
            from ai.analysis_engine import ai_engine
            import akshare as ak

            # 获取市场数据
            try:
                # 获取上证指数最新数据
                sh_index = ak.stock_zh_index_daily(symbol="sh000001")
                latest = sh_index.tail(1).iloc[0]

                market_data = {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "index_close": float(latest.get('close', 0)),
                    "index_change": float(latest.get('pct_chg', 0)) if 'pct_chg' in latest else 0,
                    "volume": float(latest.get('volume', 0)),
                }
            except Exception as e:
                logger.warning(f"获取市场数据失败: {e}，使用默认数据")
                market_data = {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "message": "今日市场早报"
                }

            # 生成早报
            brief = ai_engine.generate_morning_brief(market_data)

            # 推送早报
            if brief:
                notifier.send_morning_brief(brief)
                logger.info("市场早报任务完成，已推送")
            else:
                logger.warning("市场早报生成失败")
        except Exception as e:
            logger.error(f"市场早报任务失败: {e}", exc_info=True)

    # ─────────────────── 手动触发 ───────────────────

    def trigger_stock_pick(self):
        """手动触发选股"""
        self.daily_stock_pick_task()

    def trigger_sector_analysis(self):
        """手动触发板块分析"""
        self.daily_sector_analysis_task()


# 单例
scheduler = TaskScheduler()
