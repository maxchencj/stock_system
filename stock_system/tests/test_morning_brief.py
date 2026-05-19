"""
手动触发市场早报测试
"""
import os
from dotenv import load_dotenv
load_dotenv()

from core.scheduler import scheduler
from utils.logger import logger

logger.info("手动触发市场早报任务...")
scheduler.morning_brief_task()
logger.info("完成！")
