"""Audited corrections against synthetic, transactional in-memory fixtures only."""
from copy import deepcopy
from datetime import date
import json
import pytest
from test_nh_notices import db, row, payload
from backend.routers.ledger_adjustments import Proposal
from data.repositories import ledger_adjustments as repo, nh_notices, trades, forex
from logic.ledger_reconciliation import mask_uncertain

@pytest.fixture
def book(db):
    db.raw.executescript('''
      ALTER TABLE performance_tracking ADD COLUMN baseline_value REAL;
      ALTER TABLE performance_tracking ADD COLUMN baseline_payload TEXT;
      CREATE TABLE performance_snapshots(portfolio_id TEXT,snapshot_date TEXT,value_krw REAL,payload TEXT,record_kind TEXT DEFAULT 'close',recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(portfolio_id,snapshot_date));
      CREATE TABLE performance_snapshot_revisions(id INTEGER PRIMARY KEY AUTOINCREMENT,portfolio_id TEXT,snapshot_date TEXT,value_krw REAL,payload TEXT,record_kind TEXT,recorded_at TEXT);
      CREATE TABLE performance_close_jobs(portfolio_id TEXT,snapshot_date TEXT,state TEXT,inputs TEXT);
      UPDATE accounts SET deposit_krw=2000000;
      UPDATE performance_tracking SET baseline_date='2026-10-05',baseline_value=2014000;
    ''')
    frozen={'ledger':{'accounts':[{'id':'acc','deposit_krw':2000000,'deposit_usd':10}],'holdings':[]},'fx':{'rate':1400},'prices':{'ast':{'price_krw':100}}}
    db.raw.execute('UPDATE performance_tracking SET baseline_payload=?',(json.dumps(frozen),))
    for day in ['2026-10-05','2026-10-06','2026-10-07']:
        db.raw.execute('INSERT INTO performance_snapshots(portfolio_id,snapshot_date,value_krw,payload) VALUES(?,?,?,?)',('p',day,2014000,json.dumps(frozen)))
    db.commit()
    return db

def proposal(**kwargs):
    return Proposal(kind='PAST_WITHDRAWAL',account_id='acc',event_date='2026-09-30',reason='QA missing withdrawal',amount=1000000,**kwargs).model_dump(mode='json')

def request(book,p=None,decisions=None,ident='QA-correction-1'):
    p=p or proposal()
    proof=repo.preview(book.ctx,'p',p)
    return dict(request_id=ident,token=proof['token'],proposal=p,decisions=decisions or {},confirmed=True)

def save(book,p=None,decisions=None,ident='QA-correction-1'):
    req=request(book,p,decisions,ident)
    return repo.commit(book.ctx,'p',req)['id'],req

def test_missing_withdrawal_updates_cash_and_only_explicit_historic_errors(book):
    ident,req=save(book,decisions={'baseline':'ERROR','2026-10-05':'ERROR','2026-10-06':'NORMAL'})
    assert book.balances()==(1000000,10)
    assert book.raw.execute('SELECT baseline_value FROM performance_tracking').fetchone()[0]==1014000
    values=[r['value_krw'] for r in book.rows('performance_snapshot_revisions')]
    assert values==[2014000]
    snaps=book.raw.execute('SELECT value_krw FROM performance_snapshots ORDER BY snapshot_date').fetchall()
    assert [r[0] for r in snaps]==[1014000,2014000,2014000]
    assert not any(r['event_date']=='2026-09-30' for r in book.rows('performance_flows'))
    assert repo.commit(book.ctx,'p',req)['id']==ident and book.balances()[0]==1000000
    assert repo.read(book.ctx,'p')['adjustments'][0]['history'][-1]['decision']=='UNKNOWN'
    assert 'before' not in repo.read(book.ctx,'p')['adjustments'][0]['history'][0]

def test_later_history_review_never_withdraws_cash_twice(book):
    ident,_=save(book)
    r=repo.review_preview(book.ctx,'p',ident)
    req=dict(request_id='QA-history-1',token=r['token'],decisions={h['key']:'ERROR' for h in r['history']},confirmed=True)
    repo.review(book.ctx,'p',ident,req)
    repo.review(book.ctx,'p',ident,req)
    assert book.balances()[0]==1000000
    assert [r[0] for r in book.raw.execute('SELECT value_krw FROM performance_snapshots')]==[1014000]*3
    assert repo.read(book.ctx,'p')['adjustments'][0]['history'][0]['decision']=='ERROR'

