"""
Configuration Management Module

This module handles all system configuration loading from environment variables
and configuration files. It uses pydantic-settings for validation and type safety.
"""

from typing import Dict, List, Optional
from decimal import Decimal
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class ExchangeConfig(BaseSettings):
    """Exchange API configuration"""

    name: str
    api_key: str
    api_secret: str
    password: Optional[str] = None
    testnet: bool = Field(default=True, description="Use testnet for safety")
    rate_limit: int = Field(default=1000, description="API rate limit per minute")

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator('api_key', 'api_secret')
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Ensure API keys are not empty"""
        if not v or v == "your_api_key_here" or v == "your_api_secret_here":
            raise ValueError("API key/secret must be set")
        return v


class AIModelConfig(BaseSettings):
    """AI Model configuration"""

    provider: str = Field(..., description="Provider: deepseek/openai")
    model_name: str
    api_key: str
    base_url: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4000, gt=0)
    timeout: int = Field(default=60, description="Timeout in seconds")

    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Ensure API key is set"""
        if not v or v.startswith("your_"):
            raise ValueError("AI model API key must be set")
        return v

    model_config = SettingsConfigDict(extra="ignore")


class RiskConfig(BaseSettings):
    """Risk management parameters"""

    max_position_size: Decimal = Field(
        default=Decimal("0.2"),
        description="Max 20% of portfolio per position"
    )
    max_daily_loss: Decimal = Field(
        default=Decimal("0.05"),
        description="Max 5% daily loss"
    )
    max_drawdown: Decimal = Field(
        default=Decimal("0.15"),
        description="Max 15% drawdown"
    )
    stop_loss_percentage: Decimal = Field(
        default=Decimal("5.0"),
        description="Default stop loss %"
    )
    take_profit_percentage: Decimal = Field(
        default=Decimal("10.0"),
        description="Default take profit %"
    )

    # 杠杆限制配置
    max_leverage_mainstream: int = Field(
        default=50,
        description="Max leverage for BTC/ETH"
    )
    max_leverage_altcoin: int = Field(
        default=20,
        description="Max leverage for altcoins"
    )
    high_leverage_warning: int = Field(
        default=25,
        description="High leverage warning threshold"
    )

    @field_validator('max_position_size', 'max_daily_loss', 'max_drawdown')
    @classmethod
    def validate_percentage(cls, v: Decimal) -> Decimal:
        """Ensure percentages are between 0 and 1"""
        if v <= 0 or v > 1:
            raise ValueError("Percentage must be between 0 and 1")
        return v

    @field_validator('max_leverage_mainstream', 'max_leverage_altcoin', 'high_leverage_warning')
    @classmethod
    def validate_leverage(cls, v: int) -> int:
        """Ensure leverage is positive and reasonable"""
        if v < 1 or v > 125:
            raise ValueError("Leverage must be between 1 and 125")
        return v


