"""New synthetic loopback DB only; real schema, transactions and concurrent retries."""
import os,sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
for key in list(os.environ):
    if key.startswith('PG'):os.environ.pop(key,None)
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0',SUPABASE_URL='',PORTFOLIO_DB_SECURITY_ENABLED='0',
    NAMUH_APP_KEY='',NAMUH_APP_SECRET='',PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json
from data.repository_context import RepositoryContext
from data import schema
from data.repositories import plans,investments,trades,forex,nh_notices
from backend.routers.investments import Setup
from backend.routers.trades import BatchTradeRequest
from backend.routers.forex import CashEvent
from backend.routers.nh_notices import Batch
settings=dict(host='127.0.0.1',port=55438,user='ledger_qa',dbname='postgres',password='',passfile='NUL',sslmode='disable',connect_timeout=3)
name='investment_qa_'+uuid4().hex[:12]
owner_role='execution_owner_'+uuid4().hex[:12]
admin=psycopg2.connect(**settings);admin.autocommit=True
with admin.cursor() as c:c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
admin.close();settings['dbname']=name
def connect():
    assert settings['host']=='127.0.0.1' and settings['port']==55438 and settings['dbname']==name
    return psycopg2.connect(**settings)
ctx=RepositoryContext(connect,lambda:uuid4().hex,lambda:None,lambda:1400)
def scalar(query,args=()):
    with connect() as conn,conn.cursor() as c:
        c.execute(query,args);return c.fetchone()[0]
def cash():
    with connect() as conn,conn.cursor() as c:
        c.execute('SELECT id,deposit_krw,deposit_usd FROM accounts ORDER BY id');return c.fetchall()
def fail(fn,word=None):
    try:fn()
    except ValueError as e:
        if word:assert word in str(e),str(e)
    else:raise AssertionError('Unsafe request accepted')
