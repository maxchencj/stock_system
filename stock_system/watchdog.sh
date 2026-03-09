#!/bin/bash
# 进程守护脚本 - 确保只有一个实例运行

cd "$(dirname "$0")"

# 统计运行中的进程数
COUNT=$(ps aux | grep "main.py" | grep -v grep | wc -l | tr -d ' ')

if [ "$COUNT" -eq 1 ]; then
    # 正好1个进程，正常
    PID=$(ps aux | grep "main.py" | grep -v grep | awk '{print $2}')
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 系统正在运行 (PID: $PID)" >> logs/watchdog.log
elif [ "$COUNT" -gt 1 ]; then
    # 多个进程，杀掉全部重启
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 检测到 $COUNT 个重复进程，清理并重启..." >> logs/watchdog.log
    pkill -9 -f "python3.*main.py" 2>/dev/null || true
    pkill -9 -f "Python.*main.py" 2>/dev/null || true
    sleep 2
    nohup python3 main.py --no-web > logs/system_run.log 2>&1 &
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 系统已重启 (PID: $!)" >> logs/watchdog.log
else
    # 没有进程，启动
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 检测到系统未运行，正在启动..." >> logs/watchdog.log
    nohup python3 main.py --no-web > logs/system_run.log 2>&1 &
    NEW_PID=$!
    sleep 3
    if ps -p $NEW_PID > /dev/null 2>&1; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 系统启动成功 (PID: $NEW_PID)" >> logs/watchdog.log
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 系统启动失败" >> logs/watchdog.log
    fi
fi