def test_undo_restores_current_and_historical_values_and_is_idempotent(book):
    ident,_=save(book,decisions={k:'ERROR' for k in ['baseline','2026-10-05','2026-10-06','2026-10-07']})
    assert repo.undo(book.ctx,'p',ident)['reversed']
    assert repo.undo(book.ctx,'p',ident)['reversed']
    assert book.balances()[0]==2000000
    assert book.raw.execute('SELECT baseline_value FROM performance_tracking').fetchone()[0]==2014000
    assert [r[0] for r in book.raw.execute('SELECT value_krw FROM performance_snapshots')]==[2014000]*3
    assert len(book.rows('performance_snapshot_revisions'))==6

@pytest.mark.parametrize('change',['UPDATE accounts SET deposit_krw=2100000',"UPDATE performance_snapshots SET value_krw=3000000 WHERE snapshot_date='2026-10-07'"])
def test_stale_preview_never_applies(book,change):
    req=request(book);book.raw.execute(change);book.commit()
    with pytest.raises(ValueError,match='변경'):repo.commit(book.ctx,'p',req)
    assert not book.rows('ledger_adjustments')

def test_same_request_id_with_different_content_is_rejected(book):
    _,req=save(book);req['proposal']['reason']='QA other reason'
    with pytest.raises(ValueError,match='내용'):repo.commit(book.ctx,'p',req)
    assert book.balances()[0]==1000000

def test_write_failure_rolls_back_cash_history_and_audit(book):
    req=request(book,decisions={'baseline':'ERROR'});book.fail_on='INSERT INTO ledger_adjustments'
    with pytest.raises(Exception,match='injected'):repo.commit(book.ctx,'p',req)
    book.fail_on=None
    assert book.balances()[0]==2000000 and not book.rows('ledger_adjustments')
    assert book.raw.execute('SELECT baseline_value FROM performance_tracking').fetchone()[0]==2014000

def test_missing_frozen_evidence_cannot_be_called_an_error(book):
    book.raw.execute("UPDATE performance_tracking SET baseline_payload='{}'");book.commit()
    p=repo.preview(book.ctx,'p',proposal());assert not p['history'][0]['can_correct']
    with pytest.raises(ValueError,match='기록'):save(book,decisions={'baseline':'ERROR'})
    assert book.balances()[0]==2000000
    ident,_=save(book)
    assert repo.read(book.ctx,'p')['adjustments'][0]['history'][0]['decision']=='UNKNOWN'

def test_followup_cash_movement_blocks_undo_without_partial_changes(book):
    ident,_=save(book,decisions={'baseline':'ERROR'})
    book.raw.execute('UPDATE accounts SET deposit_krw=1000001');book.commit()
    with pytest.raises(ValueError,match='후속'):repo.undo(book.ctx,'p',ident)
    assert book.balances()[0]==1000001
    assert book.raw.execute('SELECT baseline_value FROM performance_tracking').fetchone()[0]==1014000

def test_active_close_job_blocks_correction_and_waiting_job_is_refreshed(book):
    day=repo.datetime.now(repo.forex.KST).date().isoformat()
    book.raw.execute("INSERT INTO performance_close_jobs VALUES('p',?,'running','{}')",(day,));book.commit()
    req=request(book)
    with pytest.raises(ValueError,match='종가 수집'):repo.commit(book.ctx,'p',req)
    book.raw.execute("UPDATE performance_close_jobs SET state='retry'");book.commit()
    repo.commit(book.ctx,'p',req)
    assert book.raw.execute('SELECT inputs FROM performance_close_jobs').fetchone()[0] is None

