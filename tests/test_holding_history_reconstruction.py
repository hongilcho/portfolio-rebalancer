"""Synthetic legacy overlaps; all frozen inputs and existing NAVs are immutable."""
from copy import deepcopy
from datetime import datetime, date, timedelta
import json

import pytest

from logic.holding_history import financial, history
from logic.holding_history_evidence import Evidence, with_dividend_start
from logic.realized_opening import create
from logic.close_calendar import KST


def fixture():
    holding = dict(account_id='qa-account', asset_id='qa-etf', quantity=17,
                   asset_name='합성 ETF', ticker='QATEST', market='KR',
                   avg_price=100, original_avg_price=100, avg_price_usd=0,
                   original_avg_price_usd=0, first_buy_date=None, buy_fx_rate=0)
    ledger = dict(accounts=[dict(id='qa-account', portfolio_id='qa', account_no='SYNTHETIC',
                                account_alias='합성 ISA', account_type='ISA', deposit_krw=20,
                                deposit_usd=0)],
                  assets=[dict(id='qa-etf', portfolio_id='qa', name='합성 ETF', ticker='QATEST',
                               market='KR', target_weight=100, is_active=True, is_risk_asset=False)],
                  holdings=[holding], dividend_cache={'div_KR_QATEST': {'data': []}})
    trades = [dict(id='qa-init', account_id='qa-account', asset_id='qa-etf', trade_type='INIT',
                   trade_date='2026-09-28', quantity=17, price=100, currency='KRW'),
              dict(id='qa-buy', account_id='qa-account', asset_id='qa-etf', trade_type='BUY',
                   trade_date='2026-09-28', quantity=6, price=100, currency='KRW')]
    prices = {'qa-etf': dict(id='qa-etf', price_krw=110, price_native=110)}
    return ledger, trades, prices


def snapshot(ledger, day):
    return dict(portfolio_id='qa', snapshot_date=day, value_krw=1890,
                payload={'ledger': deepcopy(ledger), 'prices': {
                    'qa-etf': dict(id='qa-etf', price_krw=110, price_native=110)}, 'fx': {'rate': 1400}})


def opening(ledger, trades):
    return create('qa', ledger['holdings'][0], trades, 'qa-opening', datetime(2026, 10, 17, tzinfo=KST))


def receipt(value):
    return {'kind': 'REALIZED_OPENING', 'positions': [value]}


def test_no_relevant_dividend_does_not_require_replaying_overlapping_initial_books():
    ledger, trades, prices = fixture()
    ledger['trade_history'] = trades
    before = deepcopy(ledger)
    metric = financial(ledger, prices, 1400, '2026-10-05', reconstructed=True)
    assert metric['status'] == 'COMPLETE' and metric['profit_krw'] == 170
    assert metric['cost_krw'] == 1700 and metric['value_krw'] == 1890
    assert ledger == before


def test_legacy_sentinel_cannot_include_ancient_distributions_or_future_buys():
    ledger, trades, prices = fixture()
    ledger['holdings'][0]['min_trade_date'] = '2000-01-01'
    trades[0]['trade_date'] = '2000-01-01'
    trades.append({**trades[1], 'id': 'future', 'trade_date': '2027-01-01', 'quantity': 999})
    ledger['trade_history'] = trades
    ledger['dividend_cache']['div_KR_QATEST']['data'] = [
        {'date': '2025-12-01', 'amount': 1000}, {'date': '2027-01-02', 'amount': 1000}]
    result = financial(ledger, prices, 1400, '2026-10-05', reconstructed=True)
    assert result['status'] == 'COMPLETE' and result['dividend_krw'] == 0
    assert with_dividend_start(ledger['holdings'][0], trades)['min_trade_date'] == '2026-07-01'


@pytest.mark.parametrize('cache', [None, {}, {'data': None}])
def test_missing_cache_is_never_treated_as_zero_dividends(cache):
    ledger, trades, prices = fixture()
    ledger['trade_history'] = trades
    ledger['dividend_cache'] = {} if cache is None else {'div_KR_QATEST': cache}
    assert financial(ledger, prices, 1400, '2026-10-05', reconstructed=True)['status'] == 'UNAVAILABLE'


def test_nonempty_cache_without_start_date_and_history_stays_unknown():
    ledger, _, prices = fixture()
    ledger['dividend_cache']['div_KR_QATEST']['data'] = [{'date': '2026-09-30', 'amount': 1}]
    assert financial(ledger, prices, 1400, '2026-10-05', reconstructed=True)['status'] == 'UNAVAILABLE'


def test_frozen_manual_start_and_dividend_override_are_preserved():
    ledger, trades, prices = fixture()
    ledger['trade_history'] = trades
    ledger['holdings'][0].update(first_buy_date='2026-10-01', manual_dividend_override=77)
    ledger['dividend_cache'] = {}
    assert financial(ledger, prices, 1400, '2026-10-05', reconstructed=True)['dividend_krw'] == 77
    h = with_dividend_start(ledger['holdings'][0], trades)
    assert h['first_buy_date'] == '2026-10-01'


