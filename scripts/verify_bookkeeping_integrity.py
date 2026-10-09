"""Only a fresh database on the existing loopback QA cluster; no config/secrets."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import os
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import parse_dsn,make_dsn
from psycopg2.extras import Json

_original=psycopg2.connect

def local_connect(dsn=None,*args,**kwargs):
    parameters=parse_dsn(dsn) if dsn else {}
    parameters.update(kwargs)
    if parameters.get('host')!='127.0.0.1' or str(parameters.get('port'))!='55438' or parameters.get('user')!='ledger_qa':
        raise RuntimeError('Only the separate synthetic loopback QA cluster is allowed.')
    return _original(dsn,*args,**kwargs)

psycopg2.connect=local_connect
settings=dict(host='127.0.0.1',port=55438,user='ledger_qa',dbname='postgres',connect_timeout=3)
name='integrity_qa_'+uuid4().hex[:12]
admin=local_connect(**settings);admin.autocommit=True
with admin.cursor() as c:c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
admin.close();settings['dbname']=name
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0',SUPABASE_URL=make_dsn(**settings),APP_PASSWORD='qa-only',
                  NAMUH_APP_KEY='',NAMUH_APP_SECRET='',PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0')
import requests
from curl_cffi import requests as curl

def blocked(*args,**kwargs):raise RuntimeError('No external HTTP during synthetic verification.')
requests.sessions.Session.request=blocked;curl.Session.request=blocked
from data import data_manager as dm
from data.repositories import trades,forex,nh_notices,accounts,assets,deposits,activity,performance
from backend.routers.trades import BatchTradeRequest
from backend.routers.forex import CashEvent
from backend.routers.nh_notices import Batch,Row
from backend.routers.deposits import Entry
ctx=dm._context()

def scalar(query,values=()):
    with dm.get_connection() as conn,conn.cursor() as c:
        c.execute(query,values);return c.fetchone()[0]

try:
    dm.init_db();dm.init_db()
    today=datetime.now(forex.KST).date();day=today.isoformat()
    with dm.get_connection() as conn,conn.cursor() as c:
        for aid,cash,usd in [('qa',1000000,400),('qa_history',1000000,0),('qa_negative',-10000,0)]:
            c.execute("INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw,deposit_usd) VALUES(%s,%s,%s,'CMA','default',%s,%s)",(aid,'QA-'+aid,'Synthetic '+aid,cash,usd))
        for aid,market,account in [('qa_vt','US','qa'),('qa_etf','KR','qa_history')]:
            c.execute('INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id) VALUES(%s,%s,%s,%s,%s,%s)',(aid,aid,'QA-'+aid,market,Json([account]),'default'))
        c.execute('INSERT INTO performance_tracking(portfolio_id,baseline_date,baseline_value,baseline_payload,close_started_on) VALUES(%s,%s,%s,%s,%s)',('default',today-timedelta(days=5),2540000,Json({'ledger':{}}),today+timedelta(days=1)))
        conn.commit()
    assert forex.record_cash_event(ctx,'qa','OPENING',day+'T08:00:00+09:00',rate=1300)[0]
    request=BatchTradeRequest(request_id='pg-buy-idempotent',portfolio_id='default',trade_date=day,trades=[dict(account_id='qa',asset_id='qa_vt',trade_type='BUY',quantity=1,price=100,currency='USD')]).model_dump(mode='json')
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:trades.execute_batch(ctx,request),range(2)))
    assert results[0]['trade_ids']==results[1]['trade_ids']
    assert scalar("SELECT COUNT(*) FROM trade_history WHERE account_id='qa'")==1
    assert scalar("SELECT deposit_usd FROM accounts WHERE id='qa'")==300
    print('PASS concurrent manual retry: one trade and one cash movement')
    request=CashEvent(request_id='pg-fx-idempotent',portfolio_id='default',kind='EXCHANGE_IN',occurred_at=day+'T09:00:00+09:00',usd_amount=100,krw_amount=130000).model_dump(mode='json')
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:forex.record_manual_event(ctx,'qa',request),range(2)))
    assert results[0]['event_id']==results[1]['event_id'] and scalar("SELECT deposit_usd FROM accounts WHERE id='qa'")==400
    print('PASS concurrent FX retry: one exchange and one cost movement')
    request=CashEvent(request_id='pg-external-usd',portfolio_id='default',kind='DEPOSIT',occurred_at=day+'T10:00:00+09:00',usd_amount=10,rate=1400).model_dump(mode='json')
    result=forex.record_manual_event(ctx,'qa',request)
    assert scalar('SELECT amount_krw FROM performance_flows WHERE id=%s',(result['flow_id'],))==14000
    page=activity.read_page(ctx,'default',today-timedelta(days=5),today)
    assert len([r for r in page['items'] if r['detail'].get('usd_event_id')==result['event_id']])==1
    assert forex.undo_event(ctx,'qa',result['event_id'])[0]
    assert scalar('SELECT voided FROM performance_flows WHERE id=%s',(result['flow_id'],))
    assert scalar("SELECT deposit_usd FROM accounts WHERE id='qa'")==400
    print('PASS linked USD flow: one history row and atomic undo')
    for offset,kind,price in [(3,'BUY',100),(1,'SELL',300),(2,'BUY',200)]:
        ok,message=trades.execute_trade(ctx,str(today-timedelta(days=offset)),'qa_history','qa_etf',kind,1,price,'KRW',1)
        assert ok,message
    assert scalar("SELECT avg_price FROM holdings WHERE account_id='qa_history'")==150
    print('PASS backdated buy: chronological cost basis 150')
    req=Batch(request_id='pg-negative-cash',confirmed=True,expected_cash={'qa_negative':{'deposit_krw':-10000,'deposit_usd':0}},rows=[Row(kind='DEPOSIT',account_id='qa_negative',event_date=day,krw_amount=20000)]).model_dump(mode='json')
    nh_notices.commit(ctx,'default',req)
    assert scalar("SELECT deposit_krw FROM accounts WHERE id='qa_negative'")==10000
    assert not accounts.delete_account(ctx,'qa')[0] and not assets.delete_asset(ctx,'qa_etf')[0]
    print('PASS negative balance recovery and destructive settings guards')
    req=Entry(request_id='pg-deposit-receipt',asset_id='qa_deposit',reason='Synthetic current deposit verification',confirmed=True,
        asset=dict(name='QA deposit',ticker='DEP-QA',deposit_principal=38239177,interest_rate=3,start_date=day,maturity_date=str(today+timedelta(days=365)))).model_dump(mode='json')
    one=deposits.save(ctx,'default',req);two=deposits.save(ctx,'default',req)
    assert one==two and scalar("SELECT COUNT(*) FROM assets WHERE id='qa_deposit'")==1
    assert scalar("SELECT deposit_principal FROM assets WHERE id='qa_deposit'")==38239177
    deposits.undo(ctx,'default','qa_deposit',req['request_id'])
    assert scalar("SELECT deposit_principal FROM assets WHERE id='qa_deposit'")==0
    print('PASS deposit registration/retry/undo and repeated schema initialization')
    # Fault inside a real transaction rolls back the successful first row too.
    req=BatchTradeRequest(request_id='pg-batch-rollback',portfolio_id='default',trade_date=day,trades=[
        dict(account_id='qa',asset_id='qa_vt',trade_type='BUY',quantity=1,price=100,currency='USD'),
        dict(account_id='qa',asset_id='qa_vt',trade_type='BUY',quantity=100,price=100,currency='USD')]).model_dump(mode='json')
    try:trades.execute_batch(ctx,req);raise AssertionError('partial batch accepted')
    except ValueError:pass
    assert scalar("SELECT deposit_usd FROM accounts WHERE id='qa'")==400
    assert scalar("SELECT COUNT(*) FROM bookkeeping_requests WHERE request_id='pg-batch-rollback'")==0
    print('PASS real PostgreSQL failure rollback and missing receipt')
finally:
    pool=dm.get_connection_pool();pool.closeall()
    settings['dbname']='postgres'
    admin=local_connect(**settings);admin.autocommit=True
    with admin.cursor() as c:c.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
    admin.close()
