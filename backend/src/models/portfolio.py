"""
投资组合模型

本模块定义账户余额、投资组合等相关的Pydantic模型。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict

from .trade import Position, OrderSide


class Balance(BaseModel):
    """账户余额"""

    model_config = ConfigDict(json_encoders={Decimal: str})

    currency: str = Field(..., description="币种")
    free: Decimal = Field(..., description="可用余额")
    used: Decimal = Field(..., description="冻结余额")
    total: Decimal = Field(..., description="总余额")


class AccountBalance(BaseModel):
    """完整账户余额"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    exchange: str = Field(..., description="交易所")
    timestamp: int = Field(..., description="时间戳(毫秒)")
    dt: datetime = Field(..., description="时间")
    balances: dict[str, Balance] = Field(..., description="各币种余额")
    total_value_usd: Decimal = Field(..., description="总价值(USD)")


class Portfolio(BaseModel):
    """投资组合"""

    model_config = ConfigDict(
        json_encoders={
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    )

    timestamp: int = Field(..., description="时间戳(毫秒)")
    dt: datetime = Field(..., description="时间")

    # 余额字段（与币安命名对齐）
    wallet_balance: Decimal = Field(..., description="钱包余额 Wallet Balance（总资金）")
    available_balance: Decimal = Field(..., description="可用保证金 Available Balance")
    margin_balance: Decimal = Field(Decimal("0"), description="保证金余额 Margin Balance（持仓占用）")

    positions: List[Position] = Field(default_factory=list, description="持仓列表")

    # 绩效指标
    unrealized_pnl: Decimal = Field(Decimal("0"), description="未实现盈亏 Unrealized PNL")
    daily_pnl: Decimal = Field(Decimal("0"), description="当日盈亏")
    total_return: Decimal = Field(Decimal("0"), description="总收益率(%)")

    # 兼容旧字段（逐步废弃）
    @property
    def total_value(self) -> Decimal:
        """兼容旧代码：total_value = wallet_balance"""
        return self.wallet_balance

    @property
    def cash(self) -> Decimal:
        """兼容旧代码：cash = available_balance"""
        return self.available_balance

    @property
    def total_pnl(self) -> Decimal:
        """兼容旧代码：total_pnl = unrealized_pnl"""
        return self.unrealized_pnl

    def get_position(
        self,
        symbol: str,
        side: Optional[OrderSide] = None,
    ) -> Optional[Position]:
        """
        获取指定持仓

        Args:
            symbol: 交易对符号（支持带或不带合约后缀，如 BTC/USDT 或 BTC/USDT:USDT）
            side: 可选，限定持仓方向（多/空）

        Returns:
            持仓信息，如果不存在则返回None
        """
        # 标准化symbol格式：去掉合约后缀（如 :USDT）
        normalized_symbol = self._normalize_symbol(symbol)

        candidates = [
            pos for pos in self.positions
            if self._normalize_symbol(pos.symbol) == normalized_symbol
        ]

        if side:
            for pos in candidates:
                if pos.side == side:
                    return pos

        return candidates[0] if candidates else None

    def get_positions(
        self,
        symbol: str,
    ) -> List[Position]:
        """返回指定symbol的全部持仓（用于双向持仓场景）"""
        normalized_symbol = self._normalize_symbol(symbol)
        return [
            pos for pos in self.positions
            if self._normalize_symbol(pos.symbol) == normalized_symbol
        ]

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """
        标准化交易对符号，统一去掉合约后缀

        Examples:
            BTC/USDT:USDT -> BTC/USDT
            BTC/USDT -> BTC/USDT
            ETH/USDT:USDT -> ETH/USDT
        """
        if ':' in symbol:
            return symbol.split(':')[0]
        return symbol

    def to_snapshot_portfolio(self) -> "Portfolio":
        """生成用于快照保存的 Portfolio 副本"""
        return Portfolio(
            timestamp=self.timestamp,
            dt=self.dt,
            wallet_balance=self.wallet_balance,
            available_balance=self.available_balance,
            margin_balance=self.margin_balance,
            positions=self.positions.copy(),
            unrealized_pnl=self.unrealized_pnl,
            daily_pnl=self.daily_pnl,
            total_return=self.total_return,
        )

    def get_allocation(self, symbol: str) -> Decimal:
        """
        获取仓位占比

        Args:
            symbol: 交易对符号

        Returns:
            仓位占比百分比
        """
        pos = self.get_position(symbol)
        if not pos or self.total_value == 0:
            return Decimal("0")
        return (pos.value / self.total_value) * Decimal("100")
