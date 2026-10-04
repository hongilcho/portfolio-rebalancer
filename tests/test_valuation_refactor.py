"""Whole-response regression snapshots use synthetic data, never private balances."""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from backend.routers import dashboard, portfolios
from logic import dividend_fetcher
from logic.dividend_calculator import calculate_holding_dividends
from logic.portfolio_valuation import index_valuation_inputs, calculate_portfolio_summary
from logic.overview_valuation import calculate_overview_summary
from backend.valuation_service import evaluate_portfolio, evaluate_portfolios


def sample_snapshot(variant="normal"):
    batch = dict(portfolios=[], accounts=[], assets=[], holdings=[], trade_history=[], crypto_holdings=[])
    quotes = []
    for pid in ("default", "second"):
        batch['portfolios'].append(dict(id=pid, name=pid, is_default=pid == "default"))
        for suffix, kind in (("normal", "GENERAL"), ("taxfree", "ISA")):
            acc_id = f"{pid}-{suffix}"
            batch['accounts'].append(dict(id=acc_id, portfolio_id=pid, account_no=acc_id,
                account_alias=suffix, account_type=kind, deposit_krw=125000.25,
                deposit_usd=123.45, annual_limit=18000000, tax_limit=9000000, priority=1))
        for suffix, market, name, ticker, weight in (
            ("kr", "KR", "ETF", "KRTEST", 50), ("us", "US", "US ETF", "USTEST", 30),
            ("gold", "KR", "금현물", "M04020000", 10),
            ("deposit", "KR", "정기예금", "DEP-test", 10),
            ("inactive", "KR", "비활성 종목", "OLD", 0),
            ("excluded", "KR", "비중 제외", "EXCLUDED", 0),
            ("zero", "KR", "전량 매도", "CLOSED", 0),
        ):
            aid = f"{pid}-{suffix}"
            asset = dict(id=aid, portfolio_id=pid, name=name, ticker=ticker, market=market,
                         target_weight=weight, is_active=suffix != "inactive",
                         include_in_rebalance=suffix != "excluded", is_risk_asset=market == "US")
            if suffix == "deposit":
                asset.update(is_deposit=True, deposit_principal=500000, interest_rate=3.5,
                             maturity_date="2027-01-01", account_no="deposit")
            batch['assets'].append(asset)
            quotes.append(dict(id=aid, price_krw=154000.5 if market == "US" else 110000.25,
                               price_usd=110.000357 if market == "US" else 0))
            if suffix == "deposit":
                quotes[-1]['price_krw'] = 510000
                continue
            owners = ("normal", "taxfree") if suffix in ("kr", "us") else ("normal",)
            for owner in owners:
                acc_id = f"{pid}-{owner}"
                qty = 0 if suffix == "zero" else (7.25 if owner == "normal" else 3.5)
                h = dict(id=f"{aid}-{owner}", asset_id=aid, account_id=acc_id,
                         asset_name=name, ticker=ticker, market=market, quantity=qty,
                         avg_price=125000 if market == "US" else 95000,
                         original_avg_price=130000 if market == "US" else 100000,
                         avg_price_usd=98.111, original_avg_price_usd=100.111,
                         buy_fx_rate=1300 if owner == "normal" else 1350,
                         first_buy_date="2026-01-01", is_risk_asset=asset['is_risk_asset'])
                batch['holdings'].append(h)
                batch['trade_history'].extend([
                    dict(id=f"{h['id']}-init", account_id=acc_id, asset_id=aid, trade_type="INIT",
                         quantity=qty + 1, trade_date="2026-01-01", trade_sequence=1),
                    dict(id=f"{h['id']}-sell", account_id=acc_id, asset_id=aid, trade_type="SELL",
                         quantity=1, trade_date="2026-02-15", trade_sequence=2),
                ])
    if variant == "manual":
        for h in batch['holdings']:
            h['manual_dividend_override'] = 4321.2345 if h['market'] == "KR" else 12.3456
    elif variant == "zero_quotes":
        for q in quotes:
            q['price_krw'] = q['price_usd'] = 0
    elif variant == "missing_quotes":
        quotes.clear()
        batch['trade_history'].clear()
    elif variant == "empty":
        batch['holdings'].clear()
        batch['assets'].clear()
        batch['trade_history'].clear()
        quotes.clear()
    fx = 0 if variant == "zero_fx" else 1400
    return batch, quotes, fx


