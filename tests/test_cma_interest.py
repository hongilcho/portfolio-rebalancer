from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from logic.cma_interest import KST, observe_balance, interest_preview, stable_return, due_slot, amount

NOW=datetime(2026,10,14,12,tzinfo=KST)


def wire(cash=4800123,rows=None,**head):
    return dict(rsp_cd='00000',rsp_msg='조회가 완료되었습니다.',
                Output_0=dict(dca=cash,nxt2_dd_dca=cash,**head),Output_1=rows or [])


def test_recorded_200000_withdrawal_is_not_subtracted_again():
    obs=observe_balance(wire(),NOW)
    account=dict(account_type='CMA',deposit_krw=5000000-200000)
    assert interest_preview(account,obs,NOW)['interest_krw']=='123'
    assert account['deposit_krw']==4800000


@pytest.mark.parametrize('hour,cash,rows,state',[
    (20,0,[],'ZERO_UNVERIFIED'),(23,0,[],'ZERO_UNVERIFIED'),
    (9,0,[],'ZERO_UNVERIFIED'),
    (9,0,[dict(iem_cd='NHKRCMA030',eal_amt=4800123)],'AWAITING_CASH_RETURN'),
    (9,123,[dict(iem_cd='NHKRCMA030',eal_amt=4800000)],'AWAITING_CASH_RETURN'),
])
def test_zero_and_sweep_do_not_become_withdrawal_or_interest(hour,cash,rows,state):
    obs=observe_balance(wire(cash,rows),NOW.replace(hour=hour))
    assert obs['state']==state
    with pytest.raises(ValueError,match='반환'):
        interest_preview(dict(account_type='CMA',deposit_krw=4800000),obs,NOW.replace(hour=hour))


@pytest.mark.parametrize('patch',[
    dict(rsp_cd='ERROR'),dict(rsp_msg='other'),dict(Output_0={}),dict(Output_1=None),
    dict(Output_0={'dca':True}),dict(Output_0={'dca':'NaN'}),dict(Output_0={'dca':-1}),
    dict(Output_1=[dict(iem_cd='NHKRCMA030',rsdl_qty=4800000)]),
    dict(Output_1=[dict(iem_cd='AAPL',rsdl_qty=1)]),
    dict(Output_1=[dict(iem_cd='RP-unknown',eal_amt=100)]),
])
def test_unverified_business_missing_fields_or_quantity_fallback_block_income(patch):
    obs=observe_balance({**wire(),**patch},NOW)
    assert obs['state']!='CASH_RETURNED'


def test_withdrawable_cash_is_never_assumed_to_be_interest_bearing_nav():
    obs=observe_balance(wire(4800000,drn_pbl_amt=9999999),NOW)
    assert obs['cash_krw']=='4800000'
    data=wire();data['Output_0']['nxt2_dd_dca']=4800000
    assert observe_balance(data,NOW)['state']=='SETTLEMENT_UNVERIFIED'


@pytest.mark.parametrize('minutes',[-1,11,1440])
def test_stale_future_or_other_day_observation_cannot_change_cash(minutes):
    with pytest.raises(ValueError,match='최근'):
        interest_preview(dict(account_type='CMA',deposit_krw=4800000),observe_balance(wire(),NOW),NOW+timedelta(minutes=minutes))


def test_negative_gap_is_never_negative_interest():
    with pytest.raises(ValueError,match='작습니다'):
        interest_preview(dict(account_type='CMA',deposit_krw=5000000),observe_balance(wire(),NOW),NOW)


def test_two_matching_cash_returns_do_not_require_a_guessed_return_hour():
    first={**observe_balance(wire(),NOW.replace(hour=9)),'book_token':'same'}
    second={**observe_balance(wire(),NOW),'book_token':'same'}
    assert stable_return(first,second)
    assert not stable_return(first,{**second,'book_token':'changed'})
    assert not stable_return(first,{**second,'cash_krw':'4800124'})
    assert not stable_return(first,{**second,'observed_at':(NOW+timedelta(days=1)).isoformat()})