def test_usd_cash_adjustment_preserves_separate_holdings_and_undo_restores_cost(book):
    p=Proposal(kind='CASH',account_id='acc',event_date='2026-10-08',reason='QA broker USD reconciliation',currency='USD',balance=20,usd_average_rate=1350).model_dump(mode='json')
    ident,_=save(book,p)
    assert book.balances()==(2000000,20)
    assert book.rows('usd_cash_state')[0]['cost_krw']==27000
    event=book.rows('usd_cash_events')[0]
    ok,msg=forex.undo_event(book.ctx,'acc',event['id']);assert not ok and '장부 정정' in msg
    repo.undo(book.ctx,'p',ident)
    assert book.balances()==(2000000,10) and book.rows('usd_cash_state')[0]['cost_krw']==13000

@pytest.mark.parametrize('us,qty',[(False,3),(False,0),(True,3),(True,0)])
def test_holding_cost_anchor_never_spends_cash_and_can_register_zero(book,us,qty):
    if us:book.raw.execute("UPDATE assets SET market='US'");book.commit()
    p=Proposal(kind='HOLDING',account_id='acc',asset_id='ast',event_date='2026-10-08',reason='QA initial holding',quantity=qty,avg_price=123,avg_price_usd=100,buy_fx_rate=1300,first_buy_date='2026-01-01',manual_dividend_override=100).model_dump(mode='json')
    cost=book.rows('usd_cash_state');ident,_=save(book,p)
    assert book.balances()==(2000000,10) and book.rows('usd_cash_state')==cost
    assert book.rows('holdings')[0]['quantity']==qty
    assert book.rows('holdings')[0]['original_avg_price']==(130000 if us else 123)
    anchor=book.rows('trade_history')[0]
    ok,msg=trades.delete_trades(book.ctx,[anchor['id']]);assert not ok and '정정' in msg
    ok,msg=trades.execute_trade(book.ctx,'2026-10-07','acc','ast','BUY',1,123,'USD' if us else 'KRW',1300)
    assert not ok and '정정 이전' in msg
    repo.undo(book.ctx,'p',ident);assert not book.rows('holdings') and not book.rows('trade_history')

def test_older_nh_batch_cannot_bypass_even_zero_delta_correction(book):
    batch=nh_notices.commit(book.ctx,'p',payload(book,[row('DEPOSIT',krw_amount=1).model_copy(update={'event_date':date(2026,10,8)})]))
    p=Proposal(kind='CASH',account_id='acc',event_date='2026-10-08',reason='QA checked cash',balance=2000001).model_dump(mode='json')
    ident,_=save(book,p)
    with pytest.raises(ValueError,match='이후'):nh_notices.undo(book.ctx,'p',batch['batch_id'])
    repo.undo(book.ctx,'p',ident);nh_notices.undo(book.ctx,'p',batch['batch_id']);assert book.balances()[0]==2000000

def test_adjustments_are_scoped_and_new_withdrawals_use_normal_flow(book):
    with pytest.raises(ValueError,match='포트폴리오'):repo.preview(book.ctx,'other',proposal())
    p=proposal();p['event_date']='2026-10-08'
    with pytest.raises(ValueError,match='이후 출금'):repo.preview(book.ctx,'p',p)
    nh_notices.commit(book.ctx,'p',payload(book,[row('WITHDRAW',krw_amount=1000000).model_copy(update={'event_date':date(2026,10,8)})]))
    assert book.balances()[0]==1000000
    assert any(r['amount_krw']==-1000000 for r in book.rows('performance_flows'))

def test_unconfirmed_masks_only_returns_that_use_unconfirmed_boundaries():
    day=lambda n:date(2026,10,n)
    r={'tracking':{'baseline_date':day(5)},'daily_reports':[{'start':day(5),'end':day(7),'partial':True,'profit':100,'return_pct':1}],
       'reports':[{'start':day(6),'end':day(7),'partial':False,'profit':100,'return_pct':1}]}
    result=mask_uncertain(deepcopy(r),[{'history':[{'key':'baseline','decision':'UNKNOWN'}]}])
    assert result['daily_reports'][0]['profit'] is None and result['reports'][0]['profit']==100
    result=mask_uncertain(deepcopy(r),[{'history':[{'key':'2026-10-07','decision':'UNKNOWN'}]}])
    assert all(x['profit'] is None for x in result['daily_reports']+result['reports'])
