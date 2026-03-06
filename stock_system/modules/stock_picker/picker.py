"""
选股模块 - 全市场扫描 + 规则筛选 + AI精选 + 每日推送
"""
import json
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from config.settings import config
from data.data_service import market_service, indicators as tech_indicators
from ai.analysis_engine import ai_engine
from utils.logger import logger


class StockScreener:
    """量化规则选股器"""

    def __init__(self):
        self.cfg = config.stock_picker

    def screen_by_rules(self, df: pd.DataFrame) -> pd.DataFrame:
        """基础规则筛选"""
        if df.empty:
            return df

        original_count = len(df)
        conditions = []

        # 价格过滤
        if "price" in df.columns:
            conditions.append(
                (df["price"] >= self.cfg.min_price) & (df["price"] <= self.cfg.max_price)
            )

        # 市值过滤（单位：元 → 亿）
        if "market_cap" in df.columns:
            cap_b = df["market_cap"] / 1e8
            conditions.append(
                (cap_b >= self.cfg.min_market_cap) & (cap_b <= self.cfg.max_market_cap)
            )

        # 量比过滤
        if "volume_ratio" in df.columns:
            conditions.append(df["volume_ratio"] >= self.cfg.min_volume_ratio)

        # 市盈率过滤
        if "pe_ratio" in df.columns:
            conditions.append(
                (df["pe_ratio"] > 0) & (df["pe_ratio"] <= self.cfg.max_pe_ratio)
            )

        # 涨幅过滤（排除涨停/跌停异动）
        if "change_pct" in df.columns:
            conditions.append(
                (df["change_pct"] > -9.5) & (df["change_pct"] < 9.5)
            )

        # 成交额过滤（至少1000万）
        if "amount" in df.columns:
            conditions.append(df["amount"] >= 1e7)

        if conditions:
            combined = conditions[0]
            for c in conditions[1:]:
                combined = combined & c
            df = df[combined]

        logger.info(f"规则筛选: {original_count} → {len(df)} 只")
        return df.reset_index(drop=True)

    def score_stock(self, row: pd.Series) -> float:
        """对单只股票打分（0-100）"""
        score = 50.0

        # 量比得分（量能放大是好信号）
        if "volume_ratio" in row and pd.notna(row["volume_ratio"]):
            vr = float(row["volume_ratio"])
            if 1.5 <= vr <= 3.0:
                score += 10
            elif vr > 3.0:
                score += 5  # 过高量比风险也大

        # 涨幅得分
        if "change_pct" in row and pd.notna(row["change_pct"]):
            cp = float(row["change_pct"])
            if 1.0 <= cp <= 5.0:
                score += 10
            elif cp > 5.0:
                score += 5

        # 换手率得分
        if "turnover_rate" in row and pd.notna(row["turnover_rate"]):
            tr = float(row["turnover_rate"])
            if 3.0 <= tr <= 10.0:
                score += 8

        # 市盈率得分
        if "pe_ratio" in row and pd.notna(row["pe_ratio"]):
            pe = float(row["pe_ratio"])
            if 10 <= pe <= 40:
                score += 10
            elif 40 < pe <= 80:
                score += 5

        # 市净率得分
        if "pb_ratio" in row and pd.notna(row["pb_ratio"]):
            pb = float(row["pb_ratio"])
            if 1.0 <= pb <= 5.0:
                score += 5

        return min(100.0, max(0.0, score))

    def rank_stocks(self, df: pd.DataFrame, top_n: int = 50) -> pd.DataFrame:
        """对筛选后的股票打分排名"""
        if df.empty:
            return df

        df["score"] = df.apply(self.score_stock, axis=1)
        df = df.sort_values("score", ascending=False)
        return df.head(top_n).reset_index(drop=True)


