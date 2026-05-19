"""
投研学习模块 - 每日推送股票深度研究报告
A股 → A股 Bot | 美股 → mcDolphin Bot
已推送股票记录在本地，不重复推送，全部推完后自动重置循环
"""
import json
import random
import time
import akshare as ak
import yfinance as yf
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from ai.analysis_engine import ai_engine
from notify.notifier import notifier
from utils.logger import logger

LOG_FILE = Path(__file__).parent.parent.parent / "data" / "research_log.json"
DAILY_COUNT = 3


# 美股优质股票池（按行业分类）
US_STOCK_POOL = [
    # 科技
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "NFLX",
    "AMD", "INTC", "ORCL", "CRM", "ADBE", "QCOM", "AVGO", "TXN",
    "MU", "AMAT", "LRCX", "PANW", "SNOW", "PLTR", "UBER", "LYFT",
    # 金融
    "JPM", "BAC", "WFC", "GS", "MS", "BLK", "V", "MA", "AXP", "C",
    "SCHW", "COF", "USB", "PNC", "TFC",
    # 医疗
    "JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "BMY", "AMGN", "GILD", "ISRG",
    # 消费
    "WMT", "COST", "TGT", "HD", "LOW", "MCD", "SBUX", "NKE", "PG", "KO",
    "PEP", "PM", "MO", "CL", "EL",
    # 能源
    "XOM", "CVX", "COP", "SLB", "EOG", "PXD", "OXY",
    # 工业
    "BA", "GE", "CAT", "MMM", "HON", "UPS", "FDX", "DE", "EMR",
    # 通信
    "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR",
    # 中概股
    "BABA", "PDD", "JD", "BIDU", "NIO", "XPEV", "LI", "NTES", "TME", "BILI",
    # 用户自选
    "SATS", "RDW",
]


class ResearchLog:
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

    def mark_pushed(self, market: str, codes: List[str]):
        if market not in self._data:
            self._data[market] = []
        self._data[market].extend(codes)
        self.save()

    def reset(self, market: str):
        self._data[market] = []
        self.save()
        logger.info(f"{market} 推送日志已重置，重新循环")


# A股兜底股票池（API失败时使用）
A_SHARE_FALLBACK = [
    ("600519", "贵州茅台"), ("000858", "五粮液"), ("002304", "洋河股份"),
    ("601318", "中国平安"), ("600036", "招商银行"), ("000001", "平安银行"),
    ("300750", "宁德时代"), ("002594", "比亚迪"), ("600276", "恒瑞医药"),
    ("000333", "美的集团"), ("600887", "伊利股份"), ("000651", "格力电器"),
    ("601899", "紫金矿业"), ("603993", "洛阳钼业"), ("600585", "海螺水泥"),
    ("601088", "中国神华"), ("600028", "中国石化"), ("601857", "中国石油"),
    ("600900", "长江电力"), ("601985", "中国核电"), ("600011", "华能国际"),
    ("002415", "海康威视"), ("002230", "科大讯飞"), ("603501", "韦尔股份"),
    ("601166", "兴业银行"), ("600000", "浦发银行"), ("601328", "交通银行"),
    ("600309", "万华化学"), ("002714", "牧原股份"), ("300498", "温氏股份"),
    ("601012", "隆基绿能"), ("600438", "通威股份"), ("002459", "晶澳科技"),
    ("300308", "中际旭创"), ("300014", "亿纬锂能"), ("002460", "赣锋锂业"),
    ("000568", "泸州老窖"), ("000596", "古井贡酒"), ("603369", "今世缘"),
    ("600346", "恒力石化"), ("002352", "顺丰控股"), ("601111", "中国国航"),
]


