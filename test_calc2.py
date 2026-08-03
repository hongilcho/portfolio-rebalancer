import sys
sys.path.append('.')
from data_manager import get_all_accounts, get_all_assets, get_trade_history
from price_fetcher import fetch_asset_prices
from rebalance_calculator import calculate_rebalancing_plan

accounts = get_all_accounts()
assets = get_all_assets()
holdings = get_trade_history()
price_results, _ = fetch_asset_prices(assets, 1400.0)
price_map = {str(p['asset_id']): p['krw_price'] for p in price_results}

total_krw_cash = sum(a['deposit_krw'] for a in accounts)

portfolio_assets = {}
for a in assets:
    portfolio_assets[str(a['id'])] = {'qty': 0, 'eval_amt_krw': 0.0, 'buy_amt_krw': 0.0}

for h in holdings:
    aid = str(h['asset_id'])
    if aid not in portfolio_assets:
        portfolio_assets[aid] = {'qty': 0, 'eval_amt_krw': 0.0, 'buy_amt_krw': 0.0}
    qty = h['quantity']
    price = price_map.get(aid, 0.0)
    portfolio_assets[aid]['qty'] += qty
    portfolio_assets[aid]['eval_amt_krw'] += qty * price

print(f"Total KRW cash: {total_krw_cash}")
print(f"Price map: {price_map}")

t_plan, tr_plan, sim_assets, success, msg = calculate_rebalancing_plan(
    assets=assets,
    portfolio_assets=portfolio_assets,
    accounts=accounts,
    holdings=holdings,
    price_map=price_map,
    total_krw_cash=total_krw_cash,
    usd_krw_rate=1400.0,
    scenario='NEW_CASH',
    new_cash_krw=1000000.0,
    drift_threshold=5.0
)

print('success:', success)
print('msg:', msg)
print('trade plan len:', len(t_plan))
for t in t_plan:
    print(t)
