"""
监控模块 - 自选股池 + 实时监控 + 多维度买卖信号 + 实时推送
信号体系：顶底分型 / MACD / KDJ / RSI / 布林带 / 均线 / 量价
"""
import time
import json
from datetime import datetime
from typing import Dict, List, Set
from threading import Thread, Event
import pandas as pd
import numpy as np

from config.settings import config
from data.data_service import market_service, indicators as tech_indicators
from ai.analysis_engine import ai_engine
from utils.logger import logger


class WatchlistManager:
    """自选股池管理"""

    def __init__(self, storage_file: str = "data/watchlist.json"):
        self.storage_file = storage_file
        self.watchlist: Dict[str, Dict] = {}  # code → {name, added_time, ...}
        self.load()

    def load(self):
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 兼容旧格式
                if "stocks" in data and isinstance(data["stocks"], list):
                    self.watchlist = {c: {"name": ""} for c in data["stocks"]}
                elif "stocks" in data and isinstance(data["stocks"], dict):
                    self.watchlist = data["stocks"]
                else:
                    self.watchlist = {}
            logger.info(f"加载自选股 {len(self.watchlist)} 只")
        except FileNotFoundError:
            logger.info("自选股文件不存在，创建新的")
            self.save()
        except Exception as e:
            logger.error(f"加载自选股失败: {e}")

    def save(self):
        try:
            import os
            os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump({"stocks": self.watchlist}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存自选股失败: {e}")

    def add(self, code: str, name: str = "") -> bool:
        if len(self.watchlist) >= config.monitor.max_watchlist:
            logger.warning(f"自选股已达上限 {config.monitor.max_watchlist}")
            return False
        self.watchlist[code] = {
            "name": name,
            "added_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.save()
        logger.info(f"添加自选股: [{code}] {name}")
        return True

    def remove(self, code: str):
        if code in self.watchlist:
            del self.watchlist[code]
            self.save()
            logger.info(f"移除自选股: {code}")

    def get_all(self) -> List[str]:
        return list(self.watchlist.keys())

    def get_all_with_info(self) -> Dict[str, Dict]:
        return self.watchlist.copy()

    def clear(self):
        self.watchlist.clear()
        self.save()


# ═══════════════════════════════════════════════════════════
#  顶底分型识别（缠论核心）
# ═══════════════════════════════════════════════════════════
class FractalDetector:
    """顶底分型检测器（基于缠论理论）"""

    @staticmethod
    def detect_fractals(df: pd.DataFrame) -> pd.DataFrame:
        """
        识别K线顶底分型
        顶分型：中间K线的high最高且low最高
        底分型：中间K线的low最低且high最低
        """
        if len(df) < 3:
            return df

        df = df.copy()
        df["fractal"] = ""  # top / bottom / ""

        for i in range(1, len(df) - 1):
            h_prev, h_curr, h_next = df["high"].iloc[i-1], df["high"].iloc[i], df["high"].iloc[i+1]
            l_prev, l_curr, l_next = df["low"].iloc[i-1], df["low"].iloc[i], df["low"].iloc[i+1]

            # 顶分型：中间K线高点最高 且 低点也最高
            if h_curr > h_prev and h_curr > h_next and l_curr > l_prev and l_curr > l_next:
                df.iloc[i, df.columns.get_loc("fractal")] = "top"
            # 底分型：中间K线低点最低 且 高点也最低
            elif l_curr < l_prev and l_curr < l_next and h_curr < h_prev and h_curr < h_next:
                df.iloc[i, df.columns.get_loc("fractal")] = "bottom"

        return df

    @staticmethod
    def check_fractal_signal(df: pd.DataFrame) -> Dict:
        """
        检测最新的顶底分型信号
        返回买卖信号
        """
        if len(df) < 10:
            return {}

        df = FractalDetector.detect_fractals(df)
        fractals = df[df["fractal"] != ""].tail(5)

        if fractals.empty:
            return {}

        last_fractal = fractals.iloc[-1]
        fractal_type = last_fractal["fractal"]
        fractal_idx = fractals.index[-1]
        current_idx = df.index[-1]

        # 只关注最近3根K线内形成的分型
        if current_idx - fractal_idx > 3:
            return {}

        price = df["close"].iloc[-1]

        if fractal_type == "bottom":
            # 底分型 → 潜在买入信号
            # 加强确认：收盘价站在底分型高点之上
            fractal_high = last_fractal["high"]
            if price >= fractal_high:
                return {
                    "type": "fractal_signal",
                    "signal": "buy",
                    "reason": f"底分型确认（分型低点{last_fractal['low']:.2f}，当前{price:.2f}站上高点）",
                    "urgency": "high",
                    "detail": {
                        "fractal_type": "bottom",
                        "fractal_low": round(float(last_fractal["low"]), 2),
                        "fractal_high": round(float(last_fractal["high"]), 2),
                        "stop_loss": round(float(last_fractal["low"]) * 0.97, 2),
                    }
                }
            else:
                return {
                    "type": "fractal_signal",
                    "signal": "buy",
                    "reason": f"底分型形成（分型低点{last_fractal['low']:.2f}，等待确认突破{fractal_high:.2f}）",
                    "urgency": "medium",
                    "detail": {"fractal_type": "bottom_pending"}
                }

        elif fractal_type == "top":
            # 顶分型 → 潜在卖出信号
            fractal_low = last_fractal["low"]
            if price <= fractal_low:
                return {
                    "type": "fractal_signal",
                    "signal": "sell",
                    "reason": f"顶分型确认（分型高点{last_fractal['high']:.2f}，当前{price:.2f}跌破低点）",
                    "urgency": "high",
                    "detail": {
                        "fractal_type": "top",
                        "fractal_high": round(float(last_fractal["high"]), 2),
                        "fractal_low": round(float(last_fractal["low"]), 2),
                    }
                }
            else:
                return {
                    "type": "fractal_signal",
                    "signal": "sell",
                    "reason": f"顶分型形成（分型高点{last_fractal['high']:.2f}，关注是否跌破{fractal_low:.2f}）",
                    "urgency": "medium",
                    "detail": {"fractal_type": "top_pending"}
                }

        return {}

    @staticmethod
    def check_fractal_trend(df: pd.DataFrame) -> Dict:
        """
        通过连续分型判断趋势
        底分型逐步抬高 → 上升趋势
        顶分型逐步降低 → 下降趋势
        """
        if len(df) < 30:
            return {}

        df = FractalDetector.detect_fractals(df)
        bottoms = df[df["fractal"] == "bottom"].tail(3)
        tops = df[df["fractal"] == "top"].tail(3)

        trend = "unknown"

        if len(bottoms) >= 2:
            lows = bottoms["low"].values
            if all(lows[i] < lows[i+1] for i in range(len(lows)-1)):
                trend = "uptrend"  # 底分型抬高 → 上升趋势

        if len(tops) >= 2:
            highs = tops["high"].values
            if all(highs[i] > highs[i+1] for i in range(len(highs)-1)):
                trend = "downtrend"  # 顶分型降低 → 下降趋势

        if trend == "unknown":
            return {}

        return {
            "type": "fractal_trend",
            "trend": trend,
            "detail": {
                "recent_bottoms": [round(float(x), 2) for x in bottoms["low"].values] if len(bottoms) > 0 else [],
                "recent_tops": [round(float(x), 2) for x in tops["high"].values] if len(tops) > 0 else [],
            }
        }


# ═══════════════════════════════════════════════════════════
#  多维度信号检测器
# ═══════════════════════════════════════════════════════════
class SignalDetector:
    """交易信号检测器 - 8大信号维度"""

    def __init__(self):
        self.cfg = config.monitor
        self.fractal = FractalDetector()

    # ────── 1. 价格异动 ──────
    def detect_price_alert(self, row: pd.Series) -> Dict:
        change_pct = float(row.get("change_pct", 0))
        if abs(change_pct) >= self.cfg.price_change_alert:
            return {
                "type": "price_alert",
                "signal": "buy" if change_pct > 0 else "sell",
                "reason": f"涨跌幅达 {change_pct:+.2f}%",
                "urgency": "high" if abs(change_pct) >= 5.0 else "medium"
            }
        return {}

    # ────── 2. 量能异动 ──────
    def detect_volume_spike(self, row: pd.Series) -> Dict:
        volume_ratio = float(row.get("volume_ratio", 1.0))
        if volume_ratio >= self.cfg.volume_spike_ratio:
            return {
                "type": "volume_spike",
                "signal": "alert",
                "reason": f"量比达 {volume_ratio:.2f} 倍",
                "urgency": "high"
            }
        return {}

    # ────── 3. RSI 超买超卖 ──────
    def detect_rsi_signal(self, hist_df: pd.DataFrame) -> Dict:
        if hist_df.empty or len(hist_df) < 20:
            return {}

        hist_df = tech_indicators.calc_rsi(hist_df)
        rsi = hist_df["rsi"].iloc[-1]
        if pd.isna(rsi):
            return {}

        rsi_val = float(rsi)
        rsi_prev = float(hist_df["rsi"].iloc[-2]) if len(hist_df) > 1 and not pd.isna(hist_df["rsi"].iloc[-2]) else rsi_val

        if rsi_val >= self.cfg.rsi_overbought:
            return {
                "type": "rsi_signal",
                "signal": "sell",
                "reason": f"RSI超买 {rsi_val:.1f}（前值{rsi_prev:.1f}）",
                "urgency": "medium"
            }
        elif rsi_val <= self.cfg.rsi_oversold:
            return {
                "type": "rsi_signal",
                "signal": "buy",
                "reason": f"RSI超卖 {rsi_val:.1f}（前值{rsi_prev:.1f}）",
                "urgency": "medium"
            }
        # RSI底背离：价格创新低但RSI没创新低
        if len(hist_df) >= 5:
            price_new_low = hist_df["close"].iloc[-1] < hist_df["close"].iloc[-5:].min() * 1.001
            rsi_not_low = rsi_val > hist_df["rsi"].iloc[-5:].min()
            if price_new_low and rsi_not_low and rsi_val < 40:
                return {
                    "type": "rsi_divergence",
                    "signal": "buy",
                    "reason": f"RSI底背离（价格新低但RSI {rsi_val:.1f} 未创新低）",
                    "urgency": "high"
                }
        return {}

    # ────── 4. MACD 金叉/死叉 ──────
    def detect_macd_cross(self, hist_df: pd.DataFrame) -> Dict:
        if hist_df.empty or len(hist_df) < 30:
            return {}

        hist_df = tech_indicators.calc_macd(hist_df)
        if "macd_dif" not in hist_df.columns or len(hist_df) < 2:
            return {}

        dif_now = hist_df["macd_dif"].iloc[-1]
        dea_now = hist_df["macd_dea"].iloc[-1]
        dif_prev = hist_df["macd_dif"].iloc[-2]
        dea_prev = hist_df["macd_dea"].iloc[-2]
        bar_now = hist_df["macd_bar"].iloc[-1]

        if any(pd.isna(v) for v in [dif_now, dea_now, dif_prev, dea_prev]):
            return {}

        # 金叉（零轴上方金叉更强）
        if dif_prev <= dea_prev and dif_now > dea_now:
            above_zero = dif_now > 0 and dea_now > 0
            return {
                "type": "macd_cross",
                "signal": "buy",
                "reason": f"MACD金叉{'（零轴上方，强势）' if above_zero else '（零轴下方）'}",
                "urgency": "high",
                "detail": {"dif": round(float(dif_now), 4), "dea": round(float(dea_now), 4), "above_zero": above_zero}
            }
        # 死叉
        elif dif_prev >= dea_prev and dif_now < dea_now:
            below_zero = dif_now < 0 and dea_now < 0
            return {
                "type": "macd_cross",
                "signal": "sell",
                "reason": f"MACD死叉{'（零轴下方，弱势）' if below_zero else '（零轴上方）'}",
                "urgency": "high",
                "detail": {"dif": round(float(dif_now), 4), "dea": round(float(dea_now), 4)}
            }
        return {}

    # ────── 5. KDJ 信号 ──────
    def detect_kdj_signal(self, hist_df: pd.DataFrame) -> Dict:
        if hist_df.empty or len(hist_df) < 15:
            return {}

        hist_df = tech_indicators.calc_kdj(hist_df)
        if "kdj_k" not in hist_df.columns or len(hist_df) < 2:
            return {}

        k = hist_df["kdj_k"].iloc[-1]
        d = hist_df["kdj_d"].iloc[-1]
        j = hist_df["kdj_j"].iloc[-1]
        k_prev = hist_df["kdj_k"].iloc[-2]
        d_prev = hist_df["kdj_d"].iloc[-2]

        if any(pd.isna(v) for v in [k, d, j, k_prev, d_prev]):
            return {}

        k, d, j = float(k), float(d), float(j)
        k_prev, d_prev = float(k_prev), float(d_prev)

        # KDJ金叉（低位更有效）
        if k_prev <= d_prev and k > d and j < 30:
            return {
                "type": "kdj_signal",
                "signal": "buy",
                "reason": f"KDJ低位金叉（K={k:.1f} D={d:.1f} J={j:.1f}）",
                "urgency": "high"
            }
        # KDJ死叉（高位更有效）
        elif k_prev >= d_prev and k < d and j > 80:
            return {
                "type": "kdj_signal",
                "signal": "sell",
                "reason": f"KDJ高位死叉（K={k:.1f} D={d:.1f} J={j:.1f}）",
                "urgency": "high"
            }
        # J值超买超卖
        if j > 100:
            return {
                "type": "kdj_signal",
                "signal": "sell",
                "reason": f"KDJ-J值超买 J={j:.1f}",
                "urgency": "medium"
            }
        elif j < 0:
            return {
                "type": "kdj_signal",
                "signal": "buy",
                "reason": f"KDJ-J值超卖 J={j:.1f}",
                "urgency": "medium"
            }
        return {}

    # ────── 6. 布林带信号 ──────
    def detect_bollinger_signal(self, hist_df: pd.DataFrame) -> Dict:
        if hist_df.empty or len(hist_df) < 25:
            return {}

        hist_df = tech_indicators.calc_bollinger(hist_df)
        if "boll_upper" not in hist_df.columns:
            return {}

        close = hist_df["close"].iloc[-1]
        upper = hist_df["boll_upper"].iloc[-1]
        lower = hist_df["boll_lower"].iloc[-1]
        mid = hist_df["boll_mid"].iloc[-1]

        if any(pd.isna(v) for v in [close, upper, lower, mid]):
            return {}

        close, upper, lower, mid = float(close), float(upper), float(lower), float(mid)

        # 突破上轨
        if close > upper:
            return {
                "type": "boll_signal",
                "signal": "sell",
                "reason": f"突破布林上轨（价格{close:.2f} > 上轨{upper:.2f}），超买风险",
                "urgency": "medium"
            }
        # 跌破下轨
        elif close < lower:
            return {
                "type": "boll_signal",
                "signal": "buy",
                "reason": f"跌破布林下轨（价格{close:.2f} < 下轨{lower:.2f}），超卖机会",
                "urgency": "medium"
            }
        # 站上中轨
        prev_close = hist_df["close"].iloc[-2] if len(hist_df) > 1 else close
        prev_mid = hist_df["boll_mid"].iloc[-2] if len(hist_df) > 1 else mid
        if float(prev_close) < float(prev_mid) and close > mid:
            return {
                "type": "boll_signal",
                "signal": "buy",
                "reason": f"站上布林中轨（价格{close:.2f}突破中轨{mid:.2f}）",
                "urgency": "medium"
            }
        return {}

    # ────── 7. 均线多空排列 ──────
    def detect_ma_signal(self, hist_df: pd.DataFrame) -> Dict:
        if hist_df.empty or len(hist_df) < 65:
            return {}

        hist_df = tech_indicators.calc_ma(hist_df)
        last = hist_df.iloc[-1]
        prev = hist_df.iloc[-2]

        ma5 = last.get("ma5", 0)
        ma10 = last.get("ma10", 0)
        ma20 = last.get("ma20", 0)
        close = last.get("close", 0)

        if any(pd.isna(v) or v == 0 for v in [ma5, ma10, ma20, close]):
            return {}

        ma5, ma10, ma20, close = float(ma5), float(ma10), float(ma20), float(close)

        # 5日线上穿10日线
        prev_ma5 = float(prev.get("ma5", 0)) if not pd.isna(prev.get("ma5", 0)) else 0
        prev_ma10 = float(prev.get("ma10", 0)) if not pd.isna(prev.get("ma10", 0)) else 0

        if prev_ma5 and prev_ma10:
            if prev_ma5 <= prev_ma10 and ma5 > ma10:
                return {
                    "type": "ma_cross",
                    "signal": "buy",
                    "reason": f"5日线上穿10日线（MA5={ma5:.2f} > MA10={ma10:.2f}）",
                    "urgency": "medium"
                }
            elif prev_ma5 >= prev_ma10 and ma5 < ma10:
                return {
                    "type": "ma_cross",
                    "signal": "sell",
                    "reason": f"5日线下穿10日线（MA5={ma5:.2f} < MA10={ma10:.2f}）",
                    "urgency": "medium"
                }

        # 多头排列
        ma60 = float(last.get("ma60", 0)) if not pd.isna(last.get("ma60", 0)) else 0
        if ma60 and close > ma5 > ma10 > ma20 > ma60:
            return {
                "type": "ma_arrangement",
                "signal": "buy",
                "reason": f"均线多头排列（5>10>20>60），趋势向上",
                "urgency": "medium"
            }

        return {}

    # ────── 8. 顶底分型 ──────
    def detect_fractal_signal(self, hist_df: pd.DataFrame) -> Dict:
        return self.fractal.check_fractal_signal(hist_df)

    # ────── 综合检测 ──────
    def detect_all(self, code: str, realtime_row: pd.Series) -> List[Dict]:
        """综合检测所有信号"""
        signals = []

        # 实时数据信号
        sig = self.detect_price_alert(realtime_row)
        if sig:
            signals.append(sig)

        sig = self.detect_volume_spike(realtime_row)
        if sig:
            signals.append(sig)

        # 技术指标信号（需要历史数据）
        try:
            hist = market_service.get_history(code)
            if not hist.empty and len(hist) >= 30:
                # RSI
                sig = self.detect_rsi_signal(hist.copy())
                if sig:
                    signals.append(sig)
                # MACD
                sig = self.detect_macd_cross(hist.copy())
                if sig:
                    signals.append(sig)
                # KDJ
                sig = self.detect_kdj_signal(hist.copy())
                if sig:
                    signals.append(sig)
                # 布林带
                sig = self.detect_bollinger_signal(hist.copy())
                if sig:
                    signals.append(sig)
                # 均线
                sig = self.detect_ma_signal(hist.copy())
                if sig:
                    signals.append(sig)
                # 顶底分型
                sig = self.detect_fractal_signal(hist.copy())
                if sig:
                    signals.append(sig)
        except Exception as e:
            logger.warning(f"获取{code}历史数据做技术分析失败: {e}")

        return signals


# ═══════════════════════════════════════════════════════════
#  监控主模块
# ═══════════════════════════════════════════════════════════
class MonitorModule:
    """监控模块主类"""

    def __init__(self):
        self.watchlist_mgr = WatchlistManager()
        self.detector = SignalDetector()
        self.cfg = config.monitor
        self.running = False
        self.stop_event = Event()
        self.monitor_thread: Thread = None
        # 信号冷却：{code_signaltype: timestamp} 避免重复推送
        self.signal_cooldown: Dict[str, float] = {}
        self.cooldown_seconds = 3600  # 同类信号1小时内不重复推送

    def start(self):
        if self.running:
            logger.warning("监控已在运行")
            return

        self.running = True
        self.stop_event.clear()
        self.monitor_thread = Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        codes = self.watchlist_mgr.get_all()
        info = self.watchlist_mgr.get_all_with_info()
        names = [f"[{c}]{info[c].get('name', '')}" for c in codes]
        logger.info(f"📡 监控模块已启动，监控 {len(codes)} 只: {', '.join(names)}")

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("监控模块已停止")

    def _is_trading_time(self) -> bool:
        """判断是否在交易时间"""
        now = datetime.now()
        weekday = now.strftime("%a")
        if weekday not in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
            return False
        t = now.hour * 100 + now.minute
        # 9:15-11:35 和 12:55-15:05（留余量）
        return (915 <= t <= 1135) or (1255 <= t <= 1505)

    def _monitor_loop(self):
        while self.running and not self.stop_event.is_set():
            try:
                if self._is_trading_time():
                    self._check_watchlist()
                else:
                    logger.debug("非交易时间，跳过监控检查")
            except Exception as e:
                logger.error(f"监控循环异常: {e}", exc_info=True)

            self.stop_event.wait(self.cfg.check_interval)

    def _check_cooldown(self, code: str, signal_type: str) -> bool:
        """检查信号是否在冷却中"""
        key = f"{code}_{signal_type}"
        last_time = self.signal_cooldown.get(key, 0)
        if time.time() - last_time < self.cooldown_seconds:
            return True  # 在冷却中
        return False

    def _set_cooldown(self, code: str, signal_type: str):
        key = f"{code}_{signal_type}"
        self.signal_cooldown[key] = time.time()

    def _check_watchlist(self):
        codes = self.watchlist_mgr.get_all()
        if not codes:
            return

        logger.info(f"📡 检查自选股 {len(codes)} 只...")
        df = market_service.get_realtime_quotes(codes)
        if df.empty:
            logger.warning("未获取到行情数据")
            return

        for _, row in df.iterrows():
            code = str(row.get("code", ""))
            if not code or code not in codes:
                continue

            signals = self.detector.detect_all(code, row)
            if not signals:
                continue

            # 过滤冷却中的信号
            new_signals = []
            for sig in signals:
                if not self._check_cooldown(code, sig["type"]):
                    new_signals.append(sig)
                    self._set_cooldown(code, sig["type"])

            if new_signals:
                self._handle_signals(code, row, new_signals)

    def _handle_signals(self, code: str, row: pd.Series, signals: List[Dict]):
        """处理信号（AI分析 + 推送）"""
        name = str(row.get("name", ""))
        price = float(row.get("price", 0))

        # 分类信号
        buy_signals = [s for s in signals if s.get("signal") == "buy"]
        sell_signals = [s for s in signals if s.get("signal") == "sell"]
        alert_signals = [s for s in signals if s.get("signal") == "alert"]

        signal_summary = []
        if buy_signals:
            signal_summary.append(f"🟢买入×{len(buy_signals)}")
        if sell_signals:
            signal_summary.append(f"🔴卖出×{len(sell_signals)}")
        if alert_signals:
            signal_summary.append(f"⚡异动×{len(alert_signals)}")

        logger.info(f"[{code}]{name} 触发: {' '.join(signal_summary)} → {[s['reason'] for s in signals]}")

        # 构造信息
        stock_info = {
            "code": code,
            "name": name,
            "price": price,
            "change_pct": float(row.get("change_pct", 0)),
            "volume_ratio": float(row.get("volume_ratio", 0)),
            "turnover_rate": float(row.get("turnover_rate", 0)),
            "signals": signals,
            "buy_count": len(buy_signals),
            "sell_count": len(sell_signals),
        }

        # 多信号共振时一定要AI分析
        has_high = any(s.get("urgency") == "high" for s in signals)
        multi_signal = len(signals) >= 2
        if has_high or multi_signal:
            try:
                primary = "buy" if len(buy_signals) >= len(sell_signals) else "sell"
                ai_result = ai_engine.analyze_monitor_signal(stock_info, primary)
                stock_info["ai_analysis"] = ai_result
            except Exception as e:
                logger.error(f"AI分析{code}失败: {e}")

        self._send_notification(stock_info)

    def _send_notification(self, stock_info: Dict):
        from notify.notifier import notifier
        notifier.send_monitor_alert(stock_info)

    def add_stock(self, code: str, name: str = "") -> bool:
        return self.watchlist_mgr.add(code, name)

    def remove_stock(self, code: str):
        self.watchlist_mgr.remove(code)

    def get_watchlist(self) -> List[str]:
        return self.watchlist_mgr.get_all()

    def get_watchlist_detail(self) -> Dict:
        return self.watchlist_mgr.get_all_with_info()


# 单例
monitor = MonitorModule()
