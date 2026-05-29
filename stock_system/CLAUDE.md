# 股票智能分析系统 - Claude 开发指南

## 数据源规范（重要）

**所有新功能必须使用 Tushare，禁止使用 AKShare。**

- 数据接口统一通过 `tushare.pro_api(os.getenv("TUSHARE_TOKEN"))` 调用
- 常用接口：`daily`（日行情）、`limit_list_d`（涨跌停，含名称/行业）、`stock_basic`（股票列表，1次/小时限频需缓存）
- `stock_basic` 调用频率限制严格，需用文件缓存（见 `data/stock_basic_cache.csv`），每日只调一次
- 大盘指数使用腾讯 Finance `qt.gtimg.cn`（不计入 Tushare 配额）

## 项目概述

这是一个基于 Claude AI 的 A 股智能分析系统，集成全市场扫描、AI 选股、实时监控、板块轮动分析等功能。系统采用模块化架构，使用 Python 3.9+ 开发。

## 核心架构

```
股票智能分析系统
├── 选股模块 (modules/stock_picker/)
│   └── 全市场扫描 → 量化筛选 → AI 精选 → 每日推送
├── 监控模块 (modules/monitor/)
│   └── 自选股池 → 实时监控 → 信号检测 → 实时推送
├── 板块分析模块 (modules/sector/)
│   └── 31 个板块 → 资金流向 → 轮动追踪 → 每日报告
├── AI 分析引擎 (ai/)
│   └── Claude API 封装 (claude-opus-4-5-20251101)
├── 数据层 (data/)
│   └── AKShare 数据服务 + SQLite 存储
├── 通知层 (notify/)
│   └── PushPlus 微信 + Telegram Bot
└── Web Dashboard (web/)
    └── FastAPI + ECharts 可视化
```

## 技术栈

- **AI 引擎**: Anthropic Claude API (claude-opus-4-5-20251101)
- **数据源**: AKShare (A 股行情、板块、资金流向)
- **Web 框架**: FastAPI + Uvicorn
- **定时任务**: APScheduler (BackgroundScheduler)
- **数据处理**: Pandas + NumPy
- **通知推送**: PushPlus + Telegram Bot
- **可视化**: ECharts + Jinja2
- **数据库**: SQLite (可选 Redis 缓存)

## 开发规范

### 代码风格

1. **遵循 PEP 8 规范**
2. **使用类型注解**: 函数参数和返回值必须标注类型
3. **文档字符串**: 所有模块、类、函数必须有清晰的 docstring
4. **命名规范**:
   - 类名: PascalCase (如 `StockScreener`)
   - 函数/变量: snake_case (如 `run_daily_scan`)
   - 常量: UPPER_SNAKE_CASE (如 `MAX_RETRY_TIMES`)
   - 私有方法: 前缀下划线 (如 `_calculate_score`)

### 错误处理

1. **必须捕获外部 API 异常**: AKShare、Claude API、通知推送
2. **使用 logger 记录错误**: 包含完整堆栈信息 (`exc_info=True`)
3. **优雅降级**: 关键功能失败时不应导致整个系统崩溃
4. **重试机制**: 网络请求失败时自动重试 (config.data.retry_times)

### 日志规范

```python
from utils.logger import logger

# 信息日志
logger.info("系统启动完成")

# 警告日志
logger.warning("数据获取失败，使用缓存数据")

# 错误日志（包含堆栈）
logger.error(f"AI 分析失败: {e}", exc_info=True)

# 调试日志
logger.debug(f"筛选后股票数量: {len(filtered_stocks)}")
```

## 核心模块说明

### 1. 选股模块 (`modules/stock_picker/picker.py`)

**职责**: 全市场扫描 → 量化筛选 → AI 精选 → 生成报告

**关键类**:
- `StockScreener`: 量化规则筛选器
- `StockPicker`: 选股主控制器

**筛选流程**:
1. 获取全市场股票列表 (AKShare)
2. 量化规则筛选 (市值、量比、PE、价格)
3. 技术指标计算 (MA、RSI、MACD)
4. AI 深度分析 (Claude API)
5. 生成每日报告并推送

**配置参数** (`config/settings.py` - `StockPickerConfig`):
```python
min_market_cap: float = 3.0      # 最小市值(亿)
max_market_cap: float = 10000.0  # 最大市值(亿)
min_volume_ratio: float = 1.0    # 最小量比
max_pe_ratio: float = 150.0      # 最大市盈率
top_n: int = 10                  # 每日推送数量
```

### 2. 监控模块 (`modules/monitor/monitor.py`)

**职责**: 实时监控自选股，检测买卖信号

