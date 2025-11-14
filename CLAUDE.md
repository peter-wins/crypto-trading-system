# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **AI-driven autonomous cryptocurrency trading system** that uses LLM (Large Language Models) for market analysis and trading decisions. The system implements a **layered decision architecture** combining macro analysis (Strategist) with micro execution (Trader).

## Development Commands

### Running the System

```bash
# Navigate to backend directory
cd backend

# Activate virtual environment
source ../venv/bin/activate

# Run the main trading system
python main.py

# Run with specific configuration
DATABASE_URL=postgresql://... BINANCE_API_KEY=... python main.py
```

### Database Operations

```bash
# Run database migrations
PGPASSWORD=dev_password psql -h localhost -p 5433 -U dev_user -d crypto_trading_dev -f migrations/001_initial_schema.sql

# Check database connection
PGPASSWORD=dev_password psql -h localhost -p 5433 -U dev_user -d crypto_trading_dev -c "\dt"

# View positions
PGPASSWORD=dev_password psql -h localhost -p 5433 -U dev_user -d crypto_trading_dev -c "SELECT * FROM positions WHERE is_open = true;"
```

### Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_specific.py

# Run with coverage
pytest --cov=src tests/
```

## Architecture Overview

### Four-Layer Architecture

```
┌──────────────────────────────────────────┐
│  Perception Layer (感知层)               │
│  - MarketEnvironment                    │
│  - Multi-source data collection         │
│  - Technical indicators                 │
└──────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────┐
│  Decision Layer (决策层)                 │
│  - Strategist (macro, hourly)          │
│  - Trader (micro, 3-5 min)             │
│  - LLM-powered analysis                │
└──────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────┐
│  Execution Layer (执行层)                │
│  - Order execution                      │
│  - Risk management                      │
│  - Position management                  │
└──────────────────────────────────────────┘
                  ↓
┌──────────────────────────────────────────┐
│  Memory Layer (记忆层)                   │
│  - Redis (short-term)                   │
│  - Qdrant (long-term, optional)        │
│  - PostgreSQL (persistence)            │
└──────────────────────────────────────────┘
```

### Key Design Patterns

1. **Builder Pattern**: `TradingSystemBuilder` constructs the complex trading system step-by-step
2. **Coordinator Pattern**:
   - `TradingCoordinator` orchestrates the main loop
   - `LayeredDecisionCoordinator` coordinates Strategist and Trader
3. **Repository Pattern**: `TradingDAO` encapsulates data access logic

### System Initialization Flow

The system initializes in this order (see `TradingSystemBuilder.build()`):

1. Load configuration
2. Setup data source (exchange, trading pairs)
3. Initialize perception components (market data collectors, analyzers)
4. Initialize memory (Redis, Qdrant)
5. Initialize database (PostgreSQL)
6. Initialize execution components (order executor, risk manager, portfolio manager)
7. Initialize data collection service (KlineManager)
8. Initialize trading executor
9. Initialize account sync service (real trading only)
10. Initialize performance service
11. Initialize layered decision (Strategist + Trader)
12. Create coordinator

## Decision Layer Deep Dive

### Strategist (战略层)

- **Frequency**: Every hour (configurable via `strategist_interval`)
- **Input**: `MarketEnvironment` (macro data, sentiment, news, crypto overview)
- **Output**: `MarketRegime` (market state, risk level, recommended symbols)
- **LLM**: DeepSeek Chat or Qwen Plus
- **File**: `src/decision/strategist.py`

**Key responsibilities**:
- Macro market analysis
- Risk assessment
- Symbol filtering (recommended/blacklisted)
- Asset allocation advice

### Trader (战术层)

- **Frequency**: Every 3-5 minutes (configurable via `trader_interval`)
- **Input**: `MarketRegime` + market snapshots + current positions
- **Output**: `TradingSignal` (action, confidence, price, quantity, leverage, stop-loss, take-profit)
- **LLM**: DeepSeek Chat or Qwen Plus
- **File**: `src/decision/trader.py`

**Key responsibilities**:
- Technical analysis
- Signal generation
- Position sizing
- Batch decision (analyzes multiple symbols in one LLM call)

### Decision Flow

```
1. Strategist runs (hourly)
   └─> Generates MarketRegime (cached for 1 hour)

