@echo off
REM Windows 启动脚本

echo 🚀 股票智能分析系统 - 启动中...
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 未找到 Python，请先安装
    pause
    exit /b 1
)

REM 检查虚拟环境
if not exist "venv" (
    echo 📦 首次运行，创建虚拟环境...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

REM 检查配置
if not exist ".env" (
    echo ⚠️  未找到 .env 文件，请先配置:
    echo    copy .env.example .env
    echo    然后编辑 .env 填写 ANTHROPIC_API_KEY
    pause
    exit /b 1
)

REM 启动系统
echo ✅ 环境检查完成，启动系统...
echo.
python main.py %*
