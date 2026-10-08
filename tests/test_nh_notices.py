"""Transactional bookkeeping tests; synthetic in-memory data only."""
import json
from datetime import date,datetime
from decimal import Decimal
from copy import deepcopy
from types import SimpleNamespace
import pytest
from psycopg2.extras import Json
from test_trade_reversal import DatabaseAdapter,CursorAdapter
from backend.routers.nh_notices import Batch,Row
from data.repositories import nh_notices,performance

class NoticeCursor(CursorAdapter):
    def __enter__(self):return self
    def __exit__(self,*args):self.cursor.close()
    def execute(self,sql,params=()):
        values=[]
        for v in params:
            if isinstance(v,Json): v=json.dumps(v.adapted,default=str)
            elif isinstance(v,(date,datetime)): v=v.isoformat()
            values.append(v)
        return super().execute(sql,values)
    @staticmethod
    def decode(row):
        if row is None:return None
        for key in ('payload','result','audit','baseline_payload','before_state','after_state','request','history','reviews'):
            if isinstance(row.get(key),str): row[key]=json.loads(row[key])
        if isinstance(row.get('baseline_date'),str): row['baseline_date']=date.fromisoformat(row['baseline_date'])
        return row
    def fetchone(self): return self.decode(super().fetchone())
    def fetchall(self): return [self.decode(row) for row in super().fetchall()]

class NoticeDatabase(DatabaseAdapter):
    def __enter__(self):return self
    def __exit__(self,kind,*args):
        self.rollback() if kind else self.commit()
    def cursor(self,**kwargs):return NoticeCursor(self)
    def rows(self,table):
        order='account_id' if table=='usd_cash_state' else 'id'
        return [dict(r) for r in self.raw.execute('SELECT * FROM '+table+' ORDER BY '+order)]

@pytest.fixture
def db():
    database=NoticeDatabase()
    database.raw.executescript('''
      CREATE TABLE portfolios(id TEXT PRIMARY KEY,name TEXT DEFAULT 'Test');
      INSERT INTO portfolios(id) VALUES('p');
      ALTER TABLE accounts ADD COLUMN account_alias TEXT DEFAULT 'Test';
      ALTER TABLE accounts ADD COLUMN portfolio_id TEXT DEFAULT 'p';
      ALTER TABLE assets ADD COLUMN portfolio_id TEXT DEFAULT 'p';
      ALTER TABLE assets ADD COLUMN is_deposit INTEGER DEFAULT 0;
      ALTER TABLE assets ADD COLUMN ticker TEXT DEFAULT '0085P0';
      ALTER TABLE assets ADD COLUMN allowed_accounts TEXT DEFAULT '["acc"]';
      ALTER TABLE trade_history ADD COLUMN import_source TEXT;
      ALTER TABLE trade_history ADD COLUMN broker_order_no TEXT;
      UPDATE accounts SET deposit_krw=4,deposit_usd=10;
      INSERT INTO usd_cash_state(account_id,usd_balance,cost_krw,last_event_date) VALUES('acc',10,13000,'2026-01-01');
      CREATE TABLE performance_tracking(portfolio_id TEXT PRIMARY KEY,baseline_date TEXT,revision INT DEFAULT 0);
      INSERT INTO performance_tracking(portfolio_id,baseline_date) VALUES('p','2026-01-01');
      CREATE TABLE performance_flows(id TEXT PRIMARY KEY,portfolio_id TEXT,account_id TEXT,request_id TEXT,
        event_date TEXT,amount_krw REAL,currency TEXT,native_amount REAL,exchange_rate REAL,notes TEXT,
        voided BOOLEAN DEFAULT 0,recorded_at TEXT DEFAULT CURRENT_TIMESTAMP);
      INSERT INTO performance_flows(id,portfolio_id,account_id,request_id,event_date,amount_krw,currency,native_amount,exchange_rate)
        VALUES('legacy','p','acc','old-request','2026-01-02',960000,'KRW',960000,1);
      CREATE TABLE nh_notice_batches(id TEXT PRIMARY KEY,portfolio_id TEXT,request_id TEXT,payload TEXT,result TEXT,audit TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,reversed_at TEXT,UNIQUE(portfolio_id,request_id));
      DROP TABLE nh_notice_items;
      CREATE TABLE nh_notice_items(id TEXT UNIQUE,sequence INTEGER PRIMARY KEY AUTOINCREMENT,batch_id TEXT,portfolio_id TEXT,
        account_id TEXT,event_date TEXT,kind TEXT,fingerprint TEXT,payload TEXT,result TEXT,performance_flow_id TEXT,linked_trade_id TEXT,linked_usd_event_id TEXT,reversed_at TEXT);
      CREATE UNIQUE INDEX notice_flow ON nh_notice_items(performance_flow_id) WHERE performance_flow_id IS NOT NULL AND reversed_at IS NULL;
    ''')
    database.commit()
    n=[0]
    def ident():n[0]+=1;return 'id-'+str(n[0])
    database.ctx=SimpleNamespace(connect=lambda:database,new_id=ident,invalidate=lambda:None,exchange_rate=lambda:1400)
    yield database
    database.raw.close()

