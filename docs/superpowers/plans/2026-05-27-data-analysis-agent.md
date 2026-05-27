# 数据分析 Agent 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个基于 Claude API 的数据分析 Agent，可通过命令行用自然语言查询 claudeForStock 系统的所有本地数据。

**Architecture:** Agent 主入口负责对话循环和工具调度，tools.py 封装 5 个数据源（SQLite + JSON），prompts.py 定义角色。Claude API 的 tool_use 机制驱动 Agent 自主决定调用哪些工具、如何组合分析。

**Tech Stack:** Python 3.11, anthropic SDK, sqlite3, pathlib, json

---

## 文件结构

| 路径 | 操作 | 职责 |
|---|---|---|
| `stock_system/agent/__init__.py` | 新建 | 包标识 |
| `stock_system/agent/prompts.py` | 新建 | System prompt |
| `stock_system/agent/tools.py` | 新建 | 5 个数据查询工具函数 |
| `stock_system/agent/analyst_agent.py` | 新建 | Agent 主入口、工具调度、对话循环 |
| `stock_system/tests/test_agent_tools.py` | 新建 | tools.py 单元测试 |

---

## Task 1: 创建包结构和 prompts.py

**Files:**
- Create: `stock_system/agent/__init__.py`
- Create: `stock_system/agent/prompts.py`

- [ ] **Step 1: 创建 `stock_system/agent/__init__.py`**

```python
```
（空文件即可）

- [ ] **Step 2: 创建 `stock_system/agent/prompts.py`**

```python
SYSTEM_PROMPT = """你是一位资深的股票数据分析师，专门分析 claudeForStock 系统的运行数据。

你拥有以下数据查询工具：
- query_push_history: 查询推送历史数据库（SQLite，仅限 SELECT 语句）
- read_portfolio: 读取持仓与交易记录
- read_quant_scores: 读取量化评分数据
- read_api_usage: 读取 API 使用量统计
- read_watchlist: 读取自选股池

分析原则：
1. 先用工具获取原始数据，再做分析，不要凭空估计
2. 每次回答结构：数据摘要 → 关键发现 → 建议（如适用）
3. 涉及数字时给出具体值，不用模糊表达
4. 投资相关建议仅供参考，须附风险提示"""
```

- [ ] **Step 3: Commit**

```bash
git add stock_system/agent/__init__.py stock_system/agent/prompts.py
git commit -m "feat: agent 包结构和 system prompt"
```

---

## Task 2: 实现 tools.py（先写测试）

**Files:**
- Create: `stock_system/tests/test_agent_tools.py`
- Create: `stock_system/agent/tools.py`

- [ ] **Step 1: 写失败测试**

新建 `stock_system/tests/test_agent_tools.py`：

```python
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from stock_system.agent.tools import (
    query_push_history,
    read_portfolio,
    read_quant_scores,
    read_api_usage,
    read_watchlist,
)


class TestQueryPushHistory:
    def test_select_count_returns_rows(self):
        result = query_push_history("SELECT COUNT(*) as total FROM push_history")
        assert "rows" in result
        assert result["rows"][0]["total"] > 0

    def test_invalid_sql_returns_error(self):
        result = query_push_history("DROP TABLE push_history")
        assert "error" in result

    def test_filter_by_bot(self):
        result = query_push_history("SELECT bot, COUNT(*) as cnt FROM push_history GROUP BY bot")
        assert "rows" in result
        assert len(result["rows"]) > 0


class TestReadPortfolio:
    def test_all_returns_positions_and_history(self):
        result = read_portfolio("all")
        assert "positions" in result or "error" in result

    def test_positions_section(self):
        result = read_portfolio("positions")
        assert "positions" in result or "error" in result

    def test_invalid_section_returns_error(self):
        result = read_portfolio("nonexistent_section")
        assert "error" in result


class TestReadQuantScores:
    def test_no_date_returns_all(self):
        result = read_quant_scores()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_valid_date_returns_that_date(self):
        all_data = read_quant_scores()
        if not all_data:
            pytest.skip("quant_scores.json 无数据")
        first_date = list(all_data.keys())[0]
        result = read_quant_scores(date=first_date)
        assert first_date in result

    def test_invalid_date_returns_error(self):
        result = read_quant_scores(date="1900-01-01")
        assert "error" in result


class TestReadApiUsage:
    def test_default_7_days(self):
        result = read_api_usage()
        assert "daily" in result
        assert len(result["daily"]) <= 7

    def test_custom_days(self):
        result = read_api_usage(days=3)
        assert "daily" in result
        assert len(result["daily"]) <= 3

    def test_includes_total(self):
        result = read_api_usage()
        assert "total" in result


class TestReadWatchlist:
    def test_all_returns_both_markets(self):
        result = read_watchlist("all")
        assert "a_share" in result or "us_stock" in result

    def test_a_share_only(self):
        result = read_watchlist("a_share")
        assert "a_share" in result
        assert "us_stock" not in result

    def test_us_stock_only(self):
        result = read_watchlist("us_stock")
        assert "us_stock" in result
        assert "a_share" not in result
```

