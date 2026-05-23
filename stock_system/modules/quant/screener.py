"""
多因子量化选股 - 每日 8:50 推送 Top10
流程：全量打分 → 截面标准化(z-score) → 加权求和 → AI解读 → 推送
"""
import time
from datetime import datetime
from typing import List, Dict

import pandas as pd

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger
from modules.quant.factors import score_stock

# ── 量化股票池（流动性好、覆盖各行业、约100只） ──────────────
QUANT_UNIVERSE = [
    # 消费
    "600519", "000858", "002304", "000568", "000596", "603369",
    "600887", "000651", "000333", "002507",
    # 医药
    "600276", "300750", "002714", "300498", "600763",
    "000538", "300122", "600436", "002601",
    # 金融
    "601318", "600036", "000001", "601166", "600000",
    "601328", "601398", "600016",
    # 科技
    "002415", "002230", "300308", "603501", "002572",
    "300059", "300760", "688111", "600703",
    # 新能源
    "300750", "002594", "601012", "600438", "002459",
    "300014", "002460", "688599", "601865",
    # 资源/周期
    "601899", "603993", "600585", "601088",
    "600028", "601857", "600011",
    # 化工/材料
    "600309", "000776", "600346", "002625",
    # 工业/制造
    "000333", "002352", "600031", "601669",
    "601800", "002062",
    # 地产/建筑
    "000002", "600048", "601390",
    # 交通/物流
    "601111", "600115", "603659",
    # 农业
    "002714", "000876", "600298",
]

# 去重、过滤非法代码
QUANT_UNIVERSE = list({
    c for c in QUANT_UNIVERSE
    if c.isdigit() and len(c) == 6
})

# ── 因子权重配置 ───────────────────────────────
FACTOR_WEIGHTS = {
    # 质量因子 40%
    "roe":         0.15,
    "net_margin":  0.12,
    "yoy_profit":  0.10,
    "low_debt":    0.08,   # debt_ratio 取反
    # 动量因子 35%
    "mom60":       0.15,
    "mom20":       0.10,
    "mom120":      0.10,
    # 技术因子 25%
    "ma_bullish":  0.12,
    "above_ma20":  0.08,
    "avg_turn20":  0.05,
}


def _zscore_clip(series: pd.Series, clip: float = 3.0) -> pd.Series:
    """截面 z-score 标准化，截断异常值"""
    mean = series.mean()
    std = series.std()
    if std == 0:
        return pd.Series(0, index=series.index)
    z = (series - mean) / std
    return z.clip(-clip, clip)


def _build_score_df(raw: List[Dict]) -> pd.DataFrame:
    """将原始因子 list 转为加权综合得分 DataFrame"""
    df = pd.DataFrame(raw).set_index("code")

    # 派生因子：低负债（debt_ratio 越低越好，取反）
    df["low_debt"] = -df["debt_ratio"]

    # 截面 z-score 标准化
    factor_cols = [k for k in FACTOR_WEIGHTS if k in df.columns]
    for col in factor_cols:
        df[f"z_{col}"] = _zscore_clip(df[col])

    # 加权综合得分
    df["score"] = sum(
        df.get(f"z_{col}", 0) * w
        for col, w in FACTOR_WEIGHTS.items()
        if f"z_{col}" in df.columns
    )

    return df.sort_values("score", ascending=False)


def _fetch_names(codes: List[str]) -> Dict[str, str]:
    """批量获取股票名称（新浪财经）"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot()
        # symbol 列最后6位是代码
        df["code"] = df.iloc[:, 0].astype(str).str[-6:]
        name_map = {}
        for _, row in df.iterrows():
            c = str(row["code"])
            if c in codes:
                name_col = "名称" if "名称" in df.columns else df.columns[1]
                name_map[c] = str(row[name_col])
        return name_map
    except Exception:
        return {}


def _ai_quant_analysis(top_stocks: List[Dict]) -> str:
    system_prompt = "你是量化投资分析师，精通多因子选股模型。"
    stocks_str = "\n".join([
        f"  {s['name']}({s['code']}) 综合得分{s['score']:.2f} "
        f"| ROE{s.get('roe', 0)*100:.1f}% 60日涨幅{s.get('mom60', 0):.1f}%"
        for s in top_stocks[:8]
    ])
    user_prompt = f"""今日多因子量化选股结果（加权：质量40%+动量35%+技术25%）：

