"""Verify imported orders on a fresh loopback PostgreSQL, never production."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import sys
import threading
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
settings = json.loads((ROOT / 'backups/local_validation/local_connection.json').read_text())
if settings.get('host') != '127.0.0.1' or settings.get('port') != 55437 or settings.get('dbname') != 'postgres':
    raise ValueError('Only the dedicated local validation PostgreSQL is allowed')
admin = psycopg2.connect(**settings)
admin.autocommit = True
name = 'portfolio_import_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
with admin.cursor() as cursor:
    cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
admin.close()
settings['dbname'] = name
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0', SUPABASE_URL=make_dsn(**settings),
                  APP_PASSWORD='test-only', NAMUH_APP_KEY='', NAMUH_APP_SECRET='')
from data import data_manager as dm
dm.init_db()
with dm.get_connection() as conn:
    with conn.cursor() as c:
        c.execute("INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw,deposit_usd) VALUES('acc','QA-import','Synthetic IRP','IRP','default',100000,0)")
        c.execute('''INSERT INTO assets(id,name,ticker,market,portfolio_id,allowed_accounts)
            VALUES('ast','Synthetic import ETF','0085P0','KR','default','["acc"]')''')
    conn.commit()

def state():
    with dm.get_connection() as conn:
        with conn.cursor() as c:
            result = []
            for table in ('accounts','holdings','trade_history'):
                c.execute('SELECT * FROM '+table+' ORDER BY id')
                result.append(c.fetchall())
            return result

def record(order):
    return dm.execute_trade('2026-10-05','acc','ast','BUY',1,9320,'KRW',1,'NAMUH_KAKAO',order)

checks = []
def check(label, condition):
    if not condition: raise AssertionError(label)
    checks.append(label); print('PASS:', label)

barrier = threading.Barrier(2)
def simultaneous(_):
    barrier.wait(timeout=10)
    return record('42954')
with ThreadPoolExecutor(max_workers=2) as pool:
    outcomes = list(pool.map(simultaneous, range(2)))
check('concurrent identical orders create exactly one cash movement', sum(success for success,_ in outcomes) == 1)
with dm.get_connection() as conn:
    with conn.cursor() as c:
        c.execute("SELECT deposit_krw FROM accounts WHERE id='acc'")
        check('cash charged once using message execution price', c.fetchone()[0] == 90680)
        c.execute("SELECT quantity,avg_price FROM holdings WHERE account_id='acc' AND asset_id='ast'")
        check('one share stored at actual execution price', c.fetchone() == (1,9320))
        c.execute("SELECT import_source,broker_order_no FROM trade_history WHERE account_id='acc'")
        check('order identity persists for reload duplicate protection', c.fetchall() == [('NAMUH_KAKAO','42954')])
before = state()
check('retry rejects already registered order', not record('42954')[0] and state() == before)
with dm.get_connection() as conn:
    with conn.cursor() as c:
        c.execute('''CREATE FUNCTION reject_import_holdings() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'synthetic rollback test'; END $$''')
        c.execute('CREATE TRIGGER fail_import_update BEFORE UPDATE ON holdings FOR EACH ROW EXECUTE FUNCTION reject_import_holdings()')
    conn.commit()
check('failed holding write rolls back order identity and cash', not record('42955')[0] and state() == before)
with dm.get_connection() as conn:
    with conn.cursor() as c: c.execute('DROP TRIGGER fail_import_update ON holdings')
    conn.commit()
check('same order can be retried after rollback', record('42955')[0])
before = state()
dm.init_db(); dm.init_db()
check('schema migrations are idempotent and preserve existing rows', state() == before)
with dm.get_connection() as conn:
    with conn.cursor() as c:
        c.execute("SELECT id FROM trade_history WHERE broker_order_no='42955'")
        trade_id = c.fetchone()[0]
check('explicit deletion restores cash and releases order identity', dm.delete_trade(trade_id)[0] and record('42955')[0])
(ROOT / 'backups/local_validation/namuh_import_report.json').write_text(json.dumps({'local_database':name,'checks':checks},indent=2))
print('Verification completed:',len(checks),'checks')
