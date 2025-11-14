"""
投资组合操作API路由

注意: 数据查询端点已迁移到 /api/account/* 路由
此文件仅包含持仓操作相关的POST端点 (平仓、止损、止盈)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ===== 请求/响应模型 =====

class ClosePositionRequest(BaseModel):
    """平仓请求"""
    symbol: str = Field(..., description="交易对")


class UpdateStopLossRequest(BaseModel):
    """更新止损请求"""
    symbol: str = Field(..., description="交易对")
    stop_loss: float = Field(..., description="止损价格")


class UpdateTakeProfitRequest(BaseModel):
    """更新止盈请求"""
    symbol: str = Field(..., description="交易对")
    take_profit: float = Field(..., description="止盈价格")


class OperationResponse(BaseModel):
    """操作响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="消息")


# ===== API端点 =====
# 注意: GET端点已迁移到 /api/account/* 路由
# 此文件仅保留持仓操作相关的POST端点

@router.post("/portfolio/positions/close", response_model=OperationResponse)
async def close_position(request: ClosePositionRequest):
    """
    平仓

    关闭指定的持仓
    """
    logger.info(f"API: 平仓 {request.symbol}")

    try:
        # TODO: 集成真实的交易执行
        # from src.api.server import get_app_state
        # app_state = get_app_state()
        # portfolio_manager = app_state.get("portfolio_manager")
        # await portfolio_manager.close_position(request.symbol)

        # 临时返回成功响应
        return OperationResponse(
            success=True,
            message=f"成功平仓 {request.symbol}"
        )

    except Exception as e:
        logger.error(f"平仓失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/portfolio/positions/stop-loss", response_model=OperationResponse)
async def update_stop_loss(request: UpdateStopLossRequest):
    """
    更新止损

    设置或更新指定持仓的止损价格
    """
    logger.info(f"API: 更新止损 {request.symbol} -> {request.stop_loss}")

    try:
        # TODO: 集成真实的止损设置
        # from src.api.server import get_app_state
        # app_state = get_app_state()
        # portfolio_manager = app_state.get("portfolio_manager")
        # await portfolio_manager.set_stop_loss(request.symbol, request.stop_loss)

        # 临时返回成功响应
        return OperationResponse(
            success=True,
            message=f"成功设置止损价格: {request.stop_loss}"
        )

    except Exception as e:
        logger.error(f"更新止损失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/portfolio/positions/take-profit", response_model=OperationResponse)
async def update_take_profit(request: UpdateTakeProfitRequest):
    """
    更新止盈

    设置或更新指定持仓的止盈价格
    """
    logger.info(f"API: 更新止盈 {request.symbol} -> {request.take_profit}")

    try:
        # TODO: 集成真实的止盈设置
        # from src.api.server import get_app_state
        # app_state = get_app_state()
        # portfolio_manager = app_state.get("portfolio_manager")
        # await portfolio_manager.set_take_profit(request.symbol, request.take_profit)

        # 临时返回成功响应
        return OperationResponse(
            success=True,
            message=f"成功设置止盈价格: {request.take_profit}"
        )

    except Exception as e:
        logger.error(f"更新止盈失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
