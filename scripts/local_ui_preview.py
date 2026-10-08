"""Synthetic browser QA backend: localhost PostgreSQL, fixed quotes, no market IO.

Requires the dedicated PostgreSQL server from predeploy verification.
This script is never imported by production; every run creates a fresh local DB.
"""
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sys
import argparse
import time

parser = argparse.ArgumentParser()
parser.add_argument('--trust-local-port',type=int,choices=[55438],help='New isolated loopback QA cluster; no private connection file is read')
parser.add_argument('--ledger-corrections',action='store_true',help='Synthetic historical cash errors for audited correction')
parser.add_argument('--port', type=int, default=8547)
parser.add_argument('--simulate-refresh', action='store_true')
parser.add_argument('--usd-ledger', action='store_true', help='Add synthetic USD cash and VT/PDBC opening positions')
parser.add_argument('--message-import', action='store_true', help='Add synthetic NH domestic full-buy message fixtures')
parser.add_argument('--workflow', action='store_true', help='Add synthetic maturity/workflow fixtures')
parser.add_argument('--closing', action='store_true', help='Add synthetic regular closing history; keep scheduler disabled')
parser.add_argument('--nh-notices', action='store_true', help='Synthetic NH deposit/FX/ISA fixtures, including an existing contribution')
parser.add_argument('--cash-transfers', action='store_true', help='Synthetic CMA and liquidity-pool transfer accounts')
args = parser.parse_args()
if args.ledger_corrections:args.cash_transfers=True
if args.cash_transfers: args.nh_notices=True
if args.nh_notices:
    args.usd_ledger = args.message_import = args.workflow = True

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn, parse_dsn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
settings = dict(host="127.0.0.1",port=args.trust_local_port,dbname="postgres",user="ledger_qa") if args.trust_local_port else json.loads((ROOT / "backups/local_validation/local_connection.json").read_text())
if settings.get("host") != "127.0.0.1" or settings.get("port") not in (55437,55438):
    raise RuntimeError("Only the dedicated loopback PostgreSQL is allowed")
name = "portfolio_ui_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
admin = psycopg2.connect(**settings)
admin.autocommit = True
with admin.cursor() as cursor:
    cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
admin.close()
settings["dbname"] = name
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES="0", SUPABASE_URL=make_dsn(**settings),
                  PERFORMANCE_CLOSE_SCHEDULER_ENABLED="0",
                  APP_PASSWORD="ui-test-only", NAMUH_APP_KEY="", NAMUH_APP_SECRET="")

# Explicitly prevent accidental production connections and external market IO.
original_connect = psycopg2.connect
def guarded_connect(dsn=None, *args, **kwargs):
    parsed = parse_dsn(dsn) if dsn else {}
    parsed.update(kwargs)
    if parsed.get("host") != "127.0.0.1" or str(parsed.get("port")) != str(settings["port"]):
        raise RuntimeError("UI preview cannot connect to a remote database")
    return original_connect(dsn, *args, **kwargs)
psycopg2.connect = guarded_connect

def blocked_http(*args, **kwargs):
    raise RuntimeError("UI preview cannot call external market APIs")
import requests
from curl_cffi import requests as curl_requests
requests.sessions.Session.request = blocked_http
curl_requests.Session.request = blocked_http

from data import data_manager as dm
dm.init_db()
with dm.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("UPDATE portfolios SET name='브라우저 검증 KR' WHERE id='default'")
        cursor.execute("INSERT INTO portfolios (id,name) VALUES ('cash_only','달러 현금만 검증')")
        cursor.execute("""INSERT INTO accounts (id,account_no,account_alias,account_type,deposit_krw,deposit_usd,portfolio_id)
            VALUES ('qa_acc','QA-001','검증 ISA','ISA',1000000,100,'default'),
                   ('qa_cash','QA-002','현금 검증','GENERAL',0,100,'cash_only')""")
        cursor.execute("""INSERT INTO assets (id,name,ticker,market,target_weight,allowed_accounts,portfolio_id)
            VALUES ('qa_asset','검증 ETF','QA_ETF','KR',100,'["qa_acc"]','default')""")
        cursor.execute("UPDATE crypto_holdings SET quantity=0.01,avg_price=1000000 WHERE owner='홍일' AND symbol='BTC'")
    conn.commit()
