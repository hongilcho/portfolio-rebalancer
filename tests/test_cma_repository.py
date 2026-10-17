import json
from copy import deepcopy
from datetime import date,datetime,timedelta
from decimal import Decimal
from types import SimpleNamespace
import pytest
from test_nh_notices import NoticeDatabase,NoticeCursor
from data.repositories import cma
from logic.cma_interest import KST,observe_balance
from logic.period_performance import report_daily
from test_cma_interest import wire,NOW
from logic import cma_policy
from logic.cma_reconciliation import reconcile
from test_cma_reconciliation import PROFILE,statement


class CmaCursor(NoticeCursor):
    @property
    def rowcount(self):return self.cursor.rowcount
    @staticmethod
    def decode(row):
        row=NoticeCursor.decode(row)
        if row and isinstance(row.get('evidence'),str):row['evidence']=json.loads(row['evidence'])
        return row


class CmaDB(NoticeDatabase):
    def cursor(self,**kwargs):return CmaCursor(self)


@pytest.fixture
def book(monkeypatch):
    monkeypatch.setenv('CMA_INTEREST_WRITES_ENABLED','1')
    monkeypatch.setattr(cma_policy,'VALIDATED_STATEMENT_PROFILES',frozenset({PROFILE}))
    db=CmaDB()
    db.raw.executescript('''
      ALTER TABLE accounts ADD COLUMN account_type TEXT DEFAULT 'CMA';
      ALTER TABLE accounts ADD COLUMN account_alias TEXT DEFAULT 'QA CMA';
      ALTER TABLE nh_notice_items ADD COLUMN account_id TEXT;
      ALTER TABLE nh_notice_items ADD COLUMN sequence INT DEFAULT 0;
      UPDATE accounts SET deposit_krw=4800000,deposit_usd=0;
      INSERT INTO performance_tracking(portfolio_id,baseline_date) VALUES('p','2026-10-13');
      CREATE TABLE performance_flows(id TEXT PRIMARY KEY,amount_krw REAL);
      INSERT INTO performance_flows VALUES('already-recorded-withdrawal',-200000);
      ATTACH DATABASE ':memory:' AS portfolio_cma;
      CREATE TABLE portfolio_cma.observations(id TEXT PRIMARY KEY,portfolio_id TEXT,account_id TEXT,observed_at TEXT,book_token TEXT,evidence TEXT);
      CREATE TABLE portfolio_cma.income(id TEXT UNIQUE,sequence INTEGER PRIMARY KEY AUTOINCREMENT,portfolio_id TEXT,account_id TEXT,request_id TEXT,observation_id TEXT,event_date TEXT,amount_krw REAL,before_cash REAL,after_cash REAL,after_token TEXT,details TEXT DEFAULT '{}',created_at TEXT DEFAULT CURRENT_TIMESTAMP,reversed_at TEXT,UNIQUE(account_id,event_date),UNIQUE(portfolio_id,request_id,event_date),UNIQUE(observation_id,event_date));
      CREATE TABLE portfolio_cma.openings(id TEXT PRIMARY KEY,portfolio_id TEXT,account_id TEXT UNIQUE,request_id TEXT,observation_id TEXT,recognized_on TEXT,amount_krw REAL,before_cash REAL,after_cash REAL,after_token TEXT,reason TEXT,details TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,reversed_at TEXT,UNIQUE(portfolio_id,request_id));
      CREATE TABLE portfolio_cma.settings(account_id TEXT PRIMARY KEY,portfolio_id TEXT,enabled BOOLEAN DEFAULT 0,auto_apply BOOLEAN DEFAULT 0,max_auto_interest REAL DEFAULT 0,movements_confirmed BOOLEAN DEFAULT 0);
      CREATE TABLE portfolio_cma.checks(account_id TEXT,event_date TEXT,slot INT,state TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(account_id,event_date,slot));
    ''')
    db.commit();ids=iter(f'cma-{i}' for i in range(100))
    db.ctx=SimpleNamespace(connect=lambda:db,new_id=lambda:next(ids),invalidate=lambda:None)
    yield db
    db.raw.close()


def proposal(book,now=NOW,cash=4800123,verified=True):
    snapshot=cma.read_book(book.ctx,'p','acc')
    evidence=observe_balance(wire(cash),now)
    proof=reconcile(statement(now,snapshot['account']['deposit_krw'],cash,
        events=[] if Decimal(str(cash))==Decimal(str(snapshot['account']['deposit_krw'])) else None),[],
        pid='p',aid='acc',book_token=snapshot['book_token'],book_cash=snapshot['account']['deposit_krw'],observation=evidence) if verified else None
    obs=cma.record_observation(book.ctx,'p','acc',evidence,snapshot['book_token'],reconciliation=proof)
    preview=cma.preview(book.ctx,'p','acc',obs['id'],now)
    request=dict(request_id='cma-request-001',account_id='acc',confirmed_movements=True,**{k:preview[k] for k in ('observation_id','book_token','interest_krw')})
    return request


