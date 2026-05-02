"""
ChiangMai1 - Core Module
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

__version__ = "1.0.0"
__author__ = "ChiangMai1 Team"

__all__ = [
    "MarketData", "AnalysisResult", "StrategyAdvice", "Report",
    "TrendDirection", "AlertLevel", "RiskLevel",
    "PriceData", "MovingAverages", "MACD", "RSI", "KDJ",
    "Bollinger", "CapitalFlow", "FundingRate", "VolumeData",
    "IndicatorCalculator", "ChiangMaiAnalyzer", "DecisionEngine"
]
