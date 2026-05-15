"""
数据层 - AKShare 主数据源
"""
import time
import re
import functools
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import requests as _requests

from utils.logger import logger

# 延迟导入 AKShare（可能失败时不影响腾讯接口）
try:
    import akshare as ak
except ImportError:
    ak = None
    logger.warning("AKShare 未安装，将仅使用腾讯财经接口")


# ─────────────────────────── HTTP Session ────────────────────────────
_session = _requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.qq.com/",
})


# ─────────────────────────── 简单内存缓存 ────────────────────────────
_cache: Dict[str, Tuple[float, object]] = {}

def _cache_get(key: str, ttl: int = 300) -> Optional[object]:
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < ttl:
            return val
        del _cache[key]
    return None

def _cache_set(key: str, val: object):
    _cache[key] = (time.time(), val)

def cached(ttl: int = 300):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}:{args}:{kwargs}"
            result = _cache_get(key, ttl)
            if result is not None:
                return result
            result = func(*args, **kwargs)
            if result is not None and (not isinstance(result, pd.DataFrame) or not result.empty):
                _cache_set(key, result)
            return result
        return wrapper
    return decorator


def retry(times: int = 3, delay: float = 2.0):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(times):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if i == times - 1:
                        logger.error(f"{func.__name__} 失败(重试{times}次): {e}")
                        raise
                    logger.warning(f"{func.__name__} 第{i+1}次失败，{delay}s后重试: {str(e)[:80]}")
                    time.sleep(delay)
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════
#  腾讯财经接口（主数据源，已验证可用）
# ═══════════════════════════════════════════════════════════
class TencentAPI:
    """腾讯财经行情接口"""

    BASE = "https://qt.gtimg.cn/q="

    @staticmethod
    def _build_code(code: str) -> str:
        """股票代码转腾讯格式: 000001 → sz000001"""
        if code.startswith(("sh", "sz")):
            return code
        if code.startswith("6"):
            return f"sh{code}"
        return f"sz{code}"

    @staticmethod
    def _parse_line(line: str) -> Optional[Dict]:
        """解析腾讯行情数据行"""
        if '="";' in line or not line.strip():
            return None
        try:
            code_match = re.search(r'v_(\w+)=', line)
            if not code_match:
                return None
            full_code = code_match.group(1)
            val = line.split('"')[1]
            p = val.split('~')
            if len(p) < 45:
                return None

            price = float(p[3]) if p[3] else 0
            prev_close = float(p[4]) if p[4] else 0
            if price == 0 or prev_close == 0:
                return None

            change_pct = round((price - prev_close) / prev_close * 100, 2)
            code = p[2]  # 纯数字代码

            return {
                "code": code,
                "name": p[1],
                "price": price,
                "pre_close": prev_close,
                "open": float(p[5]) if p[5] else 0,
                "volume": int(float(p[6])) if p[6] else 0,       # 手
                "amount": float(p[37].replace(',', '')) if len(p) > 37 and p[37] else 0,  # 万元
                "high": float(p[33]) if len(p) > 33 and p[33] else 0,
                "low": float(p[34]) if len(p) > 34 and p[34] else 0,
                "change_pct": change_pct,
                "change_amount": round(price - prev_close, 2),
                "volume_ratio": float(p[49]) if len(p) > 49 and p[49] else 0,
                "turnover_rate": float(p[38]) if len(p) > 38 and p[38] else 0,
                "pe_ratio": float(p[39]) if len(p) > 39 and p[39] else 0,
                "pb_ratio": float(p[46]) if len(p) > 46 and p[46] else 0,
                "market_cap": float(p[45].replace(',', '')) * 10000 if len(p) > 45 and p[45] else 0,  # 转为元
                "float_market_cap": float(p[44].replace(',', '')) * 10000 if len(p) > 44 and p[44] else 0,
            }
        except (IndexError, ValueError):
            return None

    @classmethod
    def get_batch_quotes(cls, codes: List[str]) -> pd.DataFrame:
        """批量获取实时行情"""
        if not codes:
            return pd.DataFrame()

        results = []
        # 腾讯接口每次最多约80个
        batch_size = 60
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            tc_codes = [cls._build_code(c) for c in batch]
            query = ','.join(tc_codes)
            try:
                r = _session.get(cls.BASE + query, timeout=15)
                r.encoding = 'gbk'
                for line in r.text.strip().split('\n'):
                    parsed = cls._parse_line(line)
                    if parsed:
                        results.append(parsed)
                time.sleep(0.3)  # 避免限流
            except Exception as e:
                logger.warning(f"腾讯行情批次{i}失败: {str(e)[:80]}")

        if results:
            return pd.DataFrame(results)
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
#  行情数据
# ═══════════════════════════════════════════════════════════
class MarketDataService:
    """行情数据服务"""

    @staticmethod
    @cached(ttl=60)
    def get_all_stocks() -> pd.DataFrame:
        """获取全市场股票列表 - 多源兜底"""
        # 方法1: AKShare
        if ak:
            try:
                df = ak.stock_info_a_code_name()
                df.columns = ["code", "name"]
                df = df[~df["name"].str.contains("ST|退|北交所", na=False)]
                df = df[df["code"].str.startswith(("0", "3", "6"))]
                logger.info(f"获取全市场股票 {len(df)} 只 (AKShare)")
                return df
            except Exception as e:
                logger.warning(f"AKShare获取股票列表失败: {str(e)[:80]}")

        # 方法2: 使用固定热门股池（应急）
        logger.warning("使用应急股票池")
        return MarketDataService._emergency_stock_pool()

    @staticmethod
    def _emergency_stock_pool() -> pd.DataFrame:
        """应急股票池 - 沪深300成分股（代码固定）"""
        codes = [
            "600519", "601318", "000858", "600036", "601166",
            "000001", "600276", "601398", "600030", "000333",
            "002415", "600887", "601888", "300750", "002594",
            "600900", "601012", "000568", "600309", "601601",
            "002304", "600438", "603259", "601225", "000725",
            "601899", "600809", "002714", "600585", "000661",
            "002475", "601669", "600104", "600050", "601088",
            "603501", "002142", "601919", "601628", "300059",
            "600010", "601688", "300124", "002049", "600690",
            "601858", "300760", "002352", "600000", "601390",
        ]
        names = [
            "贵州茅台", "中国平安", "五粮液", "招商银行", "兴业银行",
            "平安银行", "恒瑞医药", "工商银行", "中信证券", "美的集团",
            "海康威视", "伊利股份", "中国中免", "宁德时代", "比亚迪",
            "长江电力", "隆基绿能", "泸州老窖", "万华化学", "中国太保",
            "洋河股份", "片仔癀", "药明康德", "陕西煤业", "京东方A",
            "紫金矿业", "山西汾酒", "牧原股份", "海螺水泥", "长城汽车",
            "立讯精密", "三一重工", "上汽集团", "中国联通", "中国神华",
            "韦尔股份", "宁波银行", "中远海控", "中国人寿", "科大讯飞",
            "包钢股份", "华泰证券", "汇川技术", "紫光国微", "海尔智家",
            "中国中车", "迈瑞医疗", "顺丰控股", "浦发银行", "中国中铁",
        ]
        return pd.DataFrame({"code": codes, "name": names})

    @staticmethod
    @cached(ttl=30)
    def get_realtime_quotes(codes: Optional[List[str]] = None) -> pd.DataFrame:
        """获取实时行情 - 腾讯财经（主）+ AKShare（备用）"""

        # 确定需要查询的股票列表
        if not codes:
            stock_df = MarketDataService.get_all_stocks()
            if stock_df.empty:
                return pd.DataFrame()
            codes = stock_df["code"].tolist()

        # 方法1: 腾讯财经接口（主数据源）
        try:
            df = TencentAPI.get_batch_quotes(codes)
            if not df.empty:
                logger.info(f"获取实时行情 {len(df)} 只 (腾讯财经)")
                return df
        except Exception as e:
            logger.warning(f"腾讯财经实时行情失败: {str(e)[:80]}")

        # 方法2: AKShare 备用数据源
        if ak:
            try:
                df = ak.stock_zh_a_spot_em()
                if df is not None and not df.empty:
                    col_map = {
                        "代码": "code", "名称": "name", "最新价": "price",
                        "涨跌幅": "change_pct", "涨跌额": "change_amount",
                        "成交量": "volume", "成交额": "amount", "振幅": "amplitude",
                        "最高": "high", "最低": "low", "今开": "open", "昨收": "pre_close",
                        "量比": "volume_ratio", "换手率": "turnover_rate",
                        "市盈率-动态": "pe_ratio", "市净率": "pb_ratio",
                        "总市值": "market_cap", "流通市值": "float_market_cap",
                    }
                    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
                    if codes:
                        df = df[df["code"].isin(codes)]
                    num_cols = ["price", "change_pct", "volume", "amount", "high", "low",
                                "open", "pre_close", "volume_ratio", "turnover_rate",
                                "pe_ratio", "pb_ratio", "market_cap", "float_market_cap"]
                    for col in num_cols:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce")
                    df = df[df["price"] > 0].copy()
                    logger.info(f"获取实时行情 {len(df)} 只 (AKShare备用)")
                    return df.reset_index(drop=True)
            except Exception as e:
                logger.warning(f"AKShare实时行情失败: {str(e)[:80]}")

        logger.error("所有行情接口失败")
        return pd.DataFrame()

    @staticmethod
    @cached(ttl=3600)
    @retry(times=3, delay=2.0)
    def get_history(code: str, period: str = "daily",
                    start_date: str = None, end_date: str = None,
                    adjust: str = "qfq") -> pd.DataFrame:
        """获取历史K线 - AKShare（历史数据AKShare比较稳定）"""
        if not ak:
            return pd.DataFrame()
        try:
            if not start_date:
                start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
            if not end_date:
                end_date = datetime.now().strftime("%Y%m%d")

            df = ak.stock_zh_a_hist(
                symbol=code, period=period,
                start_date=start_date, end_date=end_date,
                adjust=adjust
            )
            if df is None or df.empty:
                return pd.DataFrame()

            col_map = {
                "日期": "date", "开盘": "open", "收盘": "close",
                "最高": "high", "最低": "low", "成交量": "volume",
                "成交额": "amount", "振幅": "amplitude",
                "涨跌幅": "change_pct", "涨跌额": "change_amount",
                "换手率": "turnover_rate"
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            return df
        except Exception as e:
            logger.error(f"获取{code}历史数据失败: {e}")
            return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
#  板块数据（腾讯申万行业指数）
# ═══════════════════════════════════════════════════════════
# 腾讯主题指数代码（注意：这些不是申万行业指数，而是各类主题指数）
SW_INDUSTRY_INDEX = {
    "sz399975": "证券公司", "sz399976": "CS新能车", "sz399977": "内地低碳",
    "sz399978": "医药100", "sz399979": "大宗商品", "sz399980": "中证超大",
    "sz399981": "300分层", "sz399982": "500等权", "sz399983": "地产等权",
    "sz399984": "300等权", "sz399985": "中证全指", "sz399986": "中证银行",
    "sz399987": "中证酒", "sz399989": "中证医疗", "sz399990": "煤炭等权",
    "sz399991": "一带一路", "sz399992": "CSWD并购", "sz399993": "CSWD生科",
    "sz399994": "信息安全", "sz399995": "基建工程", "sz399996": "智能家居",
    "sz399997": "中证白酒",
}


class SectorDataService:
    """板块数据服务"""

    @staticmethod
    @cached(ttl=120)
    def get_sector_realtime() -> pd.DataFrame:
        """获取行业板块实时行情 - 同花顺细分（主）+ 申万一级（备用）"""

        # 方法1: 同花顺细分行业（97个行业，更细分）
        try:
            from data.ths_service import ths_service
            df = ths_service.get_ths_industry_realtime()
            if not df.empty:
                logger.info(f"获取板块实时行情 {len(df)} 个 (同花顺细分)")
                return df
        except Exception as e:
            logger.warning(f"同花顺行业接口失败: {str(e)[:80]}")

        # 方法2: 申万一级行业（31个行业）
        try:
            from data.shenwan_service import shenwan_service
            df = shenwan_service.get_shenwan_level1_realtime()
            if not df.empty:
                logger.info(f"获取板块实时行情 {len(df)} 个 (申万一级)")
                return df
        except Exception as e:
            logger.warning(f"申万行业接口失败: {str(e)[:80]}")

        # 方法3: 腾讯主题指数
        try:
            codes = list(SW_INDUSTRY_INDEX.keys())
            df = TencentAPI.get_batch_quotes(codes)
            if not df.empty:
                # 添加板块名称
                df['sector_name'] = df['code'].apply(lambda x: SW_INDUSTRY_INDEX.get(f"sz{x}", x))
                # 重命名列以匹配原格式
                df = df.rename(columns={
                    'sector_name': '板块名称',
                    'code': '板块代码',
                    'price': '最新价',
                    'change_pct': '涨跌幅',
                    'market_cap': '总市值',
                    'turnover_rate': '换手率'
                })
                logger.info(f"获取板块实时行情 {len(df)} 个 (腾讯主题指数)")
                return df
        except Exception as e:
            logger.warning(f"腾讯板块接口失败: {str(e)[:80]}")

        # 方法4: AKShare 备用
        if ak:
            try:
                df = ak.stock_board_industry_name_em()
                if df is not None and not df.empty:
                    logger.info(f"获取板块实时行情 {len(df)} 个 (AKShare)")
                    return df
            except Exception as e:
                logger.warning(f"AKShare板块接口失败: {str(e)[:80]}")

        logger.error("所有板块接口失败")
        return pd.DataFrame()

    @staticmethod
    @cached(ttl=300)
    def get_sector_list() -> pd.DataFrame:
        """获取板块列表"""
        return SectorDataService.get_sector_realtime()

    @staticmethod
    @cached(ttl=300)
    @retry(times=2, delay=2.0)
    def get_sector_stocks(sector_name: str) -> pd.DataFrame:
        """获取板块成分股"""
        if not ak:
            return pd.DataFrame()
        try:
            df = ak.stock_board_industry_cons_em(symbol=sector_name)
            col_map = {
                "代码": "code", "名称": "name", "最新价": "price",
                "涨跌幅": "change_pct", "成交量": "volume",
                "成交额": "amount", "换手率": "turnover_rate"
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            return df
        except Exception as e:
            logger.error(f"获取{sector_name}成分股失败: {e}")
            return pd.DataFrame()


# ═══════════════════════════════════════════════════════════
#  资金流向
# ═══════════════════════════════════════════════════════════
class MoneyFlowService:

    @staticmethod
    @cached(ttl=300)
    def get_market_money_flow() -> pd.DataFrame:
        if not ak:
            return pd.DataFrame()
        try:
            df = ak.stock_fund_flow_individual(symbol="今日")
            logger.info(f"获取资金流向 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"获取市场资金流向失败: {e}")
            return pd.DataFrame()

    @staticmethod
    @cached(ttl=300)
    def get_sector_money_flow() -> pd.DataFrame:
        if not ak:
            return pd.DataFrame()
        try:
            df = ak.stock_fund_flow_industry(symbol="即时")
            if df is None or df.empty:
                return pd.DataFrame()
            logger.info(f"获取板块资金流向 {len(df)} 条")
            return df
        except Exception as e:
            logger.error(f"获取板块资金流向失败: {e}")
            return pd.DataFrame()

    @staticmethod
    @cached(ttl=120)
    def get_stock_money_flow(code: str) -> pd.DataFrame:
        if not ak:
            return pd.DataFrame()
        try:
            market = "sh" if code.startswith("6") else "sz"
            df = ak.stock_individual_fund_flow(stock=code, market=market)
            return df
        except Exception as e:
            logger.error(f"获取{code}资金流向失败: {e}")
            return pd.DataFrame()

    @staticmethod
    @cached(ttl=300)
    def get_north_flow() -> dict:
        if not ak:
            return {}
        try:
            df = ak.stock_em_hsgt_north_net_flow_in(symbol="北向资金")
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                return {
                    "date": str(latest.iloc[0]),
                    "net_flow": float(latest.iloc[1]) if len(latest) > 1 else 0,
                }
            return {}
        except Exception as e:
            logger.error(f"获取北向资金失败: {e}")
            return {}


# ═══════════════════════════════════════════════════════════
#  技术指标计算
# ═══════════════════════════════════════════════════════════
class TechnicalIndicators:

    @staticmethod
    def calc_ma(df: pd.DataFrame, periods: List[int] = [5, 10, 20, 60]) -> pd.DataFrame:
        for p in periods:
            df[f"ma{p}"] = df["close"].rolling(window=p).mean().round(2)
        return df

    @staticmethod
    def calc_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-10)
        df["rsi"] = (100 - 100 / (1 + rs)).round(2)
        return df

    @staticmethod
    def calc_macd(df: pd.DataFrame, fast=12, slow=26, signal=9) -> pd.DataFrame:
        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        df["macd_dif"] = (ema_fast - ema_slow).round(4)
        df["macd_dea"] = df["macd_dif"].ewm(span=signal, adjust=False).mean().round(4)
        df["macd_bar"] = (2 * (df["macd_dif"] - df["macd_dea"])).round(4)
        return df

    @staticmethod
    def calc_bollinger(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
        df["boll_mid"] = df["close"].rolling(window=period).mean().round(2)
        std = df["close"].rolling(window=period).std()
        df["boll_upper"] = (df["boll_mid"] + std_dev * std).round(2)
        df["boll_lower"] = (df["boll_mid"] - std_dev * std).round(2)
        return df

    @staticmethod
    def calc_kdj(df: pd.DataFrame, period: int = 9) -> pd.DataFrame:
        low_min = df["low"].rolling(window=period).min()
        high_max = df["high"].rolling(window=period).max()
        rsv = 100 * (df["close"] - low_min) / (high_max - low_min + 1e-10)
        df["kdj_k"] = rsv.ewm(com=2, adjust=False).mean().round(2)
        df["kdj_d"] = df["kdj_k"].ewm(com=2, adjust=False).mean().round(2)
        df["kdj_j"] = (3 * df["kdj_k"] - 2 * df["kdj_d"]).round(2)
        return df

    @classmethod
    def calc_all(cls, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < 30:
            return df
        df = cls.calc_ma(df)
        df = cls.calc_rsi(df)
        df = cls.calc_macd(df)
        df = cls.calc_bollinger(df)
        df = cls.calc_kdj(df)
        return df


# 单例
market_service = MarketDataService()
sector_service = SectorDataService()
money_flow_service = MoneyFlowService()
indicators = TechnicalIndicators()
