#!/bin/bash
# 快速启动脚本

echo "🚀 股票智能分析系统 - 启动中..."
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 Python3，请先安装"
    exit 1
fi

# 检查依赖
if [ ! -d "venv" ]; then
    echo "📦 首次运行，创建虚拟环境..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# 检查配置
if [ ! -f ".env" ]; then
    echo "⚠️  未找到 .env 文件，请先配置:"
    echo "   cp .env.example .env"
    echo "   然后编辑 .env 填写 ANTHROPIC_API_KEY"
    exit 1
fi

# 启动系统
echo "✅ 环境检查完成，启动系统..."
echo ""
python main.py "$@"
