"""
决策API路由
"""

from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta
from enum import Enum

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ===== 枚举类型 =====

class DecisionType(str, Enum):
    STRATEGIC = "STRATEGIC"
    TACTICAL = "TACTICAL"


class SignalType(str, Enum):
    ENTER_LONG = "ENTER_LONG"
    EXIT_LONG = "EXIT_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    EXIT_SHORT = "EXIT_SHORT"
    HOLD = "HOLD"


class MarketRegime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    VOLATILE = "VOLATILE"


# ===== 响应模型 =====

class ToolCallResponse(BaseModel):
    """工具调用响应"""
    name: str
    arguments: Dict[str, Any]
    result: Any | None = None


class DecisionRecordResponse(BaseModel):
    """决策记录响应"""
    id: str
    timestamp: str
    decision_type: DecisionType
    symbol: str | None = None
    signal: SignalType | None = None
    reasoning: str
    confidence: float
    context: Dict[str, Any] | None = None
    tool_calls: List[ToolCallResponse] | None = None
    outcome: str | None = None
    model_used: str | None = None


class StrategyConfigResponse(BaseModel):
    """策略配置响应"""
    market_regime: MarketRegime
    confidence: float
    risk_level: float
    max_position_size: float
    active_symbols: List[str]
    reasoning: str


# ===== Mock数据生成器 =====

def create_mock_decisions(limit: int = 50) -> List[DecisionRecordResponse]:
    """创建模拟决策历史"""
    import random
    import uuid

    decisions = []
    now = datetime.now(timezone.utc)

    for i in range(limit):
        decision_type = random.choice([DecisionType.STRATEGIC, DecisionType.TACTICAL])
        timestamp = now - timedelta(minutes=i * 15)

        if decision_type == DecisionType.TACTICAL:
            symbol = random.choice(["BTC/USDT", "ETH/USDT", "SOL/USDT"])
            signal = random.choice([
                SignalType.ENTER_LONG,
                SignalType.EXIT_LONG,
                SignalType.ENTER_SHORT,
                SignalType.EXIT_SHORT,
                SignalType.HOLD
            ])
            reasoning = f"基于技术指标分析，{symbol} 当前价格走势显示{signal.value}信号"
        else:
            symbol = None
            signal = None
            reasoning = "市场整体处于震荡期，建议降低仓位，观望为主"

        decisions.append(DecisionRecordResponse(
            id=str(uuid.uuid4()),
            timestamp=timestamp.isoformat(),
            decision_type=decision_type,
            symbol=symbol,
            signal=signal,
            reasoning=reasoning,
            confidence=random.uniform(0.6, 0.95),
            context={
                "market_condition": "neutral",
                "volatility": random.uniform(0.01, 0.05),
            },
            tool_calls=[
                ToolCallResponse(
                    name="get_market_data",
                    arguments={"symbol": symbol or "BTC/USDT"},
                    result={"price": random.uniform(40000, 50000)},
                )
            ] if decision_type == DecisionType.TACTICAL else None,
            outcome="executed" if random.random() > 0.3 else "pending",
        ))

    return decisions


def create_mock_strategy() -> StrategyConfigResponse:
    """创建模拟策略配置"""
    import random

    return StrategyConfigResponse(
        market_regime=random.choice([MarketRegime.BULL, MarketRegime.SIDEWAYS, MarketRegime.BEAR]),
        confidence=random.uniform(0.7, 0.9),
        risk_level=random.uniform(0.3, 0.7),
        max_position_size=random.uniform(0.2, 0.4),
        active_symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        reasoning="当前市场处于震荡期，建议采用中等风险策略，重点关注主流币种",
    )


