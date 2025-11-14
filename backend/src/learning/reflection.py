"""
学习模块 · 反思引擎

支持基于 LLM 的自我反思，未配置 LLM 时提供规则化回退。
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Protocol, Sequence

from src.core.logger import get_logger
from src.services.llm import LLMResponse, Message
from src.services.llm import ToolCall  # re-export for type hints
from src.models.memory import TradingExperience
from src.models.performance import PerformanceMetrics

logger = get_logger(__name__)


class ILLMClient(Protocol):
    async def chat(
        self,
        messages: List[Message],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 800,
    ) -> LLMResponse:
        ...


def _format_experience(experience: TradingExperience) -> str:
    pnl = experience.pnl
    pnl_pct = experience.pnl_percentage
    return (
        f"情景: {experience.situation}\n"
        f"决策: {experience.decision}\n"
        f"结果: {experience.outcome}, 盈亏: {pnl} ({pnl_pct}%)\n"
        f"经验: {', '.join(experience.lessons_learned) if experience.lessons_learned else '暂无'}"
    )


class LLMReflectionEngine:
    """
    反思引擎：优先使用 LLM，如未提供则采用规则化回退。
    """

    def __init__(
        self,
        llm_client: Optional[ILLMClient] = None,
    ) -> None:
        self.llm = llm_client
        self.use_llm = llm_client is not None
        self.logger = logger

    async def reflect_on_trade(self, experience: TradingExperience) -> str:
        """
        对单笔交易进行复盘总结。
        """
        if self.use_llm:
            try:
                prompt = self._build_trade_prompt(experience)
                response = await self.llm.chat(prompt)
                if response.content:
                    return response.content.strip()
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.error("LLM trade reflection failed: %s", exc, exc_info=True)

        return self._fallback_trade_reflection(experience)

    async def reflect_on_period(self, performance: PerformanceMetrics) -> Dict[str, Any]:
        """
        对一段周期表现提炼总结。
        """
        if self.use_llm:
            try:
                prompt = self._build_period_prompt(performance)
                response = await self.llm.chat(prompt)
                if response.content:
                    try:
                        data = json.loads(response.content)
                        if isinstance(data, dict):
                            return data
                    except json.JSONDecodeError:
                        return {
                            "summary": response.content.strip(),
                            "strengths": [],
                            "weaknesses": [],
                            "improvements": [],
                        }
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.error("LLM period reflection failed: %s", exc, exc_info=True)

        return self._fallback_period_reflection(performance)

    async def identify_patterns(
        self,
        experiences: List[TradingExperience],
    ) -> List[Dict[str, Any]]:
        """
        从历史经验中提炼常见模式。
        """
        if self.use_llm:
            try:
                prompt = self._build_pattern_prompt(experiences)
                response = await self.llm.chat(prompt)
                if response.content:
                    try:
                        data = json.loads(response.content)
                        if isinstance(data, list):
                            return data
                    except json.JSONDecodeError:
                        pass
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.error("LLM pattern identification failed: %s", exc, exc_info=True)

        return self._fallback_patterns(experiences)

    # ------------------------------------------------------------------ #
    # Prompts
    # ------------------------------------------------------------------ #

    def _build_trade_prompt(self, experience: TradingExperience) -> List[Message]:
        details = _format_experience(experience)
        return [
            Message(
                role="system",
                content=(
                    "你是资深的量化交易教练，擅长复盘并给出可执行的改进措施。"
                    "请用中文，以条理清晰的段落给出反思。"
                ),
            ),
            Message(
                role="user",
                content=(
                    "请复盘以下交易：\n"
                    f"{details}\n"
                    "请说明：1) 交易亮点；2) 可以改进的地方；3) 下次类似情景的建议。"
                ),
            ),
        ]

    def _build_period_prompt(self, performance: PerformanceMetrics) -> List[Message]:
        payload = performance.model_dump()
        return [
            Message(
                role="system",
                content="你是一位专业的量化研究员，请用 JSON 返回总结。",
            ),
            Message(
                role="user",
                content=(
                    "这是某周期的绩效指标，请提炼总结，并以 JSON 格式输出：\n"
                    f"{json.dumps(payload, ensure_ascii=False)}\n"
                    '格式要求：{"summary": str, "strengths": [], "weaknesses": [], "improvements": []}'
                ),
            ),
        ]

    def _build_pattern_prompt(self, experiences: List[TradingExperience]) -> List[Message]:
        condensed = "\n\n".join(_format_experience(exp) for exp in experiences[:10])
        return [
            Message(
                role="system",
                content="你是交易数据分析师，请找出常见模式。",
            ),
            Message(
                role="user",
                content=(
                    "以下是若干历史交易，请总结出 2-4 个模式。"
                    "每个模式需要包含 pattern、frequency、success_rate、description 字段，返回 JSON 数组。\n"
                    f"{condensed}"
                ),
            ),
        ]

    # ------------------------------------------------------------------ #
    # Fallback implementations
    # ------------------------------------------------------------------ #

    def _fallback_trade_reflection(self, experience: TradingExperience) -> str:
        outcome = experience.outcome
        pnl = _safe_str(experience.pnl)
        lessons = ", ".join(experience.lessons_learned) if experience.lessons_learned else "暂无记录"
        if outcome == "success":
            tone = "交易表现良好，请总结成功要素并继续保持。"
        elif outcome == "failure":
            tone = "交易结果不佳，需要关注风险控制并记录教训。"
        else:
            tone = "交易结果接近盈亏平衡，可进一步优化入场/止盈策略。"
        return (
            f"交易 [{experience.decision}]，结果：{outcome}，盈亏：{pnl}。\n"
            f"已有经验：{lessons}。\n"
            f"{tone}"
        )

    def _fallback_period_reflection(self, performance: PerformanceMetrics) -> Dict[str, Any]:
        summary = (
            f"本周期收益 {performance.total_return:.2f}%，年化 {performance.annualized_return:.2f}%。"
            f"最大回撤 {performance.max_drawdown:.2f}%，Sharpe {performance.sharpe_ratio:.2f}。"
        )
        strengths = []
        weaknesses = []
        improvements = []

        if performance.sharpe_ratio > 1:
            strengths.append("收益/波动比表现优秀（Sharpe>1）。")
        else:
            weaknesses.append("风险调整后收益较弱，可优化策略稳定性。")

        if performance.max_drawdown > Decimal("10"):
            weaknesses.append("最大回撤较大，需要收紧仓位或止损。")
            improvements.append("考虑降低单笔风险或缩短持仓时间。")
        else:
            strengths.append("回撤控制合理。")

        if performance.win_rate > Decimal("50"):
            strengths.append("胜率领先，说明择时有效。")
        else:
            improvements.append("提升信号质量或过滤低质量交易。")

        if performance.profit_factor < Decimal("1.2"):
            improvements.append("盈亏比偏低，可优化止盈/止损比例。")

        return {
            "summary": summary,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "improvements": improvements,
        }

    def _fallback_patterns(self, experiences: Sequence[TradingExperience]) -> List[Dict[str, Any]]:
        tag_map: Dict[str, List[TradingExperience]] = defaultdict(list)
        for exp in experiences:
            if exp.tags:
                for tag in exp.tags:
                    tag_map[tag].append(exp)
            else:
                tag_map[exp.decision].append(exp)

        patterns: List[Dict[str, Any]] = []
        for name, items in tag_map.items():
            total = len(items)
            success = sum(1 for item in items if item.outcome == "success")
            success_rate = float(success / total) if total else 0.0
            description = (
                f"与 {name} 相关的交易共 {total} 次，成功 {success} 次，成功率 {success_rate:.2%}。"
            )
            patterns.append(
                {
                    "pattern": name,
                    "frequency": total,
                    "success_rate": success_rate,
                    "description": description,
                }
            )
        return patterns


def _safe_str(value: Any) -> str:
    try:
        return str(value)
    except Exception:  # pylint: disable=broad-except
        return "未知"
