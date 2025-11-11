"""
Custom Exceptions Module

Defines all custom exceptions used throughout the trading system.
All exceptions inherit from TradingSystemError base class.
"""

from typing import Optional, Dict, Any


class TradingSystemError(Exception):
    """
    Base exception for all trading system errors.

    All custom exceptions should inherit from this class.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        """
        Initialize exception.

        Args:
            message: Error message
            details: Additional context information
            original_exception: Original exception if wrapping another error
        """
        self.message = message
        self.details = details or {}
        self.original_exception = original_exception

        # Construct full message
        full_message = message
        if details:
            details_str = ", ".join(f"{k}={v}" for k, v in details.items())
            full_message = f"{message} ({details_str})"

        super().__init__(full_message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/serialization"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details
        }


# ============================================================================
# Configuration Errors
# ============================================================================

class ConfigurationError(TradingSystemError):
    """Configuration is invalid or missing"""
    pass


class APIKeyError(ConfigurationError):
    """API key is missing or invalid"""
    pass


# ============================================================================
# Data Collection Errors
# ============================================================================

class DataCollectionError(TradingSystemError):
    """Error occurred during data collection"""
    pass


class MarketDataError(DataCollectionError):
    """Failed to fetch market data"""
    pass


class ExchangeConnectionError(DataCollectionError):
    """Failed to connect to exchange"""
    pass


class RateLimitError(DataCollectionError):
    """API rate limit exceeded"""
    pass


class SubscriptionError(DataCollectionError):
    """Failed to subscribe to data stream"""
    pass


# ============================================================================
# AI/LLM Errors
# ============================================================================

class LLMError(TradingSystemError):
    """Error occurred during LLM operation"""
    pass


class EmbeddingError(LLMError):
    """Failed to generate embedding"""
    pass


class PromptError(LLMError):
    """Invalid or malformed prompt"""
    pass


class TokenLimitError(LLMError):
    """Token limit exceeded"""
    pass


# ============================================================================
# Memory System Errors
# ============================================================================

class MemoryError(TradingSystemError):
    """Error in memory system"""
    pass


class ShortTermMemoryError(MemoryError):
    """Error in short-term memory (Redis)"""
    pass


class LongTermMemoryError(MemoryError):
    """Error in long-term memory (Vector DB)"""
    pass


class MemoryRetrievalError(MemoryError):
    """Failed to retrieve memory"""
    pass


# ============================================================================
# Decision Making Errors
# ============================================================================

class DecisionError(TradingSystemError):
    """Error occurred during decision making"""
    pass


class StrategyError(DecisionError):
    """Error in strategy formulation"""
    pass


class SignalGenerationError(DecisionError):
    """Failed to generate trading signal"""
    pass


class ToolExecutionError(DecisionError):
    """Error executing decision tool"""
    pass


# ============================================================================
# Order Execution Errors
# ============================================================================

class OrderExecutionError(TradingSystemError):
    """Error occurred during order execution"""
    pass


class OrderCreationError(OrderExecutionError):
    """Failed to create order"""
    pass


class OrderCancellationError(OrderExecutionError):
    """Failed to cancel order"""
    pass


class OrderQueryError(OrderExecutionError):
    """Failed to query order status"""
    pass


class InsufficientBalanceError(OrderExecutionError):
    """Insufficient balance to execute order"""
    pass


# ============================================================================
# Risk Management Errors
# ============================================================================

class RiskCheckError(TradingSystemError):
    """Risk check failed"""
    pass


class PositionLimitError(RiskCheckError):
    """Position limit exceeded"""
    pass


class DailyLossLimitError(RiskCheckError):
    """Daily loss limit exceeded"""
    pass


class DrawdownLimitError(RiskCheckError):
    """Drawdown limit exceeded"""
    pass


class CircuitBreakerError(RiskCheckError):
    """Circuit breaker triggered"""
    pass


# ============================================================================
# Portfolio Errors
# ============================================================================

class PortfolioError(TradingSystemError):
    """Error in portfolio management"""
    pass


class PositionNotFoundError(PortfolioError):
    """Position not found"""
    pass


class PortfolioSyncError(PortfolioError):
    """Failed to sync portfolio with exchange"""
    pass


# ============================================================================
# Learning/Evaluation Errors
# ============================================================================

class LearningError(TradingSystemError):
    """Error in learning module"""
    pass


class PerformanceEvaluationError(LearningError):
    """Failed to evaluate performance"""
    pass


class ReflectionError(LearningError):
    """Error during reflection process"""
    pass


# ============================================================================
# Database Errors
# ============================================================================

class DatabaseError(TradingSystemError):
    """Database operation failed"""
    pass


class DatabaseConnectionError(DatabaseError):
    """Failed to connect to database"""
    pass


class QueryError(DatabaseError):
    """Database query failed"""
    pass


class TransactionError(DatabaseError):
    """Database transaction failed"""
    pass


# ============================================================================
# Validation Errors
# ============================================================================

class ValidationError(TradingSystemError):
    """Data validation failed"""
    pass


class InvalidSymbolError(ValidationError):
    """Invalid trading symbol"""
    pass


class InvalidAmountError(ValidationError):
    """Invalid order amount"""
    pass


class InvalidPriceError(ValidationError):
    """Invalid price"""
    pass


# ============================================================================
# System Errors
# ============================================================================

class SystemError(TradingSystemError):
    """System-level error"""
    pass


class InitializationError(SystemError):
    """Failed to initialize component"""
    pass


class ShutdownError(SystemError):
    """Error during shutdown"""
    pass


class TimeoutError(SystemError):
    """Operation timed out"""
    pass


# ============================================================================
# Utility Functions
# ============================================================================

def wrap_exception(
    original_exception: Exception,
    custom_exception_class: type,
    message: Optional[str] = None,
    **details
) -> TradingSystemError:
    """
    Wrap an exception in a custom exception class.

    Args:
        original_exception: The original exception
        custom_exception_class: The custom exception class to wrap with
        message: Optional custom message
        **details: Additional details

    Returns:
        Custom exception instance

    Example:
        try:
            exchange.fetch_ticker("BTC/USDT")
        except ccxt.NetworkError as e:
            raise wrap_exception(
                e,
                ExchangeConnectionError,
                "Failed to fetch ticker",
                symbol="BTC/USDT",
                exchange="binance"
            )
    """
    error_message = message or str(original_exception)

    return custom_exception_class(
        message=error_message,
        details=details,
        original_exception=original_exception
    )


def handle_exception(
    exception: Exception,
    logger,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Handle exception with logging and context.

    Args:
        exception: The exception to handle
        logger: Logger instance
        context: Additional context information

    Example:
        try:
            risky_operation()
        except Exception as e:
            handle_exception(e, logger, context={"symbol": "BTC/USDT"})
            raise
    """
    context = context or {}

    if isinstance(exception, TradingSystemError):
        # Log custom exception with details
        logger.error(
            f"{exception.__class__.__name__}: {exception.message}",
            extra={
                "exception_details": exception.details,
                "context": context
            },
            exc_info=True
        )
    else:
        # Log standard exception
        logger.error(
            f"Unexpected error: {str(exception)}",
            extra={"context": context},
            exc_info=True
        )