- [ ] **Step 2: 确认测试失败**

```bash
cd /Users/maxchen/Desktop/claudeForStock
python3 -m pytest stock_system/tests/test_agent_tools.py -v 2>&1 | head -30
```

期望输出：`ModuleNotFoundError: No module named 'stock_system.agent.tools'`

- [ ] **Step 3: 实现 `stock_system/agent/tools.py`**

```python
import json
import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "stock_system" / "data"

READONLY_PREFIXES = ("SELECT", "WITH")


def query_push_history(sql: str) -> dict[str, Any]:
    if not sql.strip().upper().startswith(READONLY_PREFIXES):
        return {"error": "仅支持 SELECT / WITH 查询语句"}
    db_path = DATA_DIR / "push_history.db"
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return {"rows": rows, "count": len(rows)}
    except Exception as e:
        return {"error": str(e)}


def read_portfolio(section: str = "all") -> dict[str, Any]:
    path = DATA_DIR / "portfolio.json"
    if not path.exists():
        return {"error": f"数据文件不存在: {path}"}
    data: dict = json.loads(path.read_text(encoding="utf-8"))
    if section == "all":
        return data
    if section not in data:
        return {"error": f"section '{section}' 不存在，可选: {list(data.keys())}"}
    return {section: data[section]}


def read_quant_scores(date: str = "") -> dict[str, Any]:
    path = DATA_DIR / "quant_scores.json"
    if not path.exists():
        return {"error": f"数据文件不存在: {path}"}
    data: dict = json.loads(path.read_text(encoding="utf-8"))
    if not date:
        return data
    if date not in data:
        return {"error": f"日期 {date} 无数据，可用日期: {sorted(data.keys())}"}
    return {date: data[date]}


def read_api_usage(days: int = 7) -> dict[str, Any]:
    path = DATA_DIR / "api_usage.json"
    if not path.exists():
        return {"error": f"数据文件不存在: {path}"}
    data: dict = json.loads(path.read_text(encoding="utf-8"))
    daily: dict = data.get("daily", {})
    recent_dates = sorted(daily.keys())[-days:]
    return {
        "daily": {d: daily[d] for d in recent_dates},
        "total": data.get("total", {}),
    }


def read_watchlist(market: str = "all") -> dict[str, Any]:
    result: dict[str, Any] = {}
    if market in ("a_share", "all"):
        path = DATA_DIR / "watchlist.json"
        if path.exists():
            result["a_share"] = json.loads(path.read_text(encoding="utf-8")).get("stocks", {})
    if market in ("us_stock", "all"):
        path = DATA_DIR / "us_watchlist.json"
        if path.exists():
            result["us_stock"] = json.loads(path.read_text(encoding="utf-8")).get("stocks", {})
    if not result:
        return {"error": f"market '{market}' 无数据，可选: a_share, us_stock, all"}
    return result
```

- [ ] **Step 4: 运行测试，确认全部通过**

```bash
cd /Users/maxchen/Desktop/claudeForStock
python3 -m pytest stock_system/tests/test_agent_tools.py -v
```

期望输出：所有测试 `PASSED`

- [ ] **Step 5: Commit**

```bash
git add stock_system/agent/tools.py stock_system/tests/test_agent_tools.py
git commit -m "feat: agent 数据查询工具层（含测试）"
```

---

## Task 3: 实现 analyst_agent.py

