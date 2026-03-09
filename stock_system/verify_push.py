"""
三个定时验证推送：今晚22:30、23:00，明早07:00
"""
import os
from dotenv import load_dotenv
load_dotenv()

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime
from notify.notifier import notifier
from utils.logger import logger

def make_push(label):
    def push():
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notifier.send_all(f"⏰ 定时验证推送 {label}", f"验证消息 {label}\n\n当前时间: {now}\n✅ 系统运行正常，推送功能正常！")
        logger.info(f"定时推送已发送: {label}")
    return push

scheduler = BlockingScheduler(timezone="Asia/Shanghai")

today = datetime.now().date()
import datetime as dt

times = [
    (dt.datetime.combine(today, dt.time(22, 30)), "22:30"),
    (dt.datetime.combine(today, dt.time(23,  0)), "23:00"),
    (dt.datetime.combine(today + dt.timedelta(days=1), dt.time(7, 0)), "明早07:00"),
]

for run_date, label in times:
    scheduler.add_job(make_push(label), DateTrigger(run_date=run_date))
    logger.info(f"已设置定时推送: {run_date.strftime('%Y-%m-%d %H:%M')} ({label})")

logger.info("等待推送时间，按 Ctrl+C 取消...")
try:
    scheduler.start()
except (KeyboardInterrupt, SystemExit):
    logger.info("定时推送已取消")
