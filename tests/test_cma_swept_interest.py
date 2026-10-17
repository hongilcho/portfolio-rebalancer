from datetime import datetime,timedelta
import pytest
from logic import cma_statement as s,cma_policy
from logic.cma_interest import observe_balance,interest_preview,stable_return,KST
from logic.cma_reconciliation import reconcile
from test_cma_interest import wire
from test_cma_statement import raw_row
from test_cma_repository import book
from data.repositories import cma

NOW=datetime(2026,10,17,9,15,tzinfo=KST)


def fixture():
    paid=raw_row();paid.update(trd_dt='20261016',sps_cd_krl_anm='발행어음일괄매도',int_amt=23,tax_sum=3)
    buy=raw_row();buy.update(trd_dt='20261016',sps_cd_krl_anm='발행어음일괄매수',trd_amt=1020,
        trd_af_dca=0,trd_af_bnc_qty=1020,trd_qty=1020)
    balance=wire(0,[dict(iem_cd='NHKRCMA030',eal_amt=1043,eal_pls_amt=23,rsdl_qty=1020)],
        nas_amt=1043,tot_aet_amt=1043,tot_byn_amt=1020,drn_pbl_amt=1040)
    balance['rsp_cd']='00166'
    def query(rows,body=None):return dict(complete=True,rows=rows,pages=[dict(data=body or dict(rsp_cd='00166',rsp_msg='조회가 완료되었습니다.'))])
    snap=dict(complete=True,observed_at=NOW.isoformat(),start_date='2026-10-14',end_date='2026-10-17',
        queries={s.TOTAL:query([paid,buy]),s.MOVES:query([]),s.BALANCE:query([],balance)})
    return snap,observe_balance(balance,NOW)


@pytest.fixture
def trust(monkeypatch):monkeypatch.setattr(cma_policy,'VALIDATED_STATEMENT_PROFILES',frozenset({s.PROFILE}))


def verified(snap,obs):
    statement=s.normalize(snap,obs,pid='p',aid='acc',start_date='2026-10-15')
    obs={**obs,'state':'CMA_PRINCIPAL_VERIFIED','posted_krw':statement['posted_balance_krw'],
        'unposted_valuation_krw':statement['unposted_valuation_krw']}
    return statement,obs


def test_weekend_swept_principal_excludes_unpaid_valuation_and_withdrawal_estimate(trust):
    snap,obs=fixture();assert obs['state']=='AWAITING_CASH_RETURN'
    statement,obs=verified(snap,obs)
    assert statement['posted_balance_krw']=='1020' and statement['unposted_valuation_krw']=='23'
    assert statement['daily_interest'][0]['event_date']=='2026-10-16'
    receipt=reconcile(statement,[],pid='p',aid='acc',book_token='x',book_cash=1000,observation=obs)
    assert receipt['status']=='MATCHED' and receipt['paid_interest_krw']=='20'
    obs['reconciliation']=receipt
    assert interest_preview(dict(account_type='CMA',deposit_krw=1000),obs,NOW)['interest_krw']=='20'
    prior={**obs,'observed_at':(NOW-timedelta(minutes=2)).isoformat(),'book_token':'x'}
    assert stable_return(prior,{**obs,'book_token':'x'})


@pytest.mark.parametrize('change',[dict(eal_pls_amt=22),dict(rsdl_qty=1019),dict(eal_amt=1010),dict(lon_bnc_amt=1),dict(iem_cd='OTHER')])
def test_swept_history_must_match_actual_holdings_quantity_cost_and_evaluation(trust,change):
    snap,obs=fixture();snap['queries'][s.BALANCE]['pages'][0]['data']['Output_1'][0].update(change)
    assert s.normalize(snap,obs,pid='p',aid='acc',start_date='2026-10-15')['status']=='PRINCIPAL_MISMATCH'


def test_swept_initial_opening_keeps_pending_paid_day_across_fresh_read(book,monkeypatch):
    monkeypatch.setattr(cma_policy,'VALIDATED_STATEMENT_PROFILES',frozenset({s.PROFILE}))
    book.raw.execute('UPDATE accounts SET deposit_krw=900');book.commit()
    snap,evidence=fixture();statement,evidence=verified(snap,evidence)
    current=cma.read_book(book.ctx,'p','acc')
    proof=reconcile(statement,[],pid='p',aid='acc',book_token=current['book_token'],book_cash=900,observation=evidence)
    obs=cma.record_observation(book.ctx,'p','acc',evidence,current['book_token'],reconciliation=proof)
    cma.initialize_interest(book.ctx,'p',dict(request_id='swept-initial',account_id='acc',observation_id=obs['id'],
        book_token=current['book_token'],initial_interest_krw='100',confirmed_initial_interest=True,
        reason='Verified accumulated paid income before the statement window.'),NOW)
    assert book.balances()[0]==1000
    current=cma.read_book(book.ctx,'p','acc');assert current['source_start']=='2026-10-15'
    proof=reconcile(statement,[],pid='p',aid='acc',book_token=current['book_token'],book_cash=1000,observation=evidence)
    obs=cma.record_observation(book.ctx,'p','acc',evidence,current['book_token'],reconciliation=proof)
    cma.commit(book.ctx,'p',dict(request_id='swept-daily',account_id='acc',observation_id=obs['id'],
        book_token=current['book_token'],interest_krw='20',confirmed_movements=True),NOW)
    assert book.balances()[0]==1020
    assert book.raw.execute('SELECT event_date,amount_krw FROM portfolio_cma.income').fetchone()[0]=='2026-10-16'