**Files:**
- Create: `stock_system/agent/analyst_agent.py`

- [ ] **Step 1: 创建 `stock_system/agent/analyst_agent.py`**

```python
#!/usr/bin/env python3
"""数据分析 Agent 主入口"""

import json
import sys
from anthropic import Anthropic
from stock_system.agent.prompts import SYSTEM_PROMPT
from stock_system.agent import tools as tool_module

TOOLS = [
    {
        "name": "query_push_history",
        "description": "执行 SQL 查询 push_history 数据库，仅支持 SELECT / WITH 语句",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SELECT SQL 语句"}
            },
            "required": ["sql"],
        },
    },
    {
        "name": "read_portfolio",
        "description": "读取持仓与交易历史",
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["positions", "history", "all"],
                    "description": "读取的部分，默认 all",
                }
            },
        },
    },
    {
        "name": "read_quant_scores",
        "description": "读取量化评分数据",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "指定日期 YYYY-MM-DD，不传则返回所有日期",
                }
            },
        },
    },
    {
        "name": "read_api_usage",
        "description": "读取 API 使用量统计",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "最近 N 天，默认 7",
                }
            },
        },
    },
    {
        "name": "read_watchlist",
        "description": "读取自选股池",
        "input_schema": {
            "type": "object",
            "properties": {
                "market": {
                    "type": "string",
                    "enum": ["a_share", "us_stock", "all"],
                    "description": "市场，默认 all",
                }
            },
        },
    },
]

TOOL_DISPATCH = {
    "query_push_history": tool_module.query_push_history,
    "read_portfolio": tool_module.read_portfolio,
    "read_quant_scores": tool_module.read_quant_scores,
    "read_api_usage": tool_module.read_api_usage,
    "read_watchlist": tool_module.read_watchlist,
}


def run_agent(question: str, messages: list) -> tuple[str, list]:
    client = Anthropic()
    messages = messages + [{"role": "user", "content": question}]

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            text = next(
                (b.text for b in response.content if hasattr(b, "text")), ""
            )
            messages.append({"role": "assistant", "content": response.content})
            return text, messages

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    fn = TOOL_DISPATCH[block.name]
                    result = fn(**block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})


def main() -> None:
    messages: list = []

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        answer, _ = run_agent(question, messages)
        print(answer)
        return

    print("数据分析师已就绪，输入问题开始分析（输入 exit 退出）\n")
    while True:
        try:
            question = input("分析师> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n再见！")
            break
        if not question:
            continue
        if question.lower() in ("exit", "quit", "退出"):
            print("再见！")
            break
        answer, messages = run_agent(question, messages)
        print(f"\n{answer}\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 冒烟测试（需要 ANTHROPIC_API_KEY）**

```bash
cd /Users/maxchen/Desktop/claudeForStock
python3 stock_system/agent/analyst_agent.py "push_history 里总共有多少条记录？"
```

期望输出：Agent 调用 `query_push_history`，返回类似"共 351 条推送记录"的分析

- [ ] **Step 3: Commit**

```bash
git add stock_system/agent/analyst_agent.py
git commit -m "feat: 数据分析 Agent 主入口"
```

---

## Task 4: 验收测试

- [ ] **Step 1: 运行全部测试**

```bash
cd /Users/maxchen/Desktop/claudeForStock
python3 -m pytest stock_system/tests/test_agent_tools.py -v
```

期望输出：全部 `PASSED`，0 failed

- [ ] **Step 2: 端到端测试 4 个核心场景**

```bash
# 场景1：系统健康监控
python3 stock_system/agent/analyst_agent.py "最近7天每个Bot的推送成功率分别是多少？"

# 场景2：投资表现分析
python3 stock_system/agent/analyst_agent.py "目前持仓的量化评分情况如何？"

# 场景3：选股评估
python3 stock_system/agent/analyst_agent.py "今天量化评分最高的三只股票是哪些？"

# 场景4：历史趋势
python3 stock_system/agent/analyst_agent.py "最近一周API调用量和token消耗趋势如何？"
```

每条命令均应返回有内容的中文分析报告，无 Python 报错。

- [ ] **Step 3: 最终 Commit**

```bash
git add .
git commit -m "feat: 数据分析 Agent 完成验收"
```
