"""
ChiangMai1 - Markdown Reporter
"""
from typing import Dict, Optional
from ..core.data_models import Report, AnalysisResult, StrategyAdvice, MarketData

class MarkdownReporter:
    """Markdown 报告生成器"""

    @staticmethod
    def generate(report: Report) -> str:
        lines = []
        lines.append(f"## {report.symbol} {report.timeframe} 行情走势分析报告")
        lines.append("")
        lines.append("### 核心结论")
        lines.append(f"**{report.summary}**")
        lines.append("")
        lines.append("### 数据快照")
        lines.append("")
        lines.append("| 指标 | 数值 | 状态 |")
        lines.append("|------|------|------|")

        analysis = report.analysis
        lines.append(f"| 趋势方向 | {analysis.trend_direction.value} | - |")
        lines.append(f"| 风险评级 | {analysis.risk_level.value} | {'⚠️' if analysis.risk_level.value in ['高风险', '极高风险'] else '✓'} |")
        lines.append(f"| 极端指标数 | {analysis.extreme_alerts}/6 | {'🔴' if analysis.bubble_zone else '🟡' if analysis.extreme_alerts >= 2 else '🟢'} |")
        lines.append(f"| 泡沫区 | {'是' if analysis.bubble_zone else '否'} | {'🔴' if analysis.bubble_zone else '✓'} |")
        lines.append("")

        lines.append("### 策略矩阵")
        lines.append("")
        lines.append("| 角色 | 建议 | 入场点 | 止损 | 目标位 |")
        lines.append("|------|------|--------|------|--------|")

        strategy = report.strategy
        lines.append(f"| 有仓位者 | {strategy.for_holders} | — | — | — |")

        if strategy.for_newcomers_aggressive:
            agg = strategy.for_newcomers_aggressive
            lines.append(f"| 无仓位-激进 | 回调至{agg['entry']}介入 | {agg['entry']} | {agg['stop_loss']} | T1:{agg['target_1']} T2:{agg['target_2']} |")
        else:
            lines.append("| 无仓位-激进 | 当前不建议 | — | — | — |")

        if strategy.for_newcomers_conservative:
            con = strategy.for_newcomers_conservative
            lines.append(f"| 无仓位-稳健 | 深度回调至{con['entry']}或形态完成 | {con['entry']} | {con['stop_loss']} | T1:{con['target_1']} T2:{con['target_2']} |")
        else:
            lines.append("| 无仓位-稳健 | 等待明确信号 | — | — | — |")

        lines.append("")

        lines.append("### 详细分析")
        lines.append("")
        lines.append(f"**趋势共振**：{analysis.trend_resonance}")
        lines.append("")
        lines.append(f"**资金验证**：{analysis.capital_verdict}")
        lines.append("")
        lines.append(f"**量价健康**：{analysis.volume_health}")
        lines.append("")

        lines.append("### 默认立场")
        lines.append(f"**{strategy.default_action}**")
        lines.append("")

        if report.targets:
            lines.append("### 目标价位")
            for name, price in report.targets.items():
                lines.append(f"- {name}：**{price:.4f}**")
            lines.append("")

        if report.stop_loss:
            lines.append("### 止损参考")
            lines.append(f"**{report.stop_loss:.4f}**")
            lines.append("")

        lines.append("### 一句话总结")
        lines.append("")

        if analysis.trend_direction.value in ["极端强势上升", "强势上升"]:
            if analysis.bubble_zone:
                lines.append("📌 **持多者分批止盈，未入场者坚决观望。市场不会永远直线上升。**")
            else:
                lines.append("📌 **趋势健康，持多者持有，回调可介入。**")
        elif analysis.trend_direction.value in ["极端恐慌下降", "强势下降"]:
            lines.append("📌 **趋势向下，空仓观望，等待企稳信号。**")
        else:
            lines.append("📌 **震荡格局，区间内操作或观望。**")

        lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(f"**{report.disclaimer}**")

        return "\n".join(lines)

    @staticmethod
    def quick_summary(report: Report) -> str:
        return f"[{report.symbol}] {report.analysis.trend_direction.value} | 风险:{report.analysis.risk_level.value} | {report.strategy.default_action}"
