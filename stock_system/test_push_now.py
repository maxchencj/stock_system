"""
立即推送测试消息
"""
import os
from dotenv import load_dotenv
load_dotenv()

from notify.notifier import notifier
from datetime import datetime

message = f"""
📢 推送测试

这是一条测试消息，验证推送功能是否正常。

当前时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

✅ 系统运行正常
✅ 推送功能正常

【已设置的定时任务】
• 今天 17:00 - 定时推送测试
• 明天 08:00 - 市场早报
• 周一 08:30 - 每日选股
• 周一 17:00 - 板块分析
"""

notifier.send_all("📢 推送测试", message)
print("测试消息已推送！")
