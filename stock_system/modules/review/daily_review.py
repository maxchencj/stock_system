"""
每日复盘模板 - 交易日 21:00 自动生成当日复盘
推送内容：市场总结 / 行业轮动 / 涨停分析 / 次日关注
推送频率：交易日 21:00 → A股Bot
"""
from datetime import datetime
from typing import Dict, List

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger


def _fetch_market_summary() -> Dict:
    """获取大盘今日数据（腾讯Finance）"""
    try:
        import requests
        symbols = {
            "sh000001": "上证",
            "sz399001": "深证",
            "sz399006": "创业板",
            "sh000016": "上证50",
        }
        codes = ",".join(f"s_{c}" for c in symbols)
        url = f"http://qt.gtimg.cn/q={codes}"
        resp = requests.get(url, timeout=8)
        resp.encoding = "gbk"
        indices = {}
        for line in resp.text.strip().split("\n"):
            if "~" not in line:
                continue
            parts = line.split("~")
            if len(parts) < 35:
                continue
            for code, name in symbols.items():
                if code in line:
                    try:
                        indices[name] = {
                            "price": float(parts[3]),
                            "pct": float(parts[32]),
                            "vol": float(parts[36]) if len(parts) > 36 else 0,
                        }
                    except Exception:
                        pass
        return indices
    except Exception as e:
        logger.warning(f"获取大盘数据失败: {e}")
        return {}


def _fetch_limit_stats() -> Dict:
    """获取今日涨跌停统计"""
    try:
        import akshare as ak
        today = datetime.now().strftime("%Y%m%d")
        zt_df = ak.stock_zt_pool_em(date=today)
        dt_df = ak.stock_zt_pool_dtgc_em(date=today)
        zt_count = len(zt_df) if zt_df is not None else 0
        dt_count = len(dt_df) if dt_df is not None else 0

        # 涨停板连板统计
        lian_count = 0
        top_sectors = []
        if zt_df is not None and not zt_df.empty:
            if "连板数" in zt_df.columns:
                lian_count = int((zt_df["连板数"] >= 2).sum())
            if "所属行业" in zt_df.columns:
                top_sectors = (
                    zt_df["所属行业"].value_counts().head(3).index.tolist()
                )
        return {
            "zt": zt_count,
            "dt": dt_count,
            "lian": lian_count,
            "sectors": top_sectors,
        }
    except Exception as e:
        logger.warning(f"获取涨跌停数据失败: {e}")
        return {"zt": 0, "dt": 0, "lian": 0, "sectors": []}


def _fetch_top_stocks() -> Dict:
    """获取今日涨幅榜 / 跌幅榜 Top5"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            return {}
        df = df[df["最新价"] > 3].copy()
        df["涨跌幅"] = df["涨跌幅"].astype(float)
        df["成交额"] = df["成交额"].astype(float)

        top_up = df.nlargest(5, "涨跌幅")[["名称", "最新价", "涨跌幅"]].to_dict("records")
        top_down = df.nsmallest(5, "涨跌幅")[["名称", "最新价", "涨跌幅"]].to_dict("records")
        top_vol = df.nlargest(5, "成交额")[["名称", "最新价", "成交额"]].to_dict("records")
        return {"up": top_up, "down": top_down, "vol": top_vol}
    except Exception as e:
        logger.warning(f"获取涨跌榜失败: {e}")
        return {}


def _ai_review(indices: Dict, limit_stats: Dict, top_stocks: Dict) -> str:
    system_prompt = "你是资深A股复盘分析师，善于总结当日市场规律，寻找次日机会。"

    idx_str = "  ".join([
        f"{k} {v['pct']:+.2f}%" for k, v in indices.items()
    ]) if indices else "数据获取失败"

    sec_str = "、".join(limit_stats.get("sectors", [])) or "无"
    up_str = "  ".join([
        f"{s['名称']}{s['涨跌幅']:+.1f}%" for s in top_stocks.get("up", [])
    ]) or "无"

    user_prompt = f"""今日A股复盘数据：

【大盘指数】{idx_str}
【涨跌停】涨停{limit_stats.get('zt', 0)}家 / 跌停{limit_stats.get('dt', 0)}家 / 连板{limit_stats.get('lian', 0)}家
【涨停热点行业】{sec_str}
【涨幅榜Top5】{up_str}

请用200字以内输出：
【今日总结】市场整体情绪（强/弱/分化）及核心逻辑
【热点分析】今日主线热点板块是否延续？连板数量是否健康？
【次日关注】明天重点关注哪类机会（反弹/追板/观望）？给出具体方向"""

    return ai_engine._call(system_prompt, user_prompt, max_tokens=500)


class DailyReview:

    def run_daily_push(self):
        logger.info("执行每日复盘")
        indices = _fetch_market_summary()
        limit_stats = _fetch_limit_stats()
        top_stocks = _fetch_top_stocks()

        ai_text = _ai_review(indices, limit_stats, top_stocks)

        # 格式化指数行
        if indices:
            idx_lines = "\n".join([
                f"  {name}: {d['price']:.2f}  {d['pct']:+.2f}%"
                for name, d in indices.items()
            ])
        else:
            idx_lines = "  数据获取中..."

        # 涨幅榜
        up_lines = "\n".join([
            f"  🔴 {s['名称']}  {float(s['涨跌幅']):+.2f}%"
            for s in top_stocks.get("up", [])
        ]) or "  暂无"

        # 跌幅榜
        down_lines = "\n".join([
            f"  🟢 {s['名称']}  {float(s['涨跌幅']):+.2f}%"
            for s in top_stocks.get("down", [])
        ]) or "  暂无"

        sec_str = "  ".join(limit_stats.get("sectors", [])) or "无"

        msg = (
            f"📋 每日复盘 — {datetime.now().strftime('%Y-%m-%d')}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📊 大盘指数\n{idx_lines}\n\n"
            f"📈 今日涨跌停\n"
            f"  涨停: {limit_stats.get('zt', 0)}家  "
            f"跌停: {limit_stats.get('dt', 0)}家  "
            f"连板: {limit_stats.get('lian', 0)}家\n"
            f"  热点行业: {sec_str}\n\n"
            f"🏆 涨幅榜 Top5\n{up_lines}\n\n"
            f"💔 跌幅榜 Top5\n{down_lines}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"{ai_text}"
        )
        notifier.telegram.send(msg)
        logger.info("每日复盘已推送")


daily_review = DailyReview()