class TechnicalFilter:
    """技术形态过滤器"""

    @staticmethod
    def check_ma_arrangement(df_hist: pd.DataFrame) -> Dict:
        """检查均线排列（多头/空头）"""
        if df_hist.empty or len(df_hist) < 60:
            return {"bull": False, "bear": False, "score": 0}

        df_hist = tech_indicators.calc_ma(df_hist)
        last = df_hist.iloc[-1]

        # 多头排列：5>10>20>60
        bull = (
            last.get("ma5", 0) > last.get("ma10", 0) > last.get("ma20", 0) > last.get("ma60", 0)
            and last.get("close", 0) > last.get("ma5", 0)
        )

        # 空头排列
        bear = (
            last.get("ma5", 0) < last.get("ma10", 0) < last.get("ma20", 0) < last.get("ma60", 0)
        )

        score = 20 if bull else (-10 if bear else 0)
        return {"bull": bull, "bear": bear, "score": score}

    @staticmethod
    def check_volume_breakout(df_hist: pd.DataFrame) -> Dict:
        """检查量价突破"""
        if df_hist.empty or len(df_hist) < 20:
            return {"breakout": False, "score": 0}

        avg_vol = df_hist["volume"].tail(20).mean()
        latest_vol = df_hist["volume"].iloc[-1]
        latest_close = df_hist["close"].iloc[-1]
        prev_high = df_hist["high"].tail(20).max()

        breakout = (
            latest_vol > avg_vol * 2.0
            and latest_close >= prev_high * 0.98
        )
        score = 20 if breakout else 0
        return {"breakout": breakout, "volume_ratio": round(latest_vol / avg_vol, 2), "score": score}

    @staticmethod
    def check_rsi_signal(df_hist: pd.DataFrame) -> Dict:
        """RSI信号检测"""
        if df_hist.empty or len(df_hist) < 20:
            return {"signal": "neutral", "score": 0}

        df_hist = tech_indicators.calc_rsi(df_hist)
        rsi = df_hist["rsi"].iloc[-1]

        if pd.isna(rsi):
            return {"signal": "neutral", "score": 0, "rsi": None}

        if 40 <= rsi <= 65:
            signal, score = "healthy", 10
        elif rsi < 30:
            signal, score = "oversold", 15
        elif rsi > 80:
            signal, score = "overbought", -15
        else:
            signal, score = "neutral", 0

        return {"signal": signal, "rsi": round(float(rsi), 2), "score": score}

    @staticmethod
    def check_macd_signal(df_hist: pd.DataFrame) -> Dict:
        """MACD信号检测"""
        if df_hist.empty or len(df_hist) < 30:
            return {"signal": "neutral", "score": 0}

        df_hist = tech_indicators.calc_macd(df_hist)
        if "macd_dif" not in df_hist.columns:
            return {"signal": "neutral", "score": 0}

        dif = df_hist["macd_dif"].iloc[-1]
        dea = df_hist["macd_dea"].iloc[-1]
        bar = df_hist["macd_bar"].iloc[-1]
        prev_bar = df_hist["macd_bar"].iloc[-2] if len(df_hist) > 1 else 0

        # 金叉
        golden_cross = (
            df_hist["macd_dif"].iloc[-2] < df_hist["macd_dea"].iloc[-2]
            and dif > dea
        )
        # 死叉
        death_cross = (
            df_hist["macd_dif"].iloc[-2] > df_hist["macd_dea"].iloc[-2]
            and dif < dea
        )
        # 红柱增大
        bar_growing = bar > 0 and bar > prev_bar

        if golden_cross:
            signal, score = "golden_cross", 20
        elif death_cross:
            signal, score = "death_cross", -20
        elif bar_growing:
            signal, score = "bullish", 10
        elif dif > 0 and dea > 0:
            signal, score = "above_zero", 5
        else:
            signal, score = "neutral", 0

        return {
            "signal": signal,
            "dif": round(float(dif), 4) if pd.notna(dif) else None,
            "dea": round(float(dea), 4) if pd.notna(dea) else None,
            "golden_cross": golden_cross,
            "score": score
        }


