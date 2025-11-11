"""Tests for logging module"""

import pytest
import logging
import tempfile
from pathlib import Path
import json

from src.core.logger import (
    setup_logging,
    get_logger,
    LoggerContext,
    StructuredLogger
)


@pytest.fixture
def temp_log_file():
    """Create temporary log file"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        yield f.name
    # Cleanup
    Path(f.name).unlink(missing_ok=True)


def test_setup_logging_dev():
    """Test logging setup in development mode"""
    setup_logging(log_level="DEBUG", environment="dev")

    logger = get_logger("test")
    assert logger.level == logging.DEBUG


def test_setup_logging_prod():
    """Test logging setup in production mode"""
    setup_logging(log_level="INFO", environment="prod")

    logger = get_logger("test")
    assert logger.level == logging.INFO


def test_setup_logging_with_file(temp_log_file):
    """Test logging setup with file output"""
    setup_logging(log_level="INFO", log_file=temp_log_file, environment="prod")

    logger = get_logger("test")
    logger.info("Test message")

    # Check file exists and has content
    assert Path(temp_log_file).exists()
    content = Path(temp_log_file).read_text()
    assert "Test message" in content

    # Should be JSON formatted
    lines = content.strip().split('\n')
    for line in lines:
        data = json.loads(line)
        assert 'timestamp' in data
        assert 'level' in data
        assert 'message' in data


def test_get_logger():
    """Test get_logger function"""
    logger = get_logger("test.module")

    assert isinstance(logger, logging.Logger)
    assert logger.name == "test.module"


def test_logger_levels():
    """Test different log levels"""
    setup_logging(log_level="DEBUG", environment="dev")
    logger = get_logger("test")

    # All these should work without errors
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")


def test_logger_with_exception(temp_log_file):
    """Test logging with exception info"""
    setup_logging(log_level="ERROR", log_file=temp_log_file, environment="prod")
    logger = get_logger("test")

    try:
        raise ValueError("Test error")
    except ValueError:
        logger.error("An error occurred", exc_info=True)

    content = Path(temp_log_file).read_text()
    assert "An error occurred" in content
    assert "ValueError" in content


def test_logger_context():
    """Test LoggerContext context manager"""
    setup_logging(log_level="WARNING", environment="dev")
    logger = get_logger("test")

    # Initially at WARNING level
    assert logger.level == logging.WARNING

    # Temporarily change to DEBUG
    with LoggerContext("test", logging.DEBUG):
        assert logger.level == logging.DEBUG

    # Should be back to WARNING
    assert logger.level == logging.WARNING


def test_structured_logger():
    """Test StructuredLogger"""
    setup_logging(log_level="INFO", environment="dev")

    struct_logger = StructuredLogger("test")

    # Set context
    struct_logger.set_context(user_id="123", session="abc")

    # Log with additional data
    struct_logger.info("Test event", action="login", ip="127.0.0.1")

    # Clear context
    struct_logger.clear_context()

    # Should work without errors
    struct_logger.info("Another event")


def test_structured_logger_levels():
    """Test StructuredLogger with different levels"""
    setup_logging(log_level="DEBUG", environment="dev")

    struct_logger = StructuredLogger("test")

    # Test all levels
    struct_logger.debug("Debug message", key="value")
    struct_logger.info("Info message", key="value")
    struct_logger.warning("Warning message", key="value")
    struct_logger.error("Error message", key="value")
    struct_logger.critical("Critical message", key="value")


def test_structured_logger_with_context():
    """Test StructuredLogger context persistence"""
    setup_logging(log_level="INFO", environment="dev")

    struct_logger = StructuredLogger("test")

    # Set persistent context
    struct_logger.set_context(trader_id="trader_001", exchange="binance")

    # Context should be included in all logs
    struct_logger.info("First message")
    struct_logger.info("Second message")

    # Update context
    struct_logger.set_context(symbol="BTC/USDT")

    struct_logger.info("Third message")


def test_logging_suppression():
    """Test that verbose third-party loggers are suppressed"""
    setup_logging(log_level="DEBUG", environment="dev")

    # These loggers should be at WARNING level
    urllib3_logger = logging.getLogger('urllib3')
    httpx_logger = logging.getLogger('httpx')

    assert urllib3_logger.level == logging.WARNING
    assert httpx_logger.level == logging.WARNING


def test_log_file_creation():
    """Test that log directory is created if it doesn't exist"""
    temp_dir = tempfile.mkdtemp()
    log_file = Path(temp_dir) / "subdir" / "test.log"

    setup_logging(log_level="INFO", log_file=str(log_file), environment="dev")

    logger = get_logger("test")
    logger.info("Test message")

    assert log_file.exists()

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)


def test_json_formatter_fields(temp_log_file):
    """Test that JSON formatter includes all required fields"""
    setup_logging(log_level="INFO", log_file=temp_log_file, environment="prod")

    logger = get_logger("test.module")
    logger.info("Test message")

    content = Path(temp_log_file).read_text()
    data = json.loads(content.strip())

    # Check required fields
    assert 'timestamp' in data
    assert 'level' in data
    assert 'message' in data
    assert 'module' in data
    assert 'function' in data
    assert 'line' in data

    assert data['level'] == 'INFO'
    assert data['message'] == 'Test message'
    assert data['module'] == 'test_logger'


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
def test_all_log_levels(level):
    """Test all log levels can be set"""
    setup_logging(log_level=level, environment="dev")
    logger = get_logger("test")

    expected_level = getattr(logging, level)
    assert logger.level == expected_level
