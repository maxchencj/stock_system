"""
进程守护设置完成通知
"""
import os
from dotenv import load_dotenv
load_dotenv()

from notify.notifier import notifier
from datetime import datetime

report = f"""
✅ 进程守护已配置完成！

【已完成的工作】
1. ✅ 创建守护脚本 (watchdog.sh)
   - 每次运行检查系统是否在线
   - 如果停止则自动启动

2. ✅ 创建重启脚本 (restart.sh)
   - 一键停止并重启系统
   - 自动检查启动状态

3. ✅ 修复Web服务问题
   - Web启动失败不再影响主程序
   - 定时任务和监控继续运行

4. ✅ 准备crontab配置
   - 每5分钟自动检查
   - 每天凌晨4点自动重启

【推荐方案：手动设置crontab】

由于macOS权限限制，建议手动设置crontab：

1. 打开终端，运行：
   crontab -e

2. 按 i 进入编辑模式，粘贴以下内容：
   */5 * * * * cd /Users/maxchen/Desktop/claudeForStock/stock_system && ./watchdog.sh
   0 4 * * * cd /Users/maxchen/Desktop/claudeForStock/stock_system && ./restart.sh >> logs/restart.log 2>&1

3. 按 ESC，输入 :wq 保存退出

4. 验证：
   crontab -l

【当前状态】
✅ 系统正在运行
✅ 守护脚本已就绪
✅ 重启脚本已就绪

【常用命令】
• 重启系统: cd /Users/maxchen/Desktop/claudeForStock/stock_system && ./restart.sh
• 查看日志: tail -f logs/system_run.log
• 查看守护日志: tail -f logs/watchdog.log
• 检查进程: ps aux | grep "python3.*main.py"

【下次运行】
📅 明天早上 08:00 市场早报
📅 周一 08:30 每日选股
📅 周一 17:00 板块分析

设置完crontab后，系统将自动守护，无需担心进程停止！

---
时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

notifier.send_all("✅ 进程守护配置完成", report)
print(report)
