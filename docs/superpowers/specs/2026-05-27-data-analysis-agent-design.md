# 数据分析 Agent 设计文档

**日期**: 2026-05-27  
**项目**: claudeForStock  
**状态**: 待实施

---

## 目标

为 claudeForStock 项目构建一个基于 Claude API 的数据分析 Agent，能够用自然语言回答关于系统数据的问题，覆盖系统健康监控、投资表现分析、选股干预评估、历史趋势查询四类场景。

---

## 架构

### 目录结构

```
stock_system/agent/
├── analyst_agent.py     # Agent 主入口，对话循环
├── tools.py             # 数据查询工具定义与实现
└── prompts.py           # System prompt
```

### 运行流程

```
用户输入问题
    → Claude 分析问题，决定调用哪些工具
    → 工具执行，返回原始数据
    → Claude 综合数据，生成结构化分析报告
    → 输出（数据摘要 → 关键发现 → 建议）
```

Agent 使用 Anthropic SDK，模型为 `claude-sonnet-4-6`，支持多轮对话（messages 列表保留上下文）。

---

## 工具层（tools.py）

共 5 个工具，每个工具对应一个数据源：

### 1. `query_push_history`
- **数据源**: `stock_system/data/push_history.db`（SQLite）
- **参数**: `sql: str` — 任意 SELECT 语句
- **用途**: 推送成功率统计、Bot 对比、按时间段查询推送记录
- **实现**: `sqlite3` 执行 SQL，返回 JSON 格式结果

### 2. `read_portfolio`
- **数据源**: `stock_system/data/portfolio.json`
- **参数**: `section: str` — `"positions"` 或 `"history"` 或 `"all"`
- **用途**: 当前持仓盈亏（需结合买入价）、持仓来源分布、历史交易记录
- **实现**: 读取 JSON，返回对应 section 数据

### 3. `read_quant_scores`
- **数据源**: `stock_system/data/quant_scores.json`
- **参数**: `date: str`（可选，格式 `YYYY-MM-DD`，默认返回所有日期）
- **用途**: 某日量化评分排名、某股多日评分趋势
- **实现**: 读取 JSON，按 date 过滤返回

### 4. `read_api_usage`
- **数据源**: `stock_system/data/api_usage.json`
- **参数**: `days: int`（可选，默认 7，返回最近 N 天数据）
- **用途**: API 调用量趋势、Token 消耗统计、费用估算
- **实现**: 读取 JSON，按日期排序后取最近 N 天

### 5. `read_watchlist`
- **数据源**: `stock_system/data/watchlist.json` + `us_watchlist.json`
- **参数**: `market: str` — `"a_share"` 或 `"us_stock"` 或 `"all"`
- **用途**: 自选股池持仓数量、加入时间、与 quant_scores 交叉分析
- **实现**: 合并两个 JSON 文件，按 market 过滤返回

---

## System Prompt（prompts.py）

```
你是一位资深的股票数据分析师，专门分析 claudeForStock 系统的运行数据。

你拥有以下数据查询工具：
- query_push_history: 查询推送历史数据库
- read_portfolio: 读取持仓与交易记录
- read_quant_scores: 读取量化评分数据
- read_api_usage: 读取 API 使用量统计
- read_watchlist: 读取自选股池

分析原则：
1. 先用工具获取原始数据，再做分析，不要凭空估计
2. 每次回答结构：数据摘要 → 关键发现 → 建议（如适用）
3. 涉及数字时给出具体值，不用模糊表达
4. 投资相关建议仅供参考，须附风险提示
```

---

## 入口（analyst_agent.py）

### 单次提问模式
```bash
python3 stock_system/agent/analyst_agent.py "最近一周推送成功率是多少？"
```

### 交互式多轮对话模式
```bash
python3 stock_system/agent/analyst_agent.py
分析师> 持仓里哪只股票量化评分最高？
分析师> 它最近三天的评分趋势如何？
分析师> exit
```

### 核心逻辑

```python
# 伪代码
messages = []
while True:
    user_input = get_input()
    messages.append({"role": "user", "content": user_input})
    
    while True:  # 工具调用循环
        response = client.messages.create(
            model="claude-sonnet-4-6",
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )
        if response.stop_reason == "end_turn":
            break
        if response.stop_reason == "tool_use":
            tool_results = execute_tools(response.content)
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
    
    print(response.final_text())
```

---

## 错误处理

- SQL 执行失败：捕获异常，返回错误信息给 Claude，由 Claude 决定是否重试或换思路
- JSON 文件不存在：返回 `{"error": "数据文件不存在: <path>"}` 
- API 调用失败：最多重试 2 次，超过则终止并提示用户

---

## 文件路径约定

所有数据路径基于项目根目录自动推导，不硬编码绝对路径：

```python
PROJECT_ROOT = Path(__file__).parent.parent.parent  # stock_system/agent/ -> 项目根
DATA_DIR = PROJECT_ROOT / "stock_system" / "data"
```

---

## 不在本期范围内

- 定时自动触发分析（属于监控 Agent 范畴）
- 推送分析结果到 Telegram
- Web UI 界面
- AKShare 实时行情查询（需要另一套工具）