**关键功能**:
- 自选股池管理 (`data/watchlist.json`)
- 实时价格监控 (60 秒轮询)
- 技术信号检测 (MACD 金叉/死叉、RSI 超买/超卖)
- 异动预警 (涨跌幅、成交量突破)
- AI 实时研判 (触发信号时调用 Claude)

**信号类型**:
- `MACD_GOLDEN_CROSS`: MACD 金叉 (买入信号)
- `MACD_DEATH_CROSS`: MACD 死叉 (卖出信号)
- `RSI_OVERSOLD`: RSI 超卖 (买入信号)
- `RSI_OVERBOUGHT`: RSI 超买 (卖出信号)
- `PRICE_SPIKE`: 价格异动 (涨跌幅 > 3%)
- `VOLUME_SPIKE`: 成交量异动 (量比 > 3.0)

### 3. 板块分析模块 (`modules/sector/analyzer.py`)

**职责**: 分析 31 个一级板块，追踪资金流向和轮动规律

**分析维度**:
- 板块涨跌幅排名
- 主力资金净流入
- 板块内龙头股识别
- 板块轮动规律 (AI 分析)

**输出报告**:
- 今日热点板块 (Top 5)
- 资金流向分析
- 龙头股推荐
- 明日关注板块

### 4. AI 分析引擎 (`ai/analysis_engine.py`)

**职责**: 封装 Claude API，提供统一的 AI 分析接口

**核心方法**:
```python
# 单股深度分析
analyze_stock(stock_code, stock_data, technical_indicators) -> Dict

# 批量股票分析
analyze_stocks_batch(stocks_data) -> List[Dict]

# 板块分析
analyze_sector(sector_name, sector_data) -> str

# 市场早报生成
generate_morning_brief(market_data) -> str

# 监控信号研判
analyze_signal(stock_code, signal_type, current_data) -> str
```

**Prompt 设计原则**:
1. **角色定位**: "你是一位资深的 A 股分析师"
2. **结构化输出**: 使用 JSON 格式返回结果
3. **明确指标**: 提供买入逻辑、目标价位、风险提示
4. **温度设置**: temperature=0.3 (保证分析稳定性)

### 5. 数据层 (`data/data_service.py`)

**职责**: 封装 AKShare API，提供统一的数据接口

**核心服务**:
```python
# 市场数据
get_all_stocks() -> pd.DataFrame           # 全市场股票列表
get_stock_realtime(code) -> Dict           # 实时行情
get_stock_history(code, days) -> pd.DataFrame  # 历史 K 线

# 板块数据
get_sector_list() -> List[str]             # 板块列表
get_sector_stocks(sector) -> List[str]     # 板块成分股
get_sector_fund_flow(sector) -> Dict       # 板块资金流向

# 技术指标
calculate_ma(df, periods) -> pd.DataFrame  # 移动平均线
calculate_rsi(df, period) -> pd.Series     # 相对强弱指标
calculate_macd(df) -> Tuple                # MACD 指标
```

**缓存策略**:
- 内存缓存 (默认): 5 分钟 TTL
- Redis 缓存 (可选): 配置 `config.data.use_redis = True`

### 6. 定时任务调度器 (`core/scheduler.py`)

**职责**: 管理所有定时任务

**任务列表**:
```python
# 每日选股 (交易日 9:45)
CronTrigger(hour=9, minute=45, day_of_week="mon-fri")

# 板块分析 (交易日 17:00)
CronTrigger(hour=17, minute=0, day_of_week="mon-fri")

# 市场早报 (每天 8:00)
CronTrigger(hour=8, minute=0)
```

**手动触发**:
```python
from core.scheduler import scheduler

# 手动触发选股
scheduler.trigger_stock_pick()

# 手动触发板块分析
scheduler.trigger_sector_analysis()
```

### 7. 通知层 (`notify/notifier.py`)

**职责**: 统一管理所有通知推送

**支持渠道**:
- PushPlus 微信推送 (默认启用)
- Telegram Bot (需配置 token)
- 邮件通知 (可选)

**通知类型**:
```python
# 每日选股报告
send_daily_picks(report: str)

# 板块分析报告
send_sector_report(report: str)

# 市场早报
send_morning_brief(brief: str)

# 监控信号预警
send_monitor_alert(stock_code, signal_type, analysis)
```

## 配置管理

### 环境变量 (`.env`)

```bash
# AI 配置（必填）
ANTHROPIC_API_KEY=sk-ant-xxx

# 通知配置（可选）
PUSHPLUS_TOKEN=your-pushplus-token
TELEGRAM_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-chat-id

# 数据库配置（可选）
REDIS_URL=redis://localhost:6379/0
```

### 系统配置 (`config/settings.py`)

所有配置参数集中在 `SystemConfig` 类中，使用 `@dataclass` 定义。

