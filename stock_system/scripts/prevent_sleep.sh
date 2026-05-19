#!/bin/bash
# 防休眠脚本 - 在股票系统运行期间保持电脑唤醒

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/.caffeinate.pid"

case "$1" in
    start)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo "⚠️  防休眠已在运行中"
            exit 0
        fi

        echo "🔋 启动防休眠模式..."
        echo "   • 电脑将保持唤醒状态"
        echo "   • 显示器可以关闭（节能）"
        echo "   • 系统进程继续运行"
        echo ""

        # 使用 caffeinate 防止系统休眠（但允许显示器休眠）
        caffeinate -d -w $$ &
        CAFFEINATE_PID=$!
        echo $CAFFEINATE_PID > "$PID_FILE"

        echo "✅ 防休眠已启动 (PID: $CAFFEINATE_PID)"
        echo "💡 提示: 运行 ./prevent_sleep.sh stop 来停止"
        ;;

    stop)
        if [ ! -f "$PID_FILE" ]; then
            echo "⚠️  防休眠未运行"
            exit 0
        fi

        CAFFEINATE_PID=$(cat "$PID_FILE")
        if kill -0 $CAFFEINATE_PID 2>/dev/null; then
            kill $CAFFEINATE_PID
            rm "$PID_FILE"
            echo "✅ 防休眠已停止"
        else
            rm "$PID_FILE"
            echo "⚠️  防休眠进程已不存在"
        fi
        ;;

    status)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo "✅ 防休眠正在运行 (PID: $(cat $PID_FILE))"
            echo ""
            echo "当前电源设置:"
            pmset -g | grep -E "sleep|displaysleep"
        else
            echo "❌ 防休眠未运行"
            [ -f "$PID_FILE" ] && rm "$PID_FILE"
        fi
        ;;

    *)
        echo "用法: $0 {start|stop|status}"
        echo ""
        echo "命令说明:"
        echo "  start   - 启动防休眠（保持电脑唤醒）"
        echo "  stop    - 停止防休眠（恢复正常休眠）"
        echo "  status  - 查看防休眠状态"
        echo ""
        echo "示例:"
        echo "  ./prevent_sleep.sh start   # 启动防休眠"
        echo "  ./prevent_sleep.sh status  # 查看状态"
        echo "  ./prevent_sleep.sh stop    # 停止防休眠"
        exit 1
        ;;
esac
