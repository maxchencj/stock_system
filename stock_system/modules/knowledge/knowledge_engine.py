"""
每日股票知识学习模块
A股知识 → A股Bot | 美股知识 → mcDolphin Bot
已推送记录本地，不重复推送，全部推完后自动重置循环
"""
import json
import random
import time
from pathlib import Path
from typing import List, Tuple, Dict

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger

LOG_FILE = Path(__file__).parent.parent.parent / "data" / "knowledge_log.json"


# ─────────────────── A股知识池 ───────────────────
A_SHARE_KNOWLEDGE_POOL: List[Tuple[str, str]] = [
    # 技术分析
    ("技术分析", "K线基础：阳线、阴线、十字星的含义与信号"),
    ("技术分析", "经典K线形态：锤子线、吊颈线、吞没形态"),
    ("技术分析", "均线理论：MA5/10/20/60/120/250 各周期的意义"),
    ("技术分析", "MACD指标：金叉死叉与顶底背离的实战运用"),
    ("技术分析", "RSI指标：超买超卖区间与钝化现象"),
    ("技术分析", "布林带：压力支撑与带宽收窄突破信号"),
    ("技术分析", "KDJ指标：随机指标的高低位判断与误区"),
    ("技术分析", "量价关系：天量天价、缩量下跌的市场含义"),
    ("技术分析", "趋势线：上升通道、下降趋势与横盘整理识别"),
    ("技术分析", "支撑与阻力：历史价格与整数关口的作用"),
    ("技术分析", "头肩顶/底形态：趋势反转的经典信号"),
    ("技术分析", "双顶双底：M头W底的识别与突破确认"),
    ("技术分析", "旗形与三角形整理：上升途中的蓄力形态"),
    ("技术分析", "缺口理论：普通缺口、突破缺口、竭尽缺口"),
    ("技术分析", "筹码分布：密集区与套牢盘的解套压力"),
    # 基本面
    ("基本面分析", "市盈率PE：如何判断一只股票是否贵了"),
    ("基本面分析", "市净率PB：净资产倍数与破净股的意义"),
    ("基本面分析", "ROE：股东权益回报率，巴菲特最看重的指标"),
    ("基本面分析", "毛利率与净利率：衡量企业盈利能力的核心指标"),
    ("基本面分析", "资产负债率：企业杠杆水平与偿债风险"),
    ("基本面分析", "现金流量表解读：经营/投资/筹资三大活动"),
    ("基本面分析", "利润表精读：营收增长与利润含金量如何判断"),
    ("基本面分析", "商誉减值：并购陷阱与业绩地雷的识别"),
    ("基本面分析", "股息率与分红：价值投资者的被动收益逻辑"),
    ("基本面分析", "PEG指标：把成长性纳入估值的方法"),
    # A股特色
    ("A股特色", "涨停板机制：一字板、T字板、连板效应解析"),
    ("A股特色", "跌停板：封板逻辑与散户出逃时机判断"),
    ("A股特色", "北向资金：外资流入流出对A股的信号意义"),
    ("A股特色", "融资融券：杠杆交易规则与风险放大效应"),
    ("A股特色", "龙虎榜：游资席位解读与资金追踪方法"),
    ("A股特色", "大宗交易：折价成交背后的主力意图"),
    ("A股特色", "股权激励：与员工利益绑定的长期信号"),
    ("A股特色", "回购增持：大股东真金白银的态度信号"),
    ("A股特色", "定向增发：稀释股本还是利好融资？"),
    ("A股特色", "限售股解禁：解禁潮对股价的压力分析"),
    ("A股特色", "ST与退市制度：风险识别与规避方法"),
    ("A股特色", "板块轮动：热点切换的逻辑与跟踪方法"),
    ("A股特色", "A股历次牛熊特征：政策市与散户行为规律"),
    # 宏观经济
    ("宏观经济", "美联储加息：对A股的传导机制与历史影响"),
    ("宏观经济", "人民币汇率：贬值升值与A股市场的关系"),
    ("宏观经济", "CPI与PPI：通胀数据对不同行业的差异影响"),
    ("宏观经济", "M2货币供应量：流动性宽松与牛市的关系"),
    ("宏观经济", "社融数据：信用扩张是经济复苏的先行指标"),
    ("宏观经济", "经济周期四阶段：复苏/扩张/滞胀/衰退与股市配置"),
    # 交易心理
    ("交易心理", "锚定效应：被套后非理性等待的心理陷阱"),
    ("交易心理", "处置效应：为什么散户总是卖盈持亏"),
    ("交易心理", "过度自信：散户长期亏损的根源之一"),
    ("交易心理", "羊群效应：追涨杀跌背后的群体行为心理"),
    ("交易心理", "止损纪律：亏损时最难也最重要的操作"),
    ("交易心理", "仓位管理：金字塔加仓与风险控制方法"),
]

