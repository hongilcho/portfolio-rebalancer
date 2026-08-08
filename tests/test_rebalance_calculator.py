import pytest
from logic.rebalance_calculator import calculate_rebalancing_plan

def test_calculate_rebalancing_plan_empty():
    plan, transfers, sim_assets, success, msg = calculate_rebalancing_plan(
        assets=[],
        portfolio_assets={},
        accounts=[],
        holdings=[],
        price_map={},
        total_krw_cash=0.0,
        usd_krw_rate=1300.0,
        scenario="NEW_CASH"
    )
    assert plan == []
    assert transfers == []
    assert success is False

def test_calculate_rebalancing_plan_basic(mock_accounts, mock_assets, mock_holdings, mock_price_data):
    # Prepare data in the format expected by the calculator
    price_map = {str(p['id']): p['price_krw'] for p in mock_price_data}
    
    # Portfolio assets aggregated
    portfolio_assets = {}
    for h in mock_holdings:
        aid = h['asset_id']
        val = h['quantity'] * price_map.get(aid, 0.0)
        if aid not in portfolio_assets:
            portfolio_assets[aid] = {'qty': 0, 'eval_amt_krw': 0.0}
        portfolio_assets[aid]['qty'] += h['quantity']
        portfolio_assets[aid]['eval_amt_krw'] += val

    total_krw_cash = sum([a['deposit_krw'] + a['deposit_usd'] * 1350.0 for a in mock_accounts])
    
    plan, transfers, sim_assets, success, msg = calculate_rebalancing_plan(
        assets=mock_assets,
        portfolio_assets=portfolio_assets,
        accounts=mock_accounts,
        holdings=mock_holdings,
        price_map=price_map,
        total_krw_cash=total_krw_cash,
        usd_krw_rate=1350.0,
        scenario="NEW_CASH",
        new_cash_krw=0.0,
        drift_threshold=0.0
    )
    
    # Since there are assets and accounts, this should succeed or fail depending on if total cash > 0
    # In this mock, total portfolio value is:
    # 10 shares ast_1 @ 80k = 800k
    # acc1 cash = 1M + 1350k = 2350k
    # acc2 cash = 5M
    # Total cash = 7350k, total value = 8150k
    
    assert success is True
    assert len(plan) > 0
    
def test_risk_asset_limits(mock_accounts, mock_assets, mock_price_data):
    # Calculator logic is hardcoded to check 70% risk limit for 'IRP' accounts
    price_map = {str(p['id']): p['price_krw'] for p in mock_price_data}
    
    # Modify mock_account[1] to be an IRP account
    mock_acc2 = mock_accounts[1].copy()
    mock_acc2['account_type'] = 'IRP'
    
    plan, transfers, sim_assets, success, msg = calculate_rebalancing_plan(
        assets=mock_assets,
        portfolio_assets={},
        accounts=[mock_acc2],
        holdings=[],
        price_map=price_map,
        total_krw_cash=5000000.0,
        usd_krw_rate=1300.0,
        scenario="NEW_CASH"
    )
    
    assert success is True
    
    # Check if trades respect 70% risk limit
    risk_value = 0
    safe_value = 0
    
    for t in plan:
        val = t['qty'] * t['price']
        if t['asset_id'] in ('ast_1', 'ast_2'):
            risk_value += val
        else:
            safe_value += val
            
    assert risk_value <= 5000000 * 0.70 + 1000 # Allow small rounding err
