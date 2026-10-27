"""Private crypto valuation history; public financial records are unchanged."""
def initialize(c):
    c.execute('CREATE SCHEMA IF NOT EXISTS portfolio_analytics')
    c.execute("""DO $$ BEGIN
      IF (SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='portfolio_analytics')<>current_user THEN
        RAISE EXCEPTION 'Analytics schema ownership differs';
      END IF;
    END $$""")
    c.execute('''CREATE TABLE IF NOT EXISTS portfolio_analytics.crypto_snapshots(
      snapshot_date DATE PRIMARY KEY,valuation_at TIMESTAMPTZ NOT NULL,
      payload JSONB NOT NULL,recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    c.execute("""DO $$ BEGIN
      IF (SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='portfolio_analytics.crypto_snapshots'::regclass)<>current_user THEN
        RAISE EXCEPTION 'Analytics table ownership differs';
      END IF;
    END $$""")
    c.execute('REVOKE ALL ON SCHEMA portfolio_analytics FROM PUBLIC')
    c.execute('REVOKE ALL ON portfolio_analytics.crypto_snapshots FROM PUBLIC')
    c.execute('ALTER TABLE portfolio_analytics.crypto_snapshots ENABLE ROW LEVEL SECURITY')
    c.execute("""DO $$ DECLARE r text; BEGIN
      FOR r IN SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role') LOOP
        EXECUTE format('REVOKE ALL ON SCHEMA portfolio_analytics FROM %I',r);
        EXECUTE format('REVOKE ALL ON portfolio_analytics.crypto_snapshots FROM %I',r);
      END LOOP;
    END $$""")
