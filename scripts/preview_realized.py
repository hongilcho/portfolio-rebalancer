"""Loopback synthetic review only. Memory DB; never loads credentials or NH."""
import os
from pathlib import Path
import sys
import threading
from datetime import date
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0',SUPABASE_URL='',APP_PASSWORD='',APP_SESSION_SECRET='',
    NAMUH_APP_KEY='',NAMUH_APP_SECRET='',CMA_INTEREST_ENABLED='0',CMA_INTEREST_WRITES_ENABLED='0',
    CMA_DIAGNOSTICS_ENABLED='0',PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0')
import psycopg2
import requests
from curl_cffi import requests as curl_requests
def blocked(*a,**kw):raise RuntimeError('Preview cannot connect to production or providers')
psycopg2.connect=blocked
requests.sessions.Session.request=blocked
curl_requests.Session.request=blocked
from fastapi import FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from data import data_manager as dm
from data.repositories import trades,realized
from backend.routers.trades import BatchTradeRequest
from test_trade_reversal import DatabaseAdapter

app=FastAPI(title='Synthetic realized gains preview')
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:5200'],allow_methods=['GET','POST'],allow_headers=['Content-Type','Authorization'])
lock=threading.RLock();db=None
accounts=[dict(id='acc',account_alias='합성 ISA',account_type='ISA',portfolio_id='p'),
          dict(id='us',account_alias='합성 해외 ETF',account_type='종합매매',portfolio_id='p')]
assets=[dict(id='ast',name='합성 국내 ETF',ticker='QA000',market='KR',allowed_accounts=['acc']),
        dict(id='vt',name='합성 VT',ticker='VT',market='US',allowed_accounts=['us'])]


def reset():
    global db
    if db:db.raw.close()
    db=DatabaseAdapter();dm.get_connection=lambda:db
    db.raw.execute("INSERT INTO accounts(id,deposit_krw,deposit_usd) VALUES('us',1000000,2000)")
    db.raw.execute("INSERT INTO assets(id,market,allowed_accounts) VALUES('vt','US','[\"us\"]')");db.commit()
    for day,aid,sid,kind,qty,price,fx,krw,usd in [
        ('2026-09-01','acc','ast','BUY',10,10000,1,100,None),
        ('2026-10-01','acc','ast','SELL',10,12000,1,50,None),
        ('2026-10-05','acc','ast','BUY',3,11000,1,30,None),
        ('2026-09-01','us','vt','BUY',4,100,1300,0,1),
        ('2026-10-01','us','vt','SELL',2,120,1400,0,1)]:
        ok,msg=trades.execute_trade(dm._context(),day,aid,sid,kind,qty,price,'USD' if sid=='vt' else 'KRW',fx,fees_krw=krw,fees_usd=usd)
        assert ok,msg


@app.get('/dev/state')
def state():
    with lock:
        holdings=[{**h,'asset_name':next(a['name'] for a in assets if a['id']==h['asset_id'])} for h in db.rows('holdings')]
        return dict(accounts=[{**a,**next(r for r in db.rows('accounts') if r['id']==a['id'])} for a in accounts],assets=assets,holdings=holdings,trades=sorted(db.rows('trade_history'),key=lambda r:r['trade_sequence'],reverse=True))


@app.post('/dev/reset')
def reset_route():
    with lock:reset();return {'success':True}


@app.post('/dev/undo/{ident}')
def undo(ident:str):
    with lock:
        ok,msg=trades.delete_trades(dm._context(),[ident])
        if not ok:raise HTTPException(400,msg)
        return {'success':True}


@app.get('/api/trades/realized')
def report(portfolio_id:str,start_date:date|None=None,end_date:date|None=None,account_id:str|None=None,asset_id:str|None=None):
    if portfolio_id!='p':raise HTTPException(400,'합성 포트폴리오만 지원합니다.')
    if start_date and end_date and start_date>end_date:raise HTTPException(400,'조회 일자를 확인해주세요.')
    with lock:return realized.enrich(db.rows('trade_history'),db.rows('holdings'),accounts,assets,{},start=start_date,end=end_date,account_id=account_id,asset_id=asset_id)


@app.post('/api/trades/batch')
def record(req:BatchTradeRequest):
    with lock:
        try:return trades.execute_batch(dm._context(),req.model_dump(mode='json'))
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc


if __name__=='__main__':
    import uvicorn
    reset();uvicorn.run(app,host='127.0.0.1',port=8132,access_log=False)
