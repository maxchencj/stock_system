"""
量化回测引擎
- 策略：纯价格动量（避免财务数据前瞻偏差）
- 机制：月度调仓，等权Top N
- 基准：沪深300（sh.000300）
- 数据：baostock 历史日K
Bot 命令 /backtest 触发，后台运行后推送结果
"""
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import pandas as pd
import numpy as np

from utils.logger import logger


# ─────────────────── 数据获取 ───────────────────

def _fetch_prices(codes: List[str], start: str, end: str) -> pd.DataFrame:
    """批量获取历史收盘价，返回 DataFrame(date × code)"""
    import baostock as bs
    bs.login()
    all_data = {}
    try:
        for code in codes:
            try:
                prefix = "sh" if code.startswith("6") else "sz"
                bs_code = f"{prefix}.{code}"
                rs = bs.query_history_k_data_plus(
                    bs_code, "date,close",
                    start_date=start, end_date=end,
                    frequency="d", adjustflag="3"
                )
                rows = []
                while rs.error_code == "0" and rs.next():
                    rows.append(rs.get_row_data())
                if rows:
                    df = pd.DataFrame(rows, columns=["date", "close"])
                    df["close"] = pd.to_numeric(df["close"], errors="coerce")
                    df = df.dropna().set_index("date")["close"]
                    all_data[code] = df
            except Exception:
                pass
    finally:
        bs.logout()

    if not all_data:
        return pd.DataFrame()
    price_df = pd.DataFrame(all_data)
    price_df.index = pd.to_datetime(price_df.index)
    price_df = price_df.sort_index().ffill()
    return price_df


