"""
投资组合API路由
"""

from typing import List
from decimal import Decimal
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core.logger import get_logger
from src.models.portfolio import Portfolio
from src.models.trade import Position

logger = get_logger(__name__)

router = APIRouter()


# ===== 响应模型 =====

class PortfolioResponse(BaseModel):
    """投资组合响应（与币安命名对齐）"""
    # 币安对应字段
    wallet_balance: float = Field(..., description="钱包余额 Wallet Balance")
    available_balance: float = Field(..., description="可用保证金 Available Balance")
    margin_balance: float = Field(..., description="保证金余额 Margin Balance（持仓占用）")
    unrealized_pnl: float = Field(..., description="未实现盈亏 Unrealized PNL")

    # 额外统计字段
    total_initial_margin: float = Field(..., description="总初始保证金（已投资金额）")
    unrealized_pnl_percentage: float = Field(..., description="未实现盈亏百分比")
    daily_pnl: float = Field(..., description="当日盈亏")
    daily_pnl_percentage: float = Field(..., description="当日盈亏百分比")

    positions: List["PositionResponse"] = Field(..., description="持仓列表")
    updated_at: str = Field(..., description="更新时间")

    # 兼容旧字段（前端迁移期间）
    @property
    def total_value(self) -> float:
        """兼容：total_value = wallet_balance"""
        return self.wallet_balance

    @property
    def cash(self) -> float:
        """兼容：cash = available_balance"""
        return self.available_balance

    @property
    def invested(self) -> float:
        """兼容：invested = total_initial_margin"""
        return self.total_initial_margin


class PositionResponse(BaseModel):
    """持仓响应"""
    symbol: str = Field(..., description="交易对")
    side: str = Field(..., description="方向: BUY/SELL")
    amount: float = Field(..., description="数量")
    entry_price: float = Field(..., description="入场价格")
    current_price: float = Field(..., description="当前价格")
    average_price: float = Field(..., description="平均价格")
    unrealized_pnl: float = Field(..., description="未实现盈亏")
    unrealized_pnl_percentage: float = Field(..., description="未实现盈亏百分比")
    value: float = Field(..., description="持仓价值")
    cost: float = Field(..., description="持仓成本")
    stop_loss: float | None = Field(None, description="止损价格")
    take_profit: float | None = Field(None, description="止盈价格")


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


# ===== Mock数据生成器 (临时) =====

def create_mock_portfolio() -> PortfolioResponse:
    """创建模拟投资组合数据"""
    positions = [
        PositionResponse(
            symbol="BTC/USDT",
            side="BUY",
            amount=0.5,
            entry_price=45000.0,
            current_price=46500.0,
            average_price=45000.0,
            unrealized_pnl=750.0,
            unrealized_pnl_percentage=3.33,
            value=23250.0,
            cost=22500.0,
        ),
        PositionResponse(
            symbol="ETH/USDT",
            side="BUY",
            amount=5.0,
            entry_price=2500.0,
            current_price=2600.0,
            average_price=2500.0,
            unrealized_pnl=500.0,
            unrealized_pnl_percentage=4.0,
            value=13000.0,
            cost=12500.0,
        ),
    ]

    total_invested = sum(p.cost for p in positions)
    unrealized_pnl = sum(p.unrealized_pnl for p in positions)
    available_balance = 15000.0  # 可用保证金
    margin_balance = total_invested  # 持仓占用的保证金
    wallet_balance = available_balance + margin_balance + unrealized_pnl

    return PortfolioResponse(
        wallet_balance=wallet_balance,
        available_balance=available_balance,
        margin_balance=margin_balance,
        unrealized_pnl=unrealized_pnl,
        total_initial_margin=total_invested,
        unrealized_pnl_percentage=(unrealized_pnl / total_invested * 100) if total_invested > 0 else 0,
        daily_pnl=320.5,
        daily_pnl_percentage=0.64,
        positions=positions,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def create_mock_positions() -> List[PositionResponse]:
    """创建模拟持仓列表"""
    positions = create_mock_portfolio().positions
    # 添加止损止盈数据
    positions[0].stop_loss = 44000.0
    positions[0].take_profit = 48000.0
    positions[1].stop_loss = 2400.0
    positions[1].take_profit = 2800.0
    return positions


def convert_db_position_to_response(db_position) -> PositionResponse:
    """
    将数据库PositionModel转换为API响应

    数据库字段映射:
    - side: sell/buy -> SELL/BUY (转大写)
    - 其他字段基本一致
    """
    # 转换side: sell -> SELL, buy -> BUY
    side = db_position.side.upper()

    # 计算平均价格（如果没有，使用entry_price）
    average_price = float(db_position.entry_price)

    # 计算成本
    cost = float(db_position.entry_price * db_position.amount)

    return PositionResponse(
        symbol=db_position.symbol,
        side=side,
        amount=float(db_position.amount),
        entry_price=float(db_position.entry_price),
        current_price=float(db_position.current_price),
        average_price=average_price,
        unrealized_pnl=float(db_position.unrealized_pnl),
        unrealized_pnl_percentage=float(db_position.unrealized_pnl_percentage),
        value=float(db_position.value),
        cost=cost,
        stop_loss=float(db_position.stop_loss) if db_position.stop_loss else None,
        take_profit=float(db_position.take_profit) if db_position.take_profit else None,
    )


# ===== API端点 =====

@router.get("/portfolio", response_model=PortfolioResponse)
async def get_portfolio():
    """
    获取投资组合

    返回当前的投资组合信息，包括总价值、现金、持仓列表等
    """
    logger.info("API: 获取投资组合")

    try:
        from src.api.server import get_app_state
        from src.database.dao import TradingDAO

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            logger.warning("Database not initialized, returning mock data")
            return create_mock_portfolio()

        # 从数据库获取数据（不直接调交易所API，避免频繁请求）
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)
            positions = await dao.get_open_positions()

            # 将数据库持仓转换为响应格式
            position_responses = [convert_db_position_to_response(p) for p in positions]

            # 获取最新快照的余额数据
            snapshots = await dao.get_portfolio_snapshots(limit=1)
            if not snapshots:
                # 没有快照数据，返回空
                raise HTTPException(status_code=404, detail="No portfolio snapshot found")

            snapshot = snapshots[0]

            # 只使用新字段，没有就报错
            if not snapshot.wallet_balance:
                raise HTTPException(status_code=500, detail="Portfolio snapshot missing wallet_balance field")

            # 计算投资组合统计数据
            total_invested = sum(p.cost for p in position_responses)
            unrealized_pnl = sum(p.unrealized_pnl for p in position_responses)

            return PortfolioResponse(
                wallet_balance=float(snapshot.wallet_balance),
                available_balance=float(snapshot.available_balance),
                margin_balance=float(snapshot.margin_balance),
                unrealized_pnl=unrealized_pnl,
                total_initial_margin=total_invested,
                unrealized_pnl_percentage=(unrealized_pnl / total_invested * 100) if total_invested > 0 else 0,
                daily_pnl=unrealized_pnl,
                daily_pnl_percentage=(unrealized_pnl / float(snapshot.wallet_balance) * 100) if snapshot.wallet_balance > 0 else 0,
                positions=position_responses,
                updated_at=snapshot.datetime.replace(tzinfo=timezone.utc).isoformat() if snapshot.datetime.tzinfo is None else snapshot.datetime.isoformat(),
            )

    except Exception as e:
        logger.error(f"获取投资组合失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio/positions", response_model=List[PositionResponse])
