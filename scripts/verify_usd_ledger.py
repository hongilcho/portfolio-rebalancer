"""Verify USD journal transactions and locks on a fresh loopback PostgreSQL DB.

Requires the dedicated server and ignored local_connection.json prepared by
verify_postgres.py. Never reads production settings or makes market requests.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import threading

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn, parse_dsn
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOCAL = ROOT / 'backups/local_validation'
settings = json.loads((LOCAL / 'local_connection.json').read_text())
if settings.get('host') != '127.0.0.1' or settings.get('port') != 55437 or settings.get('dbname') != 'postgres':
    raise RuntimeError('Only the dedicated loopback PostgreSQL is allowed')
name = 'portfolio_usd_verify_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
admin = psycopg2.connect(**settings)
admin.autocommit = True
with admin.cursor() as cursor:
    cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
admin.close()
settings['dbname'] = name
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0', SUPABASE_URL=make_dsn(**settings),
                  NAMUH_APP_KEY='', NAMUH_APP_SECRET='')
original_connect = psycopg2.connect


def guarded_connect(dsn=None, *args, **kwargs):
    parsed = parse_dsn(dsn) if dsn else {}
    parsed.update(kwargs)
    if parsed.get('host') != '127.0.0.1' or str(parsed.get('port')) != '55437':
        raise RuntimeError('USD verification cannot connect to a remote database')
    return original_connect(dsn, *args, **kwargs)


psycopg2.connect = guarded_connect
def blocked_http(*args, **kwargs):
    raise RuntimeError('USD verification cannot call external market APIs')

import requests
from curl_cffi import requests as curl_requests
requests.sessions.Session.request = blocked_http
curl_requests.Session.request = blocked_http
from data import data_manager as dm
dm.init_db()


def query(statement, params=()):
    with dm.get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(statement, params)
            rows = [dict(row) for row in cursor.fetchall()] if cursor.description else []
        conn.commit()
        return rows


def require(value, message='Accounting check failed'):
    if not value:
        raise AssertionError(message)


report = {'local_database': name, 'checks': []}


def check(label, function):
    function()
    report['checks'].append(label)
    print('PASS:', label, flush=True)


query("INSERT INTO accounts (id,account_no,account_alias,account_type,deposit_krw,deposit_usd,portfolio_id) VALUES ('usd','QA-USD','USD QA','GENERAL',5000000,400,'default')")
query("INSERT INTO assets (id,name,ticker,market,portfolio_id) VALUES ('vt','VT QA','VT','US','default'),('pdbc','PDBC QA','PDBC','US','default')")
require(dm.execute_trade('2026-01-01', 'usd', 'vt', 'INIT', 5, 100, 'USD', 1250)[0])
query("UPDATE holdings SET first_buy_date='2026-01-01',manual_dividend_override=12345 WHERE account_id='usd'")


def holdings():
    return query("SELECT * FROM holdings WHERE account_id='usd' ORDER BY asset_id")


def snapshot():
    return {table: query('SELECT * FROM ' + table + ' ORDER BY ' + ('sequence' if table == 'usd_cash_events' else 'account_id' if table == 'usd_cash_state' else 'id'))
            for table in ('accounts', 'holdings', 'trade_history', 'usd_cash_state', 'usd_cash_events')}


def cash(kind, **kwargs):
    result = dm.record_usd_event('usd', kind, '2026-01-02T09:00+09:00', **kwargs)
    require(result[0], result[1])
    return dm.get_usd_events('usd')[0]['id']


def parallel(function):
    barrier = threading.Barrier(2)
    def task(_):
        barrier.wait(timeout=10)
        return function()
    with ThreadPoolExecutor(max_workers=2) as workers:
        return list(workers.map(task, range(2)))


baseline = holdings()
cash('OPENING', rate=1300)
check('opening preserves accepted holdings and dividend metadata', lambda: require(holdings() == baseline))


def concurrent_buy():
    results = parallel(lambda: dm.execute_trade('2026-01-02', 'usd', 'vt', 'BUY', 3, 100, 'USD', None))
    require(sum(result[0] for result in results) == 1)
    ledger = dm.get_usd_ledgers('default')[0]
    require(float(ledger['actual_usd']) == float(ledger['usd_balance']) == 100)
    require(float(ledger['cost_krw']) == 130000)
    require(query("SELECT exchange_rate FROM trade_history WHERE trade_type='BUY'")[0]['exchange_rate'] == 1300)


check('concurrent managed buys cannot overspend and need no market FX request', concurrent_buy)
trade_id = query("SELECT id FROM trade_history WHERE trade_type='BUY'")[0]['id']


def concurrent_undo():
    results = parallel(lambda: dm.delete_trade(trade_id))
    require(sum(result[0] for result in results) == 1)
    require(holdings() == baseline)
    require(float(dm.get_usd_ledgers()[0]['actual_usd']) == 400)
    records = dm.get_usd_events('usd')
    require(records[0]['reversed_at'] and records[0]['trade_reference'] == trade_id and records[0]['trade_id'] is None)


check('concurrent undo restores cash once and retains canceled history', concurrent_undo)


def exchange_and_buy():
    cash('EXCHANGE_IN', usd_amount=600, krw_amount=840000)
    require(dm.get_usd_ledgers()[0]['average_rate'] == 1360)
    require(dm.execute_trade('2026-01-02', 'usd', 'vt', 'BUY', 7, 100, 'USD', 9999)[0])
    holding = holdings()[0]
    require(abs(holding['original_avg_price'] * 12 - 1577000) < 1e-6)
    require(holding['first_buy_date'] == baseline[0]['first_buy_date'] and holding['manual_dividend_override'] == 12345)


check('exchange net cash and old holding cost combine using funding average', exchange_and_buy)


def later_event_blocks_delete():
    cash('DEPOSIT', usd_amount=50, rate=1400)
    before = snapshot()
    trade = query("SELECT id FROM trade_history WHERE trade_type='BUY'")[0]['id']
    require(not dm.delete_trade(trade)[0])
    require(snapshot() == before)


check('a later cash event blocks trade removal without partial writes', later_event_blocks_delete)


def rollback_failure():
    query("CREATE FUNCTION qa_reject_journal() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic journal failure'; END $$")
    query('CREATE TRIGGER qa_reject_journal BEFORE INSERT ON usd_cash_events FOR EACH ROW EXECUTE FUNCTION qa_reject_journal()')
    before = snapshot()
    require(not dm.execute_trade('2026-01-02', 'usd', 'pdbc', 'BUY', 1, 20, 'USD', 1400)[0])
    require(not dm.record_usd_event('usd', 'EXCHANGE_IN', '2026-01-02T10:00+09:00', 10, 14000)[0])
    require(snapshot() == before)
    query('DROP TRIGGER qa_reject_journal ON usd_cash_events')
    query('DROP FUNCTION qa_reject_journal()')


check('journal insertion failure rolls back holdings, history and both cash balances', rollback_failure)


def sync_and_reconcile():
    before_holding = holdings()
    rows = [dict(ticker='VT', quantity=12, avg_price=999999, avg_price_usd=9999, buy_fx_rate=9999)]
    require(dm.sync_account_with_api('usd', dict(deposit_krw=4160000, deposit_usd=355, holdings=rows))[0])
    require(holdings() == before_holding)
    require(dm.get_usd_ledgers()[0]['needs_reconciliation'])
    before = snapshot()
    require(not dm.execute_trade('2026-01-02', 'usd', 'pdbc', 'BUY', 1, 20, 'USD', 1400)[0])
    require(snapshot() == before)
    cash('RECONCILE', rate=1375)
    require(float(dm.get_usd_ledgers()[0]['actual_usd']) == 355)
    require(not dm.get_usd_ledgers()[0]['needs_reconciliation'] and holdings() == before_holding)
    rows[0]['quantity'] = 13
    before = snapshot()
    require(not dm.sync_account_with_api('usd', dict(deposit_krw=0, deposit_usd=0, holdings=rows))[0])
    require(snapshot() == before)


check('broker sync preserves US cost, exposes cash drift and rejects quantity drift', sync_and_reconcile)


def sell_proceeds():
    cash('WITHDRAW', usd_amount=355)
    before = holdings()
    require(dm.execute_trade('2026-01-02', 'usd', 'vt', 'SELL', 2, 120, 'USD', 1500)[0])
    ledger = dm.get_usd_ledgers()[0]
    require(float(ledger['actual_usd']) == 240 and float(ledger['cost_krw']) == 360000)
    require(dm.undo_usd_event('usd', dm.get_usd_events('usd')[0]['id'])[0])
    require(holdings() == before)


check('sale at zero USD credits USD at explicit receipt valuation and undoes exactly', sell_proceeds)


def full_sale_sync_undo():
    before = holdings()
    require(dm.execute_trade('2026-01-02', 'usd', 'vt', 'SELL', 12, 120, 'USD', 1500)[0])
    require(dm.sync_account_with_api('usd', dict(deposit_krw=4160000, deposit_usd=1440, holdings=[]))[0])
    require(len(holdings()) == len(before) and holdings()[0]['manual_dividend_override'] == 12345)
    require(dm.undo_usd_event('usd', dm.get_usd_events('usd')[0]['id'])[0])
    require(holdings() == before)


check('sync after full liquidation retains metadata needed for exact sale undo', full_sale_sync_undo)
(LOCAL / 'usd_ledger_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(f'Verification completed: {len(report["checks"])} checks', flush=True)