class AShareResearch:
    """A股投研推送"""

    def __init__(self):
        self.log = ResearchLog()

    def _get_quality_pool(self):
        """获取优质A股池（新浪财经接口），失败时用兜底列表"""
        import pandas as pd
        logger.info("获取A股质量股票池（新浪财经）...")
        try:
            df = ak.stock_zh_a_spot()
            # 新浪列名：symbol, open, close, high, low, volume, amount, outstanding_share, turnover_rate
            df = df.rename(columns={"symbol": "代码", "name": "名称"}) if "name" in df.columns else df
            # 过滤ST和退市风险
            if "名称" in df.columns:
                df = df[~df["名称"].str.contains("ST|退", na=False)]
            logger.info(f"优质A股池: {len(df)} 只（新浪财经）")
            # 统一输出格式
            result = pd.DataFrame({
                "代码": df.iloc[:, 0].astype(str).str[-6:],
                "名称": df["名称"] if "名称" in df.columns else df.iloc[:, 1],
                "总市值": 0, "市盈率-动态": 0, "市净率": 0
            })
            return result.reset_index(drop=True)
        except Exception as e:
            logger.warning(f"新浪接口失败，使用兜底列表: {e}")
            rows = [{"代码": c, "名称": n, "总市值": 0, "市盈率-动态": 0, "市净率": 0}
                    for c, n in A_SHARE_FALLBACK]
            return pd.DataFrame(rows)

    def _pick_stocks(self, pool):
        """从股票池中选出未推送的股票"""
        pushed = set(self.log.get_pushed("a_share"))
        not_pushed = pool[~pool["代码"].isin(pushed)]

        if len(not_pushed) < DAILY_COUNT:
            self.log.reset("a_share")
            not_pushed = pool

        return not_pushed.sample(min(DAILY_COUNT, len(not_pushed)))

    def _generate_report(self, row) -> str:
        cap = row.get("总市值", 0)
        cap_str = f"{cap/1e8:.0f}亿" if cap else "未知"
        pe = row.get("市盈率-动态", 0)
        pb = row.get("市净率", 0)

        system_prompt = "你是专业的A股投研分析师，擅长深度分析上市公司的商业价值和投资逻辑。"
        user_prompt = f"""请对以下A股公司进行深度投研分析：

股票代码：{row['代码']}  公司名称：{row['名称']}
总市值：{cap_str}  市盈率：{pe:.1f}x  市净率：{pb:.1f}x

请按以下格式输出（专业深入，600字以内）：

【公司简介】一句话描述主营业务及行业地位

【商业模式】核心收入来源、盈利逻辑、产业链位置（3-4句）

【基本面分析】
  - 营收与利润：近3年趋势如何，增长驱动力是什么
  - 盈利能力：毛利率/净利率水平，与行业对比
  - 财务健康：负债率、现金流状况
  - 股东回报：分红历史或回购情况

【企业文化】管理层风格、公司治理特点、核心价值观（2-3句）

【竞争优势】2-3个核心护城河

【风险提示】2个主要风险

【投资价值】评级 高/中/低 + 一句理由

【综合评分】
  基本面：X/10
  估值：X/10
  竞争力：X/10
  综合得分：X/10"""

        return ai_engine._call(system_prompt, user_prompt, max_tokens=1500)

    def run_daily_push(self):
        """执行每日A股投研推送"""
        logger.info("开始A股投研推送")
        pool = self._get_quality_pool()

        selected = self._pick_stocks(pool)
        pushed_codes = []

        for _, row in selected.iterrows():
            try:
                report = self._generate_report(row)
                if not report:
                    continue
                msg = (
                    f"📚 A股投研  {row['名称']}（{row['代码']}）\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"{report}"
                )
                notifier.telegram.send(msg)
                pushed_codes.append(row["代码"])
                logger.info(f"已推送A股研报: {row['名称']}({row['代码']})")
                time.sleep(3)
            except Exception as e:
                logger.error(f"推送{row['名称']}失败: {e}")

        self.log.mark_pushed("a_share", pushed_codes)
        logger.info(f"A股投研推送完成，共 {len(pushed_codes)} 只")


