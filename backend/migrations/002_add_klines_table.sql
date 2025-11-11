-- 创建K线数据表
CREATE TABLE IF NOT EXISTS klines (
    id SERIAL PRIMARY KEY,
    exchange_id INTEGER NOT NULL REFERENCES exchanges(id),
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,

    timestamp BIGINT NOT NULL,
    datetime TIMESTAMP NOT NULL,

    open NUMERIC(20, 8) NOT NULL,
    high NUMERIC(20, 8) NOT NULL,
    low NUMERIC(20, 8) NOT NULL,
    close NUMERIC(20, 8) NOT NULL,
    volume NUMERIC(30, 8) NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT klines_timeframe_check CHECK (
        timeframe IN ('1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '3d', '1w')
    )
);

-- 创建唯一索引，确保同一交易对、同一时间周期、同一时间戳只有一条记录
CREATE UNIQUE INDEX idx_klines_unique ON klines (exchange_id, symbol, timeframe, timestamp);

-- 创建查询优化索引
CREATE INDEX idx_klines_symbol_timeframe ON klines (symbol, timeframe);
CREATE INDEX idx_klines_datetime ON klines (datetime);
CREATE INDEX idx_klines_symbol_timeframe_datetime ON klines (symbol, timeframe, datetime);

-- 添加注释
COMMENT ON TABLE klines IS 'K线数据表（OHLCV）';
COMMENT ON COLUMN klines.timeframe IS '时间周期：1m, 5m, 15m, 1h, 4h, 1d等';
COMMENT ON COLUMN klines.timestamp IS 'K线开始时间戳（毫秒）';
COMMENT ON COLUMN klines.volume IS '成交量';
