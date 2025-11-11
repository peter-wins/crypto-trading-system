"""
交易历史API路由
"""

from typing import List
from datetime import datetime, timezone, date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ===== 响应模型 =====

class ClosedPositionResponse(BaseModel):
    """已平仓记录响应"""
    id: int
    symbol: str = Field(..., description="交易对")
    side: str = Field(..., description="方向: buy/sell")

    # 开仓信息
    entry_order_id: str | None = Field(None, description="开仓订单ID")
    entry_price: float = Field(..., description="入场价格")
    entry_time: str = Field(..., description="入场时间")

    # 平仓信息
    exit_order_id: str | None = Field(None, description="平仓订单ID")
    exit_price: float = Field(..., description="出场价格")
    exit_time: str = Field(..., description="出场时间")

    # 数量和金额
    amount: float = Field(..., description="数量")
    entry_value: float = Field(..., description="入场金额")
    exit_value: float = Field(..., description="出场金额")

    # 盈亏
    realized_pnl: float = Field(..., description="实际盈亏")
    realized_pnl_percentage: float = Field(..., description="盈亏百分比")

    # 其他
    holding_duration_seconds: int | None = Field(None, description="持仓时长（秒）")
    holding_duration_display: str | None = Field(None, description="持仓时长（显示）")
    leverage: int | None = Field(None, description="杠杆")


class OrderHistoryResponse(BaseModel):
    """订单历史响应"""
    id: str
    client_order_id: str
    symbol: str
    side: str = Field(..., description="买卖方向: buy/sell")
    type: str = Field(..., description="订单类型")
    status: str = Field(..., description="订单状态")

    price: float | None = Field(None, description="委托价格")
    amount: float = Field(..., description="委托数量")
    filled: float = Field(..., description="已成交数量")
    cost: float = Field(..., description="成交金额")
    average: float | None = Field(None, description="成交均价")
    fee: float | None = Field(None, description="手续费")

    datetime: str = Field(..., description="创建时间")


# ===== API端点 =====

@router.get("/history/closed-positions", response_model=List[ClosedPositionResponse])
async def get_closed_positions(
    symbol: str | None = Query(None, description="交易对筛选"),
    start_date: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(100, description="返回记录数量", le=500),
):
    """
    获取已平仓记录

    返回已平仓的交易记录，包含完整的入场/出场信息和盈亏数据
    """
    logger.info(f"API: 获取已平仓记录 symbol={symbol} start={start_date} end={end_date}")

    try:
        from src.api.server import get_app_state
        from src.database.dao import TradingDAO

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            logger.warning("Database not initialized")
            raise HTTPException(status_code=503, detail="Database not available")

        # 解析日期参数
        start_date_obj = None
        end_date_obj = None
        if start_date:
            start_date_obj = date.fromisoformat(start_date)
        if end_date:
            end_date_obj = date.fromisoformat(end_date)

        # 从数据库获取数据
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)
            closed_positions = await dao.get_closed_positions(
                symbol=symbol,
                start_date=start_date_obj,
                end_date=end_date_obj,
                limit=limit,
                exchange_name="binance"
            )

            # 转换为响应格式
            result = []
            for cp in closed_positions:
                # 计算持仓时长显示
                holding_display = None
                if cp.holding_duration_seconds:
                    duration = cp.holding_duration_seconds
                    hours = duration // 3600
                    minutes = (duration % 3600) // 60
                    if hours > 0:
                        holding_display = f"{hours}h {minutes}m"
                    else:
                        holding_display = f"{minutes}m"

                # 确保时间戳包含时区信息
                entry_time_str = cp.entry_time.replace(tzinfo=timezone.utc).isoformat() if cp.entry_time.tzinfo is None else cp.entry_time.isoformat()
                exit_time_str = cp.exit_time.replace(tzinfo=timezone.utc).isoformat() if cp.exit_time.tzinfo is None else cp.exit_time.isoformat()

                result.append(ClosedPositionResponse(
                    id=cp.id,
                    symbol=cp.symbol,
                    side=cp.side,
                    entry_order_id=cp.entry_order_id,
                    entry_price=float(cp.entry_price),
                    entry_time=entry_time_str,
                    exit_order_id=cp.exit_order_id,
                    exit_price=float(cp.exit_price),
                    exit_time=exit_time_str,
                    amount=float(cp.amount),
                    entry_value=float(cp.entry_value),
                    exit_value=float(cp.exit_value),
                    realized_pnl=float(cp.realized_pnl),
                    realized_pnl_percentage=float(cp.realized_pnl_percentage),
                    holding_duration_seconds=cp.holding_duration_seconds,
                    holding_duration_display=holding_display,
                    leverage=cp.leverage,
                ))

            return result

    except Exception as e:
        logger.error(f"获取已平仓记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/orders", response_model=List[OrderHistoryResponse])
async def get_order_history(
    symbol: str | None = Query(None, description="交易对筛选"),
    status: str | None = Query(None, description="订单状态筛选"),
    start_date: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(100, description="返回记录数量", le=500),
):
    """
    获取订单历史

    返回历史订单记录
    """
    logger.info(f"API: 获取订单历史 symbol={symbol} status={status}")

    try:
        from src.api.server import get_app_state
        from src.database.dao import TradingDAO
        from datetime import datetime as dt

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            logger.warning("Database not initialized")
            raise HTTPException(status_code=503, detail="Database not available")

        # 解析日期参数
        start_datetime = None
        end_datetime = None
        if start_date:
            start_datetime = dt.fromisoformat(start_date + "T00:00:00")
        if end_date:
            end_datetime = dt.fromisoformat(end_date + "T23:59:59")

        # 从数据库获取数据
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)
            orders = await dao.get_orders(
                symbol=symbol,
                status=status,
                start_time=start_datetime,
                end_time=end_datetime,
                limit=limit,
                exchange_name="binance"
            )

            # 转换为响应格式
            result = []
            for order in orders:
                # 确保时间戳包含时区信息
                datetime_str = order.datetime.replace(tzinfo=timezone.utc).isoformat() if order.datetime.tzinfo is None else order.datetime.isoformat()

                result.append(OrderHistoryResponse(
                    id=order.id,
                    client_order_id=order.client_order_id,
                    symbol=order.symbol,
                    side=order.side,
                    type=order.type,
                    status=order.status,
                    price=float(order.price) if order.price else None,
                    amount=float(order.amount),
                    filled=float(order.filled) if order.filled else 0,
                    cost=float(order.cost) if order.cost else 0,
                    average=float(order.average) if order.average else None,
                    fee=float(order.fee) if order.fee else None,
                    datetime=datetime_str,
                ))

            return result

    except Exception as e:
        logger.error(f"获取订单历史失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
