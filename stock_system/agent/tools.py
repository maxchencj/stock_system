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
