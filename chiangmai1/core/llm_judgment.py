"""
ChiangMai1 - LLM Judgment Layer
"""
from typing import Dict, Optional, List
from dataclasses import dataclass
from .data_models import MarketData, AnalysisResult, TrendDirection

@dataclass
class LLMJudgment:
    whale_intent: str
    intent_confidence: float
    next_move: str
    move_confidence: float
    key_signals: List[str]
    risk_assessment: str
    time_window: str
    reasoning: str

class LLMJudge:
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4"):
        self.api_key = api_key
        self.model = model
        
    def analyze(self, data: MarketData, analysis: AnalysisResult) -> LLMJudgment:
        if self.api_key:
            return self._call_llm_api(data, analysis)
        else:
            return self._rule_based_judgment(data, analysis)
    
    def _rule_based_judgment(self, data, analysis):
        price = data.price.current
        change = data.price.change_24h_pct
        volume = data.volume
        funding = data.funding.rate
        
        if change < 10 and volume.trend == "萎缩" and abs(funding) < 0.05:
            whale_intent, intent_conf = "吸筹", 0.7
        elif change > 50 and volume.trend == "放大" and funding > 0.1:
            whale_intent, intent_conf = "拉升", 0.8
        elif analysis.extreme_alerts >= 3 and volume.trend == "放大" and change > 30:
            whale_intent, intent_conf = "出货", 0.75
        elif change > 20 and analysis.bubble_zone and volume.trend == "萎缩":
            whale_intent, intent_conf = "洗盘", 0.65
        else:
            whale_intent, intent_conf = "观望", 0.5
        
        if analysis.risk_level.value == "极高风险":
            next_move, move_conf = "高位回落或横盘", 0.7
        elif analysis.risk_level.value == "高风险":
            next_move, move_conf = "震荡整理", 0.6
        elif analysis.trend_direction == TrendDirection.EXTREME_BULL:
            next_move, move_conf = "继续冲高后回落", 0.65
        elif analysis.trend_direction == TrendDirection.BULL:
            next_move, move_conf = "震荡上行", 0.6
        elif analysis.trend_direction == TrendDirection.RANGE:
            next_move, move_conf = "区间震荡", 0.55
        else:
            next_move, move_conf = "弱势整理", 0.5
        
        signals = []
        if analysis.trend_direction.value in ["极端强势上升", "强势上升"]:
            signals.append(f"趋势极强: {analysis.trend_direction.value}")
        if analysis.extreme_alerts >= 3:
            signals.append(f"极端指标: {analysis.extreme_alerts}/6 进入泡沫区")
        if "正流入" in analysis.capital_verdict:
            signals.append("资金持续流入 有支撑")
        elif "流出" in analysis.capital_verdict:
            signals.append("资金流出 警惕反转")
        if "量价背离" in analysis.volume_health:
            signals.append("量价背离 上涨不健康")
        elif "量价齐升" in analysis.volume_health:
            signals.append("量价齐升 健康上涨")
        if data.funding.rate > 0.2:
            signals.append(f"资金费率极高: {data.funding.rate}% 多头成本压力大")
        
        risk_level = analysis.risk_level.value
        if risk_level == "极高风险":
            risk = f"极高风险 {analysis.extreme_alerts}个指标极端 随时可能剧烈回调 建议减仓或观望"
        elif risk_level == "高风险":
            risk = "高风险 趋势虽强但超买严重 追高风险极大 建议等待回调"
        elif risk_level == "中风险":
            risk = "中等风险 方向不明 需等待突破确认 建议小仓位试多"
        else:
            risk = "低风险 趋势健康 可正常操作 建议逢低介入"
        
        if risk_level == "极高风险":
            time_window = "立即行动 当前极端状态 随时可能变盘 不宜持仓过夜"
        elif analysis.bubble_zone:
            time_window = "4-8小时内 等待超买指标回落或资金流入放缓确认"
        elif analysis.trend_direction == TrendDirection.RANGE:
            time_window = "24-48小时 震荡格局需要耐心等待方向选择"
        else:
            time_window = "当前即可 趋势明确 可顺势操作"
        
        reasoning = f"基于ChiangMai1分析: 趋势{analysis.trend_direction.value} 三周期{analysis.trend_resonance} 极端指标{analysis.extreme_alerts}/6 资金{analysis.capital_verdict} 量价{analysis.volume_health} 推断主力{whale_intent} 预测{next_move}"
        
        return LLMJudgment(
            whale_intent=whale_intent,
            intent_confidence=intent_conf,
            next_move=next_move,
            move_confidence=move_conf,
            key_signals=signals[:5],
            risk_assessment=risk,
            time_window=time_window,
            reasoning=reasoning
        )
    
    def _call_llm_api(self, data, analysis):
        try:
            import openai
            prompt = f"标的{data.symbol} 价格{data.price.current} 涨跌{data.price.change_24h_pct}% 趋势{analysis.trend_direction.value} 风险{analysis.risk_level.value} 请判断庄家意图和下一步走势"
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000
            )
            content = response.choices[0].message.content
            return self._parse_response(content)
        except ImportError:
            print("警告: 未安装openai库 回退到规则引擎")
            return self._rule_based_judgment(data, analysis)
    
    def _parse_response(self, content):
        return LLMJudgment(
            whale_intent="需解析",
            intent_confidence=0.5,
            next_move="需解析",
            move_confidence=0.5,
            key_signals=[],
            risk_assessment="需解析",
            time_window="需解析",
            reasoning=content
        )

def quick_judge(data, analysis, api_key=None):
    judge = LLMJudge(api_key=api_key)
    return judge.analyze(data, analysis)
