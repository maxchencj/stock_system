#!/bin/bash
# launchd 启动包装脚本

cd /Users/maxchen/Desktop/claudeForStock/stock_system

# 加载环境变量
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# 启动系统
exec /opt/homebrew/bin/python3.9 main.py
