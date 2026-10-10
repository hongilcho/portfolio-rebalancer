"""Run an existing verified production-data COPY on loopback; no external IO."""
import argparse
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import time
import psycopg2
from psycopg2.extensions import make_dsn,parse_dsn

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8568);args=parser.parse_args()
info=json.loads((ROOT/'backups/local_rehearsal/current.json').read_text(encoding='utf-8'))
name=info['database']
if not name.startswith('portfolio_rehearsal_'):raise RuntimeError('Only verified rehearsal DBs allowed')
metadata_path=Path(info['directory'])/'metadata.json'
if not metadata_path.is_absolute():metadata_path=ROOT/metadata_path
metadata=json.loads(metadata_path.read_text(encoding='utf-8'))
if not metadata.get('all_table_values_match'):raise RuntimeError('Snapshot verification required')
settings=dict(host='127.0.0.1',port=55438,dbname=name,user='ledger_qa',password='',passfile='NUL',sslmode='disable',connect_timeout=5)
for key in list(os.environ):
    if key.startswith('PG'):os.environ.pop(key,None)
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0',SUPABASE_URL=make_dsn(**settings),SUPABASE_SESSION_URL='',
    PORTFOLIO_DB_SECURITY_ENABLED='0',PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0',
    NAMUH_APP_KEY='',NAMUH_APP_SECRET='',APP_PASSWORD='local-rehearsal',APP_SESSION_SECRET=secrets.token_hex(32))
connect=psycopg2.connect

def guarded_connect(dsn=None,*arguments,**keywords):
    parsed=parse_dsn(dsn) if dsn else {};parsed.update(keywords)
    if parsed.get('host')!='127.0.0.1' or str(parsed.get('port'))!='55438' or parsed.get('dbname')!=name:
        raise RuntimeError('Rehearsal cannot connect to any other database')
    return connect(dsn,*arguments,**keywords)
psycopg2.connect=guarded_connect
original_connect_ex=socket.socket.connect_ex
original_connect=socket.socket.connect
original_dns=socket.getaddrinfo

def loopback_connect(sock,address):
    if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1','localhost'):
        raise RuntimeError('Rehearsal cannot access external services')
    return original_connect(sock,address)

def loopback_dns(host,*arguments,**keywords):
    if host not in ('127.0.0.1','::1','localhost',None):raise RuntimeError('External DNS disabled in rehearsal')
    return original_dns(host,*arguments,**keywords)
def loopback_connect_ex(sock,address):
    if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1','localhost'):
        raise RuntimeError('Rehearsal cannot access external services')
    return original_connect_ex(sock,address)
socket.socket.connect=loopback_connect;socket.socket.connect_ex=loopback_connect_ex;socket.getaddrinfo=loopback_dns

def blocked_http(*arguments,**keywords):raise RuntimeError('Rehearsal uses copied quotes; external API disabled')
import requests
from curl_cffi import requests as curl_requests
requests.sessions.Session.request=blocked_http;curl_requests.Session.request=blocked_http
from data import data_manager as dm
from backend import main
from backend.services import market_service
from backend.routers import crypto,portfolios
from logic import dividend_fetcher

with dm.get_connection() as conn,conn.cursor() as c:
    c.execute('SELECT key,data,updated_at FROM market_cache')
    cached={key:{'data':value,'updated_at':stamp} for key,value,stamp in c.fetchall()}
prices=cached.get('prices',{}).get('data')
exchange=cached.get('exchange_rate',{}).get('data') or {}
if not isinstance(prices,list) or not prices:raise RuntimeError('Copied quote cache missing; never invent market prices')
rate=float(exchange.get('usd_krw') or prices[0].get('usd_krw') or 0)
if rate<=0:raise RuntimeError('Copied FX rate required')
source='로컬 연습 · 복사 시점 고정 시세/환율'
stamp=cached['prices']['updated_at'].isoformat()
market_service.usd_krw=rate;market_service.rate_source=source;market_service.price_data=prices
snapshot={'prices':prices,'usd_krw':rate,'rate_source':source}
market_service._cache.seed(snapshot,time.time())
status={'updated_at':stamp,'stale':False,'refreshing':False,'refresh_failed':False}

def frozen_prices(**keywords):
    market_service._request.snapshot=snapshot;market_service._request.status=status
    return prices,{str(row['id']):float(row['price_krw']) for row in prices}
market_service.get_prices=frozen_prices
market_service.warmup=lambda:None
market_service.request_status=lambda:status
market_service.current_snapshot=lambda:snapshot
crypto_prices=cached.get('crypto',{}).get('data') or {}
for module in (main,crypto,portfolios):module.get_crypto_prices=lambda **kwargs:crypto_prices
# Use only copied dividend history, including its original records.
dividend_fetcher.fetch_dividend_history=lambda ticker,market:cached.get(f'div_{market}_{(ticker or "").strip().upper()}',{}).get('data') or []

@asynccontextmanager
async def local_lifespan(app):
    from backend.security import validate_settings
    validate_settings()
    dm.init_db()  # local schema upgrade only, including the new investment tab
    yield
main.app.router.lifespan_context=local_lifespan

@main.app.middleware('http')
async def rehearsal_guard(request,call_next):
    from starlette.responses import JSONResponse
    if request.url.path.startswith('/api/sync'):
        return JSONResponse({'detail':'로컬 연습에서는 증권사 연동을 실행하지 않습니다.'},status_code=409)
    response=await call_next(request)
    response.headers['X-Portfolio-Environment']='local-rehearsal'
    return response

@main.app.get('/local-rehearsal/status')
def local_status():
    return {'environment':'local-rehearsal','source_snapshot_utc':info['captured_at_utc'],
        'production_connection':False,'external_requests':False,'scheduler':False,'fixed_market_data':True}

if __name__=='__main__':
    import uvicorn
    print('Local rehearsal only; production connection and external IO blocked.',flush=True)
    uvicorn.run(main.app,host='127.0.0.1',port=args.port,access_log=False)