class Config(BaseSettings):
    """
    Main configuration class for the trading system.

    Loads configuration from environment variables and .env file.
    All sensitive data (API keys) should be stored in environment variables.

    Usage:
        config = Config()
        db_url = config.database_url
        exchange = config.get_exchange_config("binance")
    """

    # Environment
    environment: str = Field(default="dev", description="dev/test/prod")

    # Database URLs
    database_url: str = Field(
        default="postgresql://user:password@localhost:5432/crypto_trading"
    )
    redis_url: str = Field(default="redis://localhost:6379/0")
    qdrant_url: str = Field(default="http://localhost:6333")

    # AI Model Selection
    ai_provider: str = Field(
        default="deepseek",
        description="AI提供商选择: deepseek, qwen"
    )

    # DeepSeek Configuration
    deepseek_api_key: str = Field(default="")
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1")
    deepseek_model: str = Field(default="deepseek-chat")

    # Qwen (千问) Configuration
    qwen_api_key: str = Field(default="")
    qwen_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    qwen_model: str = Field(default="qwen-plus")

    # OpenAI Configuration
    openai_api_key: str = Field(default="")
    openai_embedding_model: str = Field(default="text-embedding-ada-002")

    # Market Data Source Configuration
    data_source_exchange: str = Field(
        default="binance",
        description="数据源交易所: hyperliquid, binance, binanceusdm, okx, bybit"
    )
    data_source_symbols: str = Field(
        default="BTC/USDT,ETH/USDT",
        description="监控的交易对列表（逗号分隔）"
    )
    data_collection_interval: int = Field(
        default=3,
        description="数据采集间隔（秒）"
    )

    # Binance Configuration
    binance_api_key: str = Field(default="")
    binance_api_secret: str = Field(default="")
    binance_testnet: bool = Field(default=True)
    binance_futures: bool = Field(default=False, description="是否启用USDT永续合约模式")

    # OKX Configuration (Optional)
    okx_api_key: str = Field(default="")
    okx_api_secret: str = Field(default="")
    okx_password: str = Field(default="")
    okx_testnet: bool = Field(default=True)

    # System Configuration
    loop_interval: int = Field(
        default=60,
        description="Main loop interval in seconds"
    )
    enable_trading: bool = Field(
        default=False,
        description="Enable real trading (safety switch)"
    )
    log_level: str = Field(default="INFO")
    log_file: Optional[str] = Field(default="logs/trading_system.log")
    timezone: str = Field(
        default="UTC",
        description="系统时区，例如: Asia/Dubai, Asia/Shanghai, America/New_York"
    )

    # Account Configuration
    initial_capital: Decimal = Field(
        default=Decimal("0"),
        description="初始资金（USDT），用于计算累计收益率。0表示自动从交易所获取"
    )

    # Risk Parameters
    max_position_size: Decimal = Field(default=Decimal("0.2"))
    max_daily_loss: Decimal = Field(default=Decimal("0.05"))
    max_drawdown: Decimal = Field(default=Decimal("0.15"))
    stop_loss_percentage: Decimal = Field(default=Decimal("5.0"))
    take_profit_percentage: Decimal = Field(default=Decimal("10.0"))

    # API Server
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_reload: bool = Field(default=True)

    # Security
    secret_key: str = Field(default="change_this_in_production")
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)

    # Layered Decision Architecture
    layered_decision_enabled: bool = Field(
        default=True,
        description="启用分层决策架构 (战略层+战术层) - 现已成为默认且唯一模式"
    )
    strategist_interval: int = Field(
        default=3600,
        description="战略层运行间隔(秒)"
    )
    trader_interval: int = Field(
        default=180,
        description="战术层运行间隔(秒)"
    )
    enable_news: bool = Field(
        default=False,
        description="是否启用新闻采集"
    )
    cryptopanic_api_key: str = Field(
        default="",
        description="CryptoPanic API Key"
    )

    # Prompt Style Configuration
    prompt_style: str = Field(
        default="balanced",
        description="提示词风格: conservative(保守), balanced(中性), aggressive(激进)"
    )

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    def get_exchange_config(self, exchange_name: str) -> ExchangeConfig:
        """
        Get exchange configuration by name.

        Args:
            exchange_name: Exchange name (e.g., "binance", "okx")

        Returns:
            ExchangeConfig object

        Raises:
            ValueError: If exchange is not configured
        """
        exchange_name = exchange_name.lower()

        if exchange_name == "binance":
            if not self.binance_api_key or not self.binance_api_secret:
                raise ValueError("Binance API credentials not configured")

            return ExchangeConfig(
                name="binance",
                api_key=self.binance_api_key,
                api_secret=self.binance_api_secret,
                testnet=self.binance_testnet
            )

        elif exchange_name == "okx":
            if not self.okx_api_key or not self.okx_api_secret:
                raise ValueError("OKX API credentials not configured")

            return ExchangeConfig(
                name="okx",
                api_key=self.okx_api_key,
                api_secret=self.okx_api_secret,
                password=self.okx_password,
                testnet=self.okx_testnet
            )

        else:
            raise ValueError(f"Unsupported exchange: {exchange_name}")

    def get_ai_model_config(self, purpose: str) -> AIModelConfig:
        """
        Get AI model configuration by purpose.

        Args:
            purpose: Model purpose ("strategist", "trader", "embedding")

        Returns:
            AIModelConfig object

        Raises:
            ValueError: If model is not configured
        """
        if purpose in ["strategist", "trader"]:
            # 根据 ai_provider 选择模型
            if self.ai_provider == "qwen":
                if not self.qwen_api_key:
                    raise ValueError("Qwen API key not configured")

                return AIModelConfig(
                    provider="qwen",
                    model_name=self.qwen_model,
                    api_key=self.qwen_api_key,
                    base_url=self.qwen_base_url,
                    temperature=0.7
                )
            else:  # 默认使用 deepseek
                if not self.deepseek_api_key:
                    raise ValueError("DeepSeek API key not configured")

                return AIModelConfig(
                    provider="deepseek",
                    model_name=self.deepseek_model,
                    api_key=self.deepseek_api_key,
                    base_url=self.deepseek_base_url,
                    temperature=0.7
                )

        elif purpose == "embedding":
            if not self.openai_api_key:
                raise ValueError("OpenAI API key not configured")

            return AIModelConfig(
                provider="openai",
                model_name=self.openai_embedding_model,
                api_key=self.openai_api_key,
                temperature=0.0  # Embeddings don't use temperature
            )

        else:
            raise ValueError(f"Unknown AI model purpose: {purpose}")

    def get_risk_config(self) -> RiskConfig:
        """
        Get risk management configuration.

        Returns:
            RiskConfig object
        """
        return RiskConfig(
            max_position_size=self.max_position_size,
            max_daily_loss=self.max_daily_loss,
            max_drawdown=self.max_drawdown,
            stop_loss_percentage=self.stop_loss_percentage,
            take_profit_percentage=self.take_profit_percentage
        )

    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment == "prod"

    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.environment == "dev"

    def is_test(self) -> bool:
        """Check if running in test environment"""
        return self.environment == "test"

    def get_data_source_symbols(self) -> List[str]:
        """
        获取数据源交易对列表

        Returns:
            交易对列表
        """
        if not self.data_source_symbols:
            return []
        return [s.strip() for s in self.data_source_symbols.split(",") if s.strip()]

    def validate_config(self) -> List[str]:
        """
        Validate configuration and return list of warnings.

        Returns:
            List of warning messages
        """
        warnings = []

        # Check data source configuration
        if not self.data_source_exchange:
            warnings.append("⚠️  未配置数据源交易所")

        if not self.get_data_source_symbols():
            warnings.append("⚠️  未配置监控的交易对")

        # Check if using default secret key
        if self.secret_key == "change_this_in_production" and self.is_production():
            warnings.append("⚠️  生产环境仍使用默认密钥，存在安全风险！")

        # Check if trading is enabled in production without proper setup
        if self.enable_trading and self.is_production():
            if self.binance_testnet or self.okx_testnet:
                warnings.append("⚠️  生产环境开启交易但仍使用测试网！")

        # Check if API keys are set
        if not self.deepseek_api_key:
            warnings.append("⚠️  未配置 DeepSeek API Key")

        if not self.binance_api_key and not self.okx_api_key:
            warnings.append("⚠️  未配置任何交易所 API Key，无法真实下单")

        if self.binance_futures and (not self.binance_api_key or not self.binance_api_secret):
            warnings.append("⚠️  已启用 Binance 永续模式，但未配置完整的 API Key/Secret")

        # Check risk parameters
        if self.max_position_size > Decimal("0.5"):
            warnings.append("⚠️  单笔仓位超过总资产 50%，风险极高")

        if self.max_daily_loss > Decimal("0.1"):
            warnings.append("⚠️  最大日亏损限制超过 10%，请谨慎评估")

        return warnings


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get global configuration instance (singleton pattern).

    Returns:
        Config object
    """
    global _config
    if _config is None:
        _config = Config()
    return _config


def reload_config() -> Config:
    """
    Reload configuration from environment.

    Returns:
        New Config object
    """
    global _config
    _config = Config()
    return _config


# Example usage
if __name__ == "__main__":
    config = get_config()

    print(f"Environment: {config.environment}")
    print(f"Database URL: {config.database_url}")
    print(f"Enable Trading: {config.enable_trading}")

    # Validate configuration
    warnings = config.validate_config()
    if warnings:
        print("\nConfiguration Warnings:")
        for warning in warnings:
            print(warning)

    # Test exchange config
    try:
        binance_config = config.get_exchange_config("binance")
        print(f"\nBinance configured: testnet={binance_config.testnet}")
    except ValueError as e:
        print(f"\nBinance not configured: {e}")
