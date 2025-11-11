"""
Symbol Mapping Service

负责在不同交易所之间转换交易对符号格式。
支持灵活配置、验证和缓存。
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Set
from dataclasses import dataclass

from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SymbolFormat:
    """交易所的符号格式规范"""

    exchange_id: str
    # 基础货币和计价货币的分隔符
    separator: str = "/"
    # 是否需要结算货币后缀（如 :USDC）
    has_settlement_suffix: bool = False
    # 常用的计价货币替换规则 {源币种: 目标币种}
    quote_currency_map: Dict[str, str] = None
    # 是否支持永续合约
    supports_perpetual: bool = True

    def __post_init__(self):
        if self.quote_currency_map is None:
            self.quote_currency_map = {}


# 预定义的交易所格式
EXCHANGE_FORMATS = {
    "hyperliquid": SymbolFormat(
        exchange_id="hyperliquid",
        separator="/",
        has_settlement_suffix=True,  # BTC/USDC:USDC
        quote_currency_map={},
        supports_perpetual=True,
    ),
    "binance": SymbolFormat(
        exchange_id="binance",
        separator="/",
        has_settlement_suffix=False,  # BTC/USDT
        quote_currency_map={"USDC": "USDT"},  # 币安主要用 USDT
        supports_perpetual=False,
    ),
    "binanceusdm": SymbolFormat(
        exchange_id="binanceusdm",
        separator="/",
        has_settlement_suffix=False,  # BTC/USDT
        quote_currency_map={"USDC": "USDT"},
        supports_perpetual=True,
    ),
    "okx": SymbolFormat(
        exchange_id="okx",
        separator="/",
        has_settlement_suffix=True,  # BTC/USDT:USDT
        quote_currency_map={"USDC": "USDT"},
        supports_perpetual=True,
    ),
    "bybit": SymbolFormat(
        exchange_id="bybit",
        separator="/",
        has_settlement_suffix=True,  # BTC/USDT:USDT
        quote_currency_map={"USDC": "USDT"},
        supports_perpetual=True,
    ),
}


class SymbolMapper:
    """
    符号映射器

    负责在不同交易所之间转换交易对符号。
    支持自动格式检测、规则配置和映射验证。

    Example:
        mapper = SymbolMapper("hyperliquid", "binanceusdm")

        # 自动映射
        binance_symbol = mapper.map("BTC/USDC:USDC")  # → "BTC/USDT"

        # 批量映射
        mapping = mapper.build_mapping(["BTC/USDC:USDC", "ETH/USDC:USDC"])
    """

    def __init__(
        self,
        source_exchange: str,
        target_exchange: str,
        *,
        custom_rules: Optional[Dict[str, str]] = None,
        validate_symbols: bool = False,
    ):
        """
        Args:
            source_exchange: 数据源交易所 ID
            target_exchange: 目标交易所 ID
            custom_rules: 自定义映射规则 {源符号: 目标符号}
            validate_symbols: 是否验证符号有效性（需要交易所连接）
        """
        self.source_exchange = source_exchange.lower()
        self.target_exchange = target_exchange.lower()
        self.custom_rules = custom_rules or {}
        self.validate_symbols = validate_symbols

        # 加载交易所格式
        self.source_format = EXCHANGE_FORMATS.get(self.source_exchange)
        self.target_format = EXCHANGE_FORMATS.get(self.target_exchange)

        if not self.source_format:
            logger.warning(f"未知的数据源交易所: {self.source_exchange}，使用默认格式")
            self.source_format = SymbolFormat(exchange_id=self.source_exchange)

        if not self.target_format:
            logger.warning(f"未知的目标交易所: {self.target_exchange}，使用默认格式")
            self.target_format = SymbolFormat(exchange_id=self.target_exchange)

        # 缓存已映射的符号
        self._cache: Dict[str, str] = {}

    def map(self, symbol: str) -> str:
        """
        将单个符号从源交易所格式映射到目标交易所格式

        Args:
            symbol: 源交易所的交易对符号

        Returns:
            目标交易所的交易对符号
        """
        # 检查缓存
        if symbol in self._cache:
            return self._cache[symbol]

        # 检查自定义规则
        if symbol in self.custom_rules:
            mapped = self.custom_rules[symbol]
            self._cache[symbol] = mapped
            return mapped

        # 如果交易所相同，直接返回
        if self.source_exchange == self.target_exchange:
            self._cache[symbol] = symbol
            return symbol

        # 执行自动映射
        try:
            mapped = self._auto_map(symbol)
            self._cache[symbol] = mapped
            return mapped
        except Exception as exc:
            logger.error(f"符号映射失败: {symbol} ({self.source_exchange} → {self.target_exchange}): {exc}")
            # 映射失败时返回原符号
            return symbol

    def _auto_map(self, symbol: str) -> str:
        """
        自动映射符号（基于交易所格式规范）

        解析步骤:
        1. 解析源符号: BTC/USDC:USDC → base=BTC, quote=USDC, settlement=USDC
        2. 应用计价货币映射: USDC → USDT
        3. 根据目标格式重组: BTC/USDT 或 BTC/USDT:USDT
        """
        # 解析源符号
        base, quote, settlement = self._parse_symbol(symbol, self.source_format)

        # 应用计价货币映射规则
        if quote in self.target_format.quote_currency_map:
            original_quote = quote
            quote = self.target_format.quote_currency_map[quote]
            logger.debug(f"应用计价货币映射: {original_quote} → {quote}")

        # 如果有结算货币，也需要映射
        if settlement and settlement in self.target_format.quote_currency_map:
            settlement = self.target_format.quote_currency_map[settlement]

        # 重组为目标格式
        mapped = self._format_symbol(base, quote, settlement, self.target_format)

        logger.debug(f"符号映射: {symbol} → {mapped}")
        return mapped

    def _parse_symbol(self, symbol: str, fmt: SymbolFormat) -> tuple[str, str, Optional[str]]:
        """
        解析交易对符号

        Returns:
            (base_currency, quote_currency, settlement_currency)

        Examples:
            "BTC/USDC:USDC" → ("BTC", "USDC", "USDC")
            "BTC/USDT" → ("BTC", "USDT", None)
        """
        # 检查是否有结算货币后缀
        if ":" in symbol:
            pair, settlement = symbol.split(":", 1)
        else:
            pair = symbol
            settlement = None

        # 分离基础货币和计价货币
        if fmt.separator in pair:
            base, quote = pair.split(fmt.separator, 1)
        else:
            # 尝试自动分离（如 BTCUSDT → BTC/USDT）
            base, quote = self._split_concatenated_pair(pair)

        return base, quote, settlement

    def _split_concatenated_pair(self, pair: str) -> tuple[str, str]:
        """
        分离连写的交易对 (如 BTCUSDT → BTC, USDT)

        使用启发式规则：常见的计价货币
        """
        common_quotes = ["USDT", "USDC", "USD", "BTC", "ETH", "BNB", "BUSD"]

        for quote in common_quotes:
            if pair.endswith(quote):
                base = pair[:-len(quote)]
                if base:  # 确保基础货币不为空
                    return base, quote

        # 如果无法识别，抛出异常
        raise ValueError(f"无法解析交易对: {pair}")

    def _format_symbol(
        self,
        base: str,
        quote: str,
        settlement: Optional[str],
        fmt: SymbolFormat
    ) -> str:
        """
        根据目标格式重组符号

        Args:
            base: 基础货币
            quote: 计价货币
            settlement: 结算货币（可选）
            fmt: 目标格式规范

        Returns:
            格式化后的符号
        """
        # 基础部分
        symbol = f"{base}{fmt.separator}{quote}"

        # 添加结算货币后缀（如果需要）
        if fmt.has_settlement_suffix:
            # 通常结算货币与计价货币相同
            settlement_currency = settlement if settlement else quote
            symbol = f"{symbol}:{settlement_currency}"

        return symbol

    def build_mapping(self, symbols: list[str]) -> Dict[str, str]:
        """
        批量构建符号映射

        Args:
            symbols: 源交易所的交易对列表

        Returns:
            映射字典 {源符号: 目标符号}
        """
        mapping = {}

        for symbol in symbols:
            try:
                mapped = self.map(symbol)
                mapping[symbol] = mapped
            except Exception as exc:
                logger.warning(f"跳过无法映射的符号 {symbol}: {exc}")

        return mapping

    def reverse_map(self, symbol: str) -> str:
        """
        反向映射：从目标交易所格式映射回源交易所格式

        用于将交易结果映射回数据源格式
        """
        # 检查缓存中是否有反向映射
        for src, dst in self._cache.items():
            if dst == symbol:
                return src

        # 如果没有缓存，创建反向映射器
        reverse_mapper = SymbolMapper(
            self.target_exchange,
            self.source_exchange,
            custom_rules={v: k for k, v in self.custom_rules.items()}
        )
        return reverse_mapper.map(symbol)

    def get_cache_stats(self) -> Dict[str, int]:
        """获取缓存统计信息"""
        return {
            "cached_symbols": len(self._cache),
            "custom_rules": len(self.custom_rules),
        }