def test_confirmed_opening_corroborates_quantity_without_replacing_old_cost():
    ledger, trades, prices = fixture()
    ledger['trade_history'] = trades
    ledger['dividend_cache']['div_KR_QATEST']['data'] = [{'date': '2026-09-30', 'amount': 1}]
    seed = opening(ledger, trades)
    seed['avg_krw'] = '9999'  # Confirmed cost must never overwrite the frozen one.
    evidence = Evidence([], trades, [receipt(seed)])
    before = deepcopy((ledger, seed))
    result = financial(ledger, prices, 1400, '2026-10-05', reconstructed=True, evidence=evidence)
    assert result['status'] == 'COMPLETE' and result['dividend_krw'] == 17
    assert result['cost_krw'] == 1700 and result['profit_krw'] == 187
    assert (ledger, seed) == before


@pytest.mark.parametrize('change', ['modified', 'removed', 'backdated', 'revoked'])
def test_invalid_or_revoked_confirmations_cannot_unlock_history(change):
    ledger, trades, prices = fixture()
    seed = opening(ledger, trades)
    receipts = [receipt(seed)]
    if change == 'modified': trades[1]['quantity'] = 7
    elif change == 'removed': trades.pop(0)
    elif change == 'backdated': trades.append({**trades[1], 'id': 'late-record', 'trade_date': '2026-10-01'})
    else: receipts.append({'kind': 'REALIZED_OPENING_REVOKED', 'baseline_id': seed['id']})
    ledger['trade_history'] = trades
    ledger['dividend_cache']['div_KR_QATEST']['data'] = [{'date': '2026-09-30', 'amount': 1}]
    evidence = Evidence([], trades, receipts)
    assert financial(ledger, prices, 1400, '2026-10-05', reconstructed=True, evidence=evidence)['status'] == 'UNAVAILABLE'


def test_confirmed_endpoint_cannot_certify_wrong_ex_dividend_quantity():
    ledger, trades, prices = fixture()
    trades[1]['trade_date'] = '2026-09-29'
    seed = opening(ledger, trades)
    ledger['trade_history'] = trades
    ledger['dividend_cache']['div_KR_QATEST']['data'] = [{'date': '2026-10-01', 'amount': 1}]
    # Frozen/confirmed qty=17 but the dividend engine would use 23. Fail closed.
    evidence = Evidence([], trades, [receipt(seed)])
    assert financial(ledger, prices, 1400, '2026-10-05', reconstructed=True, evidence=evidence)['status'] == 'UNAVAILABLE'


def test_later_buy_uses_confirmed_quantity_and_original_dividend_engine_together():
    ledger, trades, prices = fixture()
    seed = opening(ledger, trades)
    trades.append({**trades[1], 'id': 'after-confirmation', 'trade_date': '2026-10-18', 'quantity': 3})
    ledger['holdings'][0]['quantity'] = 20
    ledger['trade_history'] = trades
    ledger['dividend_cache']['div_KR_QATEST']['data'] = [{'date': '2026-10-19', 'amount': 1}]
    result = financial(ledger, prices, 1400, '2026-10-20', reconstructed=True,
                       evidence=Evidence([], trades, [receipt(seed)]))
    assert result['status'] == 'COMPLETE' and result['dividend_krw'] == 20
    assert result['cost_krw'] == 2000


def test_early_dividend_uses_actual_buys_before_a_later_overlapping_initial_book():
    ledger, trades, prices = fixture()
    early = [{**trades[1], 'id':'august-1','trade_date':'2026-08-20','quantity':4},
             {**trades[0], 'id':'august-init-1','trade_date':'2026-08-20','quantity':4},
             {**trades[1], 'id':'august-2','trade_date':'2026-08-25','quantity':7},
             {**trades[0], 'id':'august-init-2','trade_date':'2026-08-25','quantity':11}]
    reset = {**trades[0], 'id':'october-reset','trade_date':'2026-10-07'}
    full = early+trades+[reset]
    ledger['trade_history'] = full
    ledger['dividend_cache']['div_KR_QATEST']['data'] = [
        {'date':'2026-08-28','amount':1},{'date':'2026-09-30','amount':1}]
    evidence = Evidence([snapshot(ledger,'2026-10-07')],full)
    result = financial(ledger,prices,1400,'2026-10-05',reconstructed=True,evidence=evidence)
    assert result['status']=='COMPLETE' and result['dividend_krw']==11+17
    # An earlier reset introduces ambiguity; never replace it with future qty.
    full.insert(0,{**trades[0],'id':'earlier-reset','trade_date':'2026-08-01','quantity':2})
    evidence = Evidence([snapshot(ledger,'2026-10-07')],full)
    assert financial(ledger,prices,1400,'2026-10-05',reconstructed=True,evidence=evidence)['status']=='UNAVAILABLE'


