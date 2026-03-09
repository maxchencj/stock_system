"""
一次性定时推送 - 今天下午5点
"""
import os
from dotenv import load_dotenv
load_dotenv()

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime
from notify.notifier import notifier
from utils.logger import logger

def send_test_message():
    """发送测试消息"""
    message = f"""
📢 定时推送测试

这是一条定时推送消息，用于测试系统的定时功能。

当前时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

✅ 系统运行正常
✅ 定时任务正常
✅ 推送功能正常

明天早上8点会自动推送市场早报！
"""

    notifier.send_all("📢 定时推送测试", message)
    logger.info("定时推送已发送")

# 创建调度器
scheduler = BlockingScheduler(timezone="Asia/Shanghai")

# 设置今天下午5点的任务
target_time = datetime.now().replace(hour=17, minute=0, second=0, microsecond=0)

logger.info(f"设置定时推送: {target_time}")
scheduler.add_job(
    send_test_message,
    DateTrigger(run_date=target_time),
    id="test_push"
)

logger.info("等待推送时间...")
try:
    scheduler.start()
except (KeyboardInterrupt, SystemExit):
    logger.info("任务已取消")
