# 📊 股票智能分析系统

基于 **Claude AI** 的 A 股智能分析系统，集成全市场扫描、AI 选股、实时监控、板块轮动分析等功能。

---

## ✨ 核心功能

### 1️⃣ 选股模块
- 🔍 **全市场扫描**: 自动扫描沪深 A 股
- 📊 **量化筛选**: 市值、量比、PE、技术指标多维度过滤
- 🤖 **AI 精选**: Claude AI 深度分析，生成买入逻辑和目标价位
- 📤 **每日推送**: 微信/Telegram 自动推送选股报告

### 2️⃣ 监控模块
- 👀 **自选股池**: 管理个人关注股票
- ⚡ **实时监控**: 价格异动、成交量突破、技术信号检测
- 🔔 **智能预警**: 触发信号后 AI 实时研判，推送操作建议
- 🎯 **买卖信号**: MACD 金叉/死叉、RSI 超买/超卖等

### 3️⃣ 板块分析模块
- 🔥 **31 个一级板块**: 覆盖全行业
- 💰 **资金流向**: 追踪主力资金动向
- 🔄 **轮动追踪**: AI 识别板块轮动规律
- 📈 **每日报告**: 热点板块、龙头股、明日关注

### 4️⃣ Web Dashboard
- 📊 **可视化界面**: ECharts K 线图表
- 🎛️ **实时控制**: 启动/停止监控、手动触发扫描
- 📱 **响应式设计**: 支持移动端访问

---

## 🏗️ 系统架构

```
股票智能分析系统
├── 选股模块          全市场扫描 → 规则筛选 → AI精选 → 每日推送
├── 监控模块          自选股池 → 实时监控 → 买卖信号 → 实时推送
├── 板块分析模块      31个板块 → 资金流向 → 轮动追踪 → 每日报告
│
├── AI 分析引擎       Claude API（综合研判 + 报告生成）
├── 数据层            AKShare（行情 + 板块 + 资金流向）
├── 通知层            PushPlus微信 / Telegram Bot
└── 可视化层          Web Dashboard（FastAPI + ECharts）
```

---

## 🚀 快速开始

### 1. 环境要求
- Python 3.9+
- pip

### 2. 安装依赖
```bash
cd /tmp/stock_system
pip install -r requirements.txt
```

### 3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件，填写 ANTHROPIC_API_KEY
```

### 4. 启动系统
```bash
# 完整启动（Web + 定时任务）
python main.py

# 仅启动 Web（不启动定时任务）
python main.py --no-scheduler

# 启动时开启监控
python main.py --enable-monitor

# 测试选股模块
python main.py --test-picker

# 测试板块分析
python main.py --test-sector
```

### 5. 访问 Web Dashboard
打开浏览器访问: `http://localhost:8888`

---

## 📁 项目结构

```
stock_system/
├── main.py                 # 主程序入口
├── requirements.txt        # 依赖包
├── .env.example            # 环境变量模板
│
├── config/                 # 配置模块
│   ├── __init__.py
│   └── settings.py         # 系统配置
│
├── core/                   # 核心模块
│   └── scheduler.py        # 定时任务调度器
│
├── data/                   # 数据层
│   ├── data_service.py     # AKShare 数据服务
│   ├── stock.db            # SQLite 数据库（自动生成）
│   └── watchlist.json      # 自选股池（自动生成）
│
├── ai/                     # AI 分析引擎
│   └── analysis_engine.py  # Claude API 封装
│
├── modules/                # 功能模块
│   ├── stock_picker/       # 选股模块
│   │   └── picker.py
│   ├── monitor/            # 监控模块
│   │   └── monitor.py
│   └── sector/             # 板块分析模块
│       └── analyzer.py
│
├── notify/                 # 通知层
│   └── notifier.py         # PushPlus + Telegram
│
├── web/                    # Web Dashboard
│   ├── app.py              # FastAPI 应用
│   ├── templates/          # HTML 模板
│   │   └── index.html
│   └── static/             # 静态资源
│       ├── css/
│       └── js/
│
├── utils/                  # 工具模块
│   └── logger.py           # 日志工具
│
└── logs/                   # 日志文件（自动生成）
    └── system.log
```

