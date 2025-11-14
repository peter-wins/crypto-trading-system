#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动补齐历史平仓记录的辅助脚本

场景:
- 系统停机期间在交易所手动开/平仓，重启后 DB 没有对应的 closed_positions 记录
- 本脚本会拉取指定日期内的交易所成交记录，根据净持仓变化重建“完整仓位”
- 与数据库已有的 closed_positions 对比，插入缺失记录

使用方法:
    cd backend
    python scripts/reconcile_closed_positions.py --date 2025-11-14 --symbols BTC/USDT:USDT ETH/USDT:USDT
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


# 让脚本可以直接引用 src 包
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.core.config import get_config  # pylint: disable=wrong-import-position
from src.core.logger import get_logger, init_logging_from_config  # pylint: disable=wrong-import-position
from src.services.exchange.exchange_service import ExchangeService  # pylint: disable=wrong-import-position
from src.services.database.session import get_db_manager  # pylint: disable=wrong-import-position
from src.services.database.dao import TradingDAO  # pylint: disable=wrong-import-position
from src.services.database.models import ClosedPositionModel  # pylint: disable=wrong-import-position


logger = get_logger(__name__)


@dataclass
class TradeRecord:
    """简化过的成交记录"""

    symbol: str
    side: str  # buy / sell
    amount: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: Optional[str]
    timestamp: int
    dt: datetime
    order_id: Optional[str]
    position_side: str  # LONG / SHORT / BOTH


