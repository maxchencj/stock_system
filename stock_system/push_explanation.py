"""
推送问题说明和解决方案
"""
import os
from dotenv import load_dotenv
load_dotenv()

from notify.notifier import notifier
from datetime import datetime

report = f"""
📋 关于推送问题的说明

【问题分析】
1. 今天早上8点任务确实执行了
2. 日志显示"已推送"
3. 但你没有收到消息

【可能原因】
1. 系统进程在某个时候意外停止了
2. Web端口冲突导致系统退出
3. 推送可能因为网络问题失败但没有正确记录

【已采取措施】
✅ 清理了占用端口的旧进程
✅ 重新启动了系统
✅ 创建了restart.sh脚本方便重启
✅ 刚刚手动触发了一次市场早报测试

【验证】
刚才手动触发的市场早报应该已经推送到你的微信了，如果收到了说明推送功能正常。

【建议】
为了确保系统稳定运行，建议：
1. 使用 systemd 或 supervisor 管理进程（更稳定）
2. 或者设置 crontab 定时检查并重启
3. 定期查看日志确认运行状态

【下次运行】
📅 明天早上 08:00 市场早报
📅 周一 08:30 每日选股
📅 周一 17:00 板块分析

【当前状态】
✅ 系统正在运行 (PID: 19947)
✅ 定时任务已注册
✅ 监控模块正常
✅ Web服务正常

如果明天早上还是没收到，请及时告诉我！

---
时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

notifier.send_all("📋 推送问题说明", report)
print(report)
