"""
系统事件模型

本模块定义系统事件相关的Pydantic模型。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class EventType(str, Enum):
    """事件类型"""
    MARKET_DATA = "market_data"
    ORDER_CREATED = "order_created"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELED = "order_canceled"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    RISK_ALERT = "risk_alert"
    SYSTEM_ERROR = "system_error"
    DECISION_MADE = "decision_made"
    REFLECTION_COMPLETED = "reflection_completed"


class SystemEvent(BaseModel):
    """系统事件"""

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )

    id: str = Field(..., description="事件ID")
    timestamp: int = Field(..., description="时间戳(毫秒)")
    dt: datetime = Field(..., description="时间")
    event_type: EventType = Field(..., description="事件类型")
    severity: str = Field(..., description="严重程度: info/warning/error/critical")

    # 事件数据
    data: dict = Field(default_factory=dict, description="事件数据")

    # 关联信息
    related_order_id: Optional[str] = Field(None, description="关联订单ID")
    related_symbol: Optional[str] = Field(None, description="关联交易对")

    # 消息
    message: str = Field(..., description="事件消息")
    details: Optional[str] = Field(None, description="详细信息")