def snapshot_outputs(variant):
    batch, quotes, fx = sample_snapshot(variant)
    status = dict(updated_at=123, stale=False, refreshing=False, refresh_failed=False)
    dividends = [dict(date="2026-02-01", amount=1.2345), dict(date="2026-03-01", amount=2.3456)]
    crypto = dict(crypto_total=dict(total_buy=10000, total_eval=12345, total_profit=2345,
                                   total_profit_pct=23.45), crypto_assets=[])
    with patch.object(dashboard, 'get_overview_batch_data', return_value=batch), \
         patch.object(portfolios, 'get_overview_batch_data', return_value=batch), \
         patch.object(dashboard.market_service, 'get_prices', return_value=(quotes, {q['id']: q['price_krw'] for q in quotes})), \
         patch.object(dashboard.market_service, 'request_snapshot', return_value=dict(prices=quotes, usd_krw=fx, rate_source='fixed')), \
         patch.object(dashboard.market_service, 'request_status', return_value=status), \
         patch.object(dividend_fetcher, 'fetch_dividend_history', return_value=dividends), \
         patch.object(dashboard, 'get_dividend_status', return_value=status), \
         patch.object(portfolios, 'get_dividend_status', return_value=status), \
         patch.object(portfolios, 'get_crypto_status', return_value=status), \
         patch.object(portfolios, 'get_crypto_prices', return_value={}), \
         patch.object(portfolios, 'get_crypto_summary', return_value=crypto):
        outputs = {'bundle': dashboard.get_dashboard_bundle(),
                   'overview': portfolios.get_all_portfolios_overview(include_crypto=False),
                   'overview_crypto': portfolios.get_all_portfolios_overview(include_crypto=True)}
    return outputs


VARIANTS = ("normal", "manual", "zero_quotes", "missing_quotes", "empty", "zero_fx")


@pytest.mark.parametrize("variant", VARIANTS)
def test_full_responses_match_pre_refactor(variant):
    expected = json.loads((Path(__file__).parent / 'fixtures/valuation_before_refactor.json').read_text())
    for endpoint, output in snapshot_outputs(variant).items():
        encoded = json.dumps(output, sort_keys=True, ensure_ascii=False).encode()
        assert hashlib.sha256(encoded).hexdigest() == expected['sha256'][f'{variant}/{endpoint}'], \
            f'{variant}/{endpoint} response changed'


def test_one_adjustment_per_holding_and_one_index_per_overview():
    calculator = dashboard.calculate_adjusted_holding_prices
    with patch.object(dashboard, 'calculate_adjusted_holding_prices', wraps=calculator) as adjustments, \
         patch.object(portfolios, 'index_valuation_inputs', wraps=index_valuation_inputs) as indexes:
        snapshot_outputs('normal')
    # Eight holdings in the individual view, sixteen in each of two overviews.
    assert adjustments.call_count == 8 + 16 + 16
    assert indexes.call_count == 2
    # The same ticker's taxable and tax-free accounts retain distinct adjustments.
    types = {call.kwargs['account_type'] for call in adjustments.call_args_list}
    assert types == {'GENERAL', 'ISA'}


def test_pure_valuation_preserves_inputs_and_reuses_prepared_dividends():
    batch, quotes, fx = sample_snapshot()
    inputs = index_valuation_inputs(batch['holdings'], batch['trade_history'], quotes)
    before = copy.deepcopy((batch, quotes, inputs))
    assets = {a['id']: a for a in batch['assets']}
    accounts = {a['id']: a for a in batch['accounts']}
    records = [dict(date='2026-02-01', amount=10.5)]
    adjustments = {
        (h['account_id'], h['asset_id']): calculate_holding_dividends(
            h, assets[h['asset_id']], fx,
            account_type=accounts[h['account_id']]['account_type'],
            trades=inputs.trades_by_holding[(h['account_id'], h['asset_id'])],
            dividend_records=records)
        for h in batch['holdings']
    }
    original_adjustments = copy.deepcopy(adjustments)
    prices = {p['id']: p['price_krw'] for p in quotes}
    # Pure functions run successfully with the suite's network/DB guards enabled.
    result = calculate_portfolio_summary(batch['accounts'], batch['assets'], inputs, adjustments, prices, fx)
    assert (batch, quotes, inputs) == before
    assert adjustments == original_adjustments
    kpi = result['kpi']
    assert kpi['total_portfolio_eval'] == result['cash_assets']['total_cash_krw'] + kpi['total_stock_eval']
    assert kpi['total_stock_return'] == pytest.approx(
        (kpi['total_stock_eval'] - kpi['total_stock_buy'] + kpi['total_dividend_profit'])
        / kpi['total_stock_buy'] * 100, abs=0.0001)
    normal = adjustments[('default-normal', 'default-kr')]
    taxfree = adjustments[('default-taxfree', 'default-kr')]
    assert normal['tax_rate'] == 0.154
    assert taxfree['tax_rate'] == 0
    assert normal['avg_price'] == taxfree['avg_price'] == 100000


