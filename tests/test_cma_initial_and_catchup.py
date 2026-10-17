"""Core completion tests: opening income then dated, exactly-once daily income."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import pytest
from data.repositories import cma,activity
from logic import cma_policy,cma_statement
from logic.cma_interest import observe_balance,fingerprint
from logic.cma_reconciliation import reconcile
from backend.cma_interest import DailyCMA
from test_cma_repository import book,proposal
from test_cma_interest import NOW,wire
from test_cma_reconciliation import statement,PROFILE


def initial_request(book,*,prior=100,paid=23,now=NOW):
    current=cma.read_book(book.ctx,'p','acc');opening=Decimal(str(current['account']['deposit_krw']))+prior
    cash=opening+paid;evidence=observe_balance(wire(str(cash)),now)
    proof=reconcile(statement(now,opening,cash),[],pid='p',aid='acc',book_token=current['book_token'],
        book_cash=current['account']['deposit_krw'],observation=evidence)
    assert proof['status']=='INITIAL_BALANCE_REVIEW'
    obs=cma.record_observation(book.ctx,'p','acc',evidence,current['book_token'],reconciliation=proof)
    return dict(request_id='initial-request-01',account_id='acc',observation_id=obs['id'],
        book_token=current['book_token'],initial_interest_krw=str(prior),confirmed_initial_interest=True,
        reason='Previously accumulated paid interest; withdrawals already booked.')


def test_initial_prior_only_then_fresh_daily_receipt_without_replaying_withdrawal(book):
    req=initial_request(book);result=cma.initialize_interest(book.ctx,'p',req,NOW)
    assert Decimal(result['initial_interest_krw'])==100 and Decimal(result['pending_paid_interest_krw'])==23
    assert book.balances()[0]==4800100
    assert book.raw.execute('SELECT COUNT(*) FROM portfolio_cma.income').fetchone()[0]==0
    details=__import__('json').loads(book.raw.execute('SELECT details FROM portfolio_cma.openings').fetchone()[0])
    assert details['historical_payment_dates'] is None and details['pending_paid_interest_krw']=='23.0'
    assert book.raw.execute('SELECT amount_krw FROM performance_flows').fetchone()[0]==-200000
    with pytest.raises(ValueError,match='変|바뀌'):
        cma.commit(book.ctx,'p',dict(request_id='old-observation',account_id='acc',observation_id=req['observation_id'],
            book_token=req['book_token'],interest_krw='123',confirmed_movements=True),NOW)
    daily=proposal(book,cash=4800123,verified=True)
    cma.commit(book.ctx,'p',daily,NOW)
    assert book.balances()[0]==4800123 and Decimal(cma.read(book.ctx,'p')['interest_total_krw'])==123
    assert cma.read_book(book.ctx,'p','acc')['source_start']==NOW.date().isoformat()


def test_initial_lost_response_retry_is_idempotent_and_changed_payload_rejected(book):
    req=initial_request(book);first=cma.initialize_interest(book.ctx,'p',req,NOW)
    assert cma.initialize_interest(book.ctx,'p',req,NOW+timedelta(days=1))==first
    assert book.balances()[0]==4800100
    with pytest.raises(ValueError):cma.initialize_interest(book.ctx,'p',{**req,'initial_interest_krw':'101'},NOW)


@pytest.mark.parametrize('change',[{'confirmed_initial_interest':False},{'reason':'short'},
    {'initial_interest_krw':'123'},{'book_token':'0'*64}])
def test_initial_requires_exact_separate_amount_confirmation_and_unchanged_book(book,change):
    req=initial_request(book)
    with pytest.raises(ValueError):cma.initialize_interest(book.ctx,'p',{**req,**change},NOW)
    assert book.balances()[0]==4800000 and not cma.read(book.ctx,'p')['openings']


@pytest.mark.parametrize('failure',['INSERT INTO portfolio_cma.openings','UPDATE bookkeeping_requests'])
def test_initial_atomic_rollback(book,failure):
    req=initial_request(book);book.fail_on=failure
    with pytest.raises(Exception):cma.initialize_interest(book.ctx,'p',req,NOW)
    assert book.balances()[0]==4800000
    assert not book.raw.execute('SELECT * FROM portfolio_cma.openings').fetchall()


def test_initial_rejects_negative_or_unverified_difference_and_write_switch(book,monkeypatch):
    req=initial_request(book)
    monkeypatch.setattr(cma_policy,'VALIDATED_STATEMENT_PROFILES',frozenset())
    with pytest.raises(ValueError):cma.initialize_interest(book.ctx,'p',req,NOW)
    monkeypatch.setenv('CMA_INTEREST_WRITES_ENABLED','0')
    with pytest.raises(ValueError,match='차단'):cma.initialize_interest(book.ctx,'p',{},NOW)
    with pytest.raises(ValueError,match='차단'):cma.undo_initial_interest(book.ctx,'p','acc','unknown')
    assert book.balances()[0]==4800000


def test_initial_undo_guard_and_no_second_initialization(book):
    req=initial_request(book);saved=cma.initialize_interest(book.ctx,'p',req,NOW)
    cma.undo_initial_interest(book.ctx,'p','acc',saved['opening_id'])
    assert book.balances()[0]==4800000
    assert cma.undo_initial_interest(book.ctx,'p','acc',saved['opening_id'])['reversed']
    assert Decimal(cma.read(book.ctx,'p')['interest_total_krw'])==0
    new=initial_request(book);new['request_id']='second-initial-try'
    with pytest.raises(ValueError,match='이미'):cma.initialize_interest(book.ctx,'p',new,NOW)


def dated_statement(now=NOW,opening=4800000):
    days=[(now-timedelta(days=1)).date().isoformat(),now.date().isoformat()]
    return dict(profile=PROFILE,portfolio_id='p',account_id='acc',currency='KRW',complete=True,
        interest_posting_final=True,start_date=days[0],as_of=now.isoformat(),opening_cash_krw=str(opening),
        closing_cash_krw=str(opening+200),events=[dict(kind='PAID_INTEREST',event_date=d,
            reference_hash=fingerprint(d),amount_krw='100') for d in days])


def test_catchup_posts_actual_payment_dates_per_day_cap_and_undoes_whole_batch(book,monkeypatch):
    monkeypatch.setattr(activity,'read_page',lambda *a,**k:dict(items=[],pages=1))
    cma.configure(book.ctx,'p','acc',dict(enabled=True,auto_apply=True,max_auto_interest=150,movements_confirmed=True))
    clock=[NOW.replace(hour=9)]
    worker=DailyCMA(book.ctx,clock=lambda:clock[0],provider=lambda *_:{
        **observe_balance(wire(4800200),clock[0]),'statement':dated_statement(clock[0])})
    assert worker.tick()[0]['state']=='AWAITING_STABLE_RETURN'
    clock[0]=NOW
    assert worker.tick()[0]['state']=='APPLIED'
    assert book.balances()[0]==4800200
    rows=book.raw.execute('SELECT id,event_date,amount_krw FROM portfolio_cma.income ORDER BY event_date').fetchall()
    assert [(r[1],r[2]) for r in rows]==[((NOW-timedelta(days=1)).date().isoformat(),100),(NOW.date().isoformat(),100)]
    assert not worker.tick()
    current=cma.read_book(book.ctx,'p','acc')
    evidence={**observe_balance(wire(4800200),NOW),'statement':dated_statement()}
    receipt=cma.reconciliation_for(book.ctx,'p','acc',current,evidence)
    assert receipt['status']=='MATCHED' and Decimal(receipt['paid_interest_krw'])==0
    cma.undo(book.ctx,'p','acc',rows[0][0])
    assert book.balances()[0]==4800000
    assert book.raw.execute('SELECT COUNT(*) FROM portfolio_cma.income WHERE reversed_at IS NULL').fetchone()[0]==0
    assert not cma.policies(book.ctx)[0]['auto_apply']


def test_same_day_and_cross_day_booked_interest_are_subtracted_not_initial_gap(book):
    evidence=observe_balance(wire(4800200),NOW);s=dated_statement()
    booked=[dict(event_date=(NOW-timedelta(days=1)).date().isoformat(),amount_krw='100',reversed_at=None)]
    receipt=reconcile(s,[],pid='p',aid='acc',book_token='x',book_cash=4800100,observation=evidence,booked_income=booked)
    assert receipt['status']=='MATCHED' and Decimal(receipt['paid_interest_krw'])==100
    assert len(receipt['paid_items'])==1 and receipt['paid_items'][0]['event_date']==NOW.date().isoformat()
    for change in ({'amount_krw':'99'},{'reversed_at':'reversed'}):
        assert reconcile(s,[],pid='p',aid='acc',book_token='x',book_cash=4800100,observation=evidence,
            booked_income=[{**booked[0],**change}])['status']=='BOOKED_INTEREST_MISMATCH'


def test_parser_two_day_real_principal_chain_preserves_daily_gross_and_taxes(monkeypatch):
    from test_cma_statement import fixture,raw_row,STAMP
    monkeypatch.setattr(cma_policy,'VALIDATED_STATEMENT_PROFILES',frozenset({cma_statement.PROFILE}))
    monkeypatch.setattr(cma_statement,'PAID_CMA_LABELS',frozenset({'TEST_CMA_PAID'}))
    monkeypatch.setattr(cma_statement,'SWEEP_CMA_LABELS',frozenset({'TEST_CMA_BUY'}))
    snap,obs=fixture();snap['start_date']='2026-10-13';obs['cash_krw']='1040'
    paid=deepcopy(snap['queries'][cma_statement.TOTAL]['rows'][0]);paid['trd_dt']='20261014'
    buy=raw_row();buy.update(trd_dt='20261014',sps_cd_krl_anm='TEST_CMA_BUY',trd_amt=1020,
        trd_af_dca=0,trd_af_bnc_qty=1020,trd_qty=1020)
    returned=deepcopy(paid);returned.update(trd_dt='20261015',trd_amt=1042,int_amt=22,tax_sum=2,trd_af_dca=1040,trd_qty=1020)
    snap['queries'][cma_statement.TOTAL]['rows']=[paid,buy,returned]
    result=cma_statement.normalize(snap,obs,pid='p',aid='a',start_date='2026-10-14')
    assert result['opening_cash_krw']=='1000' and result['closing_cash_krw']=='1040'
    assert [(r['event_date'],r['amount_krw']) for r in result['daily_interest']]==[('2026-10-14','20'),('2026-10-15','20')]
    receipt=reconcile(result,[],pid='p',aid='a',book_token='x',book_cash=1020,observation=obs,
        booked_income=[dict(event_date='2026-10-14',amount_krw='20')])
    assert receipt['status']=='MATCHED' and receipt['paid_interest_krw']=='20'
    assert receipt['gross_interest_krw']=='22' and receipt['withheld_tax_krw']=='2'
