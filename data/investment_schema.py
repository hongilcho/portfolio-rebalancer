"""Private workflow metadata. Financial records remain in their original tables."""
TABLES = ('cycles', 'steps', 'attempts', 'results', 'record_links')

def initialize(c):
    c.execute("SELECT 1 FROM pg_namespace WHERE nspname='portfolio_execution'")
    if not c.fetchone(): c.execute('CREATE SCHEMA IF NOT EXISTS portfolio_execution')
    c.execute("""DO $$ BEGIN
      IF (SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='portfolio_execution')<>current_user THEN
        RAISE EXCEPTION 'Execution schema must be owned by the application database owner';
      END IF;
    END $$""")
    c.execute("""CREATE TABLE IF NOT EXISTS portfolio_execution.cycles(
      id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL REFERENCES public.portfolios(id),
      plan_id TEXT NOT NULL UNIQUE REFERENCES public.rebalance_plans(id), name TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','PAUSED','CLOSED')),
      revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0), request_id TEXT NOT NULL,
      payload JSONB NOT NULL, report JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(portfolio_id,request_id))""")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS execution_one_open ON portfolio_execution.cycles(portfolio_id) WHERE status<>'CLOSED'")
    c.execute("""CREATE TABLE IF NOT EXISTS portfolio_execution.steps(
      id TEXT PRIMARY KEY,cycle_id TEXT NOT NULL REFERENCES portfolio_execution.cycles(id),
      ordinal INTEGER NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('DEPOSIT','WITHDRAW','TRANSFER','EXCHANGE_IN','BUY','SELL')),
      payload JSONB NOT NULL, UNIQUE(cycle_id,ordinal))""")
    c.execute("""CREATE TABLE IF NOT EXISTS portfolio_execution.attempts(
      id TEXT PRIMARY KEY,step_id TEXT NOT NULL REFERENCES portfolio_execution.steps(id),
      source TEXT NOT NULL CHECK(source IN ('MANUAL','NH_NOTICE','EXISTING','MOCK_API')),
      request_key TEXT NOT NULL UNIQUE,status TEXT NOT NULL CHECK(status IN ('RECORDED','REVIEW','CANCELLED')),
      evidence JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS portfolio_execution.results(
      id TEXT PRIMARY KEY,attempt_id TEXT NOT NULL REFERENCES portfolio_execution.attempts(id),
      step_id TEXT NOT NULL REFERENCES portfolio_execution.steps(id),
      payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS portfolio_execution.record_links(
      id TEXT PRIMARY KEY,result_id TEXT NOT NULL REFERENCES portfolio_execution.results(id),
      record_kind TEXT NOT NULL CHECK(record_kind IN ('TRADE','USD','NOTICE')),
      record_id TEXT NOT NULL,released_at TIMESTAMPTZ,release_reason TEXT NOT NULL DEFAULT '')""")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS execution_record_once ON portfolio_execution.record_links(record_kind,record_id) WHERE released_at IS NULL")
    c.execute("CREATE INDEX IF NOT EXISTS execution_cycles_history ON portfolio_execution.cycles(portfolio_id,created_at DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS execution_attempt_steps ON portfolio_execution.attempts(step_id)")
    c.execute("CREATE INDEX IF NOT EXISTS execution_results_steps ON portfolio_execution.results(step_id)")
    # Independently private even when legacy public hardening is disabled locally.
    c.execute('REVOKE ALL ON SCHEMA portfolio_execution FROM PUBLIC')
    for table in TABLES:
        c.execute(f'ALTER TABLE portfolio_execution.{table} ENABLE ROW LEVEL SECURITY')
        c.execute(f'REVOKE ALL ON TABLE portfolio_execution.{table} FROM PUBLIC')
    c.execute("""DO $$ DECLARE r text; BEGIN
      FOR r IN SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role') LOOP
        EXECUTE format('REVOKE ALL ON SCHEMA portfolio_execution FROM %I',r);
        EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA portfolio_execution FROM %I',r);
      END LOOP;
    END $$""")