# ─────────────────── 美股知识池 ───────────────────
US_KNOWLEDGE_POOL: List[Tuple[str, str]] = [
    # 美股特色
    ("美股特色", "纳斯达克/标普500/道琼斯：三大指数的区别与投资意义"),
    ("美股特色", "财报季：EPS预期、营收beat/miss对股价的即时影响"),
    ("美股特色", "期权基础：Call与Put的盈亏结构与使用场景"),
    ("美股特色", "做空机制：借券卖出的流程与轧空行情（Short Squeeze）"),
    ("美股特色", "ETF投资：被动投资的逻辑与指数基金选择"),
    ("美股特色", "美股T+0交易：日内交易规则与PDT规则限制"),
    ("美股特色", "盘前盘后交易：延长交易时段的特点与风险"),
    ("美股特色", "股票回购：美股最主流的股东回报方式"),
    ("美股特色", "ADR中概股：海外上市形式与折溢价风险"),
    ("美股特色", "股息再投资计划DRIP：复利增长的长期力量"),
    ("美股特色", "SPAC：特殊目的收购公司的运作逻辑与风险"),
    ("美股特色", "美股IPO与锁定期：新股上市后的价格规律"),
    # 技术分析（美股视角）
    ("技术分析", "美股技术分析与A股的异同：流动性与机构主导"),
    ("技术分析", "52周高低点：美股最重要的支撑阻力参考位"),
    ("技术分析", "相对强度RS：威廉·欧奈尔CANSLIM选股核心指标"),
    ("技术分析", "杯柄形态：美股最经典的突破买入模式"),
    # 基本面（美股视角）
    ("基本面分析", "GAAP vs Non-GAAP：两种利润口径的差异与陷阱"),
    ("基本面分析", "自由现金流FCF：科技股估值最核心的指标"),
    ("基本面分析", "EV/EBITDA：企业价值倍数与跨行业比较"),
    ("基本面分析", "护城河理论：巴菲特的五大竞争优势框架"),
    ("基本面分析", "股东信解读：从巴菲特/贝索斯年报中学投资思维"),
    ("基本面分析", "SaaS企业估值：ARR、NRR、LTV/CAC等核心指标"),
    # 宏观（美股视角）
    ("宏观经济", "美联储点阵图：利率预期的可视化工具解读"),
    ("宏观经济", "收益率曲线倒挂：预测经济衰退的先行信号"),
    ("宏观经济", "非农就业数据：美股每月最重要的宏观数据"),
    ("宏观经济", "VIX恐慌指数：市场情绪与期权波动率的温度计"),
    ("宏观经济", "美元指数DXY：强弱美元对美股新兴市场的影响"),
    ("宏观经济", "美债收益率：无风险利率对成长股估值的压制机制"),
    # 投资理念
    ("投资理念", "价值投资 vs 成长投资：两大流派的核心分歧"),
    ("投资理念", "集中投资 vs 分散投资：巴菲特的鸡蛋篮子观点"),
    ("投资理念", "长期持有的数学：时间复利对收益的指数级放大"),
    ("投资理念", "市场先生：格雷厄姆的情绪化市场比喻与应用"),
    ("投资理念", "能力圈原则：只投自己真正理解的生意"),
]


