-- 创建账户设置表，用于记录初始资金等配置
CREATE TABLE IF NOT EXISTS account_settings (
    id SERIAL PRIMARY KEY,
    exchange_id INTEGER NOT NULL REFERENCES exchanges(id),
    initial_capital NUMERIC(20, 8) NOT NULL,
    capital_currency VARCHAR(10) DEFAULT 'USDT',
    set_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    notes TEXT,
    UNIQUE(exchange_id)
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_account_settings_exchange ON account_settings(exchange_id);

-- 注释
COMMENT ON TABLE account_settings IS '账户设置表，记录初始资金等配置信息';
COMMENT ON COLUMN account_settings.initial_capital IS '初始资金金额';
COMMENT ON COLUMN account_settings.capital_currency IS '资金币种，默认USDT';
COMMENT ON COLUMN account_settings.set_at IS '设置时间（UTC）';
COMMENT ON COLUMN account_settings.notes IS '备注信息';