{stocks_str}

请用150字以内输出：
【今日量化观点】这批股票呈现什么共同特征（行业/风格/市值）？
【重点关注】得分最高的2-3只，基本面亮点是什么？
【风险提示】当前市场环境下量化选股的注意事项"""

    return ai_engine._call(system_prompt, user_prompt, max_tokens=400)


class QuantScreener:

    def run_daily_push(self):
        logger.info(f"开始多因子量化选股，股票池 {len(QUANT_UNIVERSE)} 只")
        universe = QUANT_UNIVERSE

        # baostock 单连接非线程安全，串行计算因子
        raw_factors = []
        for code in universe:
            try:
                result = score_stock(code)
                if result:
                    raw_factors.append(result)
            except Exception as e:
                logger.debug(f"因子计算失败({code}): {e}")

        if len(raw_factors) < 10:
            logger.warning(f"有效因子数据不足({len(raw_factors)}只)，跳过推送")
            return

        logger.info(f"成功获取 {len(raw_factors)} 只股票因子数据")

        # 构建得分矩阵
        score_df = _build_score_df(raw_factors)
        top10_codes = score_df.head(10).index.tolist()
        bot10_codes = score_df.tail(5).index.tolist()

        # 获取股票名称
        name_map = _fetch_names(top10_codes + bot10_codes)

        # 组装 top10 详情
        top10 = []
        for code in top10_codes:
            row = score_df.loc[code]
            raw = next((r for r in raw_factors if r["code"] == code), {})
            top10.append({
                "code": code,
                "name": name_map.get(code, code),
                "score": round(float(row["score"]), 3),
                "roe": raw.get("roe", 0),
                "mom60": raw.get("mom60", 0),
                "ma_bullish": raw.get("ma_bullish", 0),
            })

        ai_text = _ai_quant_analysis(top10)

        # 格式化消息
        lines = []
        for i, s in enumerate(top10, 1):
            ma_icon = "📈" if s["ma_bullish"] > 0 else "📉"
            lines.append(
                f"  {i:2}. {s['name']}({s['code']})  "
                f"得分:{s['score']:+.2f}  "
                f"ROE:{s['roe']*100:.0f}%  "
                f"60日:{s['mom60']:+.0f}%  {ma_icon}"
            )

        msg = (
            f"🔢 量化选股 — {datetime.now().strftime('%Y-%m-%d')}\n"
            f"模型：质量40% + 动量35% + 技术25%\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🏆 今日 Top10（综合得分排序）\n"
            + "\n".join(lines)
            + f"\n━━━━━━━━━━━━━━━━\n"
            + ai_text
        )
        notifier.telegram.send(msg)
        logger.info(f"量化选股已推送，Top1: {top10[0]['name'] if top10 else '无'}")

        # 同步存储得分用于回测参考
        self._save_daily_scores(score_df, name_map)

    def _save_daily_scores(self, score_df: pd.DataFrame, name_map: Dict):
        """将今日得分存入 JSON，供回测对照"""
        import json
        from pathlib import Path
        scores_file = Path(__file__).parent.parent.parent / "data" / "quant_scores.json"
        try:
            scores_file.parent.mkdir(exist_ok=True)
            today = datetime.now().strftime("%Y-%m-%d")
            records = {
                row_code: {
                    "name": name_map.get(row_code, row_code),
                    "score": round(float(row["score"]), 4),
                }
                for row_code, row in score_df.head(20).iterrows()
            }
            # 读旧数据，追加今日
            existing = {}
            if scores_file.exists():
                with open(scores_file) as f:
                    existing = json.load(f)
            existing[today] = records
            # 只保留最近90天
            keys = sorted(existing.keys())[-90:]
            existing = {k: existing[k] for k in keys}
            with open(scores_file, "w") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存量化得分失败: {e}")

    def get_latest_scores(self) -> Dict:
        """读取最近一次量化得分"""
        import json
        from pathlib import Path
        scores_file = Path(__file__).parent.parent.parent / "data" / "quant_scores.json"
        if not scores_file.exists():
            return {}
        with open(scores_file) as f:
            data = json.load(f)
        if not data:
            return {}
        latest_date = sorted(data.keys())[-1]
        return {"date": latest_date, "scores": data[latest_date]}


quant_screener = QuantScreener()
