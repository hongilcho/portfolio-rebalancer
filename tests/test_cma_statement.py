from copy import deepcopy
import pytest
from logic import cma_statement as s,cma_policy
from logic.cma_reconciliation import reconcile

STAMP='2026-10-15T12:00:00+09:00'


@pytest.fixture
def verified(monkeypatch):
    # Local test registry only; does not claim these are observed NH labels.
    monkeypatch.setattr(cma_policy,'VALIDATED_STATEMENT_PROFILES',frozenset((s.PROFILE,)))
    monkeypatch.setattr(s,'PAID_CMA_LABELS',frozenset(('TEST_CMA_PAID',)))
    monkeypatch.setattr(s,'MOVEMENT_LABELS',{'TEST_WITHDRAW':'WITHDRAW','TEST_DEPOSIT':'DEPOSIT'})


def raw_row(**values):
    return dict(trd_dt='20261015',cur_cd='KRW',int_amt=0,tax_sum=0,trd_orn_fee=0,rvb_odu_fee=0,
        trd_amt=1023,trd_af_dca=1020,trd_qty=1000,trd_af_bnc_qty=0,
        iem_cd='NHKRCMA030',sps_cd_krl_anm='TEST_CMA_PAID',**values)


def fixture():
    row=raw_row();row.update(int_amt=23,tax_sum=3)
    def query(rows):return dict(complete=True,rows=rows,pages=[dict(data={'rsp_cd':'00166','rsp_msg':'조회가 완료되었습니다.'})])
    snap=dict(complete=True,observed_at=STAMP,start_date='2026-10-14',end_date='2026-10-15',
        queries={s.TOTAL:query([row]),s.MOVES:query([]),s.BALANCE:query([])})
    obs=dict(observed_at=STAMP,state='CASH_RETURNED',cash_krw='1020')
    return snap,obs


def test_profile_can_be_disabled_and_unknown_profile_never_guessed(monkeypatch):
    monkeypatch.setattr(cma_policy,'VALIDATED_STATEMENT_PROFILES',frozenset())
    snap,obs=fixture()
    assert s.normalize(snap,obs,pid='p',aid='a')['status']=='PROFILE_UNVERIFIED'


def test_posted_gross_tax_and_fees_become_exact_net_interest(verified):
    snap,obs=fixture();statement=s.normalize(snap,obs,pid='p',aid='a')
    assert statement['events'][0]['amount_krw']=='20'
    assert statement['gross_interest_krw']=='23' and statement['withheld_tax_krw']=='3'
    receipt=reconcile(statement,[],pid='p',aid='a',book_token='token',book_cash=1000,observation=obs)
    assert receipt['status']=='MATCHED' and receipt['paid_interest_krw']=='20'
    receipt=reconcile(statement,[],pid='p',aid='a',book_token='token',book_cash=900,observation=obs)
    assert receipt['status']=='INITIAL_BALANCE_REVIEW'
    assert receipt['paid_interest_krw']=='20' and receipt['prior_difference_krw']=='100'


def test_already_booked_transfer_is_matched_without_replaying_it(verified):
    snap,obs=fixture()
    snap['queries'][s.TOTAL]['rows'][0].update(trd_amt=4001023,trd_af_dca=4001020)
    move=raw_row();move.update(iem_cd='',sps_cd_krl_anm='TEST_WITHDRAW',trd_amt=4000000,trd_af_dca=1020)
    snap['queries'][s.TOTAL]['rows'].append(move)
    snap['queries'][s.MOVES]['rows'].append(deepcopy(move))
    statement=s.normalize(snap,obs,pid='p',aid='a')
    book=[dict(id='already-booked',event_date='2026-10-15',kind='WITHDRAW',amount_krw='4000000')]
    receipt=reconcile(statement,book,pid='p',aid='a',book_token='token',book_cash=1000,observation=obs)
    assert receipt['status']=='MATCHED' and receipt['paid_interest_krw']=='20'
    assert reconcile(statement,[],pid='p',aid='a',book_token='token',book_cash=1000,observation=obs)['status']=='MOVEMENT_MISMATCH'


