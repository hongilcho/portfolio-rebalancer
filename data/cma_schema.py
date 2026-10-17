"""Prepared private CMA ledger schema. Caller must explicitly initialize it."""


def initialize(cursor):
    cursor.execute('CREATE SCHEMA IF NOT EXISTS portfolio_cma')
    cursor.execute('''DO $$ BEGIN
        IF (SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='portfolio_cma')<>current_user THEN
            RAISE EXCEPTION 'CMA schema must be owned by the application database owner';
        END IF;
        IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='portfolio_cma' AND c.relkind IN ('r','S')
            AND pg_get_userbyid(c.relowner)<>current_user) THEN
            RAISE EXCEPTION 'CMA records have unexpected ownership';
        END IF;
    END $$''')
    cursor.execute('REVOKE ALL ON SCHEMA portfolio_cma FROM PUBLIC')
    cursor.execute('''CREATE TABLE IF NOT EXISTS portfolio_cma.observations (
        id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL REFERENCES public.portfolios(id),
        account_id TEXT NOT NULL REFERENCES public.accounts(id), observed_at TIMESTAMPTZ NOT NULL,
        book_token TEXT NOT NULL, evidence JSONB NOT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS portfolio_cma.income (
        id TEXT PRIMARY KEY, sequence BIGSERIAL UNIQUE, portfolio_id TEXT NOT NULL REFERENCES public.portfolios(id),
        account_id TEXT NOT NULL REFERENCES public.accounts(id), request_id TEXT NOT NULL,
        observation_id TEXT NOT NULL REFERENCES portfolio_cma.observations(id), event_date DATE NOT NULL,
        amount_krw NUMERIC(28,8) NOT NULL CHECK(amount_krw>0), before_cash NUMERIC(28,8) NOT NULL,
        after_cash NUMERIC(28,8) NOT NULL, after_token TEXT NOT NULL, details JSONB NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, reversed_at TIMESTAMPTZ,
        UNIQUE(account_id,event_date), UNIQUE(observation_id,event_date), UNIQUE(portfolio_id,request_id,event_date))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS portfolio_cma.openings (
        id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL REFERENCES public.portfolios(id),
        account_id TEXT NOT NULL UNIQUE REFERENCES public.accounts(id), request_id TEXT NOT NULL,
        observation_id TEXT NOT NULL REFERENCES portfolio_cma.observations(id), recognized_on DATE NOT NULL,
        amount_krw NUMERIC(28,8) NOT NULL CHECK(amount_krw>0), before_cash NUMERIC(28,8) NOT NULL,
        after_cash NUMERIC(28,8) NOT NULL, after_token TEXT NOT NULL, reason TEXT NOT NULL,
        details JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, reversed_at TIMESTAMPTZ,
        UNIQUE(portfolio_id,request_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS portfolio_cma.settings (
        account_id TEXT PRIMARY KEY REFERENCES public.accounts(id), portfolio_id TEXT NOT NULL REFERENCES public.portfolios(id),
        enabled BOOLEAN NOT NULL DEFAULT FALSE, auto_apply BOOLEAN NOT NULL DEFAULT FALSE,
        max_auto_interest NUMERIC(28,8) NOT NULL DEFAULT 0 CHECK(max_auto_interest>=0),
        movements_confirmed BOOLEAN NOT NULL DEFAULT FALSE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS portfolio_cma.checks (
        account_id TEXT NOT NULL REFERENCES public.accounts(id), event_date DATE NOT NULL, slot INTEGER NOT NULL,
        state TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(account_id,event_date,slot))''')
    for table in ('observations','income','openings','settings','checks'):
        cursor.execute(f'ALTER TABLE portfolio_cma.{table} ENABLE ROW LEVEL SECURITY')
        cursor.execute(f'REVOKE ALL ON TABLE portfolio_cma.{table} FROM PUBLIC')
    cursor.execute('CREATE INDEX IF NOT EXISTS cma_observation_scope ON portfolio_cma.observations(account_id,observed_at DESC)')
    cursor.execute('REVOKE ALL ON ALL SEQUENCES IN SCHEMA portfolio_cma FROM PUBLIC')
    # Do not grant Data API roles access to financial observations or journals.
    cursor.execute('''DO $$ DECLARE role_name TEXT; BEGIN
        FOREACH role_name IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
            IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
                EXECUTE format('REVOKE ALL ON SCHEMA portfolio_cma FROM %I',role_name);
                EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA portfolio_cma FROM %I',role_name);
                EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA portfolio_cma FROM %I',role_name);
            END IF;
        END LOOP;
    END $$''')
