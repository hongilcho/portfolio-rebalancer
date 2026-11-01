"""Read history without writing NAVs; crypto captures are insert-once."""
from psycopg2.extras import Json
from data.repositories.holding_history_batch import read

def crypto_exists(ctx,day):
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute('SELECT 1 FROM portfolio_analytics.crypto_snapshots WHERE snapshot_date=%s',(day,))
        return c.fetchone() is not None

def capture_crypto(ctx,day,at,payload):
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute('''INSERT INTO portfolio_analytics.crypto_snapshots(snapshot_date,valuation_at,payload)
          VALUES(%s,%s,%s) ON CONFLICT(snapshot_date) DO NOTHING''',(day,at,Json(payload)))
        saved=c.rowcount==1;conn.commit();return saved
