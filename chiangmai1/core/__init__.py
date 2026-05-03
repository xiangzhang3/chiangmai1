"""
ChiangMai1 - Core Module v1.1
"""

from .data_models import (
    MarketData, AnalysisResult, StrategyAdvice, Report,
    TrendDirection, AlertLevel, RiskLevel,
    PriceData, MovingAverages, MACD, RSI, KDJ,
    Bollinger, CapitalFlow, FundingRate, VolumeData
)
from .indicators import IndicatorCalculator
from .analyzer import ChiangMaiAnalyzer
from .decision import DecisionEngine
from .llm_judgment import LLMJudge, LLMJudgment, quick_judge

__version__ = "1.1.0"
__author__ = "ChiangMai1 Team"

__all__ = [
    "MarketData", "AnalysisResult", "StrategyAdvice", "Report",
    "TrendDirection", "AlertLevel", "RiskLevel",
    "PriceData", "MovingAverages", "MACD", "RSI", "KDJ",
    "Bollinger", "CapitalFlow", "FundingRate", "VolumeData",
    "IndicatorCalculator", "ChiangMaiAnalyzer", "DecisionEngine",
    "LLMJudge", "LLMJudgment", "quick_judge"
]
