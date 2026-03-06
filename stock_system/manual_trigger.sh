#!/bin/bash
# 手动触发任务脚本

cd "$(dirname "$0")"

echo "手动触发任务菜单"
echo "=================="
echo "1. 执行选股扫描"
echo "2. 执行板块分析"
echo "3. 测试推送"
echo ""
read -p "请选择 (1-3): " choice

case $choice in
    1)
        echo "正在执行选股扫描..."
        python3 main.py --test-picker
        ;;
    2)
        echo "正在执行板块分析..."
        python3 main.py --test-sector
        ;;
    3)
        echo "正在测试推送..."
        python3 test_pushplus_direct.py
        ;;
    *)
        echo "无效选择"
        ;;
esac
