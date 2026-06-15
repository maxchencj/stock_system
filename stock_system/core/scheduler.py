"""
定时任务调度器 - APScheduler
每日选股、板块分析、定时推送
"""
import time
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

_DATA_DIR = Path(__file__).parent.parent / "data"

from config.settings import config
from modules.stock_picker.picker import stock_picker
from modules.sector.analyzer import sector_analyzer
from modules.github_trending.trending_engine import github_trending_engine
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


        # 实时行情推送（交易日 9:15-11:30，每5分钟，无重叠）
        # 9:15-9:55（每小时 :15,:20,:25,:30,:35,:40,:45,:50,:55）
        self.scheduler.add_job(
            self.realtime_market_push_task,
            CronTrigger(hour="9", minute="15,20,25,30,35,40,45,50,55", day_of_week="mon-fri"),
            id="realtime_market_push_am",
            name="实时行情推送(上午9点)",
            replace_existing=True
        )
        # 10:00-10:55
        self.scheduler.add_job(
            self.realtime_market_push_task,
            CronTrigger(hour="10", minute="0,5,10,15,20,25,30,35,40,45,50,55", day_of_week="mon-fri"),
            id="realtime_market_push_am2",
            name="实时行情推送(上午10点)",
            replace_existing=True
        )
        # 11:00-11:30
        self.scheduler.add_job(
            self.realtime_market_push_task,
            CronTrigger(hour="11", minute="0,5,10,15,20,25,30", day_of_week="mon-fri"),
            id="realtime_market_push_am3",
            name="实时行情推送(上午11点)",
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

        # 财经早报（交易日 8:00）
        self.scheduler.add_job(
            self.morning_news_task,
            CronTrigger(hour=8, minute=0, day_of_week="mon-fri"),
            id="morning_news", name="财经早报", replace_existing=True
        )

        # 自选股每日跟踪（每天晚8:30，交易日推日报，周末推周报）
        self.scheduler.add_job(
            self.watchlist_track_task,
            CronTrigger(hour=20, minute=30),
            id="watchlist_track", name="自选股跟踪", replace_existing=True
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

        # 系统心跳监控（每天 7:00 推送系统状态）
        self.scheduler.add_job(
            self.heartbeat_task,
            CronTrigger(hour=7, minute=0),
            id="heartbeat", name="系统心跳监控", replace_existing=True
        )

        # ── Phase 2：监控增强 ──────────────────────────────

        # 宏观经济日历（每周一 8:45）
        self.scheduler.add_job(
            self.macro_calendar_task,
            CronTrigger(hour=8, minute=45, day_of_week="mon"),
            id="macro_calendar", name="宏观经济日历", replace_existing=True
        )

        # 打新提醒（每天 08:45）
        self.scheduler.add_job(
            self.ipo_reminder_task,
            CronTrigger(hour=8, minute=45),
            id="ipo_reminder", name="打新提醒", replace_existing=True
        )


        # ── Phase 4：复盘 & 持仓 ──────────────────────────────

        # 每日复盘模板（交易日 21:00）
        self.scheduler.add_job(
            self.daily_review_task,
            CronTrigger(hour=21, minute=0, day_of_week="mon-fri"),
            id="daily_review", name="每日复盘", replace_existing=True
        )

        # GitHub 科技雷达（每天 8:40）
        self.scheduler.add_job(
            self.github_trending_task,
            CronTrigger(hour=8, minute=40),
            id="github_trending_daily",
            name="GitHub科技雷达",
            replace_existing=True
        )

        # ── Phase 3：数据增强 ──────────────────────────────

        # ── 模拟仓信号扫描（交易时段，每5分钟）──────────────
        self.scheduler.add_job(
            self.sim_signal_task,
            CronTrigger(hour="9", minute="30,35,40,45,50,55", day_of_week="mon-fri"),
            id="sim_0930", name="模拟仓信号(09:30-09:55)", replace_existing=True
        )
        self.scheduler.add_job(
            self.sim_signal_task,
            CronTrigger(hour="10", minute="0,5,10,15,20,25,30,35,40,45,50,55", day_of_week="mon-fri"),
            id="sim_1000", name="模拟仓信号(10:00-10:55)", replace_existing=True
        )
        self.scheduler.add_job(
            self.sim_signal_task,
            CronTrigger(hour="11", minute="0,5,10,15,20,25,30", day_of_week="mon-fri"),
            id="sim_1100", name="模拟仓信号(11:00-11:30)", replace_existing=True
        )
        self.scheduler.add_job(
            self.sim_signal_task,
            CronTrigger(hour="13,14", minute="0,5,10,15,20,25,30,35,40,45,50,55", day_of_week="mon-fri"),
            id="sim_pm", name="模拟仓信号(13:00-14:55)", replace_existing=True
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

    def morning_news_task(self):
        """财经早报：A股Bot + mcDolphin Bot"""
        logger.info("执行财经早报任务")
        try:
            from modules.news.news_engine import a_news
            a_news.push_morning()
        except Exception as e:
            logger.error(f"A股早报失败: {e}", exc_info=True)
        time.sleep(3)
        try:
            from modules.news.news_engine import us_news
            us_news.push_morning()
        except Exception as e:
            logger.error(f"美股早报失败: {e}", exc_info=True)

    def evening_news_task(self):
        """财经晚报：A股Bot + mcDolphin Bot"""
        logger.info("执行财经晚报任务")
        try:
            from modules.news.news_engine import a_news
            a_news.push_evening()
        except Exception as e:
            logger.error(f"A股晚报失败: {e}", exc_info=True)
        time.sleep(3)
        try:
            from modules.news.news_engine import us_news
            us_news.push_evening()
        except Exception as e:
            logger.error(f"美股晚报失败: {e}", exc_info=True)

    def watchlist_track_task(self):
        """自选股跟踪：交易日推日报，周末推周报"""
        logger.info("执行自选股跟踪任务")
        try:
            from modules.watchlist_tracker.tracker import a_tracker
            a_tracker.run()
        except Exception as e:
            logger.error(f"A股自选股跟踪失败: {e}", exc_info=True)
        time.sleep(3)
        try:
            from modules.watchlist_tracker.tracker import us_tracker
            us_tracker.run()
        except Exception as e:
            logger.error(f"美股自选股跟踪失败: {e}", exc_info=True)

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

    def heartbeat_task(self):
        """系统心跳监控：每天 7:00 推送系统状态"""
        logger.info("执行系统心跳监控")
        try:
            import json
            from pathlib import Path
            from notify.notifier import notifier

            jobs = self.scheduler.get_jobs()

            # 自选股数量
            wl_file = Path(__file__).parent.parent / "data" / "watchlist.json"
            us_wl_file = Path(__file__).parent.parent / "data" / "us_watchlist.json"
            try:
                with open(wl_file) as f:
                    a_count = len(json.load(f).get("stocks", {}))
            except Exception:
                a_count = 0
            try:
                with open(us_wl_file) as f:
                    us_count = len(json.load(f).get("stocks", {}))
            except Exception:
                us_count = 0

            # 今日 API 用量
            usage_file = Path(__file__).parent.parent / "data" / "api_usage.json"
            today_tokens = 0
            today_calls = 0
            if usage_file.exists():
                with open(usage_file) as f:
                    usage = json.load(f)
                today = datetime.now().strftime("%Y-%m-%d")
                day_data = usage.get("daily", {}).get(today, {})
                today_tokens = day_data.get("total_tokens", 0)
                today_calls = day_data.get("calls", 0)

            msg = (
                f"💓 系统心跳 — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"🟢 运行状态：正常\n"
                f"📋 定时任务：{len(jobs)} 个\n"
                f"🇨🇳 A股自选股：{a_count} 只\n"
                f"🇺🇸 美股自选股：{us_count} 只\n"
                f"🤖 今日AI调用：{today_calls} 次 / {today_tokens:,} tokens"
            )
            notifier.telegram.send(msg)
            logger.info("系统心跳已推送")
        except Exception as e:
            logger.error(f"系统心跳任务失败: {e}", exc_info=True)

    def ipo_reminder_task(self):
        """打新提醒：每天 08:45"""
        logger.info("执行打新提醒任务")
        try:
            from modules.ipo.ipo_reminder import ipo_reminder
            ipo_reminder.run_daily_check()
        except Exception as e:
            logger.error(f"打新提醒任务失败: {e}", exc_info=True)

    # ── Phase 2 任务 ──────────────────────────────────

    def macro_calendar_task(self):
        """宏观经济日历：每周一 8:45"""
        logger.info("执行宏观经济日历推送")
        try:
            from modules.macro.macro_calendar import macro_calendar
            macro_calendar.run_weekly_push()
        except Exception as e:
            logger.error(f"宏观经济日历失败: {e}", exc_info=True)

    # ── Phase 3 任务 ──────────────────────────────────

    def block_trade_task(self):
        """大宗交易监控：交易日 19:30"""
        logger.info("执行大宗交易监控")
        try:
            from modules.scanner.block_trade import block_trade_monitor
            block_trade_monitor.run_daily_push()
        except Exception as e:
            logger.error(f"大宗交易监控失败: {e}", exc_info=True)


    # ── Phase 4 任务 ──────────────────────────────────

    # ── Phase 5 任务 ──────────────────────────────────

    def quant_screener_task(self):
        """多因子量化选股：工作日 8:50"""
        logger.info("执行量化多因子选股")
        try:
            from modules.quant.screener import quant_screener
            quant_screener.run_daily_push()
        except Exception as e:
            logger.error(f"量化选股失败: {e}", exc_info=True)

    def daily_review_task(self):
        """每日复盘：交易日 21:00"""
        logger.info("执行每日复盘")
        try:
            from modules.review.daily_review import daily_review
            daily_review.run_daily_push()
        except Exception as e:
            logger.error(f"每日复盘失败: {e}", exc_info=True)

    def github_trending_task(self):
        """GitHub 科技雷达任务"""
        logger.info("执行定时任务: GitHub 科技雷达")
        try:
            github_trending_engine.run()
        except Exception as e:
            logger.error(f"GitHub 科技雷达任务失败: {e}", exc_info=True)

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

    def sim_signal_task(self):
        """模拟仓信号扫描（盘中每5分钟）"""
        try:
            from modules.sim_trading.signal_engine import signal_engine
            signal_engine.scan_once()
        except Exception as e:
            logger.error(f"模拟仓信号任务失败: {e}", exc_info=True)

    def _get_watchlist(self):
        """从 watchlist.json 获取自选股列表"""
        try:
            import json
            with open(_DATA_DIR / "watchlist.json") as f:
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