class USResearch:
    """美股投研推送"""

    def __init__(self):
        self.log = ResearchLog()

    def _extract_cn_name(self, report: str) -> str:
        """从 AI 响应中提取中文名"""
        import re
        match = re.search(r'【中文名】\s*(.+)', report)
        return match.group(1).strip() if match else ""

    def _pick_stocks(self) -> List[str]:
        """选出未推送的美股"""
        pushed = set(self.log.get_pushed("us_stock"))
        not_pushed = [s for s in US_STOCK_POOL if s not in pushed]

        if len(not_pushed) < DAILY_COUNT:
            self.log.reset("us_stock")
            not_pushed = US_STOCK_POOL

        return random.sample(not_pushed, min(DAILY_COUNT, len(not_pushed)))

    def _generate_report(self, symbol: str) -> str:
        try:
            info = yf.Ticker(symbol).info
            name = info.get("longName", symbol)
            sector = info.get("sector", "")
            mkt_cap = info.get("marketCap", 0)
            pe = info.get("trailingPE") or 0
            revenue = info.get("totalRevenue", 0)
            margin = (info.get("profitMargins") or 0) * 100

            # 过滤市值过小的股票
            if mkt_cap and mkt_cap < 200_000_000:
                logger.info(f"{symbol} 市值过小，跳过")
                return ""

            cap_str = f"${mkt_cap/1e9:.1f}B" if mkt_cap else "N/A"
            rev_str = f"${revenue/1e9:.1f}B" if revenue else "N/A"

        except Exception as e:
            logger.warning(f"获取{symbol}数据失败: {e}")
            name, sector, cap_str, rev_str, pe, margin = symbol, "", "N/A", "N/A", 0, 0

        system_prompt = "你是专业的美股投研分析师，擅长深度分析上市公司的商业价值和投资逻辑。请用中文输出。"
        user_prompt = f"""请对以下美股公司进行深度投研分析，请用中文输出：

股票代码：{symbol}  公司名称：{name}
所属行业：{sector}  市值：{cap_str}
营收：{rev_str}  市盈率：{pe:.1f}x  净利润率：{margin:.1f}%

请按以下格式输出（专业深入，600字以内）：

【中文名】公司中文简称（如：英伟达、苹果、特斯拉）

【公司简介】一句话描述主营业务及行业地位

【商业模式】核心收入来源、盈利逻辑、生态系统（3-4句）

【基本面分析】
  - 营收与利润：近3年趋势，增长驱动力
  - 盈利能力：毛利率/净利率，与同行对比
  - 财务健康：资产负债表健康度、自由现金流
  - 股东回报：回购/分红政策

【企业文化】创始人/管理层风格、公司价值观、创新基因（2-3句）

【竞争优势】2-3个核心护城河

【风险提示】2个主要风险

【投资价值】评级 高/中/低 + 一句理由

【综合评分】
  基本面：X/10
  估值：X/10
  竞争力：X/10
  综合得分：X/10"""

        return ai_engine._call(system_prompt, user_prompt, max_tokens=1500)

    def run_daily_push(self):
        """执行每日美股投研推送"""
        logger.info("开始美股投研推送")
        selected = self._pick_stocks()
        pushed_symbols = []

        for symbol in selected:
            try:
                report = self._generate_report(symbol)
                if not report:
                    continue
                try:
                    info = yf.Ticker(symbol).info
                    name = info.get("longName", symbol)
                except Exception:
                    name = symbol

                cn_name = self._extract_cn_name(report)
                display = f"{cn_name}·{name}" if cn_name else name
                msg = (
                    f"📚 美股投研  {display}（{symbol}）\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"{report}"
                )
                notifier.us.send(msg)
                pushed_symbols.append(symbol)
                logger.info(f"已推送美股研报: {symbol}")
                time.sleep(3)
            except Exception as e:
                logger.error(f"推送{symbol}失败: {e}")

        self.log.mark_pushed("us_stock", pushed_symbols)
        logger.info(f"美股投研推送完成，共 {len(pushed_symbols)} 只")


a_research = AShareResearch()
us_research = USResearch()
