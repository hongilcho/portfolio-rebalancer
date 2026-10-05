"""Additive USD cost ledger; no existing holding or trade is rewritten."""


def initialize(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usd_cash_state (
            account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
            usd_balance NUMERIC(28,10) NOT NULL CHECK (usd_balance >= 0),
            cost_krw NUMERIC(28,10) NOT NULL CHECK (cost_krw >= 0),
            last_event_date DATE NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usd_cash_events (
            id TEXT PRIMARY KEY,
            sequence BIGSERIAL UNIQUE,
            account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            occurred_at TIMESTAMPTZ,
            event_date DATE NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            usd_amount NUMERIC(28,10) NOT NULL,
            krw_amount NUMERIC(28,10) NOT NULL,
            fx_rate NUMERIC(28,10) NOT NULL,
            cash_delta_krw DOUBLE PRECISION NOT NULL,
            cash_delta_usd DOUBLE PRECISION NOT NULL,
            trade_id TEXT UNIQUE REFERENCES trade_history(id) ON DELETE SET NULL,
            trade_reference TEXT,
            asset_id TEXT REFERENCES assets(id) ON DELETE RESTRICT,
            before_state JSONB NOT NULL,
            after_state JSONB NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            reversed_at TIMESTAMPTZ
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_usd_events_account ON usd_cash_events (account_id, sequence DESC)')
    cursor.execute('ALTER TABLE usd_cash_events ALTER COLUMN occurred_at DROP NOT NULL')
    # Preserve the old PostgreSQL text/API value while widening REAL columns;
    # a direct binary widening would expose float32 tails on existing positions.
    for table, columns in (('holdings', ('avg_price_usd', 'original_avg_price_usd', 'buy_fx_rate')),
                           ('trade_history', ('quantity', 'price', 'exchange_rate'))):
        for column in columns:
            cursor.execute('SELECT data_type FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = %s AND column_name = %s', (table, column))
            if cursor.fetchone()[0] == 'real':
                cursor.execute(f'ALTER TABLE {table} ALTER COLUMN {column} TYPE DOUBLE PRECISION USING {column}::text::double precision')
