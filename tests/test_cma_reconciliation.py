from decimal import Decimal
import pytest
from logic import cma_policy
from logic.cma_interest import fingerprint,observe_balance
from logic.cma_reconciliation import reconcile,require_receipt
from test_cma_interest import NOW,wire

PROFILE='SYNTHETIC_CMA_TEST_ONLY'


def statement(now=NOW,opening=4800000,closing=4800123,events=None,pid='p',aid='acc'):
    if events is None:
        events=[dict(reference_hash=fingerprint('synthetic-interest'),event_date=now.date().isoformat(),kind='PAID_INTEREST',amount_krw=str(Decimal(str(closing))-Decimal(str(opening))))]
    return dict(profile=PROFILE,portfolio_id=pid,account_id=aid,currency='KRW',complete=True,
        interest_posting_final=True,start_date=now.date().isoformat(),as_of=now.isoformat(),
        opening_cash_krw=str(opening),closing_cash_krw=str(closing),events=events)


def check(value,ledger=None,book=4800000):
    return reconcile(value,ledger or [],pid='p',aid='acc',book_token='token',book_cash=book,observation=observe_balance(wire(4800123),NOW))


@pytest.fixture
def trusted(monkeypatch):
    monkeypatch.setattr(cma_policy,'VALIDATED_STATEMENT_PROFILES',frozenset({PROFILE}))


def test_production_registry_is_empty_and_an_api_flag_cannot_validate_profile():
    assert not cma_policy.VALIDATED_STATEMENT_PROFILES
    assert check({**statement(),'profile_validated':True})['status']=='PROFILE_UNVERIFIED'


def test_complete_explicit_paid_interest_matches_exact_cash_gap(trusted):
    receipt=check(statement())
    assert receipt['status']=='MATCHED' and Decimal(receipt['paid_interest_krw'])==123
    require_receipt(receipt,pid='p',aid='acc',token='token',observation=observe_balance(wire(),NOW),delta=Decimal(123))


@pytest.mark.parametrize('change',[{'complete':False},{'interest_posting_final':False},{'account_id':'other'},{'portfolio_id':'other'},{'start_date':'2020-01-01'},{'currency':'USD'}])
def test_incomplete_wrong_scope_or_unsettled_day_never_authorizes_income(trusted,change):
    assert check({**statement(),**change})['status']=='STATEMENT_INCOMPLETE'


def test_small_unrecorded_deposit_is_not_interest_even_below_automatic_cap(trusted):
    event=dict(reference_hash=fingerprint('deposit'),event_date=NOW.date().isoformat(),kind='DEPOSIT',amount_krw='123')
    assert check(statement(events=[event]))['status']=='MOVEMENT_MISMATCH'


def test_initial_accumulated_gap_cannot_become_todays_paid_interest(trusted):
    s=statement(opening=4800100,events=[dict(reference_hash=fingerprint('interest'),event_date=NOW.date().isoformat(),kind='PAID_INTEREST',amount_krw='23')])
    assert check(s)['status']=='INITIAL_BALANCE_REVIEW'


def test_recorded_cash_movement_is_matched_before_only_interest_is_postable(trusted):
    events=[dict(reference_hash=fingerprint('interest'),event_date=NOW.date().isoformat(),kind='PAID_INTEREST',amount_krw='123'),dict(reference_hash=fingerprint('withdraw'),event_date=NOW.date().isoformat(),kind='WITHDRAW',amount_krw='200000')]
    s=statement(opening=5000000,events=events)
    ledger=[dict(id='withdraw',event_date=NOW.date().isoformat(),kind='WITHDRAW',amount_krw='200000')]
    assert check(s,ledger)['status']=='MATCHED'
    assert check(s,[])['status']=='MOVEMENT_MISMATCH'


def test_duplicate_bank_ids_and_unknown_transactions_are_rejected(trusted):
    s=statement();s['events']*=2
    assert check(s)['status']=='STATEMENT_INCOMPLETE'
    s=statement();s['events'][0]['kind']='PRINCIPAL_RETURN'
    assert check(s)['status']=='UNSUPPORTED_TRANSACTION'


def test_receipt_is_bound_to_current_book_scope_and_observation(trusted):
    receipt=check(statement())
    for change in ({'book_token':'different'},{'account_id':'other'},{'paid_interest_krw':'999'},{'profile':'unverified'}):
        with pytest.raises(ValueError):require_receipt({**receipt,**change},pid='p',aid='acc',token='token',observation=observe_balance(wire(),NOW),delta=Decimal(123))
