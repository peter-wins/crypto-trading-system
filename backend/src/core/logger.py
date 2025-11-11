"""
Logging System Module

Provides structured logging with JSON formatting for production and
human-readable formatting for development.
"""

import logging
import logging.handlers
import sys
from typing import Optional
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields"""

    def __init__(self, *args, local_tz=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.json_ensure_ascii = False
        self.local_tz = local_tz or timezone.utc

    def add_fields(self, log_record, record, message_dict):
        """Add custom fields to log record"""
        super().add_fields(log_record, record, message_dict)

        # Add timestamp in local timezone
        if not log_record.get('timestamp'):
            utc_time = datetime.now(timezone.utc)
            local_time = utc_time.astimezone(self.local_tz)
            log_record['timestamp'] = local_time.isoformat()

        # Add log level
        if log_record.get('level'):
            log_record['level'] = log_record['level'].upper()
        else:
            log_record['level'] = record.levelname

        # Add module and function
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        log_record['line'] = record.lineno

    def json_dumps(self, obj):
        """Ensure JSON dumps uses UTF-8 without escaping Chinese characters."""
        return json.dumps(obj, ensure_ascii=False)

    def process_log_record(self, log_data):  # type: ignore[override]
        processed = super().process_log_record(log_data)
        return self._sanitize(processed)

    def _sanitize(self, value):  # type: ignore[override]
        if isinstance(value, dict):
            return {k: self._sanitize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._sanitize(v) for v in value]
        if isinstance(value, str) and "\\u" in value:
            candidate = value.strip()
            if candidate.startswith(("{", "[", '"')):
                try:
                    return self._sanitize(json.loads(value))
                except json.JSONDecodeError:
                    pass
            try:
                return value.encode("utf-8").decode("unicode_escape")
            except UnicodeDecodeError:
                return value
        return value


class ColoredFormatter(logging.Formatter):
    """带颜色的控制台日志格式，便于快速辨识级别"""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
        "RESET": "\033[0m",
    }

    def __init__(self, *args, local_tz=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.local_tz = local_tz or timezone.utc

    def format(self, record: logging.LogRecord) -> str:
        # Convert to local timezone
        utc_time = datetime.fromtimestamp(record.created, tz=timezone.utc)
        local_time = utc_time.astimezone(self.local_tz)
        ts = local_time.strftime("%Y-%m-%d %H:%M:%S")

        color = self.COLORS.get(record.levelname, "")
        reset = self.COLORS["RESET"]
        level = f"{record.levelname:<7}"
        location = f"{record.name}:{record.funcName}:{record.lineno}"
        message = super().format(record)
        # 仅为级别着色，避免整行都使用同一颜色
        colored_level = f"{color}{level}{reset}"
        # 调整为：时间 | 级别 | 消息 | 位置
        return f"{ts} | {colored_level} | {message} | {location}"


class PlainFormatter(logging.Formatter):
    """无颜色的纯文本日志格式，满足用户的指定格式需求"""

    def __init__(self, *args, local_tz=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.local_tz = local_tz or timezone.utc

    def format(self, record: logging.LogRecord) -> str:
        # Convert to local timezone
        utc_time = datetime.fromtimestamp(record.created, tz=timezone.utc)
        local_time = utc_time.astimezone(self.local_tz)
        ts = local_time.strftime("%Y-%m-%d %H:%M:%S")

        level = f"{record.levelname:<7}"
        location = f"{record.name}:{record.funcName}:{record.lineno}"
        message = super().format(record)
        # 格式：时间 | 级别 | 消息 | 位置
        return f"{ts} | {level} | {message} | {location}"


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    environment: str = "dev",
    timezone_name: str = "UTC"
) -> None:
    """
    Setup logging configuration for the entire application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        environment: Environment (dev/test/prod)
        timezone_name: Timezone name (e.g., Asia/Dubai, UTC)
    """
    # Get local timezone
    try:
        local_tz = ZoneInfo(timezone_name)
    except Exception:
        local_tz = timezone.utc

    # Get root logger
    root_logger = logging.getLogger()

    # Clear existing handlers
    root_logger.handlers.clear()

    # Set log level
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    if environment == "prod":
        # 生产环境：控制台也使用 JSON 方便收集
        console_formatter = CustomJsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s',
            local_tz=local_tz
        )
    else:
        console_formatter = ColoredFormatter('%(message)s', local_tz=local_tz)
    console_handler.setFormatter(console_formatter)

    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        # Create log directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # 使用按天滚动的文件处理器，每天一个文件
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_file,
            when="midnight",
            interval=1,
            backupCount=0,  # 不自动删除旧文件，如需清理可后续配置
            utc=True,
            encoding="utf-8",
        )
        # 仅使用日期作为后缀，示例：trading_system.log.2025-11-09
        file_handler.suffix = "%Y-%m-%d"
        file_handler.setLevel(level)

        # 使用纯文本格式：时间 | 级别 | 消息 | 模块:函数:行号
        plain_formatter = PlainFormatter('%(message)s', local_tz=local_tz)
        file_handler.setFormatter(plain_formatter)

        root_logger.addHandler(file_handler)

    # Suppress overly verbose third-party loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('ccxt').setLevel(logging.INFO)
    logging.getLogger('openai').setLevel(logging.INFO)
    logging.getLogger('openai._base_client').setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Logger name (typically __name__ of the module)

    Returns:
        Logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("System started")
        logger.error("Error occurred", exc_info=True)
    """
    return logging.getLogger(name)


