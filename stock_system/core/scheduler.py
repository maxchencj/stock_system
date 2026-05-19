"""
定时任务调度器 - APScheduler
每日选股、板块分析、定时推送
"""
import time
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

        # 涨停复盘（交易日晚上7:00）
        self.scheduler.add_job(
            self.daily_zt_analysis_task,
            CronTrigger(hour=19, minute=0, day_of_week="mon-fri"),
            id="daily_zt_analysis",
            name="涨停复盘",
            replace_existing=True
        )

        # 市场早报（仅周一到周五早上8:00）
        self.scheduler.add_job(
            self.morning_brief_task,
            CronTrigger(hour=8, minute=0, day_of_week="mon-fri"),
            id="morning_brief",
            name="市场早报",
            replace_existing=True
        )

        # 实时行情推送（交易日 9:15-11:30 和 13:00-15:00，每5分钟）
        self.scheduler.add_job(
            self.realtime_market_push_task,
            CronTrigger(hour="9-11", minute="15,20,25,30,35,40,45,50,55", day_of_week="mon-fri"),
            id="realtime_market_push_am",
            name="实时行情推送(上午)",
            replace_existing=True
        )
        self.scheduler.add_job(
            self.realtime_market_push_task,
            CronTrigger(hour="10,11", minute="0,5,10,15,20,25,30", day_of_week="mon-fri"),
            id="realtime_market_push_am2",
            name="实时行情推送(上午2)",
            replace_existing=True
        )
        self.scheduler.add_job(
            self.realtime_market_push_task,
            CronTrigger(hour="13,14", minute="0,5,10,15,20,25,30,35,40,45,50,55", day_of_week="mon-fri"),
            id="realtime_market_push_pm",
            name="实时行情推送(下午)",
            replace_existing=True
        )

        # ── 美股任务 ──────────────────────────────────────────
        # 每日热门推荐（20:00，盘前1.5小时）
        self.scheduler.add_job(
            self.us_daily_picks_task,
            CronTrigger(hour=20, minute=0, day_of_week="mon-fri"),
            id="us_daily_picks", name="美股每日推荐", replace_existing=True
        )
        # 盘前异动预警（20:30）
        self.scheduler.add_job(
            self.us_premarket_task,
            CronTrigger(hour=20, minute=30, day_of_week="mon-fri"),
            id="us_premarket", name="美股盘前异动", replace_existing=True
        )
        # 盘中实时推送（21:30-04:00，每15分钟，夏令时EDT）
        # 21:30-21:45（周一至周五）
        self.scheduler.add_job(
            self.us_realtime_task,
            CronTrigger(hour=21, minute="30,45", day_of_week="mon-fri"),
            id="us_realtime_21", name="美股盘中(21:30-45)", replace_existing=True
        )
        # 22:00-23:45（周一至周五）
        self.scheduler.add_job(
            self.us_realtime_task,
            CronTrigger(hour="22,23", minute="0,15,30,45", day_of_week="mon-fri"),
            id="us_realtime_2223", name="美股盘中(22-23点)", replace_existing=True
        )
        # 00:00-03:45（周二至周六）
        self.scheduler.add_job(
            self.us_realtime_task,
            CronTrigger(hour="0,1,2,3", minute="0,15,30,45", day_of_week="tue-sat"),
            id="us_realtime_0to3", name="美股盘中(0-3点)", replace_existing=True
        )
        # 04:00 收盘前最后一次
        self.scheduler.add_job(
            self.us_realtime_task,
            CronTrigger(hour=4, minute=0, day_of_week="tue-sat"),
            id="us_realtime_0400", name="美股盘中(04:00)", replace_existing=True
        )
        # 收盘大盘日报（04:30）
        self.scheduler.add_job(
            self.us_close_report_task,
            CronTrigger(hour=4, minute=30, day_of_week="tue-sat"),
            id="us_close_report", name="美股收盘日报", replace_existing=True
        )
        # 财报日提醒（每天 09:00）
        self.scheduler.add_job(
            self.us_earnings_task,
            CronTrigger(hour=9, minute=0, day_of_week="mon-fri"),
            id="us_earnings", name="美股财报日提醒", replace_existing=True
        )

        # 每日知识学习（每天 12:00，A股+美股各1个知识点）
        self.scheduler.add_job(
            self.daily_knowledge_task,
            CronTrigger(hour=12, minute=0),
            id="daily_knowledge", name="每日知识学习", replace_existing=True
        )

        # 每日投研推送（每天 12:30，A股+美股各3只）
        self.scheduler.add_job(
            self.daily_research_task,
            CronTrigger(hour=12, minute=30),
            id="daily_research", name="每日投研推送", replace_existing=True
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

    def daily_zt_analysis_task(self):
        """每日涨停复盘任务"""
        logger.info("执行定时任务: 涨停复盘")
        try:
            from modules.zt.zt_analyzer import zt_analyzer
            result = zt_analyzer.run_daily_analysis()
            msg = zt_analyzer.format_report(result)
            if msg:
                notifier.send_all("🔴 今日涨停复盘", msg)
                logger.info("涨停复盘已推送")
            else:
                logger.info("今日无涨停数据，跳过推送")
        except Exception as e:
            logger.error(f"涨停复盘任务失败: {e}", exc_info=True)

    # ─────────────────── 美股任务 ───────────────────

    def us_daily_picks_task(self):
        """美股每日热门推荐"""
        logger.info("执行美股每日推荐任务")
        try:
            from modules.us_stock.us_picker import us_picker
            result = us_picker.run_daily_picks()
            msg = us_picker.format_report(result)
            if msg:
                notifier.us.send(msg)
                logger.info("美股推荐已推送")
        except Exception as e:
            logger.error(f"美股推荐任务失败: {e}", exc_info=True)

    def us_premarket_task(self):
        """美股盘前异动预警"""
        logger.info("执行美股盘前异动检查")
        try:
            from modules.us_stock.us_market import us_market
            result = us_market.run_premarket_alert()
            msg = us_market.format_premarket_alert(result)
            if msg:
                notifier.us.send(msg)
                logger.info("美股盘前预警已推送")
        except Exception as e:
            logger.error(f"美股盘前任务失败: {e}", exc_info=True)

    def us_realtime_task(self):
        """美股盘中实时推送"""
        logger.info("执行美股实时行情推送")
        try:
            from modules.us_stock.us_monitor import us_monitor
            msg = us_monitor.run_realtime_push()
            if msg:
                notifier.us.send(msg)
        except Exception as e:
            logger.error(f"美股实时推送失败: {e}", exc_info=True)

    def us_close_report_task(self):
        """美股收盘大盘日报"""
        logger.info("执行美股收盘日报")
        try:
            from modules.us_stock.us_market import us_market
            result = us_market.run_daily_report()
            msg = us_market.format_daily_report(result)
            if msg:
                notifier.us.send(msg)
                logger.info("美股收盘日报已推送")
        except Exception as e:
            logger.error(f"美股收盘日报失败: {e}", exc_info=True)

    def us_earnings_task(self):
        """美股财报日提醒"""
        logger.info("执行美股财报日检查")
        try:
            from modules.us_stock.us_market import us_market
            result = us_market.run_earnings_check()
            msg = us_market.format_earnings_alert(result)
            if msg:
                notifier.us.send(msg)
                logger.info("财报日提醒已推送")
        except Exception as e:
            logger.error(f"美股财报检查失败: {e}", exc_info=True)

    def daily_knowledge_task(self):
        """每日知识学习推送：A股1个 + 美股1个知识点"""
        logger.info("执行每日知识学习推送任务")
        try:
            from modules.knowledge.knowledge_engine import a_knowledge
            a_knowledge.run_daily_push()
        except Exception as e:
            logger.error(f"A股知识推送失败: {e}", exc_info=True)
        time.sleep(3)
        try:
            from modules.knowledge.knowledge_engine import us_knowledge
            us_knowledge.run_daily_push()
        except Exception as e:
            logger.error(f"美股知识推送失败: {e}", exc_info=True)

    def daily_research_task(self):
        """每日投研推送：A股10只 + 美股10只"""
        logger.info("执行每日投研推送任务")
        try:
            from modules.research.research_engine import a_research
            a_research.run_daily_push()
        except Exception as e:
            logger.error(f"A股投研推送失败: {e}", exc_info=True)
        try:
            from modules.research.research_engine import us_research
            us_research.run_daily_push()
        except Exception as e:
            logger.error(f"美股投研推送失败: {e}", exc_info=True)

    def realtime_market_push_task(self):
        """实时行情推送任务"""
        now = datetime.now()
        hour = now.hour
        minute = now.minute

        # 只在交易时间内推送（9:15-11:30 和 13:00-15:00）
        am_session = (hour == 9 and minute >= 15) or (hour == 10) or (hour == 11 and minute <= 30)
        pm_session = (hour == 13) or (hour == 14)
        if not (am_session or pm_session):
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
        """从 watchlist.json 获取自选股列表"""
        try:
            import json
            with open("data/watchlist.json") as f:
                data = json.load(f)
            codes = list(data.get("stocks", {}).keys())
            if codes:
                return codes
        except Exception as e:
            logger.warning(f"读取watchlist.json失败: {e}")

        # 兜底：使用默认热门股票
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
