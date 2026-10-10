"""Synthetic PostgreSQL tests only. Does not load private or production configuration."""
import os,sys,json
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timezone,timedelta
for key in list(os.environ):
    if key.startswith('PG'):os.environ.pop(key,None)
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0',SUPABASE_URL='',PORTFOLIO_DB_SECURITY_ENABLED='0',PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0',NAMUH_APP_KEY='',NAMUH_APP_SECRET='')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from data import schema
from data.repository_context import RepositoryContext
from data.repositories import plans,investments,trades,nh_notices
from backend.routers import investments as route,plans as plan_route
from backend.routers.investments import Setup
from backend.routers.trades import BatchTradeRequest
from backend.routers.nh_notices import Batch
local=dict(host='127.0.0.1',port=55438,user='ledger_qa',password='',passfile='NUL',sslmode='disable',connect_timeout=3)
name='cash_return_qa_'+uuid4().hex[:12]
admin=psycopg2.connect(**local,dbname='postgres');admin.autocommit=True
with admin.cursor() as c:c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
admin.close()
def connect():return psycopg2.connect(**local,dbname=name)
ctx=RepositoryContext(connect,lambda:uuid4().hex,lambda:None,lambda:1400)
def ledger():
    with connect() as conn,conn.cursor() as c:
        data=[]
        for table in ('accounts','holdings','trade_history','performance_flows'):
            c.execute(sql.SQL('SELECT to_jsonb(t) FROM {} t ORDER BY id').format(sql.Identifier(table)));data.append(c.fetchall())
        return data
def balances():
    with connect() as conn,conn.cursor() as c:
        c.execute('SELECT id,deposit_krw,deposit_usd FROM accounts ORDER BY id');return {r[0]:dict(deposit_krw=r[1],deposit_usd=r[2]) for r in c.fetchall()}
