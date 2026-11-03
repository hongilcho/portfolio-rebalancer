"""Pure receipt reconciliation; no database, credentials or provider calls."""
from copy import deepcopy
import pytest
from logic.dividend_calculator import calculate_holding_dividends


def position(**changes):
    return dict(account_id='a',asset_id='s',quantity=100,avg_price=10000,original_avg_price=10000,
                first_buy_date='2026-09-01',account_type='ISA',**changes)


def receipt(**changes):
    r=dict(kind='DIVIDEND',event_date='2026-11-03',reference_date='2026-10-30',dividend_ex_date='2026-10-29',krw_amount=4025,gross_amount=4025,tax_amount=0,receipt_id='r')
    return {**r,**changes}


def calculate(h,records=None,trades=None):
    return calculate_holding_dividends(h,dict(market='KR',ticker='QA',name='ETF'),
        trades=trades if trades is not None else [dict(trade_date='2026-09-01',trade_type='INIT',quantity=100)],
        dividend_records=records if records is not None else [dict(date='2026-10-29',amount=40.2)])


def test_receipt_replaces_estimate_instead_of_adding_and_preserves_original_inputs():
    h=position(dividend_receipts=[receipt()]);before=deepcopy(h)
    result=calculate(h)
    assert result['total_dividend_profit']==4025
    assert result['total_gross_dividend_profit']==4025
    assert result['dividend_details'][0]['source']=='NH_RECEIPT'
    assert result['avg_price']==10000 and h==before


def test_past_and_unlinked_receipts_do_not_change_historical_estimates():
    assert calculate(position(dividend_receipts=[receipt()],dividend_as_of='2026-11-02'))['total_dividend_profit']==4020
    assert calculate(position(dividend_receipts=[receipt(dividend_ex_date=None)]))['total_dividend_profit']==4020
    h=position(dividend_receipts=[receipt()]);h['first_buy_date']='2026-11-04'
    assert calculate(h)['total_dividend_profit']==0


def test_manual_override_remains_authoritative():
    assert calculate(position(dividend_receipts=[receipt()],manual_dividend_override=99))['total_dividend_profit']==99


def test_reinvestment_does_not_receive_past_dividends_twice():
    h=position(dividend_receipts=[receipt()]);h['quantity']=101
    trades=[dict(trade_date='2026-09-01',trade_type='INIT',quantity=100),dict(trade_date='2026-11-04',trade_type='BUY',quantity=1)]
    assert calculate(h,trades=trades)['total_dividend_profit']==4025


def test_confirmed_receipt_survives_later_missing_provider_event():
    result=calculate(position(dividend_receipts=[receipt()]),records=[])
    assert result['total_dividend_profit']==4025
    assert result['dividend_details'][0]['holding_quantity'] is None


def test_unknown_tax_is_not_guessed_from_message():
    result=calculate(position(dividend_receipts=[receipt(gross_amount=None,tax_amount=None)]))
    assert result['total_dividend_profit']==4025
    assert result['dividend_details'][0]['source']=='NH_RECEIPT'
    assert result['dividend_details'][0]['tax_amount'] is None
    assert result['dividend_details'][0]['gross_amount'] is None