class KnowledgeLog:
    """管理已推送记录，避免重复推送"""

    def __init__(self):
        self._data = self._load()

    def _load(self) -> Dict:
        if LOG_FILE.exists():
            try:
                with open(LOG_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"a_share": [], "us_stock": []}

    def save(self):
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "w") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get_pushed(self, market: str) -> List[str]:
        return self._data.get(market, [])

    def mark_pushed(self, market: str, topics: List[str]):
        # 写前重新读磁盘，避免两个实例互相覆盖对方的 market 数据
        self._data = self._load()
        if market not in self._data:
            self._data[market] = []
        self._data[market].extend(topics)
        self.save()

    def reset(self, market: str):
        self._data[market] = []
        self.save()
        logger.info(f"{market} 知识推送日志已重置，重新循环")


def _generate_knowledge_content(category: str, topic: str) -> str:
    system_prompt = "你是专业的股票投资教育讲师，擅长用通俗易懂的语言深入讲解投资知识。请用中文输出。"
    user_prompt = f"""请深度讲解以下股票知识点：

知识分类：{category}
知识主题：{topic}

请按以下格式输出（专业深入，500字以内）：

【是什么】一句话定义这个概念

【核心原理】深度解析这个知识点的内涵（3-4句）

【实战应用】如何在实际投资中运用（2-3个具体场景或操作方法）

【典型案例】一个具体的市场案例或数据举例说明

【注意事项】使用这个知识点时的常见误区或风险（2条）

【一句话总结】用一句话点出最核心的要点"""

    return ai_engine._call(system_prompt, user_prompt, max_tokens=1200)


class AShareKnowledge:
    """A股每日知识推送"""

    def __init__(self):
        self.log = KnowledgeLog()

    def _pick_topic(self) -> Tuple[str, str]:
        pushed = set(self.log.get_pushed("a_share"))
        not_pushed = [t for t in A_SHARE_KNOWLEDGE_POOL if t[1] not in pushed]

        if not not_pushed:
            self.log.reset("a_share")
            not_pushed = A_SHARE_KNOWLEDGE_POOL

        return random.choice(not_pushed)

    def run_daily_push(self):
        logger.info("开始A股知识推送")
        category, topic = self._pick_topic()
        try:
            content = _generate_knowledge_content(category, topic)
            if not content:
                logger.warning("A股知识内容生成失败")
                return
            msg = (
                f"📖 A股知识  【{category}】\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"📌 {topic}\n\n"
                f"{content}"
            )
            notifier.telegram.send(msg)
            self.log.mark_pushed("a_share", [topic])
            logger.info(f"已推送A股知识: {topic}")
        except Exception as e:
            logger.error(f"A股知识推送失败: {e}", exc_info=True)


class USKnowledge:
    """美股每日知识推送"""

    def __init__(self):
        self.log = KnowledgeLog()

    def _pick_topic(self) -> Tuple[str, str]:
        pushed = set(self.log.get_pushed("us_stock"))
        not_pushed = [t for t in US_KNOWLEDGE_POOL if t[1] not in pushed]

        if not not_pushed:
            self.log.reset("us_stock")
            not_pushed = US_KNOWLEDGE_POOL

        return random.choice(not_pushed)

    def run_daily_push(self):
        logger.info("开始美股知识推送")
        category, topic = self._pick_topic()
        try:
            content = _generate_knowledge_content(category, topic)
            if not content:
                logger.warning("美股知识内容生成失败")
                return
            msg = (
                f"📖 美股知识  【{category}】\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"📌 {topic}\n\n"
                f"{content}"
            )
            notifier.us.send(msg)
            self.log.mark_pushed("us_stock", [topic])
            logger.info(f"已推送美股知识: {topic}")
        except Exception as e:
            logger.error(f"美股知识推送失败: {e}", exc_info=True)


a_knowledge = AShareKnowledge()
us_knowledge = USKnowledge()
