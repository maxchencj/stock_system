"""
行业估值比较面板 - 每周末推送各行业PE/PB横向对比
判断哪些行业处于历史低估区间
每周六 10:00 推送 → A股Bot
"""
from datetime import datetime
from typing import List, Dict

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger

# 一级行业映射（申万）
TOP_INDUSTRIES = [
    "农林牧渔", "采掘", "化工", "钢铁", "有色金属",
    "电子", "家用电器", "食品饮料", "纺织服装", "轻工制造",
    "医药生物", "公用事业", "交通运输", "房地产", "商业贸易",
    "休闲服务", "银行", "非银金融", "汽车", "机械设备",
    "国防军工", "计算机", "传媒", "通信", "建筑材料",
    "建筑装饰", "电气设备", "综合",
]


def _fetch_industry_valuations() -> List[Dict]:
    """获取申万二级行业PE/PB，按一级行业汇总均值"""
    try:
        import akshare as ak
        df = ak.sw_index_second_info()
        if df is None or df.empty:
            return []

        result = {}
        for _, row in df.iterrows():
            parent = str(row.get("上级行业", ""))
            pe = row.get("TTM(滚动)市盈率", None)
            pb = row.get("市净率", None)
            div = row.get("静态股息率", None)

            if not parent or pe is None:
                continue
            try:
                pe_val = float(pe)
                pb_val = float(pb) if pb else 0
                div_val = float(div) if div else 0
            except Exception:
                continue

            if pe_val <= 0 or pe_val > 500:
                continue

            if parent not in result:
                result[parent] = {"pes": [], "pbs": [], "divs": []}
            result[parent]["pes"].append(pe_val)
            if pb_val > 0:
                result[parent]["pbs"].append(pb_val)
            if div_val > 0:
                result[parent]["divs"].append(div_val)

        rows = []
        for industry, data in result.items():
            if not data["pes"]:
                continue
            avg_pe = sum(data["pes"]) / len(data["pes"])
            avg_pb = sum(data["pbs"]) / len(data["pbs"]) if data["pbs"] else 0
            avg_div = sum(data["divs"]) / len(data["divs"]) if data["divs"] else 0
            rows.append({
                "industry": industry,
                "pe": round(avg_pe, 1),
                "pb": round(avg_pb, 2),
                "div": round(avg_div, 2),
            })

        return sorted(rows, key=lambda x: x["pe"])
    except Exception as e:
        logger.warning(f"获取行业估值失败: {e}")
        return []


def _ai_valuation_analysis(rows: List[Dict]) -> str:
    system_prompt = "你是专业的A股行业配置分析师，擅长判断各行业估值所处历史位置和配置价值。"

    low_pe = rows[:8]
    high_pe = rows[-5:]
    low_str = "\n".join([f"  {r['industry']}: PE {r['pe']} PB {r['pb']} 股息率{r['div']}%" for r in low_pe])
    high_str = "\n".join([f"  {r['industry']}: PE {r['pe']}" for r in high_pe])

    user_prompt = f"""本周A股各行业估值横向对比：

估值最低的行业（PE排序）：
{low_str}

估值最高的行业：
{high_str}

请用200字以内输出：
【低估值机会】哪2-3个低PE行业值得重点关注，理由是什么？
【高估值警惕】哪些行业估值偏高需谨慎？
【配置建议】当前市场环境下的行业配置偏好"""

    return ai_engine._call(system_prompt, user_prompt, max_tokens=500)


class IndustryPanel:

    def run_weekly_push(self):
        logger.info("执行行业估值比较面板")
        rows = _fetch_industry_valuations()
        if not rows:
            logger.warning("行业估值数据获取失败")
            return

        ai_text = _ai_valuation_analysis(rows)

        # 格式化：PE最低的前10 + 最高的后5
        low_lines = [
            f"  {r['industry']:<8} PE:{r['pe']:>6.1f}  PB:{r['pb']:>4.2f}  股息:{r['div']:.1f}%"
            for r in rows[:10]
        ]
        high_lines = [
            f"  {r['industry']:<8} PE:{r['pe']:>6.1f}"
            for r in rows[-5:]
        ]

        msg = (
            f"📊 行业估值面板 — {datetime.now().strftime('%Y-%m-%d')}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💚 低估值行业（PE最低 Top10）\n"
            + "\n".join(low_lines)
            + f"\n\n🔴 高估值行业（PE最高 Top5）\n"
            + "\n".join(high_lines)
            + f"\n━━━━━━━━━━━━━━━━\n"
            + ai_text
        )
        notifier.telegram.send(msg)
        logger.info(f"行业估值面板已推送，共{len(rows)}个行业")


industry_panel = IndustryPanel()