**修改配置示例**:
```python
# 修改选股参数
config.stock_picker.min_market_cap = 5.0
config.stock_picker.top_n = 20

# 修改监控参数
config.monitor.check_interval = 30
config.monitor.price_change_alert = 5.0

# 修改 AI 模型
config.ai.model = "claude-opus-4-5-20251101"
config.ai.temperature = 0.5
```

## 开发工作流

### 添加新功能

1. **创建功能分支**:
   ```bash
   git checkout -b feature/new-indicator
   ```

2. **编写代码**:
   - 在对应模块目录下创建文件
   - 遵循现有代码风格和架构
   - 添加完整的类型注解和文档字符串

3. **添加配置**:
   - 在 `config/settings.py` 中添加配置类
   - 在 `.env.example` 中添加环境变量说明

4. **测试**:
   ```bash
   # 单元测试
   python -m pytest tests/

   # 功能测试
   python main.py --test-picker
   ```

5. **提交代码**:
   ```bash
   git add .
   git commit -m "feat: 添加新技术指标 XXX"
   git push origin feature/new-indicator
   ```

### 调试技巧

1. **查看日志**:
   ```bash
   tail -f logs/system.log
   ```

2. **测试单个模块**:
   ```bash
   # 测试选股模块
   python main.py --test-picker

   # 测试板块分析
   python main.py --test-sector
   ```

3. **手动触发任务**:
   ```python
   from core.scheduler import scheduler
   scheduler.trigger_stock_pick()
   ```

4. **调试 AI 分析**:
   ```python
   from ai.analysis_engine import ai_engine
   result = ai_engine.analyze_stock("600519", stock_data, indicators)
   print(result)
   ```

## 常见问题

### 1. AKShare 数据获取失败

**原因**: 网络问题、API 限流、数据源维护

**解决方案**:
- 检查网络连接
- 增加重试次数 (`config.data.retry_times`)
- 增加重试延迟 (`config.data.retry_delay`)
- 使用缓存数据降级

### 2. Claude API 调用失败

**原因**: API Key 无效、配额不足、网络问题

**解决方案**:
- 检查 `.env` 中的 `ANTHROPIC_API_KEY`
- 检查 API 配额: https://console.anthropic.com/
- 降低调用频率 (减少 `top_n` 数量)

### 3. 通知推送失败

**原因**: Token 无效、网络问题

**解决方案**:
- 检查 PushPlus Token: https://www.pushplus.plus/
- 检查 Telegram Bot Token 和 Chat ID
- 查看日志中的详细错误信息

### 4. 定时任务未执行

**原因**: 系统未启动、时区问题、非交易日

**解决方案**:
- 确认系统正在运行 (`python main.py`)
- 检查调度器状态 (查看日志中的 "已注册定时任务")
- 确认当前时间和任务触发时间
- 注意交易日限制 (`day_of_week="mon-fri"`)

## 性能优化

### 1. 数据缓存

```python
# 启用 Redis 缓存
config.data.use_redis = True
config.data.cache_ttl = 300  # 5 分钟
```

### 2. 批量处理

```python
# AI 批量分析（减少 API 调用次数）
results = ai_engine.analyze_stocks_batch(stocks_data)
```

### 3. 异步处理

```python
# Web 服务在独立线程运行
web_thread = Thread(target=start_web_server, daemon=True)
web_thread.start()
```

## 安全注意事项

1. **API Key 保护**:
   - 不要将 `.env` 文件提交到 Git
   - 使用 `.env.example` 作为模板
   - 定期轮换 API Key

2. **数据验证**:
   - 验证用户输入的股票代码格式
   - 限制自选股池数量 (`max_watchlist`)
   - 防止 SQL 注入 (使用参数化查询)

3. **错误处理**:
   - 不要在日志中输出敏感信息
   - 捕获所有外部 API 异常
   - 提供友好的错误提示

## 风险提示

⚠️ **重要声明**:
1. 本系统仅供学习研究使用，不构成任何投资建议
2. AI 分析结果仅供参考，不保证准确性
3. 股市有风险，投资需谨慎
4. 请勿将本系统用于实盘交易决策
5. 使用本系统造成的任何损失，开发者不承担责任

## 开发路线图

- [ ] 回测模块 (策略回测 + 收益分析)
- [ ] 更多技术指标 (CCI、OBV、ATR、布林带)
- [ ] 基本面数据 (财报、估值、股东变动)
- [ ] 多策略支持 (趋势、均值回归、网格)
- [ ] WebSocket 实时推送
- [ ] 移动端 App
- [ ] 多市场支持 (港股、美股)

## 贡献指南

欢迎提交 Issue 和 Pull Request！

**提交 PR 前请确保**:
1. 代码通过所有测试
2. 遵循项目代码风格
3. 添加必要的文档和注释
4. 更新 README.md (如有必要)

## 许可证

MIT License

---

**祝开发顺利！📈**
