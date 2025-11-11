#!/usr/bin/env python3
"""
查询币安测试网的所有订单

用于检查止损止盈订单是否真的被创建
"""

import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import ccxt.async_support as ccxt
from dotenv import load_dotenv


async def check_orders():
    """查询所有订单"""

    # 从环境变量加载配置
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")

    if not api_key or not api_secret:
        print("❌ 未配置 BINANCE_API_KEY 或 BINANCE_API_SECRET")
        return

    # 创建 Binance USDT 永续交易所实例
    exchange = ccxt.binanceusdm({
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
            "testnet": True,  # 使用测试网
        },
    })

    try:
        print("=" * 60)
        print("币安 USDT 永续合约测试网 - 订单查询")
        print("=" * 60)
        print()

        # 查询所有交易对
        symbols = ["BTC/USDT", "ETH/USDT"]

        for symbol in symbols:
            print(f"\n📊 {symbol} 订单:")
            print("-" * 60)

            try:
                # 查询所有未完成订单
                open_orders = await exchange.fetch_open_orders(symbol)

                if not open_orders:
                    print(f"  ✓ 无未完成订单")
                else:
                    for order in open_orders:
                        order_type = order.get("type", "unknown")
                        side = order.get("side", "unknown")
                        amount = order.get("amount", 0)
                        price = order.get("price")
                        stop_price = order.get("stopPrice") or order.get("info", {}).get("stopPrice")
                        status = order.get("status", "unknown")
                        order_id = order.get("id", "N/A")

                        print(f"\n  订单 ID: {order_id}")
                        print(f"    类型: {order_type}")
                        print(f"    方向: {side}")
                        print(f"    数量: {amount}")
                        if price:
                            print(f"    价格: {price}")
                        if stop_price:
                            print(f"    触发价: {stop_price}")
                        print(f"    状态: {status}")

                        # 检查是否是止损止盈订单
                        if "STOP" in order_type.upper() or "TAKE_PROFIT" in order_type.upper():
                            print(f"    🎯 这是止损/止盈订单!")

            except Exception as exc:
                print(f"  ❌ 查询失败: {exc}")

        # 查询持仓
        print(f"\n" + "=" * 60)
        print("持仓信息:")
        print("=" * 60)

        positions = await exchange.fetch_positions()
        active_positions = [p for p in positions if float(p.get("contracts", 0)) != 0]

        if not active_positions:
            print("  ✓ 无持仓")
        else:
            for pos in active_positions:
                symbol = pos.get("symbol", "unknown")
                side = pos.get("side", "unknown")
                contracts = pos.get("contracts", 0)
                entry_price = pos.get("entryPrice", 0)
                unrealized_pnl = pos.get("unrealizedPnl", 0)

                print(f"\n  {symbol}:")
                print(f"    方向: {side}")
                print(f"    数量: {contracts}")
                print(f"    开仓价: {entry_price}")
                print(f"    未实现盈亏: {unrealized_pnl}")

        # 查询账户余额
        print(f"\n" + "=" * 60)
        print("账户余额:")
        print("=" * 60)

        balance = await exchange.fetch_balance()
        usdt_balance = balance.get("USDT", {})
        free = usdt_balance.get("free", 0)
        used = usdt_balance.get("used", 0)
        total = usdt_balance.get("total", 0)

        print(f"  可用: {free:.2f} USDT")
        print(f"  占用: {used:.2f} USDT")
        print(f"  总计: {total:.2f} USDT")

    finally:
        await exchange.close()


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(check_orders())
