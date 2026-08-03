import sys
sys.path.append('.')
from data_manager import get_all_accounts, get_all_assets, get_trade_history
from price_fetcher import fetch_asset_prices
import math

accounts = get_all_accounts()
assets = get_all_assets()
holdings = get_trade_history()
price_results, _ = fetch_asset_prices(assets, 1400.0)
price_map = {str(p['id']): p['price_krw'] for p in price_results}

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

total_asset_krw = sum(v['eval_amt_krw'] for v in portfolio_assets.values())
new_cash_krw = 1000000.0
total_cash_krw = total_krw_cash + new_cash_krw
total_portfolio_krw = total_asset_krw + total_cash_krw

targets = {}
for a in assets:
    aid = str(a['id'])
    t_weight = a['target_weight'] / 100.0
    t_value = total_portfolio_krw * t_weight
    current_price = price_map.get(aid, 0.0)
    current_qty = portfolio_assets.get(aid, {}).get('qty', 0)
    if current_price > 0:
        target_qty = math.floor(t_value / current_price)
    else:
        target_qty = current_qty
    diff_qty = target_qty - current_qty
    if diff_qty < 0: diff_qty = 0
    targets[aid] = {
        'name': a['name'],
        'target_qty': target_qty,
        'current_qty': current_qty,
        'diff_qty': diff_qty,
        'price': current_price
    }

buy_targets = {aid: t for aid, t in targets.items() if t['diff_qty'] > 0}
total_buy_needed = sum(t['diff_qty'] * t['price'] for t in buy_targets.values())
available_cash_pool = total_cash_krw

scale_factor = available_cash_pool / total_buy_needed if total_buy_needed > 0 else 0
print("Total Portfolio KRW:", total_portfolio_krw)
print("Available Cash:", available_cash_pool)
print("Total Buy Needed:", total_buy_needed)

for aid in buy_targets:
    buy_targets[aid]['diff_qty'] = math.floor(buy_targets[aid]['diff_qty'] * scale_factor)

allocated_cash = sum(t['diff_qty'] * t['price'] for t in buy_targets.values())
rem_cash = available_cash_pool - allocated_cash
print("Remaining cash:", rem_cash)

while rem_cash > 0:
    best_aid = None
    max_shortfall = 0
    for aid, t in buy_targets.items():
        if t['price'] <= 0 or t['price'] > rem_cash: continue
        planned_val = (t['current_qty'] + t['diff_qty']) * t['price']
        orig_target_val = targets[aid]['target_qty'] * t['price']
        shortfall = orig_target_val - planned_val
        if shortfall > max_shortfall:
            max_shortfall = shortfall
            best_aid = aid
    if best_aid is None: break
    buy_targets[best_aid]['diff_qty'] += 1
    rem_cash -= buy_targets[best_aid]['price']

for aid, t in buy_targets.items():
    print(t['name'], t['diff_qty'])