def test_interest_cash_and_receipt_atomic_and_not_an_external_flow(book):
    req=proposal(book);before=deepcopy(book.state())
    result=cma.commit(book.ctx,'p',req,NOW)
    assert book.balances()[0]==4800123 and Decimal(result['interest_krw'])==123
    assert book.raw.execute('SELECT amount_krw FROM performance_flows').fetchall()[0][0]==-200000
    assert len(book.rows('holdings'))==len(before['holdings'])
    assert book.rows('trade_history')==before['trade_history']
    rows=report_daily({'baseline_date':date(2026,10,13),'baseline_value':5000000},
        [{'snapshot_date':date(2026,10,14),'value_krw':book.balances()[0]}],
        [{'event_date':date(2026,10,14),'amount_krw':-200000,'voided':False}])
    assert rows[0]['profit']==123 and rows[0]['return_pct']>0


def test_initial_accrued_gap_cannot_be_posted_as_daily_interest_even_with_manual_confirmation(book):
    current=cma.read_book(book.ctx,'p','acc')
    obs=cma.record_observation(book.ctx,'p','acc',observe_balance(wire(),NOW),current['book_token'],
        reconciliation={'status':'INITIAL_BALANCE_REVIEW','paid_interest_krw':'23','prior_difference_krw':'100'})
    preview=cma.preview(book.ctx,'p','acc',obs['id'],NOW)
    assert preview['can_apply'] is False and preview['paid_interest_krw']=='23'
    req=dict(request_id='initial-gap-review-only',account_id='acc',confirmed_movements=True,
        observation_id=obs['id'],book_token=current['book_token'],interest_krw='123')
    with pytest.raises(ValueError,match='초기 누적'):
        cma.commit(book.ctx,'p',req,NOW)
    assert book.balances()[0]==4800000
    assert book.raw.execute('SELECT COUNT(*) FROM portfolio_cma.income').fetchone()[0]==0


def test_lost_response_retry_next_day_returns_original_without_new_money(book):
    req=proposal(book);first=cma.commit(book.ctx,'p',req,NOW)
    assert cma.commit(book.ctx,'p',req,NOW+timedelta(days=1))==first
    assert book.balances()[0]==4800123
    assert book.raw.execute('SELECT COUNT(*) FROM portfolio_cma.income').fetchone()[0]==1
    with pytest.raises(ValueError,match='변경'):
        cma.commit(book.ctx,'p',{**req,'interest_krw':'124'},NOW)


@pytest.mark.parametrize('failure',['INSERT INTO portfolio_cma.income','UPDATE bookkeeping_requests'])
def test_failed_journal_or_receipt_rolls_back_every_cash_change(book,failure):
    req=proposal(book);book.fail_on=failure
    with pytest.raises(Exception):cma.commit(book.ctx,'p',req,NOW)
    assert book.balances()[0]==4800000
    assert book.raw.execute('SELECT COUNT(*) FROM portfolio_cma.income').fetchone()[0]==0
    assert book.raw.execute('SELECT COUNT(*) FROM bookkeeping_requests').fetchone()[0]==0


def test_cash_change_even_a_recorded_withdrawal_requires_a_new_snapshot(book):
    req=proposal(book)
    book.raw.execute('UPDATE accounts SET deposit_krw=deposit_krw-200000');book.commit()
    with pytest.raises(ValueError,match='장부'):
        cma.commit(book.ctx,'p',req,NOW)
    assert book.balances()[0]==4600000


@pytest.mark.parametrize('change',[dict(confirmed_movements=False),dict(interest_krw='999'),dict(observation_id='missing')])
def test_unconfirmed_or_tampered_request_cannot_change_cash(book,change):
    req=proposal(book)
    with pytest.raises(ValueError):cma.commit(book.ctx,'p',{**req,**change},NOW)
    assert book.balances()[0]==4800000


def test_cross_portfolio_and_non_cma_accounts_rejected(book):
    with pytest.raises(ValueError):cma.read_book(book.ctx,'other','acc')
    book.raw.execute("UPDATE accounts SET account_type='일반'");book.commit()
    with pytest.raises(ValueError,match='CMA'):cma.read_book(book.ctx,'p','acc')


def test_same_day_new_request_cannot_add_the_interest_twice(book):
    cma.commit(book.ctx,'p',proposal(book),NOW)
    req=proposal(book,cash=4800246);req['request_id']='new-request'
    with pytest.raises(ValueError,match='이미'):cma.commit(book.ctx,'p',req,NOW)
    assert book.balances()[0]==4800123


def test_undo_is_guarded_idempotent_and_preserves_external_withdrawal(book):
    result=cma.commit(book.ctx,'p',proposal(book),NOW)
    cma.undo(book.ctx,'p','acc',result['income_id'])
    assert book.balances()[0]==4800000
    assert cma.undo(book.ctx,'p','acc',result['income_id'])['reversed']
    assert book.raw.execute('SELECT amount_krw FROM performance_flows').fetchone()[0]==-200000


def test_undo_rejects_later_cash_changes(book):
    result=cma.commit(book.ctx,'p',proposal(book),NOW)
    book.raw.execute('UPDATE accounts SET deposit_krw=deposit_krw-100');book.commit()
    with pytest.raises(ValueError,match='이후'):cma.undo(book.ctx,'p','acc',result['income_id'])


