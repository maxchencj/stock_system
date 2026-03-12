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

        # 每日选股任务（交易日早上9:45）
        self.scheduler.add_job(
            self.daily_stock_pick_task,
            CronTrigger(hour=9, minute=45, day_of_week="mon-fri"),
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

        # 实时行情推送（交易日9:30-15:00，每1分钟）
        self.scheduler.add_job(
            self.realtime_market_push_task,
            CronTrigger(hour="9-14", minute="*", day_of_week="mon-fri"),
            id="realtime_market_push",
            name="实时行情推送",
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
                try:
                    notifier.send_morning_brief(brief)
                    logger.info("市场早报任务完成，已推送")
                except Exception as push_error:
                    logger.error(f"市场早报推送失败: {push_error}", exc_info=True)
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

    def realtime_market_push_task(self):
        """实时行情推送任务"""
        now = datetime.now()
        hour = now.hour
        minute = now.minute

        # 只在交易时间内推送（9:30-15:00）
        if hour < 9 or (hour == 9 and minute < 30) or hour >= 15:
            return

        logger.info("执行实时行情推送")
        try:
            from data.data_service import market_service

            # 获取关注股票列表（可以从配置或数据库读取）
            # 这里先用一个示例列表，你可以根据需要修改
            watch_codes = self._get_watchlist()

            if not watch_codes:
                logger.warning("关注列表为空，跳过推送")
                return

            # 获取实时行情
            df = market_service.get_realtime_quotes(watch_codes)

            if df.empty:
                logger.warning("未获取到实时行情数据")
                return

            # 格式化推送内容
            report = self._format_realtime_report(df, now)

            # 推送到 Telegram
            notifier.telegram.send(report)
            logger.info(f"实时行情推送完成，共{len(df)}只股票")

        except Exception as e:
            logger.error(f"实时行情推送失败: {e}", exc_info=True)

    def _get_watchlist(self):
        """获取关注股票列表"""
        # 方法1: 从配置文件读取
        watchlist_file = "data/watchlist.txt"
        try:
            import os
            if os.path.exists(watchlist_file):
                codes = []
                with open(watchlist_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # 只取代码部分，去掉注释
                            code = line.split('#')[0].strip()
                            if code:
                                codes.append(code)
                if codes:
                    return codes
        except Exception as e:
            logger.warning(f"读取关注列表失败: {e}")

        # 方法2: 使用默认热门股票
        return [
            "600519",  # 贵州茅台
            "601318",  # 中国平安
            "000858",  # 五粮液
            "600036",  # 招商银行
            "300750",  # 宁德时代
            "002594",  # 比亚迪
            "600276",  # 恒瑞医药
            "000333",  # 美的集团
            "002415",  # 海康威视
            "600887",  # 伊利股份
        ]

    def _format_realtime_report(self, df, timestamp):
        """格式化实时行情报告"""
        lines = [
            f"⏰ {timestamp.strftime('%H:%M')} 实时行情",
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

        return "\n".join(lines)


# 单例
scheduler = TaskScheduler()