def test_schedule_is_korean_time_bounded_and_does_not_replay_missed_slots():
    assert due_slot(NOW.replace(hour=8),set()) is None
    assert due_slot(NOW.replace(hour=9),set())==0
    assert due_slot(NOW,set())==1
    assert due_slot(NOW,{1}) is None
    assert due_slot(NOW.replace(hour=15,minute=40),{0,1})==2
    assert due_slot(NOW.replace(hour=16),set()) is None
    assert due_slot(NOW.astimezone(__import__('datetime').timezone.utc),set())==1


@pytest.mark.parametrize('value',[None,True,'NaN','Infinity',float('inf'),'1e16'])
def test_decimal_money_rejects_invalid_values(value):
    with pytest.raises(ValueError):amount(value)


def test_krw_interest_keeps_decimal_precision_without_guessing_rates():
    obs=observe_balance(wire('4800000.23'),NOW)
    assert interest_preview(dict(account_type='CMA',deposit_krw='4800000.10'),obs,NOW)['interest_krw']=='0.13'


@pytest.mark.parametrize('hour',[0,18,19,20,23])
def test_verified_cash_is_not_rejected_by_an_assumed_evening_hour(hour):
    now=NOW.replace(hour=hour)
    obs=observe_balance(wire(),now)
    assert obs['state']=='CASH_RETURNED'
    assert interest_preview(dict(account_type='CMA',deposit_krw=4800000),obs,now)['interest_krw']=='123'


@pytest.mark.parametrize('hour',[9,18,19,20,23])
def test_zero_cash_with_full_withdrawable_amount_cannot_be_posted_as_interest(hour):
    now=NOW.replace(hour=hour)
    obs=observe_balance(wire(0,drn_pbl_amt='4800123'),now)
    assert obs['withdrawable_krw']=='4800123' and obs['cash_krw']=='0'
    assert obs['state']=='ZERO_UNVERIFIED'
    with pytest.raises(ValueError,match='반환'):
        interest_preview(dict(account_type='CMA',deposit_krw=4800000),obs,now)


def test_withdrawable_amount_is_not_added_to_cash_and_sweep_again():
    rows=[dict(iem_cd='NHKRCMA030',eal_amt='4800000')]
    obs=observe_balance(wire('123',rows,drn_pbl_amt='4800123'),NOW.replace(hour=18))
    assert obs['withdrawable_krw']=='4800123' and obs['total_krw']=='4800123'
    assert obs['state']=='AWAITING_CASH_RETURN'


def test_reference_withdrawable_survives_missing_cash_without_becoming_income():
    data=wire(drn_pbl_amt='4800123');del data['Output_0']['dca']
    obs=observe_balance(data,NOW)
    assert obs['state']=='UNVERIFIED' and obs['cash_krw'] is None
    assert obs['withdrawable_krw']=='4800123'


def test_settlement_mismatch_keeps_cash_sweep_and_withdrawable_distinct_for_review():
    data=wire(0,[dict(iem_cd='NHKRCMA030',eal_amt='4800123')],drn_pbl_amt='4800123')
    data['Output_0']['nxt2_dd_dca']='4800123'
    obs=observe_balance(data,NOW)
    assert obs['state']=='SETTLEMENT_UNVERIFIED'
    assert obs['cash_krw']=='0' and obs['sweep_krw']=='4800123'
    assert obs['withdrawable_krw']==obs['total_krw']=='4800123'


@pytest.mark.parametrize('value',[True,'NaN','Infinity','-1','invalid'])
def test_invalid_present_withdrawable_field_is_not_trusted(value):
    obs=observe_balance(wire(drn_pbl_amt=value),NOW)
    assert obs['withdrawable_krw'] is None and obs['state']=='UNVERIFIED'
