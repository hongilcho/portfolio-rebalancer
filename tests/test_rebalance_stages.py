"""Differential contract: planner stages preserve the original complete result."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import random

import pytest
from logic.rebalance_calculator import calculate_rebalancing_plan

_spec = importlib.util.spec_from_file_location(
    'legacy_rebalance', Path(__file__).parent / 'fixtures/legacy_rebalance_calculator.py'
)
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)


def synthetic_case(seed, asset_count=None, account_count=None):
    rng = random.Random(seed)
    n = asset_count or rng.randint(1, 12)
    m = account_count or rng.randint(1, 7)
    # Mixed raw ID types exercise the legacy account vs pair matching rules.
    ids = [str(i) if seed % 2 else i for i in range(m)]
    accounts = [dict(
        id=aid, account_alias=f'Account {aid}',
        account_type=rng.choice(['CMA', 'IRP', 'ISA', '종합매매', '금현물', '연금저축']),
        priority=rng.randint(1, 3), deposit_krw=rng.randint(0, 50000) + .3,
        deposit_usd=rng.choice([0, 5.125]), annual_limit=rng.choice([0, 20000, 200000]),
        tax_limit=rng.choice([0, 10000, 80000]), limit_preference=rng.choice(['TAX', 'ANNUAL']),
        is_limit_exhausted=rng.random() < .1,
    ) for aid in ids]
    weights = [rng.randint(1, 10) for _ in range(n)]
    assets = [dict(
        id=i if seed % 3 else str(i), name=f'Asset {i}',
        target_weight=weights[i] / sum(weights) * 100,
        is_risk_asset=rng.random() < .5, market=rng.choice(['KR', 'US']),
        allowed_accounts=[aid for aid in ids if rng.random() < .8],
        include_in_rebalance=rng.random() > .1, is_deposit=rng.random() < .1,
        lock_rebalance_sell=rng.choice([True, False, None]),
    ) for i in range(n)]
    prices = {str(i): rng.choice([0, 130.25, 2500, 140000]) for i in range(n)}
    holdings = []
    portfolio = {}
    for asset in assets:
        sid = str(asset['id'])
        for account in accounts:
            if rng.random() < .6:
                qty = rng.randint(1, 20) + rng.choice([0, .125])
                holdings.append(dict(
                    account_id=account['id'], asset_id=asset['id'],
                    quantity=qty, avg_price=rng.choice([100.75, 2000, 130000]),
                ))
                item = portfolio.setdefault(sid, {'qty': 0, 'eval_amt_krw': 0})
                item['qty'] += qty
                item['eval_amt_krw'] += qty * prices[sid]
    return dict(
        assets=assets, portfolio_assets=portfolio, accounts=accounts, holdings=holdings,
        price_map=prices, total_krw_cash=sum(a['deposit_krw'] for a in accounts),
        usd_krw_rate=1327.17, scenario=['NEW_CASH', 'DRIFT', 'PERIODIC'][seed % 3],
        new_cash_krw=rng.choice([0, 30000, 150000]), drift_threshold=rng.choice([0, 5, 100]),
    )


@pytest.mark.parametrize('seed', range(150))
def test_stages_match_complete_legacy_result_without_mutation(seed):
    case = synthetic_case(seed)
    snapshot = deepcopy(case)
    expected = _legacy.calculate_rebalancing_plan(**case)
    assert case == snapshot
    assert calculate_rebalancing_plan(**case) == expected
    assert case == snapshot