@pytest.mark.parametrize('changes',[
    {'sps_cd_krl_anm':'UNKNOWN_PURCHASE'}, {'trd_af_bnc_qty':100}, {'trd_qty':0},
    {'tax_sum':24}, {'rvb_odu_fee':1}, {'cur_cd':'USD'}, {'trd_amt':0}, {'int_amt':-1}
])
def test_ambiguous_interest_is_never_promoted(verified,changes):
    snap,obs=fixture();snap['queries'][s.TOTAL]['rows'][0].update(changes)
    assert 'events' not in s.normalize(snap,obs,pid='p',aid='a')


def test_sweep_purchase_and_empty_history_cannot_finish_daily_interest_early(verified):
    snap,obs=fixture();snap['queries'][s.TOTAL]['rows'][0].update(int_amt=0,tax_sum=0,sps_cd_krl_anm='TEST_CMA_BUY',trd_af_bnc_qty=1000)
    assert s.normalize(snap,obs,pid='p',aid='a')['status']=='INTEREST_POSTING_UNVERIFIED'
    snap['queries'][s.TOTAL]['rows']=[]
    assert s.normalize(snap,obs,pid='p',aid='a')['status']=='INTEREST_POSTING_UNVERIFIED'


def test_full_bank_histories_must_agree_on_movement_and_after_cash(verified):
    snap,obs=fixture();move=raw_row();move.update(iem_cd='',sps_cd_krl_anm='TEST_DEPOSIT',trd_amt=100,trd_af_dca=1020)
    snap['queries'][s.MOVES]['rows']=[move]
    assert s.normalize(snap,obs,pid='p',aid='a')['status']=='BANK_HISTORY_MISMATCH'


def test_nested_message_supported_but_mixed_error_does_not_certify_success(verified):
    snap,obs=fixture()
    snap['queries'][s.TOTAL]['pages'][0]['data']={'message':{'code':'00166','msg':'조회가 완료되었습니다.'}}
    assert 'events' in s.normalize(snap,obs,pid='p',aid='a')
    snap['queries'][s.TOTAL]['pages'][0]['data']['rsp_msg']='error'
    assert s.normalize(snap,obs,pid='p',aid='a')['status']=='BUSINESS_STATUS_UNVERIFIED'


def test_blank_domestic_currency_is_validated_by_exact_krw_cash_chain(verified):
    snap,obs=fixture();snap['queries'][s.TOTAL]['rows'][0]['cur_cd']=''
    assert 'events' in s.normalize(snap,obs,pid='p',aid='a')
    snap['queries'][s.TOTAL]['rows'][0]['trd_af_dca']=1019
    assert s.normalize(snap,obs,pid='p',aid='a')['status']=='BANK_CASH_CHAIN_MISMATCH'


def test_principal_purchase_return_is_checked_using_money_not_quantity(verified,monkeypatch):
    monkeypatch.setattr(s,'SWEEP_CMA_LABELS',frozenset(('TEST_CMA_BUY',)))
    snap,obs=fixture();purchase=raw_row();purchase.update(trd_dt='20261014',int_amt=0,tax_sum=0,
        trd_amt=1000,trd_af_dca=0,trd_af_bnc_qty=999999,trd_qty=999999,sps_cd_krl_anm='TEST_CMA_BUY')
    snap['queries'][s.TOTAL]['rows'].insert(0,purchase)
    assert s.normalize(snap,obs,pid='p',aid='a')['opening_cash_krw']=='1000'
    purchase['trd_amt']=999
    assert s.normalize(snap,obs,pid='p',aid='a')['status']=='PRINCIPAL_MISMATCH'


def test_tax_breakdown_must_match_paid_net_before_receipt_is_accepted(verified):
    snap,obs=fixture();statement=s.normalize(snap,obs,pid='p',aid='a')
    statement['withheld_tax_krw']='4'
    assert reconcile(statement,[],pid='p',aid='a',book_token='token',book_cash=1000,observation=obs)['status']=='INTEREST_POSTING_UNVERIFIED'