2. Trader main loop (every 3-5 min)
   ├─> Check if MarketRegime is valid
   ├─> Filter symbols based on regime
   ├─> Collect market snapshots
   ├─> Batch LLM analysis
   ├─> Generate trading signals
   └─> Execute signals via TradingExecutor
```

## Data Flow and Caching

### Market Data Flow

```
Binance API → CCXTMarketDataCollector → KlineManager
                                         ↓
                                    Redis (30s TTL)
                                         ↓
                                    PostgreSQL (persistent)
```

### Multi-Timeframe Kline Management

The system manages K-line data across multiple timeframes:
- **1m, 5m, 15m**: Recent data (7 days retention)
- **1h, 4h**: Medium-term (30 days retention)
- **1d**: Long-term (permanent retention)

K-line data is cached in three layers:
1. **Memory cache**: Fastest, most recent data
2. **Redis cache**: Near-term data with TTL
3. **PostgreSQL**: Historical data persistence

## Risk Management

### Multi-Layer Risk Control

1. **Configuration Layer** (`RiskConfig`):
   - `max_position_size`: 20% of total equity
   - `max_daily_loss`: 5% daily loss limit
   - `max_drawdown`: 15% maximum drawdown
   - `stop_loss_percentage`: 5% default stop loss
   - `take_profit_percentage`: 10% default take profit

2. **Decision Layer** (Strategist):
   - Market risk assessment (`RiskLevel`)
   - Position sizing coefficient
   - Cash ratio recommendation

3. **Execution Layer** (`StandardRiskManager`):
   - Pre-order risk checks
   - Leverage limit validation
   - Daily loss circuit breaker
   - Liquidation risk monitoring

4. **Runtime** (`TradingExecutor`):
   - Signal validation
   - Quantity adjustment
   - Stop-loss/take-profit calculation
   - Duplicate operation detection

### Leverage Limits

- **Major coins (BTC/ETH)**: 5-50x
- **Altcoins**: 5-20x
- **High leverage warning**: >25x

## Database Schema

### Core Tables

- **exchanges**: Exchange configuration
- **orders**: Order records
- **trades**: Trade executions
- **positions**: Current open positions (with unique constraint on `(exchange_id, symbol, side, is_open)`)
- **closed_positions**: Closed position records
- **portfolio_snapshots**: Portfolio snapshots over time
- **decisions**: Decision records (both Strategist and Trader)
- **klines**: Multi-timeframe K-line data
- **performance_history**: Performance metrics history

### Important Notes

- **Timezone**: All timestamps stored in UTC
- **Position Uniqueness**: For HEDGE mode (dual-direction positions), the system enforces uniqueness at database level via constraint `uq_positions_exchange_symbol_side_open`
- **Account Sync**: `AccountSyncService` runs every 10 seconds in real trading mode to sync exchange state

## Configuration Management

### Key Environment Variables

```bash
# Database
DATABASE_URL=postgresql://dev_user:dev_password@localhost:5433/crypto_trading_dev
REDIS_URL=redis://localhost:6379/0
QDRANT_URL=http://localhost:6333

# Exchange
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_TESTNET=true  # Use testnet

# AI Providers
AI_PROVIDER=deepseek  # or "qwen"
DEEPSEEK_API_KEY=your_deepseek_key
QWEN_API_KEY=your_qwen_key
OPENAI_API_KEY=your_openai_key  # For embeddings