class LoggerContext:
    """
    Context manager for temporary log level changes.

    Example:
        with LoggerContext("ccxt", logging.DEBUG):
            # ccxt logs will be at DEBUG level here
            exchange.fetch_ticker("BTC/USDT")
    """

    def __init__(self, logger_name: str, level: int):
        """
        Initialize logger context.

        Args:
            logger_name: Name of the logger
            level: Temporary log level
        """
        self.logger = logging.getLogger(logger_name)
        self.original_level = self.logger.level
        self.temp_level = level

    def __enter__(self):
        """Enter context - set temporary level"""
        self.logger.setLevel(self.temp_level)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - restore original level"""
        self.logger.setLevel(self.original_level)


class StructuredLogger:
    """
    Wrapper for structured logging with additional context.

    Example:
        logger = StructuredLogger("trading")
        logger.info(
            "Trade executed",
            extra={
                "symbol": "BTC/USDT",
                "side": "buy",
                "amount": 0.1,
                "price": 45000
            }
        )
    """

    def __init__(self, name: str):
        """
        Initialize structured logger.

        Args:
            name: Logger name
        """
        self.logger = logging.getLogger(name)
        self.context = {}

    def set_context(self, **kwargs) -> None:
        """
        Set persistent context for all log messages.

        Args:
            **kwargs: Context key-value pairs
        """
        self.context.update(kwargs)

    def clear_context(self) -> None:
        """Clear all context"""
        self.context.clear()

    def _log(self, level: int, message: str, **kwargs) -> None:
        """Internal log method with context"""
        # Merge context with kwargs
        extra = {**self.context, **kwargs}

        # Log with extra data
        self.logger.log(
            level,
            message,
            extra={'extra_data': extra}
        )

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message"""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log info message"""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message"""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, exc_info: bool = False, **kwargs) -> None:
        """
        Log error message.

        Args:
            message: Error message
            exc_info: Include exception info
            **kwargs: Additional context
        """
        extra = {**self.context, **kwargs}
        self.logger.error(message, exc_info=exc_info, extra={'extra_data': extra})

    def critical(self, message: str, exc_info: bool = False, **kwargs) -> None:
        """
        Log critical message.

        Args:
            message: Critical message
            exc_info: Include exception info
            **kwargs: Additional context
        """
        extra = {**self.context, **kwargs}
        self.logger.critical(message, exc_info=exc_info, extra={'extra_data': extra})


# Initialize logging from config
def init_logging_from_config():
    """Initialize logging using configuration from environment"""
    from src.core.config import get_config

    try:
        config = get_config()
        setup_logging(
            log_level=config.log_level,
            log_file=config.log_file,
            environment=config.environment,
            timezone_name=config.timezone
        )

        logger = get_logger(__name__)
        logger.info(
            f"Logging initialized: level={config.log_level}, "
            f"environment={config.environment}, timezone={config.timezone}"
        )

    except Exception as e:
        # Fallback to basic logging if config fails
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
        )
        logging.error(f"Failed to initialize logging from config: {e}")


# Example usage
if __name__ == "__main__":
    # Test different logging configurations

    print("=== Development Mode ===")
    setup_logging(log_level="DEBUG", environment="dev")
    logger = get_logger(__name__)

    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")

    print("\n=== Production Mode (JSON) ===")
    setup_logging(log_level="INFO", environment="prod")
    logger = get_logger(__name__)

    logger.info("System started")
    logger.warning("High memory usage detected")
    logger.error("Failed to connect to database", exc_info=False)

    print("\n=== Structured Logging ===")
    structured = StructuredLogger("trading")
    structured.set_context(trader_id="trader_001", session="abc123")

    structured.info(
        "Trade executed",
        symbol="BTC/USDT",
        side="buy",
        amount=0.1,
        price=45000
    )

    print("\n=== Context Manager ===")
    setup_logging(log_level="INFO", environment="dev")

    logger = get_logger("test")
    logger.debug("This won't show (level is INFO)")

    with LoggerContext("test", logging.DEBUG):
        logger.debug("This will show (temporary DEBUG level)")

    logger.debug("This won't show again (back to INFO)")
