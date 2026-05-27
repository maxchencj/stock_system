#!/usr/bin/env python3
"""数据分析 Agent 端到端冒烟测试

使用真实工具数据 + Mock Claude API，验证 Agent 完整调用链。
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import stock_system.agent.analyst_agent as agent_mod
from stock_system.agent import tools as t


# ─────────────────────────── helpers ────────────────────────────

def _tool_response(tool_name: str, tool_input: dict, uid: str = "tid_1"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input
    block.id = uid
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    resp.content = [block]
    return resp


def _text_response(text: str):
    block = MagicMock()
    block.text = text
    block.type = "text"
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [block]
    return resp


def _run(question: str, tool_name: str, tool_input: dict, final_text: str):
    """Run agent with one tool call then a text answer, return the answer."""
    mock_client = MagicMock()
    calls = iter([_tool_response(tool_name, tool_input), _text_response(final_text)])
    mock_client.messages.create.side_effect = lambda **kw: next(calls)
    agent_mod._client = mock_client
    answer, _ = agent_mod.run_agent(question, [])
    return answer


# ─────────────────────────── tests ──────────────────────────────

class TestE2EScenario1SystemHealth:
    """场景1：系统健康监控 — Bot 推送成功率"""

    def test_success_rate_returned(self):
        sql = (
            "SELECT bot, COUNT(*) as total, SUM(success) as success_count, "
            "ROUND(100.0*SUM(success)/COUNT(*),1) as rate "
            "FROM push_history WHERE ts >= datetime('now','-7 days') GROUP BY bot"
        )
        # Verify tool returns real data with numbers
        real_data = t.query_push_history(sql)
        assert "rows" in real_data
        assert len(real_data["rows"]) >= 1
        for row in real_data["rows"]:
            assert "bot" in row
            assert "total" in row
            assert row["total"] > 0

    def test_agent_pipeline(self):
        sql = (
            "SELECT bot, COUNT(*) as total, SUM(success) as sc "
            "FROM push_history WHERE ts >= datetime('now','-7 days') GROUP BY bot"
        )
        real_data = t.query_push_history(sql)
        bots = [r["bot"] for r in real_data["rows"]]
        summary = "、".join(f"{r['bot']} 成功率{round(100*r['sc']/r['total'])}%" for r in real_data["rows"])
        answer = _run(
            "最近7天每个Bot的推送成功率分别是多少？",
            "query_push_history",
            {"sql": sql},
            f"最近7天推送情况：{summary}。",
        )
        assert len(answer) > 10
        assert any(b in answer for b in bots)


class TestE2EScenario2PortfolioPerformance:
    """场景2：投资表现分析 — 持仓量化评分"""

    def test_portfolio_has_positions(self):
        data = t.read_portfolio(section="positions")
        assert "positions" in data
        assert len(data["positions"]) >= 1

    def test_quant_scores_available(self):
        data = t.read_quant_scores()
        assert isinstance(data, dict)
        assert len(data) >= 1
        latest_date = sorted(data.keys())[-1]
        assert len(data[latest_date]) >= 1

    def test_agent_pipeline(self):
        positions = t.read_portfolio(section="positions")
        scores = t.read_quant_scores()
        answer = _run(
            "目前持仓的量化评分情况如何？",
            "read_portfolio",
            {"section": "positions"},
            f"目前持仓 {len(positions['positions'])} 只股票。最新量化评分日期为 {sorted(scores.keys())[-1]}。",
        )
        assert len(answer) > 10
        assert any(c.isdigit() for c in answer)


class TestE2EScenario3TopQuantStocks:
    """场景3：选股评估 — 量化评分最高三只"""

    def test_scores_sorted_descending(self):
        data = t.read_quant_scores()
        latest = sorted(data.keys())[-1]
        scores = data[latest]
        sorted_scores = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)
        top3 = sorted_scores[:3]
        assert len(top3) == 3
        assert top3[0][1]["score"] >= top3[1][1]["score"] >= top3[2][1]["score"]

    def test_agent_pipeline(self):
        data = t.read_quant_scores()
        latest = sorted(data.keys())[-1]
        sorted_scores = sorted(data[latest].items(), key=lambda x: x[1]["score"], reverse=True)
        top3 = sorted_scores[:3]
        names = "、".join(f"{v['name']}({v['score']:.2f})" for _, v in top3)
        answer = _run(
            "今天量化评分最高的三只股票是哪些？",
            "read_quant_scores",
            {"date": latest},
            f"量化评分最高三只（{latest}）：{names}。",
        )
        assert len(answer) > 10
        assert any(v["name"] in answer for _, v in top3)


class TestE2EScenario4ApiTrend:
    """场景4：历史趋势 — API 调用量和 token 消耗"""

    def test_api_usage_has_daily_data(self):
        data = t.read_api_usage(days=7)
        assert "daily" in data
        assert "total" in data
        assert len(data["daily"]) >= 1
        for day_data in data["daily"].values():
            assert "calls" in day_data
            assert "total_tokens" in day_data
            assert day_data["calls"] > 0

    def test_total_aggregates_correctly(self):
        data = t.read_api_usage(days=7)
        # total is cumulative across all history, daily is filtered to N days
        # total["calls"] >= sum of filtered daily calls
        sum_daily_calls = sum(d["calls"] for d in data["daily"].values())
        assert data["total"]["calls"] >= sum_daily_calls

    def test_agent_pipeline(self):
        data = t.read_api_usage(days=7)
        total = data["total"]
        answer = _run(
            "最近一周API调用量和token消耗趋势如何？",
            "read_api_usage",
            {"days": 7},
            f"最近7天共调用API {total['calls']} 次，消耗token {total['total_tokens']} 个。",
        )
        assert len(answer) > 10
        assert str(total["calls"]) in answer or str(total["total_tokens"]) in answer
