-- ============================================================================
-- Trading System Database Initialization Script
-- ============================================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 1. Exchanges Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS exchanges (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    api_key_encrypted TEXT NOT NULL,
    api_secret_encrypted TEXT NOT NULL,
    password_encrypted TEXT,
    testnet BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_exchanges_name ON exchanges(name);
CREATE INDEX IF NOT EXISTS idx_exchanges_active ON exchanges(is_active);

-- ============================================================================
-- 2. Orders Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS orders (
    id VARCHAR(100) PRIMARY KEY,
    client_order_id VARCHAR(100) UNIQUE NOT NULL,
    exchange_id INTEGER REFERENCES exchanges(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
    type VARCHAR(20) NOT NULL CHECK (
        type IN ('market', 'limit', 'stop_loss', 'stop_loss_limit',
                 'take_profit', 'take_profit_limit')
    ),
    status VARCHAR(20) NOT NULL CHECK (
        status IN ('pending', 'open', 'partially_filled', 'filled',
                   'canceled', 'rejected', 'expired')
    ),
    price NUMERIC(20, 8),
    amount NUMERIC(20, 8) NOT NULL,
    filled NUMERIC(20, 8) DEFAULT 0,
    remaining NUMERIC(20, 8),
    cost NUMERIC(20, 8) DEFAULT 0,
    average NUMERIC(20, 8),
    fee NUMERIC(20, 8),
    fee_currency VARCHAR(10),
    stop_price NUMERIC(20, 8),
    take_profit_price NUMERIC(20, 8),
    stop_loss_price NUMERIC(20, 8),
    decision_id VARCHAR(100),
    timestamp BIGINT NOT NULL,
    datetime TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_datetime ON orders(datetime DESC);
CREATE INDEX IF NOT EXISTS idx_orders_exchange ON orders(exchange_id);
CREATE INDEX IF NOT EXISTS idx_orders_decision ON orders(decision_id);

-- ============================================================================
-- 3. Trades Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS trades (
    id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) REFERENCES orders(id),
    exchange_id INTEGER REFERENCES exchanges(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
    price NUMERIC(20, 8) NOT NULL,
    amount NUMERIC(20, 8) NOT NULL,
    cost NUMERIC(20, 8) NOT NULL,
    fee NUMERIC(20, 8),
    fee_currency VARCHAR(10),
    timestamp BIGINT NOT NULL,
    datetime TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_trades_order ON trades(order_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_datetime ON trades(datetime DESC);

-- ============================================================================
-- 4. Positions Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    exchange_id INTEGER REFERENCES exchanges(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('buy', 'sell')),
    amount NUMERIC(20, 8) NOT NULL,
    entry_price NUMERIC(20, 8) NOT NULL,
    current_price NUMERIC(20, 8) NOT NULL,
    unrealized_pnl NUMERIC(20, 8),
    unrealized_pnl_percentage NUMERIC(10, 4),
    value NUMERIC(20, 8),
    stop_loss NUMERIC(20, 8),
    take_profit NUMERIC(20, 8),
    is_open BOOLEAN DEFAULT TRUE,
    opened_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(exchange_id, symbol, is_open)
);

CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_is_open ON positions(is_open);
CREATE INDEX IF NOT EXISTS idx_positions_exchange ON positions(exchange_id);

-- ============================================================================
-- 5. Portfolio Snapshots Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    exchange_id INTEGER REFERENCES exchanges(id),
    total_value NUMERIC(20, 8) NOT NULL,
    cash NUMERIC(20, 8) NOT NULL,
    positions_value NUMERIC(20, 8),
    total_pnl NUMERIC(20, 8),
    daily_pnl NUMERIC(20, 8),
    total_return NUMERIC(10, 4),
    positions JSONB,
    snapshot_date DATE NOT NULL,
    timestamp BIGINT NOT NULL,
    datetime TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(exchange_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date ON portfolio_snapshots(snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_exchange ON portfolio_snapshots(exchange_id);

-- ============================================================================
-- 6. Decisions Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS decisions (
    id VARCHAR(100) PRIMARY KEY,
    decision_layer VARCHAR(20) NOT NULL CHECK (
        decision_layer IN ('strategic', 'tactical')
    ),
    input_context JSONB NOT NULL,
    thought_process TEXT NOT NULL,
    tools_used TEXT[],
    decision TEXT NOT NULL,
    action_taken TEXT,
    model_used VARCHAR(50),
    tokens_used INTEGER,
    latency_ms INTEGER,
    timestamp BIGINT NOT NULL,
    datetime TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_decisions_layer ON decisions(decision_layer);
CREATE INDEX IF NOT EXISTS idx_decisions_datetime ON decisions(datetime DESC);

-- ============================================================================
-- 7. Experiences Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS experiences (
    id VARCHAR(100) PRIMARY KEY,
    situation TEXT NOT NULL,
    situation_tags TEXT[],
    decision TEXT NOT NULL,
    decision_reasoning TEXT NOT NULL,
    decision_id VARCHAR(100) REFERENCES decisions(id),
    outcome VARCHAR(20) NOT NULL CHECK (outcome IN ('success', 'failure')),
    pnl NUMERIC(20, 8),
    pnl_percentage NUMERIC(10, 4),
    reflection TEXT,
    lessons_learned TEXT[],
    importance_score NUMERIC(3, 2) DEFAULT 0.5,
    related_orders TEXT[],
    symbol VARCHAR(20),
    timestamp BIGINT NOT NULL,
    datetime TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_experiences_outcome ON experiences(outcome);
CREATE INDEX IF NOT EXISTS idx_experiences_importance ON experiences(importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_experiences_datetime ON experiences(datetime DESC);
CREATE INDEX IF NOT EXISTS idx_experiences_symbol ON experiences(symbol);
CREATE INDEX IF NOT EXISTS idx_experiences_tags ON experiences USING GIN(situation_tags);

-- ============================================================================
-- 8. Strategies Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    version VARCHAR(20) NOT NULL,
    description TEXT,
    config JSONB NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    total_trades INTEGER DEFAULT 0,
    win_rate NUMERIC(5, 2),
    total_return NUMERIC(10, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP,
    deactivated_at TIMESTAMP,
    reason_for_update TEXT,
    UNIQUE(name, version)
);

CREATE INDEX IF NOT EXISTS idx_strategies_active ON strategies(is_active);
CREATE INDEX IF NOT EXISTS idx_strategies_name ON strategies(name);

-- ============================================================================
-- 9. Performance Metrics Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS performance_metrics (
    id SERIAL PRIMARY KEY,
    strategy_id INTEGER REFERENCES strategies(id),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    total_return NUMERIC(10, 4),
    annualized_return NUMERIC(10, 4),
    daily_returns JSONB,
    volatility NUMERIC(10, 4),
    max_drawdown NUMERIC(10, 4),
    sharpe_ratio NUMERIC(10, 4),
    sortino_ratio NUMERIC(10, 4),
    calmar_ratio NUMERIC(10, 4),
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate NUMERIC(5, 2),
    avg_win NUMERIC(20, 8),
    avg_loss NUMERIC(20, 8),
    profit_factor NUMERIC(10, 4),
    max_consecutive_wins INTEGER,
    max_consecutive_losses INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(strategy_id, start_date, end_date)
);

CREATE INDEX IF NOT EXISTS idx_performance_metrics_strategy ON performance_metrics(strategy_id);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_date_range ON performance_metrics(start_date, end_date);

-- ============================================================================
-- 10. System Events Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS system_events (
    id VARCHAR(100) PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (
        severity IN ('info', 'warning', 'error', 'critical')
    ),
    data JSONB,
    related_order_id VARCHAR(100),
    related_symbol VARCHAR(20),
    message TEXT NOT NULL,
    details TEXT,
    timestamp BIGINT NOT NULL,
    datetime TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_system_events_type ON system_events(event_type);
CREATE INDEX IF NOT EXISTS idx_system_events_severity ON system_events(severity);
CREATE INDEX IF NOT EXISTS idx_system_events_datetime ON system_events(datetime DESC);
CREATE INDEX IF NOT EXISTS idx_system_events_order ON system_events(related_order_id);

-- ============================================================================
-- Triggers
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add triggers to tables
CREATE TRIGGER update_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_positions_updated_at
    BEFORE UPDATE ON positions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_experiences_updated_at
    BEFORE UPDATE ON experiences
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_strategies_updated_at
    BEFORE UPDATE ON strategies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_exchanges_updated_at
    BEFORE UPDATE ON exchanges
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Views
-- ============================================================================

-- Current positions view
CREATE OR REPLACE VIEW current_positions AS
SELECT * FROM positions
WHERE is_open = TRUE;

-- Today's trades view
CREATE OR REPLACE VIEW today_trades AS
SELECT * FROM trades
WHERE DATE(datetime) = CURRENT_DATE;

-- Active strategies view
CREATE OR REPLACE VIEW active_strategies AS
SELECT * FROM strategies
WHERE is_active = TRUE;

-- ============================================================================
-- Functions
-- ============================================================================

-- Calculate win rate
CREATE OR REPLACE FUNCTION calculate_win_rate(
    p_start_date DATE,
    p_end_date DATE
) RETURNS NUMERIC AS $$
DECLARE
    total_count INTEGER;
    win_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_count
    FROM experiences
    WHERE datetime::DATE BETWEEN p_start_date AND p_end_date;

    SELECT COUNT(*) INTO win_count
    FROM experiences
    WHERE datetime::DATE BETWEEN p_start_date AND p_end_date
      AND outcome = 'success';

    IF total_count = 0 THEN
        RETURN 0;
    END IF;

    RETURN (win_count::NUMERIC / total_count) * 100;
END;
$$ LANGUAGE plpgsql;

-- Get portfolio summary
CREATE OR REPLACE FUNCTION get_portfolio_summary(
    p_exchange_id INTEGER
) RETURNS TABLE (
    total_value NUMERIC,
    cash NUMERIC,
    positions_value NUMERIC,
    open_positions INTEGER,
    total_pnl NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ps.total_value,
        ps.cash,
        ps.positions_value,
        (SELECT COUNT(*)::INTEGER FROM positions WHERE exchange_id = p_exchange_id AND is_open = TRUE),
        ps.total_pnl
    FROM portfolio_snapshots ps
    WHERE ps.exchange_id = p_exchange_id
    ORDER BY ps.snapshot_date DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Initial Data (Optional)
-- ============================================================================

-- Insert default strategy
INSERT INTO strategies (name, version, description, config, is_active)
VALUES (
    'adaptive_strategy',
    '1.0.0',
    'AI-driven adaptive trading strategy',
    '{"max_position_size": 0.2, "max_daily_loss": 0.05}'::jsonb,
    TRUE
)
ON CONFLICT DO NOTHING;

-- ============================================================================
-- Grants (if needed)
-- ============================================================================

-- Grant permissions to application user
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO trading_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO trading_app;

-- ============================================================================
-- Completion Message
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Database initialization completed successfully!';
    RAISE NOTICE 'Tables created: %', (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE');
    RAISE NOTICE 'Indexes created: %', (SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public');
END $$;
