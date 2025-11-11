"""
Tests for Symbol Mapper
"""

import pytest
from src.perception.symbol_mapper import SymbolMapper, EXCHANGE_FORMATS


def test_hyperliquid_to_binance_usdm():
    """测试 Hyperliquid → Binance USDT 永续映射"""
    mapper = SymbolMapper("hyperliquid", "binanceusdm")

    assert mapper.map("BTC/USDC:USDC") == "BTC/USDT"
    assert mapper.map("ETH/USDC:USDC") == "ETH/USDT"
    assert mapper.map("SOL/USDC:USDC") == "SOL/USDT"


def test_hyperliquid_to_binance_spot():
    """测试 Hyperliquid → Binance 现货映射"""
    mapper = SymbolMapper("hyperliquid", "binance")

    assert mapper.map("BTC/USDC:USDC") == "BTC/USDT"
    assert mapper.map("ETH/USDC:USDC") == "ETH/USDT"


def test_same_exchange_no_mapping():
    """测试相同交易所不进行映射"""
    mapper = SymbolMapper("binance", "binance")

    assert mapper.map("BTC/USDT") == "BTC/USDT"
    assert mapper.map("ETH/USDT") == "ETH/USDT"


def test_custom_rules():
    """测试自定义映射规则"""
    custom_rules = {
        "BTC/USD": "BTCUSD",
        "ETH/USD": "ETHUSD",
    }

    mapper = SymbolMapper(
        "custom_exchange",
        "target_exchange",
        custom_rules=custom_rules
    )

    assert mapper.map("BTC/USD") == "BTCUSD"
    assert mapper.map("ETH/USD") == "ETHUSD"


def test_batch_mapping():
    """测试批量映射"""
    mapper = SymbolMapper("hyperliquid", "binanceusdm")

    symbols = ["BTC/USDC:USDC", "ETH/USDC:USDC", "SOL/USDC:USDC"]
    mapping = mapper.build_mapping(symbols)

    assert mapping == {
        "BTC/USDC:USDC": "BTC/USDT",
        "ETH/USDC:USDC": "ETH/USDT",
        "SOL/USDC:USDC": "SOL/USDT",
    }


def test_reverse_mapping():
    """测试反向映射"""
    mapper = SymbolMapper("hyperliquid", "binanceusdm")

    # 正向映射
    forward = mapper.map("BTC/USDC:USDC")
    assert forward == "BTC/USDT"

    # 反向映射
    reverse = mapper.reverse_map("BTC/USDT")
    assert reverse == "BTC/USDC:USDC"


def test_caching():
    """测试映射缓存"""
    mapper = SymbolMapper("hyperliquid", "binanceusdm")

    # 第一次映射
    result1 = mapper.map("BTC/USDC:USDC")

    # 检查缓存
    stats = mapper.get_cache_stats()
    assert stats["cached_symbols"] == 1

    # 第二次映射应该使用缓存
    result2 = mapper.map("BTC/USDC:USDC")
    assert result1 == result2


def test_okx_format():
    """测试 OKX 交易所格式"""
    mapper = SymbolMapper("binanceusdm", "okx")

    # Binance: BTC/USDT → OKX: BTC/USDT:USDT
    assert mapper.map("BTC/USDT") == "BTC/USDT:USDT"


def test_exchange_format_definitions():
    """测试交易所格式定义"""
    assert "hyperliquid" in EXCHANGE_FORMATS
    assert "binance" in EXCHANGE_FORMATS
    assert "binanceusdm" in EXCHANGE_FORMATS
    assert "okx" in EXCHANGE_FORMATS

    # Hyperliquid 应该有结算货币后缀
    assert EXCHANGE_FORMATS["hyperliquid"].has_settlement_suffix is True

    # Binance 现货不应该有结算货币后缀
    assert EXCHANGE_FORMATS["binance"].has_settlement_suffix is False

    # Binance USDT 永续应该将 USDC 映射为 USDT
    assert EXCHANGE_FORMATS["binanceusdm"].quote_currency_map.get("USDC") == "USDT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