def row(kind,**kw):
    return Row(kind=kind,account_id='acc',event_date='2026-01-02',fingerprint=('a' if kind=='DEPOSIT' else 'b')*64,**kw)

def payload(db,rows,request='request-1'):
    return Batch(request_id=request,confirmed=True,rows=rows,
        expected_cash={'acc':{'deposit_krw':db.balances()[0],'deposit_usd':db.balances()[1]}}).model_dump(mode='json')

def scenario(db,request='request-1'):
    return payload(db,[row('DEPOSIT',krw_amount=960000,existing_flow_id='legacy'),
        row('EXCHANGE_IN',krw_amount=959997,usd_amount=717.31,quoted_rate=1338.33)],request)

def test_existing_flow_cash_exchange_commit_and_idempotent_retry(db):
    data=scenario(db); result=nh_notices.commit(db.ctx,'p',data)
    assert db.balances()==pytest.approx((7,727.31))
    state=db.rows('usd_cash_state')[0]
    assert state['cost_krw']==pytest.approx(972997)
    assert len(db.rows('performance_flows'))==1
    assert db.rows('usd_cash_events')[0]['occurred_at'] is None
    assert nh_notices.commit(db.ctx,'p',data)==result
    assert db.balances()==pytest.approx((7,727.31))
    assert len(db.rows('nh_notice_batches'))==1
    changed=deepcopy(data);changed['rows'][0]['krw_amount']=960001
    with pytest.raises(ValueError,match='같은 저장 요청'):nh_notices.commit(db.ctx,'p',changed)

def test_failed_exchange_rolls_back_deposit_journal_and_every_cash_change(db):
    data=scenario(db);data['rows'][1]['krw_amount']=970000
    with pytest.raises(ValueError,match='부족'):nh_notices.commit(db.ctx,'p',data)
    assert db.balances()==(4,10)
    assert len(db.rows('performance_flows'))==1
    assert not db.rows('nh_notice_items') and not db.rows('nh_notice_batches') and not db.rows('usd_cash_events')

def test_scoped_account_and_stale_cash_block_all_writes(db):
    data=scenario(db);data['expected_cash']['acc']['deposit_krw']=3
    with pytest.raises(ValueError,match='변경'):nh_notices.commit(db.ctx,'p',data)
    db.raw.execute("UPDATE accounts SET portfolio_id='other'");db.commit()
    with pytest.raises(ValueError,match='포트폴리오'):nh_notices.commit(db.ctx,'p',scenario(db))
    assert db.balances()==(4,10)

def test_unknown_usd_cost_and_changed_dollar_balance_are_not_guessed(db):
    db.raw.execute('DELETE FROM usd_cash_state');db.commit()
    with pytest.raises(ValueError,match='기준환율'):nh_notices.commit(db.ctx,'p',scenario(db))
    assert db.balances()==(4,10)
    db.raw.execute("INSERT INTO usd_cash_state(account_id,usd_balance,cost_krw,last_event_date) VALUES('acc',11,13000,'2026-01-01')");db.commit()
    with pytest.raises(ValueError,match='원가 기록'):nh_notices.commit(db.ctx,'p',scenario(db))
    assert db.balances()==(4,10)

def test_existing_flow_must_match_and_cannot_receive_cash_twice(db):
    data=scenario(db);data['rows'][0]['existing_flow_id']='wrong'
    with pytest.raises(ValueError,match='연결할'):nh_notices.commit(db.ctx,'p',data)
    nh_notices.commit(db.ctx,'p',scenario(db))
    data=scenario(db,'request-2');data['rows'][0]['duplicate_confirmed']=True
    with pytest.raises(ValueError,match='이미 예수금'):nh_notices.commit(db.ctx,'p',data)
    assert db.balances()==pytest.approx((7,727.31))