def convert_db_decision_to_response(db_decision) -> DecisionRecordResponse:
    """
    将数据库DecisionModel转换为API响应

    数据库字段映射:
    - decision_layer -> decision_type (strategic/tactical -> STRATEGIC/TACTICAL)
    - decision (JSON字段) -> 包含 signal_type, confidence等
    - input_context (JSON) -> 包含 symbol, regime等
    - thought_process -> reasoning
    - action_taken -> 用于推断outcome状态
    """
    import json

    # 解析decision JSON字段
    decision_data = {}
    if isinstance(db_decision.decision, str):
        try:
            decision_data = json.loads(db_decision.decision)
        except:
            decision_data = {}
    elif isinstance(db_decision.decision, dict):
        decision_data = db_decision.decision
    else:
        decision_data = {}

    # 解析input_context JSON字段
    context_data = db_decision.input_context or {}

    # 提取信号类型并映射到标准格式
    signal_str = decision_data.get("signal_type", "").lower()
    signal = None

    # 映射后端信号到标准格式
    signal_mapping = {
        "enter_long": "ENTER_LONG",
        "exit_long": "EXIT_LONG",
        "enter_short": "ENTER_SHORT",
        "exit_short": "EXIT_SHORT",
        "hold": "HOLD",
    }

    mapped_signal = signal_mapping.get(signal_str)
    if mapped_signal:
        signal = SignalType(mapped_signal)

    # 提取交易对
    symbol = context_data.get("symbol")

    # 提取置信度
    confidence = decision_data.get("confidence", 0.0)

    # 决策类型转换
    decision_type = DecisionType.STRATEGIC if db_decision.decision_layer == "strategic" else DecisionType.TACTICAL

    # 提取工具调用
    tool_calls = []
    if db_decision.tools_used:
        for tool_name in db_decision.tools_used:
            tool_calls.append(ToolCallResponse(
                name=tool_name,
                arguments={},
                result=None
            ))

    # 推断outcome状态
    outcome = "executed" if db_decision.action_taken else "pending"

    # 确保时间戳包含时区信息（UTC）
    if db_decision.datetime:
        if db_decision.datetime.tzinfo is None:
            # 如果没有时区信息，假设是UTC
            from datetime import timezone
            dt_with_tz = db_decision.datetime.replace(tzinfo=timezone.utc)
            timestamp_str = dt_with_tz.isoformat()
        else:
            timestamp_str = db_decision.datetime.isoformat()
    else:
        timestamp_str = ""

    return DecisionRecordResponse(
        id=db_decision.id,
        timestamp=timestamp_str,
        decision_type=decision_type,
        symbol=symbol,
        signal=signal,
        reasoning=db_decision.thought_process or "",
        confidence=float(confidence),
        context=context_data,
        tool_calls=tool_calls if tool_calls else None,
        outcome=outcome,
        model_used=db_decision.model_used
    )


# ===== API端点 =====

@router.get("/decisions", response_model=List[DecisionRecordResponse])
async def get_decision_history(
    limit: int | None = Query(None, ge=1, description="返回数量限制，不传则返回所有"),
):
    """
    获取决策历史

    返回最近的决策记录列表
    """
    logger.info(f"API: 获取决策历史 limit={limit}")

    try:
        from src.api.server import get_app_state
        from src.services.database import TradingDAO

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            logger.warning("Database not initialized, returning mock data")
            return create_mock_decisions(limit)

        # 从数据库获取真实数据
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)
            decisions = await dao.get_decisions(limit=limit)
            return [convert_db_decision_to_response(d) for d in decisions]

    except Exception as e:
        logger.error(f"获取决策历史失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions/{decision_id}", response_model=DecisionRecordResponse)
async def get_decision(decision_id: str):
    """
    获取决策详情

    返回指定ID的决策详细信息
    """
    logger.info(f"API: 获取决策详情 {decision_id}")

    try:
        from src.api.server import get_app_state
        from src.services.database import TradingDAO

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            logger.warning("Database not initialized, returning mock data")
            decisions = create_mock_decisions(1)
            if decisions:
                decision = decisions[0]
                decision.id = decision_id
                return decision

        # 从数据库获取真实数据
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)
            decision = await dao.get_decision_by_id(decision_id)

            if not decision:
                raise HTTPException(status_code=404, detail=f"Decision not found: {decision_id}")

            return convert_db_decision_to_response(decision)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取决策详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions/latest", response_model=DecisionRecordResponse)
async def get_latest_decision():
    """
    获取最新决策

    返回最近的一条决策记录
    """
    logger.info("API: 获取最新决策")

    try:
        from src.api.server import get_app_state
        from src.services.database import TradingDAO

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            logger.warning("Database not initialized, returning mock data")
            decisions = create_mock_decisions(1)
            if decisions:
                return decisions[0]
            raise HTTPException(status_code=404, detail="No decisions found")

        # 从数据库获取真实数据
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)
            decisions = await dao.get_decisions(limit=1)

            if not decisions:
                raise HTTPException(status_code=404, detail="No decisions found")

            return convert_db_decision_to_response(decisions[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取最新决策失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategy/current", response_model=StrategyConfigResponse)
async def get_current_strategy():
    """
    获取当前策略配置

    返回当前的战略层策略配置
    """
    logger.info("API: 获取当前策略配置")

    try:
        # TODO: 集成真实的战略决策器
        # from src.api.server import get_app_state
        # app_state = get_app_state()
        # strategist = app_state.get("strategist")
        # if not strategist:
        #     raise HTTPException(status_code=500, detail="Strategist not initialized")
        #
        # strategy = await strategist.get_current_strategy()
        # return convert_strategy_to_response(strategy)

        # 临时返回Mock数据
        return create_mock_strategy()

    except Exception as e:
        logger.error(f"获取当前策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