def _fetch_benchmark(start: str, end: str) -> pd.Series:
    """获取沪深300基准"""
    import baostock as bs
    bs.login()
    rows = []
    try:
        rs = bs.query_history_k_data_plus(
            "sh.000300", "date,close",
            start_date=start, end_date=end,
            frequency="d", adjustflag="3"
        )
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
    except Exception:
        pass
    finally:
        bs.logout()

    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows, columns=["date", "close"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna().set_index("date")["close"]
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


# ─────────────────── 因子计算（纯价格）───────────────────

def _momentum_rank(prices: pd.DataFrame, lookback: int = 60) -> pd.Series:
    """截面动量排名（lookback 日收益率）"""
    if len(prices) < lookback + 1:
        return pd.Series(dtype=float)
    ret = prices.iloc[-1] / prices.iloc[-lookback - 1] - 1
    return ret.rank(ascending=True)  # 排名越高 = 动量越强


# ─────────────────── 回测核心 ───────────────────

def run_backtest(
    universe: List[str],
    start: str,
    end: str,
    top_n: int = 10,
    lookback: int = 60,
    rebalance: str = "M",   # 月末调仓（pandas 2.1.x 用 "M"，2.2+ 改为 "ME"）
) -> Dict:
    """
    运行价格动量策略回测
    返回：performance metrics + 每期持仓记录
    """
    logger.info(f"开始回测: {start} ~ {end}, 股票池{len(universe)}只, Top{top_n}")

    # 下载价格数据
    prices = _fetch_prices(universe, start, end)
    benchmark = _fetch_benchmark(start, end)

    if prices.empty:
        return {"error": "价格数据获取失败"}

    # 月末日期列表（调仓日）
    rebalance_dates = prices.resample(rebalance).last().index

    # 模拟组合
    portfolio_values = []
    current_holding = []
    trade_log = []

    # 初始资金 = 1.0
    pf_nav = 1.0
    last_prices = None

    for i, date in enumerate(rebalance_dates):
        # 当前可用历史
        hist = prices.loc[:date]
        if len(hist) < lookback + 5:
            continue

        # 计算动量排名，选 Top N
        ranks = _momentum_rank(hist, lookback)
        if ranks.empty:
            continue

        # 剔除当月涨幅 > 30% 的（过热避免追高）
        last_ret = hist.iloc[-1] / hist.iloc[-20] - 1 if len(hist) >= 20 else ranks * 0
        valid = ranks[last_ret < 0.30] if not last_ret.empty else ranks
        if valid.empty:
            valid = ranks

        new_holding = valid.nlargest(top_n).index.tolist()

        # 计算上期持仓收益
        if current_holding and last_prices is not None:
            cur_prices = hist.iloc[-1]
            ret_sum = 0
            count = 0
            for code in current_holding:
                if code in cur_prices and code in last_prices and last_prices[code] > 0:
                    ret_sum += cur_prices[code] / last_prices[code] - 1
                    count += 1
            period_ret = ret_sum / count if count > 0 else 0
            pf_nav *= (1 + period_ret)

        portfolio_values.append({"date": date, "nav": pf_nav})
        current_holding = new_holding
        last_prices = prices.loc[:date].iloc[-1].to_dict()

        trade_log.append({
            "date": date.strftime("%Y-%m"),
            "holdings": new_holding[:5],  # 记录前5只
        })

    if not portfolio_values:
        return {"error": "回测周期不足，无法生成结果"}

    # 组装 NAV 序列
    pf_series = pd.DataFrame(portfolio_values).set_index("date")["nav"]

    # 对齐基准，获取调仓日基准价格
    bm_start = pf_series.index[0]
    bm_end = pf_series.index[-1]
    bm_sub = benchmark.loc[bm_start:bm_end]

    bm_resampled = pd.Series(dtype=float)
    bm_final = 1.0
    if not bm_sub.empty:
        bm_nav = bm_sub / bm_sub.iloc[0]
        bm_final = float(bm_nav.iloc[-1])
        # 用调仓日对齐基准 NAV，计算月度收益率
        bm_resampled = bm_nav.reindex(pf_series.index, method="ffill")

    # 绩效指标
    metrics = _calc_metrics(pf_series, float(bm_final), len(rebalance_dates), bm_resampled)

    return {
        "start": start,
        "end": end,
        "universe_size": len(universe),
        "top_n": top_n,
        "lookback": lookback,
        "metrics": metrics,
        "recent_trades": trade_log[-6:],
        "nav_series": [(str(p["date"].date()), round(p["nav"], 4)) for p in portfolio_values],
    }


# ─────────────────── 绩效指标 ───────────────────

def _calc_metrics(nav: pd.Series, bm_final: float, n_periods: int,
                  bm_nav: pd.Series = None) -> Dict:
    total_ret = nav.iloc[-1] - 1
    years = n_periods / 12
    annual_ret = (1 + total_ret) ** (1 / max(years, 0.1)) - 1

    monthly_rets = nav.pct_change().dropna()
    sharpe = (
        monthly_rets.mean() / monthly_rets.std() * (12 ** 0.5)
        if monthly_rets.std() > 0 else 0
    )

    cummax = nav.cummax()
    drawdowns = nav / cummax - 1
    max_dd = float(drawdowns.min())

    # 胜率：用真实基准月收益对比（L2 修复）
    if bm_nav is not None and not bm_nav.empty:
        bm_monthly = bm_nav.pct_change().dropna()
    else:
        # 退化：均匀分布近似
        bm_monthly = pd.Series(
            [(bm_final ** (1 / max(n_periods, 1)) - 1)] * len(monthly_rets),
            index=monthly_rets.index
        )
    min_len = min(len(monthly_rets), len(bm_monthly))
    win_rate = float((monthly_rets.values[:min_len] > bm_monthly.values[:min_len]).mean())

    return {
        "total_ret": round(total_ret * 100, 2),
        "annual_ret": round(annual_ret * 100, 2),
        "sharpe": round(float(sharpe), 2),
        "max_dd": round(max_dd * 100, 2),
        "win_rate": round(win_rate * 100, 1),
        "bm_total_ret": round((bm_final - 1) * 100, 2),
        "excess_ret": round((total_ret - (bm_final - 1)) * 100, 2),
    }


# ─────────────────── 格式化报告 ───────────────────

def format_backtest_report(result: Dict) -> str:
    if "error" in result:
        return f"❌ 回测失败: {result['error']}"

    m = result["metrics"]
    trades = result.get("recent_trades", [])

    excess_icon = "🔴" if m["excess_ret"] >= 0 else "🟢"
    dd_icon = "🟡" if m["max_dd"] > -20 else "🔴"

    recent_str = "\n".join([
        f"  {t['date']}: {' / '.join(t['holdings'][:3])}"
        for t in trades[-4:]
    ]) or "  无记录"

    return (
        f"📊 量化回测报告\n"
        f"策略：价格动量 Top{result['top_n']}  月度调仓\n"
        f"周期：{result['start']} ~ {result['end']}\n"
        f"股票池：{result['universe_size']} 只\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📈 策略累计收益：{m['total_ret']:+.1f}%\n"
        f"📊 沪深300同期：{m['bm_total_ret']:+.1f}%\n"
        f"{excess_icon} 超额收益：{m['excess_ret']:+.1f}%\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"年化收益率：{m['annual_ret']:+.1f}%\n"
        f"夏普比率：{m['sharpe']:.2f}\n"
        f"{dd_icon} 最大回撤：{m['max_dd']:.1f}%\n"
        f"月度胜率：{m['win_rate']:.0f}%\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"近期持仓\n{recent_str}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⚠️ 本回测仅供学习研究，不构成投资建议"
    )