def test_record_only_does_not_change_cash_and_cash_linked_flow_cannot_be_voided_alone(db):
    result=nh_notices.commit(db.ctx,'p',payload(db,[row('DEPOSIT',krw_amount=960000,existing_flow_id='legacy',apply_cash=False)]))
    assert db.balances()==(4,10)
    with pytest.raises(ValueError,match='묶음 취소'):performance.void_flow(db.ctx,'p','legacy',True)
    nh_notices.undo(db.ctx,'p',result['batch_id'])
    assert db.balances()==(4,10) and not db.rows('performance_flows')[0]['voided']

def test_undo_restores_cost_and_original_flow_preserves_audit_and_blocks_late_changes(db):
    result=nh_notices.commit(db.ctx,'p',scenario(db))
    db.raw.execute('UPDATE accounts SET deposit_krw=8');db.commit()
    with pytest.raises(ValueError,match='후속 거래'):nh_notices.undo(db.ctx,'p',result['batch_id'])
    assert db.balances()==pytest.approx((8,727.31))
    db.raw.execute('UPDATE accounts SET deposit_krw=7');db.commit()
    nh_notices.undo(db.ctx,'p',result['batch_id'])
    assert db.balances()==pytest.approx((4,10))
    assert db.rows('usd_cash_state')[0]['cost_krw']==13000
    assert len(db.rows('performance_flows'))==1 and not db.rows('performance_flows')[0]['voided']
    assert db.rows('nh_notice_items')[0]['reversed_at']
    assert db.rows('usd_cash_events')[0]['reversed_at']
    assert nh_notices.undo(db.ctx,'p',result['batch_id'])['reversed']

def test_legacy_cash_adjustment_is_blocked_without_audited_correction(db):
    before=db.balances(),db.rows('usd_cash_state')
    with pytest.raises(ValueError,match='4번 탭'):
        nh_notices.commit(db.ctx,'p',payload(db,[row('KRW_ADJUST',krw_amount=960004)]))
    assert (db.balances(),db.rows('usd_cash_state'))==before


def test_new_deposit_buy_and_undo_preserve_manually_seeded_holdings(db):
    db.raw.execute("INSERT INTO holdings(id,account_id,asset_id,quantity,avg_price,avg_price_usd,buy_fx_rate,original_avg_price,original_avg_price_usd) VALUES('prior','acc','ast',3,9000,0,0,9000,0)");db.commit()
    before=db.rows('holdings')
    data=payload(db,[row('DEPOSIT',krw_amount=190000),row('BUY',asset_id='ast',quantity=20,price=9320,broker_order_no='42954')])
    result=nh_notices.commit(db.ctx,'p',data)
    assert db.balances()==(3604,10)
    assert db.holding()[0]==23 and len(db.rows('performance_flows'))==2
    nh_notices.undo(db.ctx,'p',result['batch_id'])
    assert db.balances()==(4,10) and db.rows('holdings')==before
    assert not db.rows('trade_history')
    assert sum(not f['voided'] for f in db.rows('performance_flows'))==1

def test_buy_failure_after_cash_and_new_flow_rolls_everything_back(db):
    db.fail_on='INSERT INTO holdings'
    data=payload(db,[row('DEPOSIT',krw_amount=190000),row('BUY',asset_id='ast',quantity=20,price=9320,broker_order_no='42954')])
    with pytest.raises(ValueError):nh_notices.commit(db.ctx,'p',data)
    assert db.balances()==(4,10) and len(db.rows('performance_flows'))==1
    assert not db.rows('trade_history') and not db.rows('nh_notice_items')

def test_context_exposes_link_status_and_no_raw_notification_text(db):
    nh_notices.commit(db.ctx,'p',scenario(db))
    context=nh_notices.read_context(db.ctx,'p',date(2026,1,2))
    assert context['flows'][0]['cash_handled']
    assert len(context['notices'])==2 and len(context['batches'])==1
    assert 'audit' not in context['batches'][0] and 'raw' not in json.dumps(context,default=str)


def test_individual_fx_cancel_cannot_split_confirmed_batch(db):
    from data.repositories import forex
    result=nh_notices.commit(db.ctx,'p',scenario(db))
    event=result['items'][1]['usd_event_id']
    ok,msg=forex.undo_event(db.ctx,'acc',event)
    assert not ok and '묶음 취소' in msg
    assert db.balances()==pytest.approx((7,727.31))
    nh_notices.undo(db.ctx,'p',result['batch_id'])
    assert db.balances()==(4,10)

