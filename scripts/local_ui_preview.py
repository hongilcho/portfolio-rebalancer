"""Synthetic browser QA backend: localhost PostgreSQL, fixed quotes, no market IO.

Requires the dedicated PostgreSQL server from predeploy verification.
This script is never imported by production; every run creates a fresh local DB.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import argparse
import time

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=8547)
parser.add_argument('--simulate-refresh', action='store_true')
args = parser.parse_args()

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn, parse_dsn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
settings = json.loads((ROOT / "backups/local_validation/local_connection.json").read_text())
if settings.get("host") != "127.0.0.1" or settings.get("port") != 55437:
    raise RuntimeError("Only the dedicated loopback PostgreSQL is allowed")
name = "portfolio_ui_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
admin = psycopg2.connect(**settings)
admin.autocommit = True
with admin.cursor() as cursor:
    cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
admin.close()
settings["dbname"] = name
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES="0", SUPABASE_URL=make_dsn(**settings),
                  APP_PASSWORD="ui-test-only", NAMUH_APP_KEY="", NAMUH_APP_SECRET="")

# Explicitly prevent accidental production connections and external market IO.
original_connect = psycopg2.connect
def guarded_connect(dsn=None, *args, **kwargs):
    parsed = parse_dsn(dsn) if dsn else {}
    parsed.update(kwargs)
    if parsed.get("host") != "127.0.0.1" or str(parsed.get("port")) != "55437":
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

from backend import main
from backend.services import market_service
from backend.routers import crypto, portfolios
from logic import dividend_fetcher

quotes = [{"id":"qa_asset", "name":"검증 ETF", "ticker":"QA_ETF", "market":"KR",
           "price_krw":110000, "price_usd":0, "source":"고정 검증 시세"}]
crypto_quotes = {"BTC":{"price":1200000,"source":"고정 검증 시세"},
                 "ETH":{"price":0,"source":"고정 검증 시세"}}
market_service.price_data = quotes
market_service.usd_krw = 1400
market_service.rate_source = "고정 검증 환율"
market_service.get_prices = lambda **_: (quotes, {"qa_asset":110000})
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
    import uvicorn
    print(f"Synthetic QA backend: http://127.0.0.1:{args.port}; local DB:",name, flush=True)
    uvicorn.run(main.app, host='127.0.0.1', port=args.port)
