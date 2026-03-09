"""
市场早报功能修复通知
"""
import os
from dotenv import load_dotenv
load_dotenv()

from notify.notifier import notifier
from datetime import datetime

report = f"""
✅ 市场早报功能已修复！

【问题原因】
今天早上8点的市场早报任务虽然执行了，但AI生成和推送的代码被注释掉了，所以没有实际推送消息。

【已修复】
✅ 启用了AI市场早报生成功能
✅ 启用了自动推送功能
✅ 系统已重启，使用新代码

【测试结果】
刚刚手动触发了一次市场早报，应该已经收到推送了。

【下次运行】
📅 明天（周六）早上 08:00
之后每天早上8点都会自动推送市场早报（含周末）

【其他定时任务】
• 每日选股: 周一 08:30
• 板块分析: 周一 17:00

系统现在完全正常，明天开始会按时推送！

---
修复时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

notifier.send_all("✅ 市场早报功能已修复", report)
print(report)