def test_auto_apply_requires_current_opt_in_cap_and_stable_second_observation(book):
    settings=dict(enabled=True,auto_apply=True,max_auto_interest='200',movements_confirmed=True)
    cma.configure(book.ctx,'p','acc',settings)
    req=proposal(book,now=NOW.replace(hour=9));req=proposal(book,verified=True)
    req['automatic']=True
    assert Decimal(cma.commit(book.ctx,'p',req,NOW)['interest_krw'])==123


def test_auto_opt_out_after_observation_blocks_commit(book):
    cma.configure(book.ctx,'p','acc',dict(enabled=False,auto_apply=False,max_auto_interest=0,movements_confirmed=False))
    req=proposal(book);req['automatic']=True
    with pytest.raises(ValueError,match='설정'):cma.commit(book.ctx,'p',req,NOW)
    assert book.balances()[0]==4800000


def test_slot_claim_is_durable_and_query_budget_not_reset_on_restart(book):
    assert cma.claim_check(book.ctx,'acc',NOW.date(),0)
    assert not cma.claim_check(book.ctx,'acc',NOW.date(),0)
    assert cma.check_slots(book.ctx,'acc',NOW.date())[0]['state']=='CHECKING'


def test_no_change_does_not_create_income_or_move_money(book):
    result=cma.commit(book.ctx,'p',proposal(book,cash=4800000),NOW)
    assert not result['saved'] and book.balances()[0]==4800000
    assert book.raw.execute('SELECT COUNT(*) FROM portfolio_cma.income').fetchone()[0]==0


def test_income_summary_is_scoped_and_reversed_income_not_counted(book):
    result=cma.commit(book.ctx,'p',proposal(book),NOW)
    assert Decimal(cma.read(book.ctx,'p')['interest_total_krw'])==123
    assert Decimal(cma.read(book.ctx,'different')['interest_total_krw'])==0
    cma.undo(book.ctx,'p','acc',result['income_id'])
    assert Decimal(cma.read(book.ctx,'p')['interest_total_krw'])==0


def test_reversed_interest_disables_automatic_reapplication(book):
    cma.configure(book.ctx,'p','acc',dict(enabled=True,auto_apply=True,max_auto_interest=200,movements_confirmed=True))
    result=cma.commit(book.ctx,'p',proposal(book),NOW)
    cma.undo(book.ctx,'p','acc',result['income_id'])
    policy=cma.policies(book.ctx)[0]
    assert policy['enabled'] and not policy['auto_apply']


def test_only_normalized_balance_components_are_saved_for_zero_cash_review(book):
    current=cma.read_book(book.ctx,'p','acc')
    evidence={**observe_balance(wire(0,drn_pbl_amt='4800123'),NOW),
              'raw_response':{'private':'must not persist'},'account_no':'private-number'}
    saved=cma.record_observation(book.ctx,'p','acc',evidence,current['book_token'])
    raw=book.raw.execute('SELECT evidence FROM portfolio_cma.observations WHERE id=?',(saved['id'],)).fetchone()[0]
    normalized=json.loads(raw)
    assert normalized['cash_krw']=='0' and normalized['withdrawable_krw']=='4800123'
    assert 'raw_response' not in normalized and 'account_no' not in normalized
    with pytest.raises(ValueError,match='반환'):cma.preview(book.ctx,'p','acc',saved['id'],NOW)
    assert book.balances()[0]==4800000


def test_after_20_verified_cash_can_be_reviewed_without_repeating_withdrawal(book):
    now=NOW.replace(hour=21)
    result=cma.commit(book.ctx,'p',proposal(book,now=now),now)
    assert Decimal(result['interest_krw'])==123 and book.balances()[0]==4800123
    assert book.raw.execute('SELECT amount_krw FROM performance_flows').fetchone()[0]==-200000


def test_unrecorded_cross_portfolio_transfer_must_be_booked_before_interest(book):
    # Synthetic replay of the read-only finding; no real ledger is connected.
    now=NOW+timedelta(days=1)
    book.raw.execute('UPDATE accounts SET deposit_krw=38036748');book.commit()
    with pytest.raises(ValueError,match='작습니다'):
        proposal(book,now=now,cash=34074558)
    assert book.balances()[0]==38036748
    assert book.raw.execute('SELECT COUNT(*) FROM portfolio_cma.income').fetchone()[0]==0
    # The separate, synthetic transfer is recorded before the income proposal.
    book.raw.execute('UPDATE accounts SET deposit_krw=deposit_krw-4000000')
    book.raw.execute("INSERT INTO performance_flows VALUES('synthetic-portfolio-transfer',-4000000)")
    book.commit()
    result=cma.commit(book.ctx,'p',proposal(book,now=now,cash=34074558),now)
    assert Decimal(result['interest_krw'])==37810 and book.balances()[0]==34074558
    daily=report_daily({'baseline_date':NOW.date(),'baseline_value':38036748},
        [{'snapshot_date':now.date(),'value_krw':34074558}],
        [{'event_date':now.date(),'amount_krw':-4000000,'voided':False}])
    assert daily[0]['profit']==37810