async def get_positions():
    """
    获取所有持仓

    返回当前所有持仓的列表
    """
    logger.info("API: 获取持仓列表")

    try:
        from src.api.server import get_app_state
        from src.database.dao import TradingDAO

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            logger.warning("Database not initialized, returning mock data")
            return create_mock_positions()

        # 从数据库获取真实数据
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)
            positions = await dao.get_open_positions()
            return [convert_db_position_to_response(p) for p in positions]

    except Exception as e:
        logger.error(f"获取持仓列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio/positions/{symbol}", response_model=PositionResponse)
async def get_position(symbol: str):
    """
    获取单个持仓

    返回指定交易对的持仓信息
    """
    logger.info(f"API: 获取持仓 {symbol}")

    try:
        from src.api.server import get_app_state
        from src.database.dao import TradingDAO

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            logger.warning("Database not initialized, returning mock data")
            positions = create_mock_positions()
            for pos in positions:
                if pos.symbol == symbol or pos.symbol.replace("/", "") == symbol.replace("/", ""):
                    return pos
            raise HTTPException(status_code=404, detail=f"Position not found: {symbol}")

        # 从数据库获取真实数据
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)
            positions = await dao.get_open_positions()

            # 查找匹配的持仓
            for pos in positions:
                if pos.symbol == symbol or pos.symbol.replace("/", "").replace(":", "") == symbol.replace("/", "").replace(":", ""):
                    return convert_db_position_to_response(pos)

            raise HTTPException(status_code=404, detail=f"Position not found: {symbol}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取持仓失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


# ===== 辅助函数 (未来使用) =====

def convert_portfolio_to_response(portfolio: Portfolio) -> PortfolioResponse:
    """将Portfolio模型转换为API响应"""
    positions = [convert_position_to_response(p) for p in portfolio.positions]
    total_invested = sum(p.cost for p in positions)

    return PortfolioResponse(
        wallet_balance=float(portfolio.wallet_balance),
        available_balance=float(portfolio.available_balance),
        margin_balance=float(portfolio.margin_balance),
        unrealized_pnl=float(portfolio.unrealized_pnl),
        total_initial_margin=total_invested,
        unrealized_pnl_percentage=float(portfolio.total_return),
        daily_pnl=float(portfolio.daily_pnl),
        daily_pnl_percentage=0.0,  # TODO: 计算
        positions=positions,
        updated_at=portfolio.dt.replace(tzinfo=timezone.utc).isoformat() if portfolio.dt.tzinfo is None else portfolio.dt.isoformat(),
    )


def convert_position_to_response(position: Position) -> PositionResponse:
    """将Position模型转换为API响应"""
    cost = float(position.entry_price * position.amount)
    pnl_pct = float(position.unrealized_pnl_percentage) if position.unrealized_pnl_percentage else 0.0

    return PositionResponse(
        symbol=position.symbol,
        side=position.side.value,
        amount=float(position.amount),
        entry_price=float(position.entry_price),
        current_price=float(position.current_price),
        average_price=float(position.entry_price),  # 简化处理
        unrealized_pnl=float(position.unrealized_pnl),
        unrealized_pnl_percentage=pnl_pct,
        value=float(position.value),
        cost=cost,
    )
