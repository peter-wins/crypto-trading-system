"""
账户同步 API 路由

提供实时账户数据，包括余额、持仓和同步状态
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ===== 响应模型 =====

class AccountSnapshotResponse(BaseModel):
    """账户快照响应"""
    timestamp: str = Field(..., description="快照时间")
    total_balance: float = Field(..., description="总余额 (USDT)")
    available_balance: float = Field(..., description="可用余额 (USDT)")
    used_margin: float = Field(..., description="已用保证金 (USDT)")
    unrealized_pnl: float = Field(..., description="未实现盈亏 (USDT)")
    position_count: int = Field(..., description="持仓数量")
    total_position_value: float = Field(..., description="总持仓价值 (USDT)")


class PositionInfoResponse(BaseModel):
    """持仓信息响应"""
    symbol: str = Field(..., description="交易对")
    side: str = Field(..., description="方向: buy/sell")
    amount: float = Field(..., description="数量")
    entry_price: float = Field(..., description="入场价格")
    current_price: float = Field(..., description="当前价格")
    unrealized_pnl: float = Field(..., description="未实现盈亏")
    leverage: Optional[int] = Field(None, description="杠杆倍数")
    margin: float = Field(..., description="保证金")
    liquidation_price: Optional[float] = Field(None, description="强平价格")


class SyncStatsResponse(BaseModel):
    """同步服务统计响应"""
    sync_count: int = Field(..., description="同步次数")
    error_count: int = Field(..., description="错误次数")
    last_sync_time: Optional[str] = Field(None, description="最后同步时间")
    is_running: bool = Field(..., description="是否运行中")
    sync_interval: int = Field(..., description="同步间隔(秒)")


# ===== API端点 =====

@router.get("/account/snapshot", response_model=AccountSnapshotResponse)
async def get_account_snapshot():
    """
    获取最新的账户快照

    从数据库读取最新快照（已由 AccountSyncService 每 10 秒自动同步）
    """
    logger.info("API: 获取账户快照")

    try:
        from src.api.server import get_app_state
        from src.services.database import TradingDAO

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            raise HTTPException(
                status_code=503,
                detail="Database not available"
            )

        # 从数据库查询最新快照（由 AccountSyncService 自动同步）
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)

            # 获取最新的投资组合快照
            from src.core.config import get_config

            config = get_config()
            exchange_name = "binanceusdm" if config.binance_futures else (config.data_source_exchange or "binance")

            snapshots = await dao.get_portfolio_snapshots(
                limit=1,
                exchange_name=exchange_name,
            )
            if not snapshots:
                raise HTTPException(
                    status_code=404,
                    detail="No account snapshot found. Service may be starting up."
                )

            snapshot = snapshots[0]

            # 获取当前持仓
            positions = await dao.get_open_positions(exchange_name=exchange_name)

            # 计算汇总数据
            total_unrealized_pnl = sum(float(p.unrealized_pnl or 0) for p in positions)
            total_position_value = sum(float(p.value or 0) for p in positions)

            return AccountSnapshotResponse(
                timestamp=snapshot.datetime.isoformat(),
                total_balance=float(snapshot.wallet_balance or 0),
                available_balance=float(snapshot.available_balance or 0),
                used_margin=float(snapshot.margin_balance or 0),
                unrealized_pnl=total_unrealized_pnl,
                position_count=len(positions),
                total_position_value=total_position_value,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取账户快照失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/account/positions", response_model=List[PositionInfoResponse])
async def get_account_positions():
    """
    获取账户中的持仓列表

    从数据库读取持仓数据（已由 AccountSyncService 每 10 秒自动同步）
    """
    logger.info("API: 获取账户持仓")

    try:
        from src.api.server import get_app_state
        from src.services.database import TradingDAO

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            raise HTTPException(
                status_code=503,
                detail="Database not available"
            )

        from src.core.config import get_config
        config = get_config()
        exchange_name = "binanceusdm" if config.binance_futures else (config.data_source_exchange or "binance")

        # 从数据库查询持仓（由 AccountSyncService 自动同步）
        async with db_manager.get_session() as session:
            dao = TradingDAO(session)
            db_positions = await dao.get_open_positions(exchange_name=exchange_name)

            positions = []
            for pos in db_positions:
                # 计算保证金 = 仓位价值 / 杠杆
                margin = float(pos.value) / pos.leverage if pos.leverage and pos.leverage > 0 else float(pos.value)

                positions.append(PositionInfoResponse(
                    symbol=pos.symbol,
                    side=pos.side,
                    amount=float(pos.amount),
                    entry_price=float(pos.entry_price),
                    current_price=float(pos.current_price),
                    unrealized_pnl=float(pos.unrealized_pnl or 0),
                    leverage=pos.leverage,
                    margin=margin,
                    liquidation_price=float(pos.liquidation_price) if pos.liquidation_price else None,
                ))

            return positions

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取账户持仓失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/account/sync")
async def force_account_sync():
    """
    强制立即同步账户数据（慎用）

    触发一次立即同步，会调用交易所 API。
    通常不需要手动调用，因为服务已每 10 秒自动同步。
    """
    logger.info("API: 强制同步账户 (会调用交易所 API)")

    try:
        from src.api.server import get_app_state
        from src.services.database import TradingDAO

        app_state = get_app_state()
        coordinator = app_state.get("coordinator")
        db_manager = app_state.get("db_manager")

        if not coordinator or not coordinator.account_sync_service:
            raise HTTPException(
                status_code=503,
                detail="Account sync service not available. Enable real trading mode to use this feature."
            )

        # 强制同步（会调用交易所 API）
        snapshot = await coordinator.account_sync_service.force_sync()

        return AccountSnapshotResponse(
            timestamp=snapshot.timestamp.isoformat(),
            total_balance=float(snapshot.total_balance),
            available_balance=float(snapshot.available_balance),
            used_margin=float(snapshot.used_margin),
            unrealized_pnl=float(snapshot.unrealized_pnl),
            position_count=snapshot.position_count,
            total_position_value=float(snapshot.total_position_value),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"强制同步失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/account/stats", response_model=SyncStatsResponse)
async def get_sync_stats():
    """
    获取账户同步服务的统计信息

    返回同步次数、错误次数、运行状态等
    """
    logger.info("API: 获取同步统计")

    try:
        from src.api.server import get_app_state

        app_state = get_app_state()
        coordinator = app_state.get("coordinator")

        if not coordinator or not coordinator.account_sync_service:
            raise HTTPException(
                status_code=503,
                detail="Account sync service not available"
            )

        stats = coordinator.account_sync_service.get_stats()

        return SyncStatsResponse(
            sync_count=stats['sync_count'],
            error_count=stats['error_count'],
            last_sync_time=stats['last_sync_time'],
            is_running=stats['is_running'],
            sync_interval=stats['sync_interval'],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取同步统计失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
