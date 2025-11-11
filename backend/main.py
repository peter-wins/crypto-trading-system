#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Autonomous Cryptocurrency Trading System
Main Entry Point (Refactored)

简化版主入口,使用构建器模式和协调器模式。
"""

import sys
import asyncio
import signal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.logger import init_logging_from_config, get_logger
from src.core.config import get_config
from src.core.trading_system_builder import TradingSystemBuilder


async def main():
    """主函数"""
    # 初始化日志系统 (内部会自动加载配置)
    init_logging_from_config()

    # 获取配置和日志记录器
    config = get_config()
    logger = get_logger(__name__)

    logger.info("=" * 60)
    logger.info("AI 自主加密货币交易系统")
    logger.info("=" * 60)

    builder = TradingSystemBuilder()
    coordinator = None
    shutdown_task = None

    # 信号处理器
    def signal_handler(signum, frame):
        logger.info(f"\n收到信号 {signum}，开始执行停止流程...")
        nonlocal shutdown_task
        if coordinator:
            asyncio.create_task(coordinator.stop())
        if shutdown_task is None or shutdown_task.done():
            shutdown_task = asyncio.create_task(builder.cleanup())

    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    exit_code = 0

    try:
        # 构建系统
        coordinator = await builder.build()

        # 运行系统（分层决策模式）
        logger.info("使用分层决策模式运行")
        await coordinator.run_layered_decision_mode()

    except KeyboardInterrupt:
        logger.info("\n收到 KeyboardInterrupt，准备退出。")
        exit_code = 0
    except Exception as e:
        logger.critical(f"致命错误: {e}", exc_info=True)
        exit_code = 1
    finally:
        # 清理资源
        if shutdown_task:
            await shutdown_task
        else:
            await builder.cleanup()

    return exit_code


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n收到中断，退出程序。")
        sys.exit(0)
