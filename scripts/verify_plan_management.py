"""Real transaction tests in a fresh synthetic loopback DB; no private config."""
import os,sys
from pathlib import Path
from uuid import uuid4
from datetime import date
from concurrent.futures import ThreadPoolExecutor
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
from data.repositories import plans,investments
from backend.routers import plans as router
from backend.routers.investments import Setup
local=dict(host='127.0.0.1',port=55438,user='ledger_qa',password='',passfile='NUL',sslmode='disable',connect_timeout=3)
name='plan_delete_qa_'+uuid4().hex[:12]
admin=psycopg2.connect(**local,dbname='postgres');admin.autocommit=True
with admin.cursor() as c:c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
admin.close()
def connect():return psycopg2.connect(**local,dbname=name)
ctx=RepositoryContext(connect,lambda:uuid4().hex,lambda:None,lambda:1400)
def journal():
    with connect() as conn,conn.cursor() as c:
        result=[]
        for table in ('accounts','holdings','trade_history'):
            c.execute(sql.SQL('SELECT to_jsonb(t) FROM {} t ORDER BY id').format(sql.Identifier(table)))
            result.append(c.fetchall())
        return result
payload=dict(name='Synthetic plan',scenario='NEW_CASH',new_cash_krw=0,drift_threshold=5,trade_plan=[dict(account_id='a',asset_id='s',account_alias='CMA',asset_name='Bond',type='BUY',qty=1,price=100,total_krw=100)],transfer_plan=[])
try:
    schema.init_db(ctx)
    with connect() as conn,conn.cursor() as c:
        c.execute("INSERT INTO portfolios(id,name) VALUES('other','Synthetic other')")
        c.execute("INSERT INTO accounts(id,account_no,account_alias,account_type,deposit_krw,portfolio_id) VALUES('a','SYNTHETIC','CMA','CMA',10000,'default')")
        c.execute("INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id) VALUES('s','Synthetic bond','QA','KR',%s,'default')",(Json(['a']),))
    router.context=lambda:ctx
    app=FastAPI();app.include_router(router.router);client=TestClient(app)
    def save():
        response=client.post('/api/plans/default',json=payload);assert response.status_code==200;return response.json()['id']
    first=save();before=journal()
    assert client.delete('/api/plans/other/'+first).status_code==400
    assert any(p['id']==first for p in plans.read(ctx,'default')['plans'])
    assert client.delete('/api/plans/default/'+first).status_code==200
    assert not any(p['id']==first for p in plans.read(ctx,'default')['plans'])
    assert journal()==before
    archived=save();plans.archive(ctx,'default',archived,True)
    assert client.delete('/api/plans/default/'+archived).status_code==200
    linked=save()
    with connect() as conn,conn.cursor() as c:
        c.execute("INSERT INTO trade_history(id,trade_date,account_id,asset_id,trade_type,quantity,price,currency,exchange_rate) VALUES('t',%s,'a','s','BUY',1,100,'KRW',1)",(date.today().isoformat(),))
    plans.link(ctx,'default',linked,0,'t');before=journal()
    response=client.delete('/api/plans/default/'+linked);assert response.status_code==400 and '거래' in response.json()['detail']
    assert journal()==before
    in_use=save();setup=Setup(request_id='qa-cycle-start',plan_id=in_use,representative_account_id='a',usd_krw=1400).model_dump()
    setup['preview_token']=investments.prepare(ctx,'default',setup)['preview_token']
    cycle=investments.create(ctx,'default',setup)['id']
    for state in ('ACTIVE','PAUSED','CLOSED'):
        if state!='ACTIVE':investments.set_status(ctx,'default',cycle,state,'Synthetic end' if state=='CLOSED' else '')
        response=client.delete('/api/plans/default/'+in_use);assert response.status_code==400 and '회차' in response.json()['detail']
        assert journal()==before
    plans.archive(ctx,'default',in_use,True)
    assert client.delete('/api/plans/default/'+in_use).status_code==400
    # Start/delete racing for a second portfolio cannot produce an orphan cycle.
    with connect() as conn,conn.cursor() as c:
        c.execute("UPDATE accounts SET portfolio_id='other' WHERE id='a'")
        c.execute("UPDATE assets SET portfolio_id='other' WHERE id='s'")
    racing=plans.save(ctx,'other','Race',payload)
    setup=Setup(request_id='qa-racing-start',plan_id=racing,representative_account_id='a',usd_krw=1400).model_dump()
    setup['preview_token']=investments.prepare(ctx,'other',setup)['preview_token']
    def attempt(which):
        try:return ('ok',investments.create(ctx,'other',setup) if which=='start' else plans.delete(ctx,'other',racing))
        except ValueError:return ('blocked',None)
    with ThreadPoolExecutor(2) as pool:outcomes=list(pool.map(attempt,['start','delete']))
    assert [x[0] for x in outcomes].count('ok')==1
    with connect() as conn,conn.cursor() as c:
        c.execute('SELECT count(*) FROM portfolio_execution.cycles cy LEFT JOIN rebalance_plans p ON p.id=cy.plan_id WHERE p.id IS NULL');assert c.fetchone()[0]==0
    print('PASS unused/archived delete, cross-portfolio protection, linked journal preservation, ACTIVE/PAUSED/CLOSED protection, start-delete race.')
finally:
    client.close() if 'client' in globals() else None
    admin=psycopg2.connect(**local,dbname='postgres');admin.autocommit=True
    with admin.cursor() as c:c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
    admin.close()