try:
    schema.init_db(ctx)
    with connect() as conn,conn.cursor() as c:
        for aid,kind,krw in [('cma','CMA',1000000),('stock','GENERAL',50000),('isa','ISA',10000),('irp','IRP',20000),('pension','PENSION',30000)]:
            c.execute("INSERT INTO accounts(id,account_no,account_alias,account_type,deposit_krw,deposit_usd,portfolio_id) VALUES(%s,%s,%s,%s,%s,%s,'default')",(aid,'SYNTHETIC-'+aid,aid,kind,krw,12 if aid=='stock' else 0))
        c.execute("INSERT INTO assets(id,name,ticker,market,is_risk_asset,allowed_accounts,portfolio_id) VALUES('b','Synthetic bond','TEST','KR',0,%s,'default')",(Json(['stock','isa','irp','pension']),))
    lines=[dict(account_id=aid,account_alias=aid,asset_id='b',asset_name='Bond',type='BUY',qty=qty,price=price,total_krw=qty*price) for aid,qty,price in [('stock',2,10000),('isa',1,9000),('irp',1,10000),('pension',1,10000)]]
    plan=plans.save(ctx,'default','Buy',dict(scenario='NEW_CASH',new_cash_krw=0,drift_threshold=5,trade_plan=lines,transfer_plan=[]))
    setup=Setup(request_id='initial-cycle',plan_id=plan,representative_account_id='cma',usd_krw=1400,price_buffer_percent=1,fx_buffer_percent=1).model_dump(mode='json')
    setup['preview_token']=investments.prepare(ctx,'default',setup)['preview_token'];cycle=investments.create(ctx,'default',setup)['id']
    assert investments.create(ctx,'default',setup)['id']==cycle
    app=FastAPI();plan_route.context=lambda:ctx;app.include_router(route.router);client=TestClient(app)
    path='/api/investments/default/'+cycle+'/cash-return'
    assert client.get(path).status_code==400
    current=investments.read(ctx,'default',cycle);day=datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    for step in current['steps']:
        payload=BatchTradeRequest(request_id='fill-'+step['id'],portfolio_id='default',trade_date=day,trades=[dict(account_id=step['account_id'],asset_id='b',trade_type='BUY',quantity=float(step['target_quantity']),price=float(step['estimated_price']),currency='KRW',exchange_rate=1,execution=dict(cycle_id=cycle,step_id=step['id'],revision=1))]).model_dump(mode='json')
        result=trades.execute_batch(ctx,payload);assert result['results'][0]['success']
    investments.set_status(ctx,'default',cycle,'CLOSED')
    before=ledger();response=client.get(path);assert response.status_code==200
    data=response.json();assert {a['id'] for a in data['accounts'] if not a['transfer_allowed']}=={'isa','irp','pension'}
    assert client.get(path.replace('/default/','/other/')).status_code==400
    request=dict(request_id='return-plan-once',name='CMA return',destination_account_id='cma',keep_amounts={'stock':1000})
    for invalid in ({**request,'keep_amounts':{'isa':0}},{**request,'keep_amounts':{'outside':0}},{**request,'keep_amounts':{'stock':-1}},{**request,'destination_account_id':'isa'}):
        assert client.post(path+'/prepare',json=invalid).status_code==400
    preview=client.post(path+'/prepare',json=request);assert preview.status_code==200
    assert preview.json()['total_krw']==29000
    stale={**request,'preview_token':preview.json()['preview_token']}
    with connect() as conn,conn.cursor() as c:c.execute("UPDATE accounts SET deposit_krw=deposit_krw+1 WHERE id='stock'")
    assert client.post(path,json=stale).status_code==400
    with connect() as conn,conn.cursor() as c:c.execute("UPDATE accounts SET deposit_krw=deposit_krw-1 WHERE id='stock'")
    saved=client.post(path,json=stale);assert saved.status_code==200;saved_id=saved.json()['id']
    assert client.post(path,json=stale).json()['id']==saved_id
    assert client.post(path,json={**stale,'name':'Changed repeat'}).status_code==400
    assert ledger()==before
    start=Setup(request_id='return-cycle',plan_id=saved_id,representative_account_id='cma',usd_krw=1400).model_dump(mode='json')
    start['preview_token']=investments.prepare(ctx,'default',start)['preview_token'];return_cycle=investments.create(ctx,'default',start)['id']
    assert ledger()==before
    detail=investments.read(ctx,'default',return_cycle);assert detail['plan_type']=='CASH_RETURN' and detail['budget_krw']==29000
    step=detail['steps'][0];assert step['kind']=='TRANSFER'
    cash=balances();request=Batch(request_id='return-cash-transfer',confirmed=True,expected_cash={a:cash[a] for a in ('stock','cma')},rows=[dict(kind='WITHDRAW',account_id='stock',destination_account_id='cma',external=False,event_date=day,krw_amount=29000,notes='Synthetic return',execution=dict(cycle_id=return_cycle,step_id=step['id'],revision=1))]).model_dump(mode='json')
    result=nh_notices.commit(ctx,'default',request);after=balances()
    assert nh_notices.commit(ctx,'default',request)==result and balances()==after
    assert after['stock']['deposit_krw']==1000 and after['cma']['deposit_krw']==1029000
    assert after['stock']['deposit_usd']==12
    for aid in ('isa','irp','pension'):assert after[aid]==cash[aid]
    assert ledger()[1:]==before[1:]
    investments.set_status(ctx,'default',return_cycle,'CLOSED')
    assert client.get('/api/investments/default/'+return_cycle+'/cash-return').status_code==400
    print('PASS buffer setup, completed-investment recovery, protected accounts, stale balances, idempotent plan/start/transfer, shared ledger and USD preservation.')
finally:
    client.close() if 'client' in globals() else None
    admin=psycopg2.connect(**local,dbname='postgres');admin.autocommit=True
    with admin.cursor() as c:c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
    admin.close()