# Example usage
if __name__ == "__main__":
    # Example 1: Raising a custom exception
    try:
        raise OrderExecutionError(
            "Failed to execute order",
            details={
                "symbol": "BTC/USDT",
                "side": "buy",
                "amount": 0.1,
                "reason": "insufficient balance"
            }
        )
    except TradingSystemError as e:
        print(f"Error: {e}")
        print(f"Details: {e.details}")
        print(f"Dict: {e.to_dict()}")

    print("\n" + "="*50 + "\n")

    # Example 2: Wrapping an exception
    try:
        # Simulate an external library error
        raise ValueError("Invalid parameter")
    except ValueError as e:
        wrapped = wrap_exception(
            e,
            ValidationError,
            "Parameter validation failed",
            parameter="amount",
            value=-1
        )
        print(f"Wrapped error: {wrapped}")
        print(f"Original: {wrapped.original_exception}")

    print("\n" + "="*50 + "\n")

    # Example 3: Exception hierarchy
    errors = [
        DataCollectionError("Data error"),
        MarketDataError("Market data error"),
        ExchangeConnectionError("Connection error"),
        RateLimitError("Rate limit error")
    ]

    for error in errors:
        print(f"{error.__class__.__name__}: {error}")
        print(f"  Is TradingSystemError: {isinstance(error, TradingSystemError)}")
        print(f"  Is DataCollectionError: {isinstance(error, DataCollectionError)}")
