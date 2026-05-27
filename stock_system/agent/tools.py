import json
import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "stock_system" / "data"

READONLY_PREFIXES = ("SELECT", "WITH")


def query_push_history(sql: str) -> dict[str, Any]:
    """执行只读 SQL 查询 push_history 数据库，仅支持 SELECT/WITH 语句。

    返回: {"rows": [...], "count": N} 或 {"error": "..."}
    """
    if not sql.strip().upper().startswith(READONLY_PREFIXES):
        return {"error": "仅支持 SELECT / WITH 查询语句"}
    db_path = DATA_DIR / "push_history.db"
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(sql)
            rows = [dict(r) for r in cur.fetchall()]
        return {"rows": rows, "count": len(rows)}
    except Exception as e:
        return {"error": str(e)}


def read_portfolio(section: str = "all") -> dict[str, Any]:
    """读取持仓与交易历史。

    section: "positions" | "history" | "all"（默认）
    返回对应数据或 {"error": "..."}
    """
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
    """读取量化评分数据。

    date: 格式 YYYY-MM-DD，不传则返回所有日期数据
    返回 {date: {股票代码: {name, score}}} 或 {"error": "..."}
    """
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
    """读取 API 使用量统计，返回最近 N 天数据。

    days: 正整数，默认 7
    返回 {"daily": {date: {calls, tokens}}, "total": {...}} 或 {"error": "..."}
    """
    if days <= 0:
        return {"error": "days 必须为正整数"}
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
    """读取自选股池。

    market: "a_share" | "us_stock" | "all"（默认）
    返回 {"a_share": {...}, "us_stock": {...}} 或 {"error": "..."}
    """
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