class StockPickerModule:
    """选股模块主类"""

    def __init__(self):
        self.screener = StockScreener()
        self.tech_filter = TechnicalFilter()
        self.cfg = config.stock_picker

    def run_daily_scan(self) -> Dict:
        """
        执行每日选股扫描
        流程: 全市场扫描 → 规则筛选 → 技术过滤 → AI精选 → 生成报告
        """
        logger.info("=" * 50)
        logger.info("开始每日选股扫描...")
        start_time = datetime.now()

        result = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "scan_time": start_time.strftime("%H:%M:%S"),
            "candidates": [],
            "ai_picks": {},
            "status": "success"
        }

        try:
            # Step 1: 获取全市场实时行情
            logger.info("Step1: 获取全市场行情...")
            df = market_service.get_realtime_quotes()
            if df.empty:
                result["status"] = "no_data"
                return result

            # Step 2: 规则初筛
            logger.info("Step2: 规则筛选...")
            df = self.screener.screen_by_rules(df)
            if df.empty:
                result["status"] = "no_candidates"
                return result

            # Step 3: 打分排名，取候选50只
            logger.info("Step3: 打分排名...")
            df = self.screener.rank_stocks(df, top_n=50)

            # Step 4: 技术形态过滤（取前20）
            logger.info("Step4: 技术形态分析（前20只）...")
            candidates = []
            for _, row in df.head(20).iterrows():
                code = str(row.get("code", ""))
                if not code:
                    continue

                try:
                    hist = market_service.get_history(code)
                    if hist.empty or len(hist) < 30:
                        continue

                    ma_info = self.tech_filter.check_ma_arrangement(hist)
                    vol_info = self.tech_filter.check_volume_breakout(hist)
                    rsi_info = self.tech_filter.check_rsi_signal(hist)
                    macd_info = self.tech_filter.check_macd_signal(hist)

                    tech_score = ma_info["score"] + vol_info["score"] + rsi_info["score"] + macd_info["score"]

                    stock_info = {
                        "code": code,
                        "name": str(row.get("name", "")),
                        "price": float(row.get("price", 0)),
                        "change_pct": float(row.get("change_pct", 0)),
                        "volume_ratio": float(row.get("volume_ratio", 0)),
                        "turnover_rate": float(row.get("turnover_rate", 0)),
                        "pe_ratio": float(row.get("pe_ratio", 0)),
                        "market_cap_b": round(float(row.get("market_cap", 0)) / 1e8, 2),
                        "base_score": float(row.get("score", 50)),
                        "tech_score": tech_score,
                        "total_score": float(row.get("score", 50)) + tech_score,
                        "ma_arrangement": "多头" if ma_info["bull"] else ("空头" if ma_info["bear"] else "中性"),
                        "volume_breakout": vol_info["breakout"],
                        "rsi": rsi_info.get("rsi"),
                        "rsi_signal": rsi_info["signal"],
                        "macd_signal": macd_info["signal"],
                        "macd_golden_cross": macd_info.get("golden_cross", False),
                    }
                    candidates.append(stock_info)

                except Exception as e:
                    logger.warning(f"处理{code}技术分析失败: {e}")
                    continue

            # 按总分排序
            candidates.sort(key=lambda x: x["total_score"], reverse=True)
            result["candidates"] = candidates[:self.cfg.top_n]

            logger.info(f"技术分析完成，最终候选: {len(result['candidates'])} 只")

            # Step 5: AI精选
            if result["candidates"]:
                logger.info("Step5: AI精选分析...")
                result["ai_picks"] = ai_engine.analyze_stock_picks(result["candidates"])

            elapsed = (datetime.now() - start_time).total_seconds()
            result["elapsed_seconds"] = round(elapsed, 1)
            logger.info(f"每日选股扫描完成，耗时 {elapsed:.1f}s")

        except Exception as e:
            logger.error(f"选股扫描异常: {e}", exc_info=True)
            result["status"] = "error"
            result["error"] = str(e)

        return result

    def format_daily_report(self, scan_result: Dict) -> str:
        """格式化每日选股报告（用于推送）"""
        date = scan_result.get("date", "今日")
        ai_picks = scan_result.get("ai_picks", {})
        candidates = scan_result.get("candidates", [])

        lines = [
            f"📊 【每日选股报告 {date}】",
            f"扫描时间: {scan_result.get('scan_time', '')}",
            f"候选股票: {len(candidates)} 只",
            ""
        ]

        # AI精选
        top_picks = ai_picks.get("top_picks", [])
        if top_picks:
            lines.append("🎯 AI精选推荐:")
            for i, pick in enumerate(top_picks, 1):
                lines.append(
                    f"{i}. [{pick.get('code')}] {pick.get('name')} "
                    f"| 评分:{pick.get('score')} "
                    f"| {pick.get('recommendation')}"
                )
                lines.append(f"   📌 {pick.get('buy_reason', '')}")
                lines.append(f"   🛡️ 止损: {pick.get('stop_loss')} | 目标: {pick.get('target_price')}")
                lines.append("")

        # 市场研判
        if ai_picks.get("market_outlook"):
            lines.append(f"🌐 市场研判: {ai_picks['market_outlook']}")
            lines.append("")

        if ai_picks.get("summary"):
            lines.append(f"📝 总结: {ai_picks['summary']}")

        return "\n".join(lines)


# 单例
stock_picker = StockPickerModule()
