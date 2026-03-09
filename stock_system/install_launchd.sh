#!/bin/bash
# launchd 安装脚本

PLIST_FILE="com.stock.analysis.system.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$LAUNCH_AGENTS_DIR/$PLIST_FILE"

echo "📦 安装股票分析系统 launchd 服务..."
echo ""

# 创建 LaunchAgents 目录
mkdir -p "$LAUNCH_AGENTS_DIR"

# 停止旧服务（如果存在）
if launchctl list | grep -q "com.stock.analysis.system"; then
    echo "停止旧服务..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    sleep 2
fi

# 停止手动运行的进程
echo "停止手动运行的进程..."
pkill -f "python3.*main.py" 2>/dev/null || true
sleep 2

# 复制配置文件
echo "复制配置文件..."
cp "$PLIST_FILE" "$PLIST_PATH"

# 加载服务
echo "加载服务..."
launchctl load "$PLIST_PATH"

sleep 3

# 检查状态
if launchctl list | grep -q "com.stock.analysis.system"; then
    echo ""
    echo "✅ 服务安装成功！"
    echo ""
    echo "服务状态:"
    launchctl list | grep "com.stock.analysis.system"
    echo ""
    echo "查看日志:"
    echo "  输出日志: tail -f logs/launchd.out.log"
    echo "  错误日志: tail -f logs/launchd.err.log"
    echo ""
    echo "管理命令:"
    echo "  停止服务: launchctl unload ~/Library/LaunchAgents/$PLIST_FILE"
    echo "  启动服务: launchctl load ~/Library/LaunchAgents/$PLIST_FILE"
    echo "  查看状态: launchctl list | grep stock"
else
    echo ""
    echo "❌ 服务安装失败，请检查配置"
fi