def add_counterparty(db, *, track=True):
    db.raw.execute("INSERT INTO portfolios(id) VALUES('pool')")
    db.raw.execute("INSERT INTO accounts(id,portfolio_id,deposit_krw,deposit_usd) VALUES('peer','pool',100,0)")
    if track: db.raw.execute("INSERT INTO performance_tracking(portfolio_id,baseline_date) VALUES('pool','2026-01-01')")
    db.raw.execute("UPDATE accounts SET deposit_krw=1000004 WHERE id='acc'")
    db.commit()


def transfer_payload(db, *, kind='WITHDRAW', apply=True, request='transfer-1'):
    kw={'destination_account_id':'peer'} if kind=='WITHDRAW' else {'source_account_id':'peer'}
    data=payload(db,[row(kind,external=False,cross_portfolio=True,apply_cash=apply,krw_amount=1000000,**kw)],request)
    data['expected_cash']['peer']={'deposit_krw':db.raw.execute("SELECT deposit_krw FROM accounts WHERE id='peer'").fetchone()[0],'deposit_usd':0}
    return data


def test_withdrawal_subtracts_cash_and_records_signed_flow_and_undo(db):
    data=payload(db,[row('WITHDRAW',krw_amount=3)])
    result=nh_notices.commit(db.ctx,'p',data)
    assert db.balances()==(1,10)
    f=next(f for f in db.rows('performance_flows') if f['id']!='legacy')
    assert f['amount_krw']==-3 and f['native_amount']==3
    nh_notices.undo(db.ctx,'p',result['batch_id'])
    assert db.balances()==(4,10)
    assert next(f for f in db.rows('performance_flows') if f['id']!='legacy')['voided']


def test_insufficient_withdrawal_rolls_back_new_flow_and_all_items(db):
    with pytest.raises(ValueError,match='부족'):nh_notices.commit(db.ctx,'p',payload(db,[row('WITHDRAW',krw_amount=5)]))
    assert db.balances()==(4,10) and len(db.rows('performance_flows'))==1 and not db.rows('nh_notice_items')


def test_historical_withdrawal_is_auditable_without_changing_cash_or_current_performance(db):
    old=row('WITHDRAW',krw_amount=1000000,apply_cash=False).model_copy(update={'event_date':date(2025,9,30)})
    result=nh_notices.commit(db.ctx,'p',payload(db,[old]))
    assert db.balances()==(4,10) and len(db.rows('performance_flows'))==1
    assert db.rows('nh_notice_items')[0]['kind']=='WITHDRAW'
    assert result['items'][0]['flow_id'] is None
    nh_notices.undo(db.ctx,'p',result['batch_id'])
    old=old.model_copy(update={'apply_cash':True})
    with pytest.raises(ValueError,match='기준일 이전'):nh_notices.commit(db.ctx,'p',payload(db,[old],'history-2'))


def test_cross_portfolio_withdrawal_updates_both_cash_and_offsetting_flows_atomically(db):
    add_counterparty(db)
    data=transfer_payload(db);result=nh_notices.commit(db.ctx,'p',data)
    cash={r['id']:r['deposit_krw'] for r in db.rows('accounts')}
    assert cash=={'acc':4,'peer':1000100}
    flows=[f for f in db.rows('performance_flows') if f['id']!='legacy']
    assert {f['portfolio_id']:f['amount_krw'] for f in flows}=={'p':-1000000,'pool':1000000}
    assert sum(f['amount_krw'] for f in flows)==0
    assert result['notice_count']==1 and len(result['items'])==2
    assert nh_notices.commit(db.ctx,'p',data)==result
    context=nh_notices.read_context(db.ctx,'pool',date(2026,1,2))
    assert context['flows'][0]['cash_handled'] and context['batches'][0]['id']==result['batch_id']
    with pytest.raises(ValueError,match='묶음 취소'):performance.void_flow(db.ctx,'pool',context['flows'][0]['id'],True)
    nh_notices.undo(db.ctx,'pool',result['batch_id'])
    assert {r['id']:r['deposit_krw'] for r in db.rows('accounts')}=={'acc':1000004,'peer':100}
    assert all(f['voided'] for f in db.rows('performance_flows') if f['id']!='legacy')


def test_cross_portfolio_deposit_notification_uses_its_source_account(db):
    add_counterparty(db)
    db.raw.execute("UPDATE accounts SET deposit_krw=1000100 WHERE id='peer'");db.commit()
    result=nh_notices.commit(db.ctx,'p',transfer_payload(db,kind='DEPOSIT'))
    assert {r['id']:r['deposit_krw'] for r in db.rows('accounts')}=={'acc':2000004,'peer':100}
    assert {f['portfolio_id']:f['amount_krw'] for f in db.rows('performance_flows') if f['id']!='legacy'}=={'p':1000000,'pool':-1000000}
    nh_notices.undo(db.ctx,'pool',result['batch_id'])


