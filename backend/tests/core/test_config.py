"""Tests for configuration module"""

import pytest
import os
from decimal import Decimal
from src.core.config import Config, ExchangeConfig, AIModelConfig, RiskConfig


@pytest.fixture
def test_env(monkeypatch):
    """Set up test environment variables"""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test_db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test_deepseek_key")
    monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
    monkeypatch.setenv("BINANCE_API_KEY", "test_binance_key")
    monkeypatch.setenv("BINANCE_API_SECRET", "test_binance_secret")
    monkeypatch.setenv("ENABLE_TRADING", "false")


def test_config_load(test_env):
    """Test configuration loading from environment"""
    config = Config()

    assert config.environment == "test"
    assert config.database_url == "postgresql://test:test@localhost/test_db"
    assert config.deepseek_api_key == "test_deepseek_key"
    assert config.enable_trading is False


def test_config_defaults():
    """Test default configuration values"""
    config = Config()

    assert config.loop_interval == 60
    assert config.log_level == "INFO"
    assert config.api_port == 8000
    assert config.max_position_size == Decimal("0.2")


def test_exchange_config(test_env):
    """Test exchange configuration"""
    config = Config()

    binance = config.get_exchange_config("binance")
    assert binance.name == "binance"
    assert binance.api_key == "test_binance_key"
    assert binance.api_secret == "test_binance_secret"
    assert binance.testnet is True


def test_exchange_config_invalid():
    """Test invalid exchange name"""
    config = Config()

    with pytest.raises(ValueError, match="Unsupported exchange"):
        config.get_exchange_config("invalid_exchange")


def test_exchange_config_missing_credentials(monkeypatch):
    """Test exchange config with missing credentials"""
    monkeypatch.setenv("BINANCE_API_KEY", "")
    config = Config()

    with pytest.raises(ValueError, match="Binance API credentials not configured"):
        config.get_exchange_config("binance")


def test_ai_model_config_strategist(test_env):
    """Test AI model configuration for strategist"""
    config = Config()

    strategist = config.get_ai_model_config("strategist")
    assert strategist.provider == "deepseek"
    assert strategist.api_key == "test_deepseek_key"
    assert strategist.temperature == 0.7


def test_ai_model_config_embedding(test_env):
    """Test AI model configuration for embedding"""
    config = Config()

    embedding = config.get_ai_model_config("embedding")
    assert embedding.provider == "openai"
    assert embedding.api_key == "test_openai_key"
    assert embedding.temperature == 0.0


def test_ai_model_config_invalid():
    """Test invalid AI model purpose"""
    config = Config()

    with pytest.raises(ValueError, match="Unknown AI model purpose"):
        config.get_ai_model_config("invalid_purpose")


def test_risk_config(test_env):
    """Test risk configuration"""
    config = Config()

    risk = config.get_risk_config()
    assert risk.max_position_size == Decimal("0.2")
    assert risk.max_daily_loss == Decimal("0.05")
    assert risk.max_drawdown == Decimal("0.15")
    assert risk.stop_loss_percentage == Decimal("5.0")
    assert risk.take_profit_percentage == Decimal("10.0")


def test_environment_checks(test_env):
    """Test environment check methods"""
    config = Config()

    assert config.is_test() is True
    assert config.is_development() is False
    assert config.is_production() is False


def test_config_validation_warnings():
    """Test configuration validation"""
    config = Config()

    warnings = config.validate_config()
    assert isinstance(warnings, list)
    # Should have at least warning about API keys
    assert len(warnings) > 0


def test_config_validation_high_risk(monkeypatch):
    """Test validation catches high risk parameters"""
    monkeypatch.setenv("MAX_POSITION_SIZE", "0.6")
    monkeypatch.setenv("MAX_DAILY_LOSS", "0.15")

    config = Config()
    warnings = config.validate_config()

    # Should warn about risky parameters
    assert any("max_position_size" in w for w in warnings)
    assert any("max_daily_loss" in w for w in warnings)


def test_config_singleton():
    """Test config singleton pattern"""
    from src.core.config import get_config, reload_config

    config1 = get_config()
    config2 = get_config()

    # Should be the same instance
    assert config1 is config2

    # Reload should create new instance
    config3 = reload_config()
    assert config3 is not config1


def test_exchange_config_validation():
    """Test exchange config validation"""
    with pytest.raises(ValueError, match="API key/secret must be set"):
        ExchangeConfig(
            name="test",
            api_key="",
            api_secret="secret"
        )

    with pytest.raises(ValueError, match="API key/secret must be set"):
        ExchangeConfig(
            name="test",
            api_key="your_api_key_here",
            api_secret="secret"
        )


def test_ai_model_config_validation():
    """Test AI model config validation"""
    with pytest.raises(ValueError, match="AI model API key must be set"):
        AIModelConfig(
            provider="deepseek",
            model_name="deepseek-chat",
            api_key="your_api_key_here"
        )


def test_risk_config_validation():
    """Test risk config validation"""
    with pytest.raises(ValueError, match="Percentage must be between 0 and 1"):
        RiskConfig(max_position_size=Decimal("1.5"))

    with pytest.raises(ValueError, match="Percentage must be between 0 and 1"):
        RiskConfig(max_position_size=Decimal("-0.1"))