---

## ⚙️ 配置说明

### AI 配置
在 `.env` 中配置 Claude API Key:
```bash
ANTHROPIC_API_KEY=sk-ant-xxx
```

获取 API Key: https://console.anthropic.com/

### 通知配置（可选）

#### PushPlus 微信推送
1. 访问 https://www.pushplus.plus/
2. 微信扫码登录，获取 token
3. 在 `.env` 中配置:
```bash
PUSHPLUS_TOKEN=your-token
```
4. 在 `config/settings.py` 中启用:
```python
pushplus_enabled: bool = True
```

#### Telegram Bot
1. 与 @BotFather 对话创建 Bot，获取 token
2. 与 @userinfobot 对话获取 chat_id
3. 在 `.env` 中配置:
```bash
TELEGRAM_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```
4. 在 `config/settings.py` 中启用:
```python
telegram_enabled: bool = True
```

---

## 📊 使用示例

### 1. 每日选股
系统会在每个交易日早上 8:30 自动执行选股扫描，并推送报告。

手动触发:
```bash
python main.py --test-picker
```

### 2. 实时监控
启动系统后，在 Web Dashboard 中:
1. 进入"监控模块"标签页
2. 输入股票代码（如 600519）
3. 点击"添加"
4. 点击"启动监控"

系统会每 60 秒检查一次自选股，触发信号时自动推送。

### 3. 板块分析
系统会在每个交易日下午 5:00 自动执行板块分析，并推送报告。

手动触发:
```bash
python main.py --test-sector
```

---

## 🔧 高级配置

### 修改选股参数
编辑 `config/settings.py` 中的 `StockPickerConfig`:
```python
@dataclass
class StockPickerConfig:
    min_market_cap: float = 5.0      # 最小市值(亿)
    max_market_cap: float = 5000.0   # 最大市值(亿)
    min_volume_ratio: float = 1.5    # 最小量比
    max_pe_ratio: float = 100.0      # 最大市盈率
    top_n: int = 10                  # 每日推送数量
```

### 修改监控参数
编辑 `config/settings.py` 中的 `MonitorConfig`:
```python
@dataclass
class MonitorConfig:
    check_interval: int = 60          # 检查间隔(秒)
    price_change_alert: float = 3.0   # 涨跌幅预警(%)
    volume_spike_ratio: float = 3.0   # 成交量异动倍数
    rsi_overbought: float = 75.0      # RSI超买
    rsi_oversold: float = 25.0        # RSI超卖
```

### 修改定时任务
编辑 `core/scheduler.py` 中的 CronTrigger:
```python
# 每日选股时间（默认 8:30）
CronTrigger(hour=8, minute=30, day_of_week="mon-fri")

# 板块分析时间（默认 17:00）
CronTrigger(hour=17, minute=0, day_of_week="mon-fri")
```

---

## 🛡️ 风险提示

⚠️ **重要声明**:
1. 本系统仅供学习研究使用，不构成任何投资建议
2. AI 分析结果仅供参考，不保证准确性
3. 股市有风险，投资需谨慎
4. 请勿将本系统用于实盘交易决策
5. 使用本系统造成的任何损失，开发者不承担责任

---

## 📝 开发计划

- [ ] 回测模块（策略回测 + 收益分析）
- [ ] 更多技术指标（CCI、OBV、ATR 等）
- [ ] 基本面数据（财报、估值）
- [ ] 多策略支持（趋势、均值回归、网格等）
- [ ] WebSocket 实时推送
- [ ] 移动端 App

---

## 📄 许可证

MIT License

---

## 🙏 致谢

- **数据源**: [AKShare](https://github.com/akfamily/akshare)
- **AI 引擎**: [Anthropic Claude](https://www.anthropic.com/)
- **Web 框架**: [FastAPI](https://fastapi.tiangolo.com/)
- **图表库**: [ECharts](https://echarts.apache.org/)

---

## 📧 联系方式

如有问题或建议，欢迎提 Issue 或 PR。

**祝投资顺利！📈**