assert dm.execute_trade('2026-01-01','qa_acc','qa_asset','INIT',10,100000,'KRW',1)[0]
if args.message_import:
    with dm.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE accounts SET account_no='212-03-521234',account_alias='검증 IRP',account_type='IRP' WHERE id='qa_acc'")
            cursor.execute('''INSERT INTO assets (id,name,ticker,market,target_weight,allowed_accounts,portfolio_id)
                VALUES ('qa_nh_bond','ACE 미국10년국채액티브','0085P0','KR',20,'["qa_acc"]','default'),
                       ('qa_nh_stock','TIGER 미국S&P500','360750','KR',20,'["qa_acc"]','default')''')
        conn.commit()
if args.usd_ledger:
    with dm.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE accounts SET deposit_krw=5000000,deposit_usd=400 WHERE id='qa_acc'")
            cursor.execute('''INSERT INTO assets (id,name,ticker,market,target_weight,allowed_accounts,portfolio_id)
                VALUES ('qa_vt','Vanguard Total World Stock ETF','VT','US',20,'["qa_acc"]','default'),
                       ('qa_pdbc','Invesco PDBC','PDBC','US',10,'["qa_acc"]','default')''')
        conn.commit()
    assert dm.execute_trade('2026-01-01','qa_acc','qa_vt','INIT',5,100,'USD',1250)[0]
    assert dm.execute_trade('2026-01-01','qa_acc','qa_pdbc','INIT',10,20,'USD',1350)[0]

if args.workflow:
    today = (datetime.now(timezone.utc) + timedelta(hours=9)).date()
    with dm.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE assets SET target_weight=60 WHERE id='qa_asset'")
            cursor.execute('''INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id,is_deposit,
                deposit_principal,interest_rate,start_date,maturity_date,tax_rate,is_risk_asset,include_in_rebalance)
                VALUES('qa_deposit','검증 정기예금','-','KR','["qa_acc"]','default',TRUE,1000000,4,%s,%s,15.4,0,FALSE)''',
                (str(today-timedelta(days=355)), str(today+timedelta(days=10))))
        conn.commit()
    assert dm.execute_trade(str(today),'qa_acc','qa_deposit','INIT',1,1000000,'KRW',1)[0]

from backend import main
from backend.services import market_service
from backend.routers import crypto, portfolios
from logic import dividend_fetcher

quotes = [{"id":"qa_asset", "name":"검증 ETF", "ticker":"QA_ETF", "market":"KR",
           "price_krw":110000, "price_usd":0, "source":"고정 검증 시세"}]
if args.message_import:
    quotes.extend([{'id':'qa_nh_bond','name':'ACE 미국10년국채액티브','ticker':'0085P0','market':'KR','price_krw':9000,'price_usd':0,'source':'고정 검증 시세'},
                   {'id':'qa_nh_stock','name':'TIGER 미국S&P500','ticker':'360750','market':'KR','price_krw':20000,'price_usd':0,'source':'고정 검증 시세'}])
if args.usd_ledger:
    quotes.extend([{'id': 'qa_vt', 'name': 'Vanguard Total World Stock ETF', 'ticker': 'VT', 'market': 'US', 'price_usd': 100, 'price_krw': 140000, 'source': '고정 검증 시세'},
                   {'id': 'qa_pdbc', 'name': 'Invesco PDBC', 'ticker': 'PDBC', 'market': 'US', 'price_usd': 20, 'price_krw': 28000, 'source': '고정 검증 시세'}])
if args.workflow:
    from logic.price_fetcher import calculate_deposit_price
    dep = next(a for a in dm.get_all_assets() if a['id']=='qa_deposit')
    quotes.append({'id':'qa_deposit','name':'검증 정기예금','ticker':'-','market':'KR',
                   'price_krw':calculate_deposit_price(dep)[0], 'price_usd':0,'source':'검증 예금 계산'})
crypto_quotes = {"BTC":{"price":1200000,"source":"고정 검증 시세"},
                 "ETH":{"price":0,"source":"고정 검증 시세"}}
market_service.price_data = quotes
market_service.usd_krw = 1400
market_service.rate_source = "고정 검증 환율"
market_service.get_prices = lambda **_: (quotes, {q['id']: q['price_krw'] for q in quotes})
if args.workflow:
    market_service.request_status = lambda: {'updated_at':datetime.now(timezone.utc).isoformat(), 'stale':False,'refreshing':False,'refresh_failed':False}
