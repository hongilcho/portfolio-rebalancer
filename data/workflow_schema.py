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
