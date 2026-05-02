"""
ChiangMai1 - Decision Matrix
决策矩阵：角色区分 + 入场策略 + 止损计算
"""
from typing import Dict, Optional, List
from dataclasses import dataclass
from .data_models import (
    AnalysisResult, StrategyAdvice, MarketData, 
    TrendDirection, RiskLevel
)

class DecisionEngine:
    """决策引擎"""

    def __init__(self, analyzer_config: Optional[Dict] = None):
        self.config = analyzer_config or {}
        self.thresholds = {
            "hard_stop_pct": 0.05,
            "support_buffer": 0.03,
            "atr_mult_aggressive": 1.5,
            "atr_mult_conservative": 2.0,
            "max_position_aggressive": 0.05,
            "max_position_conservative": 0.10
        }
        self.thresholds.update(self.config.get("thresholds", {}))

    def calculate_stop_loss(self, entry_price: float, support: float, atr: float, strategy: str = "aggressive") -> float:
        hard_stop = entry_price * (1 - self.thresholds["hard_stop_pct"])
        support_stop = support * (1 - self.thresholds["support_buffer"])

        if strategy == "aggressive":
            atr_stop = entry_price - atr * self.thresholds["atr_mult_aggressive"]
        else:
            atr_stop = entry_price - atr * self.thresholds["atr_mult_conservative"]

        stop = max(hard_stop, support_stop, atr_stop)
        max_stop = entry_price * 0.85
        return max(stop, max_stop)

    def get_support_levels(self, data: MarketData) -> List[float]:
        supports = []
        supports.append(data.mas.ma5)
        supports.append(data.mas.ma20)
        supports.append(data.price.low_24h)
        if data.mas.ma60:
            supports.append(data.mas.ma60)

        unique_supports = list(dict.fromkeys([round(s, 4) for s in supports if s > 0]))
        return sorted(unique_supports, reverse=True)

    def get_resistance_levels(self, data: MarketData) -> List[float]:
        resistances = []
        resistances.append(data.price.high_24h)
        if data.price.ath:
            resistances.append(data.price.ath)
        resistances.append(data.boll.upper)

        unique_res = list(dict.fromkeys([round(r, 4) for r in resistances if r > 0]))
        return sorted(unique_res)

    def advice_for_holders(self, analysis: AnalysisResult, data: MarketData) -> str:
        trend = analysis.trend_direction
        risk = analysis.risk_level

        if risk == RiskLevel.EXTREME:
            if analysis.bubble_zone:
                return "分批止盈：建议减持50%仓位，剩余设移动止损至MA5下方3%"
            return "减仓至30%，等待趋势明朗"

        if risk == RiskLevel.HIGH:
            if "放缓" in analysis.capital_verdict:
                return "减仓至50%，资金动能衰竭，保护利润优先"
            return "持有，但收紧止损至入场价上方10%（保本）"

        if trend in [TrendDirection.EXTREME_BULL, TrendDirection.BULL]:
            return "持有，移动止损跟随MA5"

        if trend == TrendDirection.RANGE:
            return "区间内高抛低吸，或减仓观望"

        if trend in [TrendDirection.BEAR, TrendDirection.EXTREME_BEAR]:
            return "全部止盈或止损离场"

        return "持有观察"

    def advice_aggressive(self, analysis: AnalysisResult, data: MarketData) -> Optional[Dict]:
        if analysis.bubble_zone and analysis.trend_direction == TrendDirection.EXTREME_BULL:
            return None

        supports = self.get_support_levels(data)
        if not supports:
            return None

        entry = supports[0] if len(supports) > 0 else data.price.current * 0.9

        if entry >= data.price.current:
            entry = data.price.current * 0.95

        stop = self.calculate_stop_loss(entry, entry * 0.95, data.atr, "aggressive")

        targets = self.get_resistance_levels(data)
        target1 = targets[0] if targets else data.price.current * 1.1
        target2 = data.price.current * 1.2 if not targets else targets[-1] * 1.05

        return {
            "trigger": f"回调至 {entry:.4f} 且1H/4H资金流恢复正流入，出现pin bar/吞没形态",
            "entry": round(entry, 4),
            "stop_loss": round(stop, 4),
            "position_size": f"≤{self.thresholds['max_position_aggressive']*100}%",
            "target_1": round(target1, 4),
            "target_2": round(target2, 4),
            "risk_reward": round((target1 - entry) / (entry - stop), 2) if (entry - stop) > 0 else 0
        }

    def advice_conservative(self, analysis: AnalysisResult, data: MarketData) -> Optional[Dict]:
        supports = self.get_support_levels(data)

        if len(supports) >= 2:
            entry = supports[1]
        else:
            entry = data.mas.ma20 if data.mas.ma20 < data.price.current else data.price.current * 0.85

        stop = self.calculate_stop_loss(entry, entry * 0.9, data.atr, "conservative")

        targets = self.get_resistance_levels(data)
        target1 = data.price.high_24h
        target2 = targets[0] if targets else data.price.current * 1.15

        return {
            "trigger": f"深度回调至 {entry:.4f}（MA20）或形成高位整理形态（旗形/三角形）",
            "entry": round(entry, 4),
            "stop_loss": round(stop, 4),
            "position_size": f"≤{self.thresholds['max_position_conservative']*100}%",
            "target_1": round(target1, 4),
            "target_2": round(target2, 4),
            "risk_reward": round((target1 - entry) / (entry - stop), 2) if (entry - stop) > 0 else 0
        }

    def generate_strategy(self, analysis: AnalysisResult, data: MarketData) -> StrategyAdvice:
        holders = self.advice_for_holders(analysis, data)
        aggressive = self.advice_aggressive(analysis, data)
        conservative = self.advice_conservative(analysis, data)

        if analysis.risk_level == RiskLevel.EXTREME:
            default = "强烈观望。当前处于情绪泡沫区，风险回报比极差，禁止追高"
        elif analysis.risk_level == RiskLevel.HIGH:
            default = "观望。等待回调或整理形态完成"
        else:
            default = "可小仓位试多，严格止损"

        return StrategyAdvice(
            for_holders=holders,
            for_newcomers_aggressive=aggressive,
            for_newcomers_conservative=conservative,
            default_action=default
        )
