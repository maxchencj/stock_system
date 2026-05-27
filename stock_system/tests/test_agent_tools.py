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
