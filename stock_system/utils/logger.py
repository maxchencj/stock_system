"""
日志工具
"""
import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logger(name: str, log_file: str = "logs/system.log", level: str = "INFO") -> logging.Logger:
    """设置日志器"""
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        # 控制台输出
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(console_fmt)

        # 文件输出（带轮转）
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(console_fmt)

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger


# 全局日志
logger = setup_logger("stock_system")
