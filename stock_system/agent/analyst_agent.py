#!/usr/bin/env python3
"""数据分析 Agent 主入口"""

import json
import sys
import anthropic
from anthropic import Anthropic
from stock_system.agent.prompts import SYSTEM_PROMPT
from stock_system.agent import tools as tool_module

MAX_TOOL_ROUNDS = 10

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

_client = Anthropic()


def run_agent(question: str, messages: list[dict]) -> tuple[str, list[dict]]:
    """执行一轮 Agent 推理，自动处理工具调用循环。

    Args:
        question: 用户问题字符串
        messages: 历史对话列表，每项为 {"role": ..., "content": ...}

    Returns:
        (最终回答文本, 更新后的 messages 列表)
    """
    messages = messages + [{"role": "user", "content": question}]

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = _client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        except anthropic.APIError as e:
            return f"API 错误：{e}", messages

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
                    fn = TOOL_DISPATCH.get(block.name)
                    if fn is None:
                        result: dict = {"error": f"未知工具: {block.name}"}
                    else:
                        try:
                            result = fn(**block.input)
                        except Exception as e:
                            result = {"error": str(e)}
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})
            continue

        # max_tokens / stop_sequence 等非预期 stop_reason，兜底退出
        return f"意外停止原因：{response.stop_reason}", messages

    return "已达最大工具调用轮次，任务中止", messages


def main() -> None:
    """命令行入口：单次提问或交互式多轮对话。

    用法：
      python3 analyst_agent.py "问题"   # 单次模式
      python3 analyst_agent.py          # 交互式模式
    """
    messages: list[dict] = []

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