def test_counterparty_failure_rolls_back_primary_cash_and_flow(db):
    add_counterparty(db)
    db.raw.execute("INSERT INTO performance_flows(id,portfolio_id,account_id,request_id,event_date,amount_krw,currency,native_amount,exchange_rate) VALUES('peer-existing','pool','peer','peer-existing','2026-01-02',1000000,'KRW',1000000,1)");db.commit()
    with pytest.raises(ValueError,match='같은 입출금'):nh_notices.commit(db.ctx,'p',transfer_payload(db))
    assert {r['id']:r['deposit_krw'] for r in db.rows('accounts')}=={'acc':1000004,'peer':100}
    assert len(db.rows('performance_flows'))==2 and not db.rows('nh_notice_items')


def test_record_only_cross_portfolio_and_untracked_counterparty(db):
    add_counterparty(db,track=False)
    result=nh_notices.commit(db.ctx,'p',transfer_payload(db,apply=False))
    assert {r['id']:r['deposit_krw'] for r in db.rows('accounts')}=={'acc':1000004,'peer':100}
    assert len(db.rows('performance_flows'))==2 and len(db.rows('nh_notice_items'))==2
    assert result['performance_portfolios']==['p']


def test_wrong_transfer_scope_and_missing_peer_expected_cash_cannot_write(db):
    add_counterparty(db)
    data=transfer_payload(db);data['rows'][0]['cross_portfolio']=False
    with pytest.raises(ValueError,match='구분'):nh_notices.commit(db.ctx,'p',data)
    data=transfer_payload(db);data['expected_cash'].pop('peer')
    with pytest.raises(ValueError,match='변경'):nh_notices.commit(db.ctx,'p',data)
    assert len(db.rows('performance_flows'))==1 and not db.rows('nh_notice_items')


def test_opposite_notification_cannot_repeat_a_registered_transfer(db):
    add_counterparty(db)
    nh_notices.commit(db.ctx,'p',transfer_payload(db))
    other=Batch(request_id='opposite-1',confirmed=True,rows=[Row(kind='DEPOSIT',account_id='peer',source_account_id='acc',external=False,cross_portfolio=True,event_date='2026-01-02',krw_amount=1000000,fingerprint='c'*64)],expected_cash={'acc':{'deposit_krw':4,'deposit_usd':10},'peer':{'deposit_krw':1000100,'deposit_usd':0}}).model_dump(mode='json')
    with pytest.raises(ValueError,match='이미 반영'):nh_notices.commit(db.ctx,'pool',other)
    assert len(db.rows('nh_notice_batches'))==1


def test_later_counterparty_change_blocks_transfer_undo(db):
    add_counterparty(db);result=nh_notices.commit(db.ctx,'p',transfer_payload(db))
    db.raw.execute("UPDATE accounts SET deposit_krw=0 WHERE id='peer'");db.commit()
    with pytest.raises(ValueError,match='후속 거래'):nh_notices.undo(db.ctx,'p',result['batch_id'])
    assert all(not f['voided'] for f in db.rows('performance_flows'))

def test_retry_of_a_pre_upgrade_pending_request_remains_idempotent(db):
    data=scenario(db);result=nh_notices.commit(db.ctx,'p',data)
    old=deepcopy(data)
    for r in old['rows']:
        for key in ('cross_portfolio','destination_account_id','counterparty_flow_id','reported_available_krw'):r.pop(key,None)
    db.raw.execute('UPDATE nh_notice_batches SET payload=?',(json.dumps(old),));db.commit()
    assert nh_notices.commit(db.ctx,'p',data)==result
    assert len(db.rows('nh_notice_batches'))==1


def test_unrelated_portfolio_cannot_undo_a_transfer(db):
    add_counterparty(db);result=nh_notices.commit(db.ctx,'p',transfer_payload(db))
    db.raw.execute("INSERT INTO portfolios(id) VALUES('unrelated')");db.commit()
    with pytest.raises(ValueError,match='이력'):nh_notices.undo(db.ctx,'unrelated',result['batch_id'])
    assert {r['id']:r['deposit_krw'] for r in db.rows('accounts')}=={'acc':4,'peer':1000100}
