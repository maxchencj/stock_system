"""
剩余两个定时验证推送：今晚23:00，明早07:00
"""
import os
from dotenv import load_dotenv
load_dotenv()

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta, time
from notify.notifier import notifier
from utils.logger import logger

def make_push(label):
    def push():
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"""
⏰ 定时验证推送 {label}

当前时间: {now}

✅ 系统运行正常
✅ 推送功能正常
✅ 定时任务正常

这是验证推送，确认系统能够按时推送消息。
"""
        notifier.send_all(f"⏰ 定时验证 {label}", message)
        logger.info(f"定时推送已发送: {label}")
    return push

scheduler = BlockingScheduler(timezone="Asia/Shanghai")

today = datetime.now().date()
tomorrow = today + timedelta(days=1)

times = [
    (datetime.combine(today, time(23, 0)), "今晚23:00"),
    (datetime.combine(tomorrow, time(7, 0)), "明早07:00"),
]

for run_date, label in times:
    scheduler.add_job(make_push(label), DateTrigger(run_date=run_date))
    logger.info(f"已设置定时推送: {run_date.strftime('%Y-%m-%d %H:%M')} ({label})")

logger.info("等待推送时间...")
try:
    scheduler.start()
except (KeyboardInterrupt, SystemExit):
    logger.info("定时推送已取消")
