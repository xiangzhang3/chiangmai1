"""
ChiangMai1 - Analysis Engine
核心分析引擎：趋势定性、超买量化、资金验证、量价健康
"""
from typing import Dict, List, Optional
from .data_models import (
    MarketData, AnalysisResult, TrendDirection, AlertLevel, RiskLevel,
    MovingAverages, MACD, RSI, KDJ, Bollinger, CapitalFlow, FundingRate
)

class ChiangMaiAnalyzer:
    """ChiangMai1 主分析引擎"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.thresholds = {
            "rsi6_extreme": 85,
            "rsi6_warning": 70,
            "rsi14_extreme": 80,
            "rsi14_warning": 65,
            "pct_b_extreme": 1.2,
            "pct_b_warning": 1.0,
            "j_extreme": 95,
            "j_warning": 80,
            "funding_extreme": 0.3,
            "funding_warning": 0.1,
            "deviation_extreme": 200,
            "bubble_zone_count": 3,
            "atr_stop_multiplier_aggressive": 1.5,
            "atr_stop_multiplier_conservative": 2.0,
            "hard_stop_pct": 0.05,
            "support_buffer": 0.03
        }
        self.thresholds.update(self.config.get("thresholds", {}))

    def analyze_trend(self, data: MarketData) -> TrendDirection:
        price = data.price.current
        mas = data.mas
        dev_ma5 = mas.deviation_from(price, "ma5")
        dev_ma20 = mas.deviation_from(price, "ma20")
        short_bull = price > mas.ma5
        mid_bull = price > mas.ma20
        long_bull = price > mas.ma120
        extreme_up = dev_ma5 > self.thresholds["deviation_extreme"]
        strong_up = dev_ma5 > 50 and dev_ma20 > 20

        if short_bull and mid_bull and long_bull:
            if extreme_up:
                return TrendDirection.EXTREME_BULL
            elif strong_up:
                return TrendDirection.BULL
            else:
                return TrendDirection.WEAK_BULL
        elif not short_bull and not mid_bull and not long_bull:
            if dev_ma5 < -50:
                return TrendDirection.EXTREME_BEAR
            elif dev_ma5 < -20:
                return TrendDirection.BEAR
            else:
                return TrendDirection.WEAK_BEAR
        else:
            return TrendDirection.RANGE

    def analyze_resonance(self, data: MarketData) -> str:
        price = data.price.current
        mas = data.mas
        short = "多头" if price > mas.ma5 else "空头"
        mid = "多头" if price > mas.ma20 else "空头"
        long = "多头" if price > mas.ma120 else "空头"

        if short == mid == long:
            return f"三周期共振：全{short}，趋势强化"
        elif short != mid and mid == long:
            return f"短期{short} vs 中/长期{mid}，出现分歧，警惕回调"
        elif short == mid and mid != long:
            return f"短/中期{short} vs 长期{long}，趋势可能反转"
        else:
            return "三周期全部分歧，处于混沌状态"

    def analyze_overbought(self, data: MarketData) -> Dict:
        alerts = {
            "rsi6": False,
            "rsi14": False,
            "pct_b": False,
            "j_value": False,
            "funding": False,
            "deviation": False
        }

        if data.rsi.rsi6 > self.thresholds["rsi6_extreme"] or data.rsi.rsi6 < (100 - self.thresholds["rsi6_extreme"]):
            alerts["rsi6"] = True
        if data.rsi.rsi14 > self.thresholds["rsi14_extreme"] or data.rsi.rsi14 < (100 - self.thresholds["rsi14_extreme"]):
            alerts["rsi14"] = True

        pct_b = data.boll.percent_b(data.price.current)
        if pct_b > self.thresholds["pct_b_extreme"] or pct_b < -0.2:
            alerts["pct_b"] = True

        if data.kdj.j > self.thresholds["j_extreme"] or data.kdj.j < (100 - self.thresholds["j_extreme"]):
            alerts["j_value"] = True

        if abs(data.funding.rate) > self.thresholds["funding_extreme"]:
            alerts["funding"] = True

        dev_ma5 = data.mas.deviation_from(data.price.current, "ma5")
        if abs(dev_ma5) > self.thresholds["deviation_extreme"]:
            alerts["deviation"] = True

        extreme_count = sum(1 for v in alerts.values() if v)
        bubble_zone = extreme_count >= self.thresholds["bubble_zone_count"]

        return {
            "alerts": alerts,
            "extreme_count": extreme_count,
            "bubble_zone": bubble_zone,
            "pct_b_value": pct_b,
            "deviation_ma5": dev_ma5
        }

    def analyze_capital(self, data: MarketData) -> str:
        cf = data.capital_flow

        if not cf.all_positive:
            if cf.h24 < 0:
                return "资金流出，趋势支撑不足，警惕反转"
            else:
                return "部分周期资金流入放缓，动能减弱"

        if cf.slowing_down():
            return "资金持续流入但4H周期开始放缓，关注动能衰竭信号"

        h24_abs = abs(cf.h24)
        if h24_abs > 50_000_000:
            intensity = "巨量"
        elif h24_abs > 10_000_000:
            intensity = "大量"
        else:
            intensity = "中等"

        return f"全周期资金正流入，24H{intensity}净流入，趋势有资金支撑"

    def analyze_volume_price(self, data: MarketData) -> str:
        vol = data.volume
        price_change = data.price.change_24h_pct

        if price_change > 0:
            if vol.trend == "放大":
                return "量价齐升，健康上涨"
            elif vol.trend == "萎缩":
                return "量价背离，上涨缺乏成交量支撑，警惕假突破"
            else:
                return "价格上升但成交量持平，关注后续量能"
        elif price_change < 0:
            if vol.trend == "放大":
                return "放量下跌，恐慌抛售，等待企稳"
            else:
                return "缩量下跌，抛压减轻，可能接近底部"
        else:
            return "价格持平，成交量" + vol.trend

    def determine_risk(self, trend: TrendDirection, overbought: Dict, capital: str) -> RiskLevel:
        extreme_count = overbought["extreme_count"]
        bubble = overbought["bubble_zone"]

        if bubble and trend in [TrendDirection.EXTREME_BULL, TrendDirection.EXTREME_BEAR]:
            return RiskLevel.EXTREME

        if extreme_count >= 2 and trend in [TrendDirection.BULL, TrendDirection.BEAR]:
            return RiskLevel.HIGH

        if "流出" in capital or "放缓" in capital:
            if trend in [TrendDirection.BULL, TrendDirection.EXTREME_BULL]:
                return RiskLevel.HIGH

        if extreme_count >= 1 or trend == TrendDirection.RANGE:
            return RiskLevel.MEDIUM

        return RiskLevel.LOW

    def analyze(self, data: MarketData) -> AnalysisResult:
        trend = self.analyze_trend(data)
        resonance = self.analyze_resonance(data)
        overbought = self.analyze_overbought(data)
        capital = self.analyze_capital(data)
        volume_health = self.analyze_volume_price(data)
        risk = self.determine_risk(trend, overbought, capital)

        return AnalysisResult(
            trend_direction=trend,
            trend_resonance=resonance,
            extreme_alerts=overbought["extreme_count"],
            bubble_zone=overbought["bubble_zone"],
            capital_verdict=capital,
            volume_health=volume_health,
            risk_level=risk
        )
