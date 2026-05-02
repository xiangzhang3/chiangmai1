"""
ChiangMai1 - Data Models
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from enum import Enum

class TrendDirection(Enum):
    EXTREME_BULL = "极端强势上升"
    BULL = "强势上升"
    WEAK_BULL = "震荡上升"
    RANGE = "区间震荡"
    WEAK_BEAR = "震荡下降"
    BEAR = "强势下降"
    EXTREME_BEAR = "极端恐慌下降"

class AlertLevel(Enum):
    NORMAL = "正常"
    WARNING = "警戒"
    EXTREME = "极端"

class RiskLevel(Enum):
    LOW = "低风险"
    MEDIUM = "中风险"
    HIGH = "高风险"
    EXTREME = "极高风险"

@dataclass
class PriceData:
    current: float
    change_24h_pct: float
    high_24h: float
    low_24h: float
    ath: Optional[float] = None

@dataclass
class MovingAverages:
    ma5: float
    ma20: float
    ma120: float
    ma60: Optional[float] = None
    def deviation_from(self, price: float, ma_name: str) -> float:
        ma_value = getattr(self, ma_name, None)
        if ma_value is None or ma_value == 0:
            return 0.0
        return (price - ma_value) / ma_value * 100

@dataclass
class MACD:
    dif: float
    dea: float
    histogram: float
    @property
    def status(self) -> str:
        if self.dif > self.dea and self.histogram > 0:
            return "金叉运行中"
        elif self.dif < self.dea and self.histogram < 0:
            return "死叉运行中"
        return "粘合"

@dataclass
class RSI:
    rsi6: float
    rsi14: float
    def get_level(self, value: float) -> AlertLevel:
        if value > 85 or value < 15:
            return AlertLevel.EXTREME
        elif value > 70 or value < 30:
            return AlertLevel.WARNING
        return AlertLevel.NORMAL

@dataclass
class KDJ:
    k: float
    d: float
    j: float
    def get_j_level(self) -> AlertLevel:
        if self.j > 95 or self.j < 5:
            return AlertLevel.EXTREME
        elif self.j > 80 or self.j < 20:
            return AlertLevel.WARNING
        return AlertLevel.NORMAL

@dataclass
class Bollinger:
    upper: float
    middle: float
    lower: float
    @property
    def bandwidth_pct(self) -> float:
        if self.middle == 0:
            return 0.0
        return (self.upper - self.lower) / self.middle * 100
    def percent_b(self, price: float) -> float:
        if self.upper == self.lower:
            return 0.5
        return (price - self.lower) / (self.upper - self.lower)

@dataclass
class CapitalFlow:
    h1: float
    h4: float
    h24: float
    h6: Optional[float] = None
    d7: Optional[float] = None
    @property
    def all_positive(self) -> bool:
        values = [v for v in [self.h1, self.h4, self.h6, self.h24, self.d7] if v is not None]
        return all(v > 0 for v in values) if values else False
    def slowing_down(self, threshold: float = 0.3) -> bool:
        if self.h4 is None or self.h1 is None:
            return False
        return self.h4 < self.h1 * 4 * (1 - threshold)

@dataclass
class FundingRate:
    rate: float
    def get_level(self) -> AlertLevel:
        abs_rate = abs(self.rate)
        if abs_rate > 0.3:
            return AlertLevel.EXTREME
        elif abs_rate > 0.1:
            return AlertLevel.WARNING
        return AlertLevel.NORMAL

@dataclass
class VolumeData:
    current: float
    previous: float
    trend: str = "持平"

@dataclass
class MarketData:
    symbol: str
    timeframe: str
    price: PriceData
    mas: MovingAverages
    macd: MACD
    rsi: RSI
    kdj: KDJ
    boll: Bollinger
    atr: float
    funding: FundingRate
    capital_flow: CapitalFlow
    volume: VolumeData

@dataclass
class AnalysisResult:
    trend_direction: TrendDirection
    trend_resonance: str
    extreme_alerts: int
    bubble_zone: bool
    capital_verdict: str
    volume_health: str
    risk_level: RiskLevel

@dataclass
class StrategyAdvice:
    for_holders: str
    for_newcomers_aggressive: Optional[Dict] = None
    for_newcomers_conservative: Optional[Dict] = None
    default_action: str = "观望"

@dataclass
class Report:
    symbol: str
    timeframe: str
    analysis: AnalysisResult
    strategy: StrategyAdvice
    targets: Dict[str, float]
    stop_loss: Optional[float] = None
    summary: str = ""
    disclaimer: str = "本次分析仅供参考，不构成投资建议。加密货币波动极大，请严格做好风险管理。"
