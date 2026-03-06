# 🚀 快速开始指南

## 第一步：安装依赖

```bash
cd /Users/maxchen/Desktop/claudeForStock/stock_system

# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

## 第二步：配置 API Key

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件
nano .env  # 或使用任何文本编辑器
```

在 `.env` 中填写您的 Claude API Key:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

获取 API Key: https://console.anthropic.com/

## 第三步：启动系统

### 方式 1: 使用启动脚本（推荐）
```bash
./start.sh
```

### 方式 2: 直接运行
```bash
python main.py
```

### 方式 3: 测试模式
```bash
# 测试选股功能
python main.py --test-picker

# 测试板块分析
python main.py --test-sector

# 仅启动 Web（不启动定时任务）
python main.py --no-scheduler
```

## 第四步：访问 Web Dashboard

打开浏览器访问: **http://localhost:8888**

---

## 📱 配置通知推送（可选）

### PushPlus 微信推送

1. 访问 https://www.pushplus.plus/
2. 微信扫码登录，获取 token
3. 在 `.env` 中添加:
   ```
   PUSHPLUS_TOKEN=your-token-here
   ```
4. 在 `config/settings.py` 中启用:
   ```python
   pushplus_enabled: bool = True
   ```

### Telegram Bot

1. 与 @BotFather 对话创建 Bot，获取 token
2. 与 @userinfobot 对话获取 chat_id
3. 在 `.env` 中添加:
   ```
   TELEGRAM_TOKEN=your-bot-token
   TELEGRAM_CHAT_ID=your-chat-id
   ```
4. 在 `config/settings.py` 中启用:
   ```python
   telegram_enabled: bool = True
   ```

---

## 🎯 核心功能使用

### 1. 每日选股

**自动执行**: 每个交易日早上 8:30 自动扫描并推送

**手动触发**:
```bash
python main.py --test-picker
```

**Web 操作**: 进入"选股模块"标签页，点击"开始扫描"

### 2. 实时监控

1. 启动系统后访问 Web Dashboard
2. 进入"监控模块"标签页
3. 输入股票代码（如 600519）
4. 点击"添加"
5. 点击"启动监控"

系统会每 60 秒检查一次，触发信号时自动推送。

### 3. 板块分析

**自动执行**: 每个交易日下午 5:00 自动分析并推送

**手动触发**:
```bash
python main.py --test-sector
```

**Web 操作**: 进入"板块分析"标签页，点击"开始分析"

---

## ⚙️ 常见问题

### Q1: 提示 "未找到 akshare 模块"
```bash
pip install akshare
```

### Q2: Claude API 调用失败
- 检查 `.env` 中的 `ANTHROPIC_API_KEY` 是否正确
- 确认 API Key 有足够的额度
- 检查网络连接（国内可能需要代理）

### Q3: 获取行情数据失败
- AKShare 数据源可能临时不可用，稍后重试
- 检查网络连接

### Q4: 如何修改选股参数？
编辑 `config/settings.py` 中的 `StockPickerConfig` 类

### Q5: 如何修改定时任务时间？
编辑 `core/scheduler.py` 中的 `CronTrigger` 参数

---

## 🛡️ 风险提示

⚠️ **重要**: 本系统仅供学习研究，不构成投资建议。股市有风险，投资需谨慎！

---

## 📞 技术支持

如有问题，请查看 `README.md` 或提交 Issue。

**祝使用愉快！📈**