def test_conflicting_confirmation_and_reset_evidence_stays_unknown():
    ledger, trades, _ = fixture()
    reset = {**trades[0], 'id': 'reset', 'trade_date': '2026-10-07'}
    seed = opening(ledger, trades+[reset])
    seed['quantity'] = '18'
    evidence = Evidence([snapshot(ledger, '2026-10-07')], trades+[reset], [receipt(seed)])
    # Opening cannot be projected across the intervening reset, so a prior
    # date uses only its separately corroborated reset, not the conflicting 18.
    assert evidence.expected(ledger['holdings'][0], '2026-10-05') == 17
    # Same-day/new uncovered trades cannot be ordered against a confirmation.
    new = {**trades[1], 'id': 'same-day', 'trade_date': '2026-10-17'}
    assert Evidence([], trades+[reset,new], [receipt(seed)]).expected(ledger['holdings'][0], '2026-10-18') is None


def test_later_reset_requires_matching_frozen_book_and_handles_identical_duplicates():
    ledger, trades, prices = fixture()
    resets = [{**trades[0], 'id': 'reset-'+str(i), 'trade_date': '2026-10-07'} for i in range(2)]
    ledger['dividend_cache']['div_KR_QATEST']['data'] = [{'date': '2026-09-30', 'amount': 1}]
    rows = [snapshot(ledger, '2026-10-05'), snapshot(ledger, '2026-10-07')]
    all_trades = trades + resets
    recon = {'trade_history': all_trades, 'dividend_cache': ledger['dividend_cache']}
    before = deepcopy((rows, recon))
    result = history(rows, [], ['qa'], scope='qa', reconstruction=recon)
    assert result['rows'][0]['status'] == 'COMPLETE' and result['rows'][0]['dividend_krw'] == 17
    assert (rows, recon) == before
    rows[1]['payload']['ledger']['holdings'][0]['quantity'] = 18
    assert history(rows, [], ['qa'], scope='qa', reconstruction=recon)['rows'][0]['status'] == 'UNAVAILABLE'


def test_conflicting_duplicate_resets_or_uncertain_books_do_not_corroborate():
    ledger, trades, _ = fixture()
    resets = [{**trades[0], 'id': 'reset-'+str(i), 'trade_date': '2026-10-07', 'quantity': 17+i} for i in range(2)]
    row = snapshot(ledger, '2026-10-07')
    assert Evidence([row], trades+resets).expected(ledger['holdings'][0], '2026-10-05') is None
    resets[1]['quantity'] = 17
    row['payload']['holding_metrics'] = {'status': 'UNCONFIRMED'}
    assert Evidence([row], trades+resets).expected(ledger['holdings'][0], '2026-10-05') is None


def test_ambiguous_same_day_buy_preserves_frozen_quantity_when_dividend_irrelevant():
    ledger, trades, prices = fixture()
    seed = opening(ledger, trades)
    later = {**trades[1], 'id': 'later-buy', 'trade_date': '2026-10-08', 'quantity': 5}
    seed['covered_trades'] = create('qa', {**ledger['holdings'][0], 'quantity': 22},
        trades+[later], 'covered', datetime(2026, 10, 17, tzinfo=KST))['covered_trades']
    seed['quantity'] = '22'
    ledger['trade_history'] = trades+[later]
    evidence = Evidence([], trades+[later], [receipt(seed)])
    assert evidence.expected(ledger['holdings'][0], '2026-10-08') == 22
    result = financial(ledger, prices, 1400, '2026-10-08', reconstructed=True, evidence=evidence)
    assert result['status'] == 'COMPLETE' and result['cost_krw'] == 1700
    assert ledger['holdings'][0]['quantity'] == 17  # Do not replace with 22.


def test_sixteen_synthetic_observations_restore_without_touching_original_period_data():
    ledger, trades, _ = fixture()
    resets = [{**trades[0], 'id': 'reset-'+str(i), 'trade_date': '2026-10-07'} for i in range(2)]
    ledger['dividend_cache']['div_KR_QATEST']['data'] = [{'date': '2026-09-30', 'amount': 1}]
    days = [(date(2026, 10, 5)+timedelta(days=i)).isoformat() for i in range(16)]
    rows = [snapshot(ledger, day) for day in days]
    original = json.dumps(rows, sort_keys=True)
    result = history(rows, [], ['qa'], scope='qa', reconstruction={
        'trade_history': trades+resets, 'dividend_cache': ledger['dividend_cache']})
    observed = [r for r in result['rows'] if r['date'] in days]
    assert len(observed) == 16 and all(r['status'] == 'COMPLETE' for r in observed)
    assert all(r['profit_krw'] == 187 and r['cost_krw'] == 1700 and r['value_krw'] == 1890 for r in observed)
    assert json.dumps(rows, sort_keys=True) == original
