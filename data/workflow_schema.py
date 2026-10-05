"""Opt-in workflow records. Existing balances and trades are never migrated."""


def initialize(cursor):
    cursor.execute('''CREATE TABLE IF NOT EXISTS rebalance_plans (
        id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
        name TEXT NOT NULL, payload JSONB NOT NULL, cutoff BIGINT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        archived BOOLEAN NOT NULL DEFAULT FALSE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS rebalance_plan_links (
        plan_id TEXT NOT NULL REFERENCES rebalance_plans(id) ON DELETE CASCADE,
        line_no INTEGER NOT NULL CHECK(line_no >= 0),
        trade_id TEXT PRIMARY KEY REFERENCES trade_history(id) ON DELETE CASCADE)''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_rebalance_plans_scope ON rebalance_plans(portfolio_id,created_at DESC)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS performance_tracking (
        portfolio_id TEXT PRIMARY KEY REFERENCES portfolios(id) ON DELETE CASCADE,
        baseline_date DATE NOT NULL, baseline_value NUMERIC(28,8) NOT NULL CHECK(baseline_value>0),
        baseline_payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        revision BIGINT NOT NULL DEFAULT 0, confirmed_revision BIGINT NOT NULL DEFAULT -1,
        confirmed_through DATE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS performance_snapshots (
        portfolio_id TEXT NOT NULL REFERENCES performance_tracking(portfolio_id) ON DELETE CASCADE,
        snapshot_date DATE NOT NULL, value_krw NUMERIC(28,8) NOT NULL CHECK(value_krw>=0),
        payload JSONB NOT NULL, recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(portfolio_id,snapshot_date))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS performance_flows (
        id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL REFERENCES performance_tracking(portfolio_id) ON DELETE CASCADE,
        account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
        request_id TEXT NOT NULL, event_date DATE NOT NULL, amount_krw NUMERIC(28,8) NOT NULL,
        currency TEXT NOT NULL CHECK(currency IN ('KRW','USD')), native_amount NUMERIC(28,8) NOT NULL CHECK(native_amount>0),
        exchange_rate NUMERIC(28,8) NOT NULL CHECK(exchange_rate>0),
        notes TEXT NOT NULL DEFAULT '', voided BOOLEAN NOT NULL DEFAULT FALSE,
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(portfolio_id,request_id))''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_performance_flows_scope ON performance_flows(portfolio_id,event_date)')