market_service.warmup = lambda: None
dividend_fetcher.fetch_dividend_history = lambda *_: [{"date":"2026-02-01","amount":5000}]
for module in (main, crypto, portfolios):
    module.get_crypto_prices = lambda **_: crypto_quotes

if args.simulate_refresh:
    from logic import crypto_price_fetcher
    from backend.services import MarketStateService
    market_service.get_prices = MarketStateService.get_prices.__get__(market_service)
    market_service._cache.seed({'prices': quotes, 'usd_krw': 1400, 'rate_source': '고정 검증 환율'}, time.time()-400)
    simulation = {'fail': False, 'delay': 3}
    def delayed_market():
        time.sleep(simulation['delay'])
        if simulation['fail']:
            raise RuntimeError('Synthetic provider offline')
        return {'prices': [{**quotes[0], 'price_krw': 120000}], 'usd_krw': 1400, 'rate_source': '갱신된 검증 환율'}
    market_service._cache.fetch = delayed_market
    crypto_price_fetcher._crypto_snapshots.seed(crypto_quotes, time.time()-120)
    def delayed_crypto():
        time.sleep(simulation['delay'])
        if simulation['fail']:
            raise RuntimeError('Synthetic provider offline')
        return {**crypto_quotes, 'BTC': {**crypto_quotes['BTC'], 'price': 1300000}}
    crypto_price_fetcher._crypto_snapshots.fetch = delayed_crypto
    for module in (main, crypto, portfolios):
        module.get_crypto_prices = crypto_price_fetcher.get_crypto_prices

    @main.app.post('/qa/reset-cache')
    def reset_qa_cache(fail: bool = False, delay: float = 3):
        simulation['fail'] = fail
        simulation['delay'] = max(0, min(delay, 20))
        for cache, value, age in (
            (market_service._cache, {'prices': quotes, 'usd_krw': 1400, 'rate_source': '고정 검증 환율'}, 400),
            (crypto_price_fetcher._crypto_snapshots, crypto_quotes, 120),
        ):
            with cache.condition:
                if cache.refreshing:
                    raise RuntimeError('Wait for the current QA refresh')
                cache.seed(value, time.time()-age)
                cache.last_error, cache.retry_at = False, 0
        return {'ok': True}