@dataclass
class ClosedPositionCandidate:
    """根据成交重建出的完整仓位"""

    symbol: str
    position_side: str  # LONG/SHORT
    side: str  # buy for long entries, sell for short entries
    amount: Decimal
    entry_price: Decimal
    exit_price: Decimal
    entry_time: datetime
    exit_time: datetime
    entry_value: Decimal
    exit_value: Decimal
    total_fee: Decimal
    realized_pnl: Decimal
    realized_pnl_pct: Decimal
    entry_fee: Decimal
    exit_fee: Decimal

    def signature(self) -> Tuple[str, str, int, int]:
        """生成用于比对的签名 (symbol, side, amount_in_micro, exit_ts)"""
        amount_micro = int((self.amount * Decimal("1e6")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        exit_ts = int(self.exit_time.timestamp())
        return (self.symbol, self.side, amount_micro, exit_ts)


class PositionRebuilder:
    """根据成交记录重建“净仓位”生命周期"""

    def __init__(self, symbol: str, position_side: str) -> None:
        self.symbol = symbol
        self.position_side = position_side  # LONG/SHORT
        self.entry_side = "buy" if position_side == "LONG" else "sell"
        self.close_side = "sell" if position_side == "LONG" else "buy"
        self.current_amount = Decimal("0")
        self.entry_value = Decimal("0")
        self.entry_amount_total = Decimal("0")
        self.entry_fee = Decimal("0")
        self.entry_time: Optional[datetime] = None
        self.exit_value = Decimal("0")
        self.exit_amount_total = Decimal("0")
        self.exit_fee = Decimal("0")
        self.exit_time: Optional[datetime] = None
        self.completed: List[ClosedPositionCandidate] = []

    def process(self, trade: TradeRecord) -> None:
        """处理单笔成交"""
        amount = trade.amount
        price = trade.price
        fee = trade.fee

        if trade.side == self.entry_side:
            self._handle_entry(amount, price, fee, trade.dt)
        elif trade.side == self.close_side:
            self._handle_exit(amount, price, fee, trade.dt)
        else:
            logger.debug(
                "忽略无法识别的成交方向: %s %s (position_side=%s)",
                trade.symbol,
                trade.side,
                trade.position_side,
            )

    def _handle_entry(self, amount: Decimal, price: Decimal, fee: Decimal, dt: datetime) -> None:
        if self.current_amount == 0:
            # 新仓位
            self.entry_time = dt
            self.exit_time = None
            self.exit_value = Decimal("0")
            self.exit_fee = Decimal("0")

        self.current_amount += amount
        self.entry_value += price * amount
        self.entry_amount_total += amount
        self.entry_fee += fee
        if not self.entry_time or dt < self.entry_time:
            self.entry_time = dt

    def _handle_exit(self, amount: Decimal, price: Decimal, fee: Decimal, dt: datetime) -> None:
        if self.current_amount <= 0:
            # 没有对应的持仓，直接忽略
            logger.warning("检测到没有开仓记录的平仓成交，忽略：%s %s", self.symbol, dt.isoformat())
            return

        self.current_amount -= amount
        if self.current_amount < Decimal("0"):
            logger.warning(
                "成交导致净仓位为负，自动截断: %s amount=%s",
                self.symbol,
                self.current_amount,
            )
            self.current_amount = Decimal("0")

        self.exit_value += price * amount
        self.exit_amount_total += amount
        self.exit_fee += fee
        self.exit_time = dt

        if self.current_amount == 0:
            self._finalize()

    def _finalize(self) -> None:
        """当前仓位归零后生成记录"""
        if not self.entry_time or not self.exit_time:
            return

        entry_amount = self.entry_amount_total
        exit_amount = self.exit_amount_total
        amount = min(entry_amount, exit_amount)

        if amount <= 0:
            self._reset()
            return

        entry_price = (self.entry_value / entry_amount).quantize(Decimal("0.0001"))
        exit_price = (self.exit_value / exit_amount).quantize(Decimal("0.0001"))

        entry_value = entry_price * amount
        exit_value = exit_price * amount

        if self.entry_side == "buy":
            realized_pnl = exit_value - entry_value
        else:
            realized_pnl = entry_value - exit_value

        realized_pct = (
            (realized_pnl / entry_value * Decimal("100")).quantize(Decimal("0.0001"))
            if entry_value != 0
            else Decimal("0")
        )

        candidate = ClosedPositionCandidate(
            symbol=self.symbol,
            position_side=self.position_side,
            side="buy" if self.entry_side == "buy" else "sell",
            amount=amount.quantize(Decimal("0.0001")),
            entry_price=entry_price,
            exit_price=exit_price,
            entry_time=self.entry_time.replace(tzinfo=None),
            exit_time=self.exit_time.replace(tzinfo=None),
            entry_value=entry_value,
            exit_value=exit_value,
            total_fee=(self.entry_fee + self.exit_fee),
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pct,
            entry_fee=self.entry_fee,
            exit_fee=self.exit_fee,
        )

        self.completed.append(candidate)
        self._reset()

    def _reset(self) -> None:
        self.current_amount = Decimal("0")
        self.entry_value = Decimal("0")
        self.entry_amount_total = Decimal("0")
        self.exit_value = Decimal("0")
        self.exit_amount_total = Decimal("0")
        self.entry_fee = Decimal("0")
        self.exit_fee = Decimal("0")
        self.entry_time = None
        self.exit_time = None


def normalize_symbol_for_exchange(symbol: str) -> str:
    """期货内部使用 BTC/USDT:USDT，交易所只认 BTC/USDT"""
    return symbol.split(":")[0]


def parse_trade(raw: dict) -> TradeRecord:
    """把 ccxt trade 转成内部结构"""
    dt = datetime.fromisoformat(raw["datetime"].replace("Z", "+00:00"))
    fee_cost = Decimal(str(raw.get("fee", {}).get("cost", "0")))
    fee_currency = raw.get("fee", {}).get("currency")
    position_side = raw.get("info", {}).get("positionSide", "BOTH").upper()
    return TradeRecord(
        symbol=raw["symbol"],
        side=raw["side"],
        amount=Decimal(str(raw["amount"])),
        price=Decimal(str(raw["price"])),
        fee=fee_cost,
        fee_currency=fee_currency,
        timestamp=raw["timestamp"],
        dt=dt,
        order_id=raw.get("order"),
        position_side=position_side,
    )


async def fetch_trades_for_date(
    exchange: ExchangeService,
    symbol: str,
    day: date,
) -> List[TradeRecord]:
    """拉取某日期的成交记录"""
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    since = int(start.timestamp() * 1000)

    market_symbol = normalize_symbol_for_exchange(symbol)
    raw_trades = await exchange.fetch_my_trades(market_symbol, since=since, limit=1000)
    if not raw_trades:
        return []

    trades = []
    for item in raw_trades:
        trade = parse_trade(item)
        if start <= trade.dt.astimezone(timezone.utc) < end:
            trades.append(trade)

    # 以 timestamp 排序，确保按时间重建
    trades.sort(key=lambda t: t.timestamp)
    return trades


def build_candidates(symbol: str, trades: Sequence[TradeRecord]) -> List[ClosedPositionCandidate]:
    """从成交记录重建可能缺失的平仓事件"""
    long_builder = PositionRebuilder(symbol, "LONG")
    short_builder = PositionRebuilder(symbol, "SHORT")

    for trade in trades:
        position_side = trade.position_side
        if position_side == "SHORT":
            short_builder.process(trade)
        else:
            # 如果交易所返回 BOTH，我们默认按照 LONG 处理（即多头）
            long_builder.process(trade)

    return long_builder.completed + short_builder.completed


async def load_db_closed_positions(
    dao: TradingDAO,
    symbol: str,
    day: date,
    exchange_name: str,
) -> List[ClosedPositionModel]:
    """加载数据库里某日的 closed_positions"""
    records = await dao.get_closed_positions(
        symbol=symbol,
        start_date=day,
        end_date=day,
        exchange_name=exchange_name,
    )
    return records


def is_duplicate(candidate: ClosedPositionCandidate, existing: Iterable[ClosedPositionModel]) -> bool:
    """判断候选是否已经存在于数据库"""
    for record in existing:
        if record.symbol != candidate.symbol:
            continue
        if record.side != candidate.side:
            continue
        if abs(Decimal(record.amount) - candidate.amount) > Decimal("1e-6"):
            continue
        if record.exit_time and abs((record.exit_time - candidate.exit_time).total_seconds()) > 5:
            continue
        return True
    return False


async def insert_candidate(
    dao: TradingDAO,
    candidate: ClosedPositionCandidate,
    exchange_name: str,
) -> ClosedPositionModel:
    """把缺失的仓位写入数据库"""
    exchange_id = await dao._get_or_create_exchange_id(exchange_name)  # pylint: disable=protected-access

    model = ClosedPositionModel(
        exchange_id=exchange_id,
        symbol=candidate.symbol,
        side=candidate.side,
        entry_order_id=None,
        entry_price=candidate.entry_price,
        entry_time=candidate.entry_time,
        exit_order_id=None,
        exit_price=candidate.exit_price,
        exit_time=candidate.exit_time,
        amount=candidate.amount,
        entry_value=candidate.entry_value,
        exit_value=candidate.exit_value,
        realized_pnl=candidate.realized_pnl,
        realized_pnl_percentage=candidate.realized_pnl_pct,
        total_fee=candidate.total_fee,
        fee_currency="USDT",
        close_reason="manual",
        holding_duration_seconds=int(
            (candidate.exit_time - candidate.entry_time).total_seconds()
        ),
        leverage=None,
        created_at=datetime.utcnow(),
    )

    dao.session.add(model)
    await dao.session.flush()
    logger.info(
        "已补录平仓: %s %s amount=%s entry=%.4f exit=%.4f pnl=%.4f",
        candidate.symbol,
        candidate.side,
        candidate.amount,
        candidate.entry_price,
        candidate.exit_price,
        candidate.realized_pnl,
    )
    return model


async def reconcile(day: date, symbols: Sequence[str], exchange_name: str) -> None:
    """主逻辑"""
    init_logging_from_config()
    config = get_config()
    db_manager = get_db_manager(config.database_url)
    exchange_service = ExchangeService()

    async with db_manager.get_session() as session:
        dao = TradingDAO(session, default_exchange_name=exchange_name)

        for symbol in symbols:
            trades = await fetch_trades_for_date(exchange_service, symbol, day)
            if not trades:
                logger.info("日期 %s 没有交易记录: %s", day.isoformat(), symbol)
                continue

            candidates = build_candidates(symbol, trades)
            if not candidates:
                logger.info("未发现可重建的完整仓位: %s", symbol)
                continue

            existing = await load_db_closed_positions(dao, symbol, day, exchange_name)

            for candidate in candidates:
                if is_duplicate(candidate, existing):
                    continue
                await insert_candidate(dao, candidate, exchange_name)

        await session.commit()

    await exchange_service.close()
    await db_manager.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="同步交易所历史仓位到数据库")
    parser.add_argument(
        "--date",
        dest="date",
        required=True,
        help="目标日期 (YYYY-MM-DD, UTC)",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        required=True,
        help="需要对齐的永续合约列表，例如: BTC/USDT:USDT ETH/USDT:USDT",
    )
    parser.add_argument(
        "--exchange",
        default="binanceusdm",
        help="数据库里的交易所名称，默认 binanceusdm",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    asyncio.run(reconcile(target_date, args.symbols, args.exchange))
