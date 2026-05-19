#!/bin/bash
# 重启股票分析系统（确保单实例）

cd "$(dirname "$0")"

echo "停止所有旧进程..."
pkill -9 -f "python3.*main.py" 2>/dev/null || true
pkill -9 -f "Python.*main.py" 2>/dev/null || true
sleep 2

# 二次确认
REMAINING=$(ps aux | grep "main.py" | grep -v grep | wc -l | tr -d ' ')
if [ "$REMAINING" -gt 0 ]; then
    echo "仍有 $REMAINING 个残留进程，强制清理..."
    ps aux | grep "main.py" | grep -v grep | awk '{print $2}' | while read pid; do
        kill -9 "$pid" 2>/dev/null
    done
    sleep 2
fi

echo "启动新进程..."
nohup python3 main.py --no-web > logs/system_run.log 2>&1 &
PID=$!

sleep 3

if ps -p $PID > /dev/null 2>&1; then
    echo "✅ 系统已启动成功"
    echo "PID: $PID"
    echo ""
    tail -20 logs/system_run.log
else
    echo "❌ 系统启动失败，查看日志:"
    tail -50 logs/system_run.log
fi