try:
    schema.init_db(ctx);schema.init_db(ctx)
    with connect() as conn,conn.cursor() as c:
        c.execute("INSERT INTO portfolios(id,name) VALUES('other','Synthetic other')")
        for aid,kind,krw,usd in [('cma','CMA',1150000,0),('isa','ISA',0,0),('us','GENERAL',0,100)]:
            c.execute("INSERT INTO accounts(id,account_no,account_alias,account_type,deposit_krw,deposit_usd,portfolio_id) VALUES(%s,%s,%s,%s,%s,%s,'default')",(aid,'QA-'+aid,aid,kind,krw,usd))
        for aid,market,account in [('bond','KR','isa'),('vt','US','us')]:
            c.execute("INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id) VALUES(%s,%s,%s,%s,%s,'default')",(aid,aid,'QA-'+aid,market,Json([account])))
        conn.commit()
    moment=datetime.now(forex.KST).isoformat();day=moment[:10]
    opening=CashEvent(request_id='qa-opening-01',portfolio_id='default',kind='OPENING',occurred_at=moment,usd_amount=100,rate=1400).model_dump(mode='json')
    forex.record_manual_event(ctx,'us',opening)
    plan_data=dict(scenario='NEW_CASH',new_cash_krw=0,drift_threshold=5,transfer_plan=[],trade_plan=[
        dict(account_id='isa',asset_id='bond',type='BUY',qty=20,price=9000,total_krw=180000),
        dict(account_id='us',asset_id='vt',type='BUY',qty=5,price=140000,total_krw=700000)])
    pid=plans.save(ctx,'default','Synthetic cycle',plan_data)
    req=Setup(request_id='qa-start-001',plan_id=pid,representative_account_id='cma',usd_krw=1400).model_dump(mode='json')
    before=cash();preview=investments.prepare(ctx,'default',req)
    req['preview_token']=preview['preview_token']
    assert cash()==before and scalar('SELECT count(*) FROM portfolio_execution.cycles')==0
    # The same transfer instructions can survive a changed CMA balance. Review
    # must still be invalidated instead of assuming the incoming cash is future.
    with connect() as conn,conn.cursor() as c:
        c.execute("UPDATE accounts SET deposit_krw=deposit_krw+1 WHERE id='cma'");conn.commit()
    fail(lambda:investments.create(ctx,'default',req),'변경')
    assert scalar('SELECT count(*) FROM portfolio_execution.cycles')==0
    with connect() as conn,conn.cursor() as c:
        c.execute("UPDATE accounts SET deposit_krw=deposit_krw-1 WHERE id='cma'");conn.commit()
    with ThreadPoolExecutor(2) as pool:created=list(pool.map(lambda _:investments.create(ctx,'default',req),range(2)))
    assert created[0]==created[1] and cash()==before
    cycle_id=created[0]['id'];cycle=investments.read(ctx,'default',cycle_id)
    fail(lambda:investments.set_status(ctx,'default',cycle_id,'CLOSED'),'남은')
    fail(lambda:investments.set_status(ctx,'default',cycle_id,'CLOSED','   '),'남은')
    assert cash()==before and scalar('SELECT report FROM portfolio_execution.cycles WHERE id=%s',(cycle_id,)) is None
    assert plans.read(ctx,'default')['plans'][0]['execution']['id']==cycle_id
    assert not any(s['kind']=='DEPOSIT' for s in cycle['steps'])
    fail(lambda:investments.create(ctx,'default',{**req,'request_id':'qa-second-cycle'}),'진행 중')
    step_by={s['key']:s for s in cycle['steps']}
    def link(key):return dict(cycle_id=cycle_id,step_id=step_by[key]['id'],revision=1)
    def transfer(key,request_id,execution=None):
        step=step_by[key];before=dict((r[0],dict(deposit_krw=r[1],deposit_usd=r[2])) for r in cash())
        return Batch(request_id=request_id,confirmed=True,expected_cash={a:before[a] for a in (step['account_id'],step['destination_account_id'])},rows=[
          dict(kind='WITHDRAW',account_id=step['account_id'],destination_account_id=step['destination_account_id'],external=False,event_date=day,krw_amount=float(step['target_amount']),execution=execution or link(key))]).model_dump(mode='json')
    first=transfer('transfer:cma:isa','qa-transfer-01')
    old=cash()
    bad=transfer('transfer:cma:isa','qa-transfer-wrong',link('trade:0'))
    fail(lambda:nh_notices.commit(ctx,'default',bad),'다릅니다');assert cash()==old
    saved=nh_notices.commit(ctx,'default',first)
    assert nh_notices.commit(ctx,'default',first)==saved
    nh_notices.commit(ctx,'default',transfer('transfer:cma:us','qa-transfer-02'))
    def buy(request_id,account,asset,qty,price,currency,key):
        return BatchTradeRequest(request_id=request_id,portfolio_id='default',trade_date=day,trades=[
          dict(account_id=account,asset_id=asset,trade_type='BUY',quantity=qty,price=price,currency=currency,execution=link(key))]).model_dump(mode='json')
    partial=buy('qa-partial-01','isa','bond',7,9000,'KRW','trade:0')
    with ThreadPoolExecutor(2) as pool:receipts=list(pool.map(lambda _:trades.execute_batch(ctx,partial),range(2)))
    assert receipts[0]==receipts[1] and scalar("SELECT quantity FROM holdings WHERE account_id='isa'")==7
    journal=cash();trade_id=receipts[0]['trade_ids'][0]
    assert investments.link_existing(ctx,'default',cycle_id,dict(step_id=step_by['trade:0']['id'],revision=1,record_kind='TRADE',record_id=trade_id))['existing']
    assert cash()==journal
    fail(lambda:plans.unlink(ctx,'default',pid,trade_id),'8번')
    fail(lambda:plans.link(ctx,'default',pid,0,trade_id),'8번')
    fail(lambda:plans.archive(ctx,'default',pid,True),'8번')
    fail(lambda:investments.read(ctx,'other',cycle_id),'찾을 수')
    fail(lambda:trades.execute_batch(ctx,buy('qa-wrong-step','us','vt',1,100,'USD','trade:0')),'다릅니다')
    assert cash()==journal and scalar("SELECT count(*) FROM bookkeeping_requests WHERE request_id='qa-wrong-step'")==0
    investments.set_status(ctx,'default',cycle_id,'PAUSED')
    fail(lambda:trades.execute_batch(ctx,buy('qa-paused','isa','bond',1,9000,'KRW','trade:0')),'중단')
    assert cash()==journal
    investments.set_status(ctx,'default',cycle_id,'ACTIVE')

    # Revise only goals: the task ID, original trade and its cost must survive.
    larger=dict(request_id='qa-larger-goal-01',revision=1,reason='Synthetic larger allocation',changes=[dict(step_id=step_by['trade:0']['id'],target=35,status='ACTIVE')])
    assert investments.revise(ctx,'default',cycle_id,larger)=={'revision':2}
    larger_cycle=investments.read(ctx,'default',cycle_id)
    assert float(next(s for s in larger_cycle['steps'] if s['key']=='transfer:cma:isa')['target_amount'])==315000
    assert cash()==journal
    revision=dict(request_id='qa-goal-change-01',revision=2,reason='Synthetic smaller allocation',
        changes=[dict(step_id=step_by['trade:0']['id'],target=18,status='ACTIVE')])
    assert investments.revise(ctx,'default',cycle_id,revision)=={'revision':3}
    assert investments.revise(ctx,'default',cycle_id,revision)=={'revision':3}
    fail(lambda:investments.revise(ctx,'default',cycle_id,{**revision,'reason':'Changed retry'}),'내용')
    assert cash()==journal and scalar("SELECT quantity FROM holdings WHERE account_id='isa'")==7
    revised=investments.read(ctx,'default',cycle_id)
    assert revised['revision']==3 and [s['id'] for s in revised['steps']]==[s['id'] for s in cycle['steps']]
    assert next(s for s in revised['steps'] if s['id']==step_by['trade:0']['id'])['target_quantity']=='18'
    fail(lambda:trades.execute_batch(ctx,buy('qa-old-goal','isa','bond',1,9000,'KRW','trade:0')),'변경')
    def link(key):return dict(cycle_id=cycle_id,step_id=step_by[key]['id'],revision=3)
    # Adapter results are synthetic; their posting goes through the same trade
    # repository as manual input. Evidence survives a failed journal transaction.
    from data.repositories import execution_confirmations as confirmations
    mock_trade=dict(account_id='isa',asset_id='bond',trade_type='BUY',quantity=3,price=9000,currency='KRW',
        import_source='NAMUH_KAKAO',broker_order_no='891')
    uncertain=confirmations.preserve(ctx,'default',link('trade:0'),'qa-uncertain-fill',day,{**mock_trade,'broker_order_no':'890'},False)
    fail(lambda:confirmations.post(ctx,'default',uncertain['attempt_id']),'불명확')
    assert cash()==journal
    verified=confirmations.preserve(ctx,'default',link('trade:0'),'qa-mock-fill-891',day,mock_trade,True)
    assert confirmations.preserve(ctx,'default',link('trade:0'),'qa-mock-fill-891',day,mock_trade,True)==verified
    fail(lambda:confirmations.preserve(ctx,'default',link('trade:0'),'qa-mock-fill-891',day,{**mock_trade,'quantity':4},True),'내용')
    investments.set_status(ctx,'default',cycle_id,'PAUSED')
    fail(lambda:confirmations.post(ctx,'default',verified['attempt_id']),'중단')
    assert cash()==journal
    assert scalar('SELECT status FROM portfolio_execution.attempts WHERE id=%s',(verified['attempt_id'],))=='REVIEW'
    investments.set_status(ctx,'default',cycle_id,'ACTIVE')
    with ThreadPoolExecutor(2) as pool:list(pool.map(lambda _:confirmations.post(ctx,'default',verified['attempt_id']),range(2)))
    assert scalar("SELECT quantity FROM holdings WHERE account_id='isa'")==10
    posted=investments.read(ctx,'default',cycle_id)
    assert sum(float(r.get('quantity') or 0) for r in posted['results'] if r['ledger_status']=='RECORDED' and r['step_id']==step_by['trade:0']['id'])==10
    # A later notification for a sufficiently identified same broker order must
    # not create another trade or silently count another fill.
    balances=dict((r[0],dict(deposit_krw=r[1],deposit_usd=r[2])) for r in cash())
    duplicate=Batch(request_id='qa-nh-mock-duplicate',confirmed=True,expected_cash={'isa':balances['isa']},rows=[
        dict(kind='BUY',account_id='isa',asset_id='bond',event_date=day,quantity=3,price=9000,broker_order_no='891',
            execution=link('trade:0'))]).model_dump(mode='json')
    current=cash();fail(lambda:nh_notices.commit(ctx,'default',duplicate),'이미');assert cash()==current
    late=confirmations.preserve(ctx,'default',{**link('trade:0'),'revision':1},'qa-late-old-version',day,{**mock_trade,'quantity':1,'broker_order_no':'889'},True)
    fail(lambda:confirmations.post(ctx,'default',late['attempt_id']),'계획 변경')
    assert cash()==current
    confirmations.post(ctx,'default',late['attempt_id'],reviewed_revision=3)
    assert scalar("SELECT quantity FROM holdings WHERE account_id='isa'")==11
    # Reverse arrival order: notification already posted, confirmed adapter later.
    balances=dict((r[0],dict(deposit_krw=r[1],deposit_usd=r[2])) for r in cash())
    first_notice=Batch(request_id='qa-notice-first',confirmed=True,expected_cash={'isa':balances['isa']},rows=[
        dict(kind='BUY',account_id='isa',asset_id='bond',event_date=day,quantity=1,price=9000,broker_order_no='888',execution=link('trade:0'))]).model_dump(mode='json')
    nh_notices.commit(ctx,'default',first_notice)
    reverse=confirmations.preserve(ctx,'default',link('trade:0'),'qa-mock-after-notice',day,{**mock_trade,'quantity':1,'broker_order_no':'888'},True)
    current=cash();assert confirmations.post(ctx,'default',reverse['attempt_id'])['matched_existing']
    assert cash()==current and scalar("SELECT quantity FROM holdings WHERE account_id='isa'")==12

    fx=CashEvent(request_id='qa-fx-01',portfolio_id='default',kind='EXCHANGE_IN',occurred_at=datetime.now(forex.KST).isoformat(),usd_amount=400,krw_amount=560000,execution=link('fx:us')).model_dump(mode='json')
    forex.record_manual_event(ctx,'us',fx);before=cash();forex.record_manual_event(ctx,'us',fx);assert cash()==before
    vt=trades.execute_batch(ctx,buy('qa-vt-01','us','vt',5,100,'USD','trade:1'))
    assert scalar("SELECT deposit_usd FROM accounts WHERE id='us'")==0
    assert scalar("SELECT buy_fx_rate FROM holdings WHERE account_id='us'")==1400
    live=investments.read(ctx,'default',cycle_id)
    assert len(live['results'])==10
    assert sum(float(r.get('quantity') or 0) for r in live['results'] if r['ledger_status']=='RECORDED' and r['step_id']==step_by['trade:0']['id'])==12
    ok,message=trades.delete_trades(ctx,vt['trade_ids']);assert ok,message
    live=investments.read(ctx,'default',cycle_id);assert next(r for r in live['results'] if r['step_id']==step_by['trade:1']['id'])['voided']
    # Old receipts never recreate a cancelled financial event or a connection.
    journal=cash();trades.execute_batch(ctx,buy('qa-vt-01','us','vt',5,100,'USD','trade:1'));assert cash()==journal
    fail(lambda:trades.execute_batch(ctx,{**partial,'request_id':'qa-stale-plan','trades':[{**partial['trades'][0],'execution':{**link('trade:0'),'revision':1}}]}),'변경')
    assert cash()==journal
    investments.set_status(ctx,'default',cycle_id,'CLOSED','Synthetic partial close')
    report=scalar('SELECT report FROM portfolio_execution.cycles WHERE id=%s',(cycle_id,))
    assert report['remaining_steps'] and any(s['kind']=='BUY' for s in report['remaining_steps'])
    investments.set_status(ctx,'default',cycle_id,'CLOSED');assert scalar('SELECT report FROM portfolio_execution.cycles WHERE id=%s',(cycle_id,))==report
    fail(lambda:investments.set_status(ctx,'default',cycle_id,'ACTIVE'),'재개')
    plans.archive(ctx,'default',pid,True)
    assert scalar("SELECT count(*) FROM pg_class cl JOIN pg_namespace ns ON ns.oid=cl.relnamespace WHERE ns.nspname='portfolio_execution' AND cl.relkind='r' AND cl.relrowsecurity")==5
    with connect() as conn,conn.cursor() as c:
        for role in ('anon','authenticated','service_role'):
            c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(role,))
            if not c.fetchone():c.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
            c.execute('SAVEPOINT unauthorized')
            try:
                c.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
                c.execute('SELECT * FROM portfolio_execution.cycles')
                raise AssertionError('Public role accessed workflow')
            except psycopg2.Error as e:assert e.pgcode=='42501',e.pgcode
            finally:c.execute('ROLLBACK TO SAVEPOINT unauthorized')

    # Check the deployed access model: non-superuser owner/BYPASSRLS, not just
    # the QA cluster administrator. All ownership changes are in this new DB.
    with connect() as conn,conn.cursor() as c:
        c.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER BYPASSRLS').format(sql.Identifier(owner_role)))
        c.execute('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=%s',(owner_role,))
        assert c.fetchone()==(False,True)
        c.execute(sql.SQL('ALTER SCHEMA public OWNER TO {}').format(sql.Identifier(owner_role)))
        c.execute(sql.SQL('ALTER SCHEMA portfolio_execution OWNER TO {}').format(sql.Identifier(owner_role)))
        for namespace,names in [('public',__import__('data.security_schema',fromlist=['APP_TABLES']).APP_TABLES),
                                ('portfolio_execution',__import__('data.investment_schema',fromlist=['TABLES']).TABLES)]:
            for table in names:
                c.execute(sql.SQL('ALTER TABLE {}.{} OWNER TO {}').format(sql.Identifier(namespace),sql.Identifier(table),sql.Identifier(owner_role)))
        conn.commit()
    def owner_connect():
        conn=connect()
        with conn.cursor() as c:c.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(owner_role)))
        return conn
    owner_ctx=RepositoryContext(owner_connect,lambda:uuid4().hex,lambda:None,lambda:1400)
    schema.init_db(owner_ctx)
    owner_plan=plans.save(owner_ctx,'default','Non-super owner cycle',plan_data)
    owner_req=Setup(request_id='qa-owner-start',plan_id=owner_plan,representative_account_id='cma',usd_krw=1400).model_dump(mode='json')
    owner_req['preview_token']=investments.prepare(owner_ctx,'default',owner_req)['preview_token']
    owner_cycle=investments.create(owner_ctx,'default',owner_req)
    owner_read=investments.read(owner_ctx,'default',owner_cycle['id'])
    owner_step=next(s for s in owner_read['steps'] if s.get('asset_id')=='bond')
    owner_buy=BatchTradeRequest(request_id='qa-owner-buy',portfolio_id='default',trade_date=day,trades=[
        dict(account_id='isa',asset_id='bond',trade_type='BUY',quantity=1,price=9000,currency='KRW',
            execution=dict(cycle_id=owner_cycle['id'],step_id=owner_step['id'],revision=1))]).model_dump(mode='json')
    owner_receipt=trades.execute_batch(owner_ctx,owner_buy)
    assert len(investments.read(owner_ctx,'default',owner_cycle['id'])['results'])==1
    before_excluded=cash()
    excluded=dict(request_id='qa-owner-exclude',revision=1,reason='Synthetic exclusion',changes=[dict(step_id=owner_step['id'],status='EXCLUDED')])
    investments.revise(owner_ctx,'default',owner_cycle['id'],excluded)
    extra_buy={**owner_buy,'request_id':'qa-owner-excluded-buy','trades':[{**owner_buy['trades'][0],'execution':{**owner_buy['trades'][0]['execution'],'revision':2}}]}
    fail(lambda:trades.execute_batch(owner_ctx,extra_buy),'제외')
    assert cash()==before_excluded and scalar("SELECT count(*) FROM bookkeeping_requests WHERE request_id='qa-owner-excluded-buy'")==0
    ok,message=trades.delete_trades(owner_ctx,owner_receipt['trade_ids']);assert ok,message
    assert investments.read(owner_ctx,'default',owner_cycle['id'])['results'][0]['voided']
    print('PASS: start/retry, funding/transfers, atomic posting, partial fills, goal revision/recalculation, mock confirmation/failure recovery, identified cross-source duplicate blocking, FX cost, cancellation, scope/auth/private RLS, report')
finally:
    settings['dbname']='postgres';admin=psycopg2.connect(**settings);admin.autocommit=True
    assert name.startswith('investment_qa_')
    with admin.cursor() as c:
        c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        assert owner_role.startswith('execution_owner_')
        c.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(owner_role)))
    admin.close()
