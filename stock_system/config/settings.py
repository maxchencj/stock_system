"""
系统配置文件 - 股票智能分析系统
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AIConfig:
    """AI 分析引擎配置"""
    api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    model: str = "claude-opus-4-5-20251101"
    max_tokens: int = 4096
    temperature: float = 0.3  # 低温度保证分析稳定性


@dataclass
class DataConfig:
    """数据层配置"""
    # AKShare 相关
    request_timeout: int = 30
    retry_times: int = 3
    retry_delay: float = 1.0

    # 数据缓存
    cache_ttl: int = 300  # 5分钟缓存
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    use_redis: bool = False  # 默认用内存缓存

    # 数据存储
    db_path: str = "data/stock.db"


@dataclass
class StockPickerConfig:
    """选股模块配置"""
    # 每日选股时间
    scan_time: str = "09:30"
    push_time: str = "09:45"

    # 筛选条件（已放宽，适应更多股票）
    min_market_cap: float = 3.0    # 最小市值(亿) - 降低门槛
    max_market_cap: float = 10000.0  # 最大市值(亿) - 提高上限
    min_volume_ratio: float = 1.0   # 最小量比 - 降低要求
    max_pe_ratio: float = 150.0     # 最大市盈率 - 提高上限
    min_price: float = 1.0          # 最低股价 - 降低门槛
    max_price: float = 300.0        # 最高股价 - 提高上限
    top_n: int = 10                 # 每日推送数量

    # 技术指标
    ma_periods: List[int] = field(default_factory=lambda: [5, 10, 20, 60])
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9


@dataclass
class MonitorConfig:
    """监控模块配置"""
    check_interval: int = 60  # 检查间隔(秒)

    # 信号阈值
    price_change_alert: float = 3.0   # 涨跌幅预警(%)
    volume_spike_ratio: float = 3.0   # 成交量异动倍数
    rsi_overbought: float = 75.0      # RSI超买
    rsi_oversold: float = 25.0        # RSI超卖

    # 最大监控股票数
    max_watchlist: int = 50


@dataclass
class SectorConfig:
    """板块分析配置"""
    report_time: str = "17:00"
    top_sectors: int = 5  # 每日报告前N板块


@dataclass
class NotifyConfig:
    """通知层配置"""
    # PushPlus 微信推送
    pushplus_token: str = os.getenv("PUSHPLUS_TOKEN", "")
    pushplus_enabled: bool = True  # 已启用

    # Telegram Bot
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_enabled: bool = bool(os.getenv("TELEGRAM_TOKEN", "") and os.getenv("TELEGRAM_CHAT_ID", ""))

    # 邮件通知（备选）
    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    email_user: str = os.getenv("EMAIL_USER", "")
    email_password: str = os.getenv("EMAIL_PASSWORD", "")
    email_to: str = os.getenv("EMAIL_TO", "")


@dataclass
class WebConfig:
    """可视化层配置"""
    host: str = "0.0.0.0"
    port: int = 8888
    debug: bool = False
    secret_key: str = os.getenv("SECRET_KEY", "stock-system-secret-2024")


@dataclass
class SystemConfig:
    """系统总配置"""
    ai: AIConfig = field(default_factory=AIConfig)
    data: DataConfig = field(default_factory=DataConfig)
    stock_picker: StockPickerConfig = field(default_factory=StockPickerConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    sector: SectorConfig = field(default_factory=SectorConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    web: WebConfig = field(default_factory=WebConfig)

    # 日志配置
    log_level: str = "INFO"
    log_file: str = "logs/system.log"

    # 交易时间
    market_open: str = "09:30"
    market_close: str = "15:00"
    trading_days: List[str] = field(default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri"])


# 全局配置实例
config = SystemConfig()