if __name__ == '__main__':
    if args.nh_notices:
        from backend.close_performance import context
        from data.repositories import performance
        from backend.performance_valuation import current_nav
        today = (datetime.now(timezone.utc)+timedelta(hours=9)).date()
        with dm.get_connection() as conn, conn.cursor() as cursor:
            cursor.execute("UPDATE portfolios SET name='NH 알림 합성 검증' WHERE id='default'")
            cursor.execute("UPDATE accounts SET account_no='123-45-671231',account_alias='검증 VT 계좌',account_type='GENERAL',deposit_krw=4,deposit_usd=10 WHERE id='qa_acc'")
            cursor.execute("INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw,deposit_usd) VALUES('qa_isa','123-45-671232','검증 ISA','ISA','default',190000,0)")
            cursor.execute("UPDATE assets SET allowed_accounts='[\"qa_isa\"]' WHERE id='qa_nh_bond'")
            conn.commit()
        if args.cash_transfers:
            with dm.get_connection() as conn,conn.cursor() as cursor:
                cursor.execute("UPDATE portfolios SET name='미래 성장포트 · 검증용' WHERE id='default'")
                cursor.execute("INSERT INTO portfolios(id,name) VALUES('qa_pool','유동성 Pool · 검증용')")
                cursor.execute('''INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw)
                    VALUES('qa_cma','123-45-679991','검증 CMA','GENERAL','default',38239177),
                    ('qa_pool_cash','123-45-679992','검증 유동성 계좌','GENERAL','qa_pool',1000000)''')
                conn.commit()
            performance.capture(context(),'qa_pool',1000000,{},start=True)
        assert dm.record_usd_event('qa_acc','OPENING',str(today)+'T09:00:00+09:00',rate=1300)[0]
        performance.capture(context(),'default',current_nav(dm.get_rebalance_batch_data('default'),
            {q['id']:q['price_krw'] for q in quotes},1400),{'source':'QA synthetic baseline'},start=True)
        performance.add_flow(context(),'default',dict(request_id='QA-existing-deposit',account_id='qa_acc',
            event_date=today,direction='DEPOSIT',currency='KRW',native_amount=960000,exchange_rate=1,notes='이미 기록된 합성 입금'))
    if args.ledger_corrections:
        from psycopg2.extras import Json
        from datetime import date
        # Read-only broker comparison demonstration; no real broker HTTP calls.
        from backend.routers import sync
        def qa_broker(account_no):
            if account_no=='123-45-679991':return {'deposit_krw':37239177},None
            if account_no=='123-45-671231':return {'deposit_krw':4,'deposit_usd':10},None
            return None,'QA account unsupported'
        sync.nh_api_client.fetch_account_balance=qa_broker
        sync.nh_api_client.fetch_full_account_balance=qa_broker
        ledger=dm.get_rebalance_batch_data('default')
        frozen={'ledger':ledger,'fx':{'rate':1400},'prices':{q['id']:{'price_krw':q['price_krw']} for q in quotes},'baseline_kind':'close','source':'QA synthetic record'}
        nav=current_nav(ledger,{q['id']:q['price_krw'] for q in quotes},1400)
        with dm.get_connection() as conn,conn.cursor() as c:
            c.execute("DELETE FROM performance_snapshots WHERE portfolio_id='default'")
            c.execute("UPDATE performance_tracking SET baseline_date='2026-10-05',close_started_on='2026-10-06',baseline_value=%s,baseline_payload=%s WHERE portfolio_id='default'",(nav,Json(frozen)))
            for n in (5,6,7):
                c.execute("INSERT INTO performance_snapshots(portfolio_id,snapshot_date,value_krw,payload,record_kind) VALUES('default',%s,%s,%s,%s)",(date(2026,10,n),nav,Json(frozen),'baseline' if n==5 else 'close'))
            conn.commit()
    if args.closing:
        from backend.close_performance import ClosePerformance, context
        from data.repositories import performance, close_jobs
        from logic.close_calendar import KST, previous_session, cutoff, us_session
        from backend.performance_valuation import current_nav
        from datetime import date
        base = date(2026,9,29)
        actual_today = performance.today
        performance.today = lambda: base
        performance.capture(context(),'default',current_nav(dm.get_rebalance_batch_data('default'),
            {q['id']:q['price_krw'] for q in quotes},1400),{'source':'QA synthetic baseline'},start=True)
        performance.today = actual_today
        with dm.get_connection() as conn, conn.cursor() as cursor:
            cursor.execute("UPDATE portfolios SET name='종가 기록 합성 검증' WHERE id='default'")
            cursor.execute("UPDATE performance_tracking SET created_at='2026-09-29T14:00:00+09:00',close_started_on='2026-09-30' WHERE portfolio_id='default'")
            conn.commit()
        class SyntheticCloses:
            def exchange_rate(self, now):
                return {'rate':1400,'source':'QA 합성 환율','published_at':now.isoformat(),'collected_at':now.isoformat()}
            def asset(self, a, day, fx):
                price = calculate_deposit_price(a,day)[0] if a.get('is_deposit') else next(q['price_krw'] for q in quotes if q['id']==a['id']) * {date(2026,9,30):0.98,date(2026,10,1):1.01,date(2026,10,2):1.03}[day]
                return {'id':a['id'],'ticker':a['ticker'],'price_krw':price,
                    'price_date':str(us_session(cutoff(day)) if a['market']=='US' else day),'source':'QA 합성 종가 (실제 투자자료 아님)'}
        for day in (date(2026,9,30),date(2026,10,1),date(2026,10,2)):
            now = cutoff(day)
            worker = ClosePerformance(prices=SyntheticCloses(),now=lambda:now)
            worker.schedule(now,'default')
            with dm.get_connection() as conn, conn.cursor() as cursor:
                cursor.execute("UPDATE performance_close_jobs SET next_attempt_at=%s WHERE portfolio_id='default' AND snapshot_date=%s",(now,day))
                conn.commit()
            assert worker.tick('default')
        # No daily/manual confirmation: recorded flows alone drive returns.
    import uvicorn
    print(f"Synthetic QA backend: http://127.0.0.1:{args.port}; local DB:",name, flush=True)
    uvicorn.run(main.app, host='127.0.0.1', port=args.port)
