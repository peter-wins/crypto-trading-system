"""
账户设置API路由
"""

from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ===== 请求/响应模型 =====

class InitialCapitalRequest(BaseModel):
    """设置初始资金请求"""
    initial_capital: float = Field(..., gt=0, description="初始资金（USDT）")
    notes: Optional[str] = Field(None, description="备注信息")


class InitialCapitalResponse(BaseModel):
    """初始资金响应"""
    exchange_id: int
    initial_capital: float
    capital_currency: str
    set_at: str
    notes: Optional[str] = None


# ===== API端点 =====

@router.get("/settings/initial-capital", response_model=InitialCapitalResponse)
async def get_initial_capital():
    """
    获取当前配置的初始资金
    """
    logger.info("API: 获取初始资金配置")

    try:
        from src.api.server import get_app_state
        from sqlalchemy import text

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            raise HTTPException(status_code=500, detail="Database not initialized")

        from src.core.config import get_config
        config = get_config()
        exchange_name = "binanceusdm" if config.binance_futures else (config.data_source_exchange or "binance")

        async with db_manager.get_session() as session:
            # 获取exchange_id
            result = await session.execute(
                text("SELECT id FROM exchanges WHERE name = :name"),
                {"name": exchange_name}
            )
            exchange_row = result.fetchone()

            if not exchange_row:
                raise HTTPException(status_code=404, detail=f"Exchange {exchange_name} not found")

            exchange_id = exchange_row[0]

            # 获取初始资金配置
            result = await session.execute(
                text("""
                    SELECT exchange_id, initial_capital, capital_currency, set_at, notes
                    FROM account_settings
                    WHERE exchange_id = :exchange_id
                """),
                {"exchange_id": exchange_id}
            )
            row = result.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Initial capital not configured")

            return InitialCapitalResponse(
                exchange_id=row[0],
                initial_capital=float(row[1]),
                capital_currency=row[2],
                set_at=row[3].isoformat() if isinstance(row[3], datetime) else str(row[3]),
                notes=row[4]
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取初始资金配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/initial-capital", response_model=InitialCapitalResponse)
async def set_initial_capital(request: InitialCapitalRequest):
    """
    设置初始资金

    注意：
    - 初始资金应该是开始交易前的账户余额
    - 修改初始资金会影响所有累计收益率的计算
    - 建议只在系统初始化时设置一次
    """
    logger.info(f"API: 设置初始资金 = {request.initial_capital}")

    try:
        from src.api.server import get_app_state
        from sqlalchemy import text

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            raise HTTPException(status_code=500, detail="Database not initialized")

        from src.core.config import get_config
        config = get_config()
        exchange_name = "binanceusdm" if config.binance_futures else (config.data_source_exchange or "binance")

        async with db_manager.get_session() as session:
            # 获取exchange_id
            result = await session.execute(
                text("SELECT id FROM exchanges WHERE name = :name"),
                {"name": exchange_name}
            )
            exchange_row = result.fetchone()

            if not exchange_row:
                raise HTTPException(status_code=404, detail=f"Exchange {exchange_name} not found")

            exchange_id = exchange_row[0]

            # 插入或更新初始资金
            await session.execute(
                text("""
                    INSERT INTO account_settings (exchange_id, initial_capital, capital_currency, notes)
                    VALUES (:exchange_id, :initial_capital, 'USDT', :notes)
                    ON CONFLICT (exchange_id)
                    DO UPDATE SET
                        initial_capital = EXCLUDED.initial_capital,
                        set_at = NOW() AT TIME ZONE 'UTC',
                        notes = EXCLUDED.notes
                """),
                {
                    "exchange_id": exchange_id,
                    "initial_capital": request.initial_capital,
                    "notes": request.notes
                }
            )
            await session.commit()

            # 返回最新配置
            result = await session.execute(
                text("""
                    SELECT exchange_id, initial_capital, capital_currency, set_at, notes
                    FROM account_settings
                    WHERE exchange_id = :exchange_id
                """),
                {"exchange_id": exchange_id}
            )
            row = result.fetchone()

            return InitialCapitalResponse(
                exchange_id=row[0],
                initial_capital=float(row[1]),
                capital_currency=row[2],
                set_at=row[3].isoformat() if isinstance(row[3], datetime) else str(row[3]),
                notes=row[4]
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置初始资金失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/settings/initial-capital")
async def delete_initial_capital():
    """
    删除初始资金配置

    删除后系统将使用最早的快照作为初始值
    """
    logger.info("API: 删除初始资金配置")

    try:
        from src.api.server import get_app_state
        from sqlalchemy import text

        app_state = get_app_state()
        db_manager = app_state.get("db_manager")

        if not db_manager:
            raise HTTPException(status_code=500, detail="Database not initialized")

        from src.core.config import get_config
        config = get_config()
        exchange_name = "binanceusdm" if config.binance_futures else (config.data_source_exchange or "binance")

        async with db_manager.get_session() as session:
            # 获取exchange_id
            result = await session.execute(
                text("SELECT id FROM exchanges WHERE name = :name"),
                {"name": exchange_name}
            )
            exchange_row = result.fetchone()

            if not exchange_row:
                raise HTTPException(status_code=404, detail=f"Exchange {exchange_name} not found")

            exchange_id = exchange_row[0]

            # 删除配置
            await session.execute(
                text("DELETE FROM account_settings WHERE exchange_id = :exchange_id"),
                {"exchange_id": exchange_id}
            )
            await session.commit()

            return {"message": "Initial capital configuration deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除初始资金配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
