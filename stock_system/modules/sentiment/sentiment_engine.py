"""
大盘情绪雷达 - 每日综合市场情绪评分
每个交易日 15:30 推送 → A股Bot
数据来源：涨跌停池(AKShare) + 指数(腾讯) + 北向资金(AKShare)
"""
import requests
from datetime import datetime
from typing import Dict, Optional

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger


# ─────────────────── 数据采集 ───────────────────

def _get_indices() -> Dict:
    """腾讯财经获取主要指数"""
    try:
        url = "http://qt.gtimg.cn/q=s_sh000001,s_sz399001,s_sz399006,s_sh000016"
        r = requests.get(url, timeout=6)
        r.encoding = "gbk"
        result = {}
        names = {"000001": "上证指数", "399001": "深证成指", "399006": "创业板指", "000016": "上证50"}
        for line in r.text.strip().split("\n"):
            if "~" not in line:
                continue
            parts = line.split("~")
            if len(parts) < 6:
                continue
            code = parts[2]
            name = names.get(code, parts[1])
            try:
                result[name] = {
                    "price": float(parts[3]),
                    "change": float(parts[4]),
                    "pct": float(parts[5]),
                }
            except Exception:
                pass
        return result
    except Exception as e:
        logger.warning(f"获取指数数据失败: {e}")
        return {}


def _get_limit_counts() -> Dict:
    """获取涨跌停数量（AKShare涨停池 + 跌停池）"""
    today = datetime.now().strftime("%Y%m%d")
    result = {"limit_up": 0, "limit_down": 0, "consecutive_up": 0}
    try:
        import akshare as ak
        df_zt = ak.stock_zt_pool_em(date=today)
        if df_zt is not None and not df_zt.empty:
            result["limit_up"] = len(df_zt)
            if "连板数" in df_zt.columns:
                result["consecutive_up"] = len(df_zt[df_zt["连板数"] > 1])
    except Exception as e:
        logger.warning(f"获取涨停数据失败: {e}")

    try:
        import akshare as ak
        df_dt = ak.stock_zt_pool_dtgc_em(date=today)
        if df_dt is not None and not df_dt.empty:
            result["limit_down"] = len(df_dt)
    except Exception as e:
        logger.warning(f"获取跌停数据失败: {e}")

    return result


def _get_north_flow() -> Optional[float]:
    """获取北向资金当日净流入（亿元），沪深股通合计"""
    try:
        import akshare as ak
        import math
        total = 0.0
        valid = False
        for sym in ["沪股通", "深股通"]:
            df = ak.stock_hsgt_hist_em(symbol=sym)
            if df is None or df.empty:
                continue
            val = df.iloc[-1]["当日成交净买额"]
            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                total += float(val)
                valid = True
        return round(total / 1e8, 2) if valid else None
    except Exception as e:
        logger.warning(f"获取北向资金失败: {e}")
        return None


def _score_sentiment(indices: Dict, limits: Dict, north_flow: Optional[float]) -> int:
    """计算情绪分 0-100"""
    score = 50  # 基准

    # 上证涨跌幅 (-3% ~ +3% → -20 ~ +20)
    sh = indices.get("上证指数", {})
    pct = sh.get("pct", 0)
    score += max(-20, min(20, pct * 7))

    # 涨跌停比 (-15 ~ +15)
    zt = limits.get("limit_up", 0)
    dt = limits.get("limit_down", 0)
    if zt + dt > 0:
        ratio = (zt - dt) / (zt + dt)
        score += ratio * 15

    # 连板数量（市场赚钱效应）
    consec = limits.get("consecutive_up", 0)
    score += min(10, consec * 0.5)

    # 北向资金方向 (-10 ~ +10)
    if north_flow is not None:
        score += max(-10, min(10, north_flow * 0.5))

    return max(0, min(100, int(score)))


def _ai_sentiment_analysis(indices: Dict, limits: Dict, north_flow: Optional[float], score: int) -> str:
    """AI 生成情绪解读"""
    sh = indices.get("上证指数", {})
    chuang = indices.get("创业板指", {})
    system_prompt = "你是专业的A股市场分析师，请根据当日市场数据，给出简洁专业的市场情绪解读。"
    north_str = f"{north_flow:+.2f}亿元" if north_flow is not None else "数据暂缺"
    user_prompt = f"""今日市场数据：

上证指数: {sh.get('price', '?')} ({sh.get('pct', 0):+.2f}%)
创业板指: {chuang.get('price', '?')} ({chuang.get('pct', 0):+.2f}%)
涨停数量: {limits.get('limit_up', 0)} 只（其中连板 {limits.get('consecutive_up', 0)} 只）
跌停数量: {limits.get('limit_down', 0)} 只
北向资金净流入: {north_str}
综合情绪评分: {score}/100

请用150字以内输出：
【市场定性】一句话判断今日市场性质（强势/偏弱/震荡等）
【关键信号】最值得关注的1-2个信号
【明日预判】简要预判明日市场方向"""

    return ai_engine._call(system_prompt, user_prompt, max_tokens=400)


class SentimentEngine:

    def run_daily_push(self):
        logger.info("执行大盘情绪雷达")
        indices = _get_indices()
        limits = _get_limit_counts()
        north_flow = _get_north_flow()
        score = _score_sentiment(indices, limits, north_flow)

        # 情绪等级
        if score >= 70:
            level, emoji = "乐观", "🟢"
        elif score >= 55:
            level, emoji = "偏多", "🔵"
        elif score >= 45:
            level, emoji = "中性", "⚪"
        elif score >= 30:
            level, emoji = "偏空", "🟡"
        else:
            level, emoji = "悲观", "🔴"

        sh = indices.get("上证指数", {})
        chuang = indices.get("创业板指", {})
        north_str = f"{north_flow:+.2f}亿" if north_flow is not None else "暂缺"
        ai_text = _ai_sentiment_analysis(indices, limits, north_flow, score)

        msg = (
            f"{emoji} 大盘情绪雷达 — {datetime.now().strftime('%m/%d')}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🌡 情绪评分：{score}/100（{level}）\n\n"
            f"📊 指数\n"
            f"  上证 {sh.get('price','?')} ({sh.get('pct',0):+.2f}%)\n"
            f"  创业板 {chuang.get('price','?')} ({chuang.get('pct',0):+.2f}%)\n\n"
            f"📈 涨跌停\n"
            f"  涨停 {limits.get('limit_up',0)} 只 | 跌停 {limits.get('limit_down',0)} 只\n"
            f"  连板股 {limits.get('consecutive_up',0)} 只\n\n"
            f"🌏 北向资金：{north_str}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{ai_text}"
        )
        notifier.telegram.send(msg)
        logger.info(f"大盘情绪雷达已推送，评分:{score}")


sentiment_engine = SentimentEngine()
