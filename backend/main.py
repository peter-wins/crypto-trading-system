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
import warnings
from pathlib import Path

# 过滤 Python 关闭时的清理警告
# 这些警告在程序正常退出时出现，是由于 Python 解释器关闭顺序导致的
# 不影响程序功能，可以安全忽略
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*was never awaited.*')
warnings.filterwarnings('ignore', category=ResourceWarning, message='.*unclosed.*')

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

    logger.info("✓ [系统] 启动中...")

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
        logger.info("✓ [系统] 启动完成，开始运行分层决策模式")
        await coordinator.run_layered_decision_mode()

    except KeyboardInterrupt:
        logger.info("\n收到 KeyboardInterrupt，准备退出。")
        exit_code = 0
    except Exception as e:
        logger.critical(f"致命错误: {e}", exc_info=True)
        exit_code = 1
    finally:
        if shutdown_task:
            await shutdown_task
        else:
            await builder.cleanup()
        logger.info("📋 所有资源清理完毕，准备退出。")
        return exit_code


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    import logging as _logging
    _logging.shutdown()
    sys.exit(exit_code)
