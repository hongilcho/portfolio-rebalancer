"""Loopback-only synthetic review. Never loads production config or calls NH."""
import os,sys,json,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0',SUPABASE_URL='',APP_PASSWORD='',APP_SESSION_SECRET='',
    NAMUH_APP_KEY='',NAMUH_APP_SECRET='',CMA_INTEREST_ENABLED='0',CMA_INTEREST_WRITES_ENABLED='0',
    PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0',PORTFOLIO_DB_SECURITY_ENABLED='0')
import requests
from curl_cffi import requests as curl_requests
def blocked(*a,**kw):raise RuntimeError('External HTTP disabled in local fee review')
requests.sessions.Session.request=blocked;curl_requests.Session.request=blocked
import psycopg2
psycopg2.connect=blocked
from fastapi import FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from test_nh_notices import db as fixture
from test_ledger_adjustments import book
from data.repositories import trades,ledger_adjustments,nh_notices
from backend.routers import ledger_adjustments as ledger_router
from backend.routers.trades import BatchTradeRequest
from backend.routers.nh_notices import Batch
from logic.trading_fees import schedule
from datetime import datetime
from data.repositories.forex import KST

lock=threading.RLock();generator=None;database=None
def reset():
    global generator,database
    if generator:
        try:next(generator)
        except StopIteration:pass
    generator=fixture.__wrapped__();database=book.__wrapped__(next(generator))
    database.raw.executescript('''
      UPDATE accounts SET account_alias='합성 일반계좌',deposit_krw=1000000,deposit_usd=1000;
      UPDATE usd_cash_state SET usd_balance=1000,cost_krw=1350000;
      ALTER TABLE assets ADD COLUMN name TEXT;
      UPDATE assets SET name='합성 국내 ETF';
      INSERT INTO assets(id,market,ticker,name,portfolio_id,allowed_accounts) VALUES('us','US','VT','합성 미국 ETF','p','["acc"]'),('gold','KR','M04020000','합성 금현물','p','["acc"]');
    ''')
    policy={k:[{'from':'2026-01-01','rate_pct':rate,'vat_included':k!='GOLD','note':'나무멤버스 유지' if k=='US' else ''}] for k,rate in [('KR','0.0141639'),('US','0.07'),('GOLD','0.2')]}
    database.raw.execute('UPDATE accounts SET fee_schedule=?',(json.dumps(policy),));database.commit()
reset()
app=FastAPI(title='Synthetic fee review')
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:5202','http://localhost:5202'],allow_methods=['*'],allow_headers=['*'])
def perform(fn,*args):
    with lock:
        try:return fn(database.ctx,*args)
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
ledger_router.perform=perform;app.include_router(ledger_router.router)
@app.get('/dev/state')
def state():
    with lock:
        accounts=[dict(r) for r in database.raw.execute('SELECT * FROM accounts')]
        for a in accounts:a['fee_schedule']=json.loads(a['fee_schedule'])
        return dict(synthetic_only=True,day=str(datetime.now(KST).date()),accounts=accounts,
            assets=[dict(r) for r in database.raw.execute('SELECT * FROM assets')],
            trades=[dict(r) for r in database.raw.execute('SELECT * FROM trade_history ORDER BY trade_sequence DESC')])
@app.post('/dev/reset')
def restart():
    with lock:reset();return dict(reset=True)
@app.post('/dev/policy')
def policy(value:dict):
    with lock:
        try:clean=schedule(value)
        except (ValueError,KeyError) as exc:raise HTTPException(400,str(exc)) from exc
        database.raw.execute('UPDATE accounts SET fee_schedule=?',(json.dumps(clean),));database.commit();return dict(saved=True)
@app.post('/api/trades/batch')
def trade(value:BatchTradeRequest):return perform(trades.execute_batch,value.model_dump(mode='json'))
@app.get('/api/nh-notices/{pid}/context')
def context(pid:str,day:str):return perform(nh_notices.read_context,pid,day)
@app.post('/api/nh-notices/{pid}')
def notice(pid:str,value:Batch):return perform(nh_notices.commit,pid,value.model_dump(mode='json'))

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8144,log_level='warning')
