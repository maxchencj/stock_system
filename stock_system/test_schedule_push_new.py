"""
定时测试推送 - 今晚23:30 和 明天07:00
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
⏰ *定时测试推送 {label}*

当前时间: `{now}`

✅ 系统运行正常
✅ Telegram推送正常
✅ 定时任务正常

_这是验证推送，确认系统能够按时推送消息。_
"""
        success = notifier.telegram.send(message)
        logger.info(f"定时推送已发送: {label}, 结果: {'成功' if success else '失败'}")
    return push

scheduler = BlockingScheduler(timezone="Asia/Shanghai")

today = datetime.now().date()
tomorrow = today + timedelta(days=1)

# 今晚23:30
time1 = datetime.combine(today, time(23, 30))
# 明天07:00
time2 = datetime.combine(tomorrow, time(7, 0))

# 如果今晚23:30已经过了，就不设置
if time1 > datetime.now():
    scheduler.add_job(make_push("今晚23:30"), DateTrigger(run_date=time1))
    logger.info(f"已设置定时推送: {time1.strftime('%Y-%m-%d %H:%M')} (今晚23:30)")
else:
    logger.info("今晚23:30已过，跳过")

scheduler.add_job(make_push("明天07:00"), DateTrigger(run_date=time2))
logger.info(f"已设置定时推送: {time2.strftime('%Y-%m-%d %H:%M')} (明天07:00)")

logger.info("等待推送时间...")
try:
    scheduler.start()
except (KeyboardInterrupt, SystemExit):
    logger.info("定时推送已取消")