def test_new_request_recalculates_overrides_without_retaining_old_results():
    batch, quotes, fx = sample_snapshot()
    accounts = [a for a in batch['accounts'] if a['portfolio_id'] == 'default']
    assets = [a for a in batch['assets'] if a['portfolio_id'] == 'default']
    prices = {p['id']: p['price_krw'] for p in quotes}
    records = [dict(date='2026-02-01', amount=10.5)]
    calculator = Mock(side_effect=lambda h, a, fx, **kwargs: calculate_holding_dividends(
        h, a, fx, dividend_records=records, **kwargs))
    first = evaluate_portfolio(accounts, assets,
        index_valuation_inputs(batch['holdings'], batch['trade_history'], quotes),
        prices, fx, calculate_adjustment=calculator)
    batch['holdings'][0]['manual_dividend_override'] = 12345
    second = evaluate_portfolio(accounts, assets,
        index_valuation_inputs(batch['holdings'], batch['trade_history'], quotes),
        prices, fx, calculate_adjustment=calculator)
    assert calculator.call_count == 16
    assert first['accounts'][0]['holdings'][0]['dividend_profit_krw'] != 12345
    assert second['accounts'][0]['holdings'][0]['dividend_profit_krw'] == 12345
    assert first['kpi']['total_stock_eval'] == second['kpi']['total_stock_eval']
    assert first['kpi']['total_stock_buy'] == second['kpi']['total_stock_buy']


def test_pure_calculators_do_not_import_database_or_provider_modules():
    check = subprocess.run([sys.executable, '-c',
        'import sys; import logic.dividend_calculator; import logic.portfolio_valuation; '
        'import logic.overview_valuation; '
        'assert not ({"psycopg2", "yfinance", "pandas", "backend.config"} & set(sys.modules))'],
        capture_output=True, text=True)
    assert check.returncode == 0, check.stderr


def test_overview_pure_aggregation_keeps_cash_and_crypto_and_does_not_mutate_inputs():
    batch, quotes, fx = sample_snapshot()
    inputs = index_valuation_inputs(batch['holdings'], batch['trade_history'], quotes)
    calculator = lambda h, a, fx, **kwargs: calculate_holding_dividends(
        h, a, fx, dividend_records=[dict(date='2026-02-01', amount=10.5)], **kwargs)
    dashboards, errors, accounts_by_pid = evaluate_portfolios(
        batch['portfolios'], batch['accounts'], batch['assets'], inputs,
        {q['id']: q['price_krw'] for q in quotes}, fx, calculate_adjustment=calculator)
    assert errors == []
    crypto = dict(crypto_total=dict(total_buy=10000, total_eval=12345), crypto_assets=[
        dict(symbol='BTC', name='Bitcoin', quantity=0.01, avg_price=1000000,
             current_price=1234500, buy_amount=10000, eval_amount=12345)])
    before = copy.deepcopy((batch, dashboards, crypto, accounts_by_pid))
    response, errors = calculate_overview_summary(
        batch['portfolios'], dashboards, crypto, True, fx, accounts_by_pid)
    assert errors == []
    assert (batch, dashboards, crypto, accounts_by_pid) == before
    grand = response['grand_total']
    assert grand['total_eval'] == grand['portfolios_total_eval'] + 12345
    assert grand['total_buy'] == sum(d['kpi']['total_stock_buy'] for d in dashboards.values()) + 10000
    assert grand['total_profit_pct'] == grand['total_profit'] / grand['total_buy'] * 100
    assert grand['usd_summary']['cash_usd'] == 493.8


def test_one_portfolio_failure_keeps_other_portfolios_available():
    batch, quotes, fx = sample_snapshot()
    def calculator(h, a, fx, **kwargs):
        if h['account_id'].startswith('default-'):
            raise RuntimeError('Unavailable dividend data')
        return calculate_holding_dividends(h, a, fx, dividend_records=[], **kwargs)
    dashboards, errors, _ = evaluate_portfolios(
        batch['portfolios'], batch['accounts'], batch['assets'],
        index_valuation_inputs(batch['holdings'], batch['trade_history'], quotes),
        {q['id']: q['price_krw'] for q in quotes}, fx, calculate_adjustment=calculator)
    assert set(dashboards) == {'second'}
    assert errors == ['Error calculating overview for portfolio default: Unavailable dividend data']