# Trading Configuration
ENABLE_TRADING=false  # Paper trading vs real trading
BINANCE_FUTURES=false  # Spot vs futures
DATA_SOURCE_SYMBOLS=BTC/USDT,ETH/USDT
```

### Configuration Class

Key config options in `src/core/config.py`:

- `binance_futures`: Spot or futures trading
- `enable_trading`: Paper trading or real trading
- `ai_provider`: "deepseek" or "qwen"
- `prompt_style`: "conservative", "balanced", or "aggressive"
- `strategist_interval`: Strategist run interval (default: 3600s)
- `trader_interval`: Trader run interval (default: 180s)

## External Dependencies

### Trading Exchange
- **Binance**: Main exchange (spot + USDT perpetual futures)
- **Integration**: Via CCXT library
- **Testnet**: Supports Binance testnet for safe testing

### LLM Providers
- **DeepSeek**: Primary decision model (`deepseek-chat`)
- **Qwen**: Alternative model (`qwen-plus`)
- **OpenAI**: Embedding model (`text-embedding-ada-002`)

### Data Sources
- **FRED API**: Macro economic data (interest rates, CPI, unemployment)
- **Yahoo Finance**: US stock indices (S&P500, NASDAQ)
- **Alternative.me**: Fear & Greed Index
- **CoinGecko**: Crypto market overview
- **Binance API**: Funding rates, long/short ratios
- **CryptoPanic**: Crypto news (optional)

## Key Code Locations

### Entry Points
- `backend/main.py`: Main entry point
- `src/core/trading_system_builder.py`: System builder
- `src/core/coordinator.py`: Main coordinator

### Decision Making
- `src/decision/strategist.py`: Macro analysis
- `src/decision/trader.py`: Micro trading decisions
- `src/decision/layered_coordinator.py`: Decision layer coordination
- `src/decision/prompt_templates.py`: LLM prompt templates

### Execution
- `src/execution/trading_executor.py`: Trading execution service
- `src/execution/order.py`: Order executor
- `src/execution/risk.py`: Risk manager
- `src/execution/portfolio.py`: Portfolio manager

### Data & Services
- `src/services/market_data/ccxt_collector.py`: Market data collection
- `src/services/kline/kline_service.py`: K-line data manager
- `src/services/account_sync.py`: Account synchronization
- `src/services/database/`: Database access layer

### Perception
- `src/perception/environment_builder.py`: Market environment builder
- `src/perception/collectors/`: Various data collectors

## Common Patterns

### Async Context Management

Most services implement async context managers:

```python
async with TradingCoordinator(...) as coordinator:
    await coordinator.run_layered_decision_mode()
```

### Error Handling for Network Issues

Network errors are common and handled gracefully:
- Market data collection failures: Logged as warnings, auto-retry on next cycle
- LLM API failures: Caught and logged, system continues
- Exchange API failures: Retry with exponential backoff

### Session Management

Database sessions should be properly managed:
- Use `db_manager.get_dao()` to create independent sessions
- Always close sessions in `finally` blocks
- Don't share sessions across concurrent operations

Example:
```python
dao = None
try:
    dao = await self.db_manager.get_dao()
    # ... do work
    await dao.session.commit()
except Exception as e:
    if dao:
        await dao.session.rollback()
finally:
    if dao and dao.session:
        await dao.session.close()
```

## Logging Strategy

The system uses structured logging with these levels:
- **DEBUG**: Internal technical details, frequent operations
- **INFO**: Key system events, initialization, decisions
- **WARNING**: Recoverable errors (e.g., network timeouts)
- **ERROR**: Serious errors requiring attention
- **CRITICAL**: System-threatening errors

Log format: `[模块] ✓ 描述` for consistency

## Important Constraints

### Binance HEDGE Mode
The system supports Binance HEDGE mode (dual-direction positions):
- Can hold both LONG and SHORT positions for the same symbol simultaneously
- Database enforces uniqueness on `(exchange_id, symbol, side, is_open)`
- Position side mapping: `LONG/BUY` → "buy", `SHORT/SELL` → "sell"

### LLM Decision Format
All LLM responses must be valid JSON:
- Strategist returns: `MarketRegime` object
- Trader returns: Array of `TradingSignal` objects
- System includes retry logic for JSON parsing failures

### Rate Limiting
- Exchange API: Managed by `ExchangeRateLimiters`
- LLM API: No built-in rate limiting (rely on provider limits)
- Market data: Collected at configured intervals to avoid over-fetching

## Migration Strategy

When modifying database schema:
1. Create new migration file in `backend/migrations/`
2. Use sequential numbering: `00X_description.sql`
3. Include both forward migration and rollback instructions
4. Test on development database first
5. Run migration: `psql "$DATABASE_URL" -f migrations/00X_description.sql`
