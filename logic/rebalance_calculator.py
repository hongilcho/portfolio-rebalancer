import math
import pandas as pd
from typing import List, Dict, Tuple

def calculate_rebalancing_plan(
    assets: List[dict],
    portfolio_assets: Dict[str, dict], # aggregated current holdings by asset id
    accounts: List[dict],
    holdings: List[dict], # raw holdings to know exact qty per account
    price_map: Dict[str, float],
    total_krw_cash: float,
    usd_krw_rate: float,
    scenario: str, # "NEW_CASH", "DRIFT", "PERIODIC"
    new_cash_krw: float = 0.0,
    drift_threshold: float = 5.0
) -> Tuple[List[dict], List[dict], List[dict], bool, str]:
    """
    Returns:
      trade_plan: List of planned trades (account_id, asset_id, type, qty, price)
      transfer_plan: List of cash transfers needed per account
      simulated_assets: Projected asset weights after rebalancing
      success: bool
      msg: string
    """
    # Normalize price_map keys to string to prevent lookup failures
    price_map = {str(k): float(v) for k, v in price_map.items()}

    # 1. Total Current Value
    total_asset_krw = sum(d['eval_amt_krw'] for d in portfolio_assets.values())
    total_cash_krw = total_krw_cash + new_cash_krw
    
    total_portfolio_krw = total_asset_krw + total_cash_krw
    if total_portfolio_krw <= 0:
        return [], [], [], False, "포트폴리오 총액이 0원입니다."

    # Sort accounts by user priority (lowest number = highest priority)
    # Default to 99 if not set.
    import copy
    sorted_accounts = copy.deepcopy(sorted(accounts, key=lambda x: int(x.get('priority', 99))))
    
    # 2. Check Drift Condition (if scenario == "DRIFT")
    if scenario == "DRIFT":
        needs_rebalance = False
        for aid, data in portfolio_assets.items():
            current_w = (data['eval_amt_krw'] / total_asset_krw * 100) if total_asset_krw > 0 else 0
            # We match with asset target
            target_w = next((a['target_weight'] for a in assets if str(a['id']) == str(aid)), 0)
            if abs(current_w - target_w) >= drift_threshold:
                needs_rebalance = True
                break
        if not needs_rebalance:
            return [], [], [], True, "모든 자산이 허용 괴리율 이내에 있어 리밸런싱이 필요하지 않습니다."

    # 3. Calculate Target Values
    targets = {}
    for a in assets:
        aid = str(a['id'])
        t_weight = a.get('target_weight', 0) / 100.0
        t_value = total_portfolio_krw * t_weight
        current_price = price_map.get(aid, 0.0)
        
        current_price_krw = current_price

        current_qty = portfolio_assets.get(aid, {}).get('qty', 0)
        current_val = portfolio_assets.get(aid, {}).get('eval_amt_krw', 0.0)

        if current_price_krw > 0:
            target_qty = math.floor(t_value / current_price_krw)
        else:
            target_qty = current_qty

        diff_qty = target_qty - current_qty

        # Scenario constraint
        if scenario == "NEW_CASH" and diff_qty < 0:
            diff_qty = 0 # No selling allowed

        targets[aid] = {
            "target_qty": target_qty,
            "diff_qty": diff_qty,
            "current_qty": current_qty,
            "price": current_price,
            "price_krw": current_price_krw,
            "is_risk": a['is_risk_asset'],
            "allowed_accounts": a.get('allowed_accounts', [])
        }

    # 4. Handle Sells First (to free up cash)
    trade_plan = []
    
    # Reverse priority for selling: Sell from General -> ISA -> Pension -> IRP
    sell_accounts = list(reversed(sorted_accounts))
    
    for aid, t_data in targets.items():
        if t_data["diff_qty"] < 0:
            qty_to_sell = abs(t_data["diff_qty"])
            
            # Find accounts holding this asset
            for acc in sell_accounts:
                if qty_to_sell <= 0: break
                
                # Check how much of this asset is in this account
                acc_holdings = [h for h in holdings if str(h['account_id']) == str(acc['id']) and str(h['asset_id']) == str(aid)]
                acc_qty = sum(h['quantity'] for h in acc_holdings)
                
                if acc_qty > 0:
                    sell_amt = min(acc_qty, qty_to_sell)
                    trade_plan.append({
                        "account_id": acc['id'],
                        "account_alias": acc['account_alias'],
                        "asset_id": aid,
                        "asset_name": next(a['name'] for a in assets if str(a['id']) == aid),
                        "type": "SELL",
                        "qty": sell_amt,
                        "price": t_data["price"],
                        "total_krw": sell_amt * t_data["price"]
                    })
                    qty_to_sell -= sell_amt
                    t_data["current_qty"] -= sell_amt

    # 5. Handle Buys (Compartmentalized)
    
    local_cash = {acc['id']: float(acc.get('deposit_krw', 0.0)) for acc in accounts if acc['account_type'] != 'CMA'}
    # Credit sell proceeds to local cash
    for t in trade_plan:
        if t["type"] == "SELL":
            acc_id = t["account_id"]
            if acc_id in local_cash:
                local_cash[acc_id] += t["total_krw"]
                
    global_cash = new_cash_krw
    
    if scenario != "NEW_CASH":
        for acc in accounts:
            if acc['account_type'] in ['종합매매', '금현물']:
                acc_id = acc['id']
                if acc_id in local_cash:
                    global_cash += local_cash[acc_id]
                    local_cash[acc_id] = 0.0
    # Pre-calculate limits based on principal value (invested principal + local cash)
    remaining_limits = {}
    for acc in sorted_accounts:
        if acc['account_type'] == 'CMA': continue
        
        acc_id = acc['id']
        acc_stock_buy_total = sum(h['quantity'] * h['avg_price'] for h in holdings if h['account_id'] == acc_id)
        acc_local_krw = float(acc.get('deposit_krw', 0.0))
        acc_local_usd = float(acc.get('deposit_usd', 0.0))
        principal_val = acc_stock_buy_total + acc_local_krw + (acc_local_usd * usd_krw_rate)
        
        is_exhausted = bool(acc.get('is_limit_exhausted', False))
        if is_exhausted:
            remaining_limits[acc_id] = 0.0
        else:
            limit_pref = acc.get('limit_preference', 'ANNUAL')
            limit_val = float(acc.get('annual_limit', 0)) if limit_pref == 'ANNUAL' else float(acc.get('tax_limit', 0))
            remaining_limits[acc_id] = float('inf') if limit_val <= 0 else max(0.0, limit_val - principal_val)
        
    # Planned holdings for IRP risk check
    planned_holdings = {acc['id']: {} for acc in sorted_accounts if acc['account_type'] != 'CMA'}
    for h in holdings:
        acc_id = h['account_id']
        if acc_id not in planned_holdings: continue
        aid = str(h['asset_id'])
        planned_holdings[acc_id][aid] = planned_holdings[acc_id].get(aid, 0) + h['quantity']
        
    # Subtract sold quantities from planned holdings
    for t in trade_plan:
        if t["type"] == "SELL":
            acc_id = t["account_id"]
            if acc_id in planned_holdings:
                aid = str(t["asset_id"])
                planned_holdings[acc_id][aid] = max(0, planned_holdings[acc_id].get(aid, 0) - t["qty"])

    while True:
        best_aid = None
        best_acc = None
        best_qty = 0
        best_cost_local = 0
        best_cost_global = 0
        
        # In NEW_CASH, we want to buy even if shortfall < 0, to use up cash. Start from -inf.
        max_shortfall = -float('inf') if scenario == "NEW_CASH" else 0.0
        
        for aid, t in targets.items():
            price = t["price_krw"]
            if price <= 0: continue
            
            t_weight = next((a['target_weight'] for a in assets if str(a['id']) == aid), 0) / 100.0
            orig_target_val = total_portfolio_krw * t_weight
            
            planned_global_qty = sum(planned_holdings[acc_id].get(aid, 0) for acc_id in planned_holdings)
            target_qty_floored = math.floor(orig_target_val / price)
            
            if scenario != "NEW_CASH" and planned_global_qty >= target_qty_floored:
                continue
                
            planned_val = planned_global_qty * price
            shortfall = orig_target_val - planned_val
                
            if shortfall > max_shortfall:
                allowed_acc_ids = [str(x) for x in t.get("allowed_accounts", [])]
                valid_accounts = [acc for acc in sorted_accounts if str(acc['id']) in allowed_acc_ids and acc['account_type'] != 'CMA']
                
                can_buy = False
                for acc in valid_accounts:
                    acc_id = acc['id']
                    
                    acc_local = local_cash[acc_id]
                    acc_limit = remaining_limits[acc_id]
                    acc_global = min(global_cash, acc_limit) if acc_limit != float('inf') else global_cash
                    
                    max_shares_by_cash = math.floor((acc_local + acc_global) / price)
                    if max_shares_by_cash <= 0: continue
                    
                    max_shares_by_irp = float('inf')
                    if acc['account_type'] == 'IRP' and t['is_risk']:
                        irp_asset_val = sum(planned_holdings[acc_id].get(h_aid, 0) * targets[h_aid]["price_krw"] for h_aid in planned_holdings[acc_id] if h_aid in targets)
                        irp_risk_val = sum(planned_holdings[acc_id].get(h_aid, 0) * targets[h_aid]["price_krw"] for h_aid in planned_holdings[acc_id] if h_aid in targets and targets[h_aid]["is_risk"])
                        
                        allowed_cost_1 = (irp_asset_val + acc_local + acc_global) * 0.7 - irp_risk_val
                        allowed_cost_2 = (irp_asset_val * 0.7 - irp_risk_val) / 0.3 if (irp_asset_val * 0.7 - irp_risk_val) > 0 else 0
                        max_irp_cost = max(allowed_cost_1, allowed_cost_2)
                        max_shares_by_irp = math.floor(max_irp_cost / price) if max_irp_cost > 0 else 0
                        
                    max_shares = min(max_shares_by_cash, max_shares_by_irp)
                    
                    if shortfall > 0:
                        shares_for_shortfall = math.ceil(shortfall / price)
                        max_shares = min(max_shares, shares_for_shortfall)
                        
                    if max_shares > 0:
                        can_buy = True
                        cost = max_shares * price
                        cost_local = min(acc_local, cost)
                        cost_global = cost - cost_local
                        
                        max_shortfall = shortfall
                        best_aid = aid
                        best_acc = acc
                        best_qty = max_shares
                        best_cost_local = cost_local
                        best_cost_global = cost_global
                        break
                        
                if can_buy:
                    # Keep checking if another asset has an EVEN BIGGER shortfall, but we found a valid one
                    pass

        if best_aid is None:
            break
            
        local_cash[best_acc['id']] -= best_cost_local
        global_cash -= best_cost_global
        if remaining_limits[best_acc['id']] != float('inf'):
            remaining_limits[best_acc['id']] -= best_cost_global
            
        planned_holdings[best_acc['id']][best_aid] = planned_holdings[best_acc['id']].get(best_aid, 0) + best_qty
        
        found = False
        for tr in trade_plan:
            if tr['account_id'] == best_acc['id'] and tr['asset_id'] == best_aid and tr['type'] == 'BUY':
                tr['qty'] += best_qty
                tr['total_krw'] += (best_cost_local + best_cost_global)
                found = True
                break
        if not found:
            trade_plan.append({
                "account_id": best_acc['id'],
                "account_alias": best_acc['account_alias'],
                "asset_id": best_aid,
                "asset_name": next((a['name'] for a in assets if str(a['id']) == best_aid), "Unknown"),
                "type": "BUY",
                "qty": best_qty,
                "price": targets[best_aid]["price_krw"],
                "total_krw": best_cost_local + best_cost_global
            })

    # 6. Generate Transfer Plan
    transfer_plan = []
    
    # Calculate how much cash each account needs from outside to settle its trades
    # net_trade_flow = (total KRW spent on BUYS) - (total KRW received from SELLS)
    net_trade_flow = {acc['id']: 0.0 for acc in accounts}
    for t in trade_plan:
        acc_id = t["account_id"]
        if t["type"] == "BUY":
            net_trade_flow[acc_id] += t["total_krw"]
        else:
            net_trade_flow[acc_id] -= t["total_krw"]
            
    deposits_needed = {}
    surplus_available = {}
    
    for acc in accounts:
        acc_id = acc["id"]
        starting_cash = float(acc['deposit_krw'])
        flow = net_trade_flow[acc_id]
        
        if flow > starting_cash:
            deposits_needed[acc_id] = flow - starting_cash
        else:
            # This account has leftover cash
            surplus = starting_cash - flow
            if acc['account_type'] in ['종합매매', '금현물']:
                surplus_available[acc_id] = surplus
                
    total_deposits_needed = sum(deposits_needed.values())
    
    # Track how much new_cash is used
    new_cash_used = min(new_cash_krw, total_deposits_needed)
    internal_transfers_needed = max(0.0, total_deposits_needed - new_cash_used)
    
    # Generate Deposit Instructions
    for acc_id, amount in deposits_needed.items():
        if amount > 0:
            acc_alias = next(a['account_alias'] for a in accounts if a['id'] == acc_id)
            transfer_plan.append({
                "account_id": acc_id,
                "account_alias": acc_alias,
                "type": "DEPOSIT",
                "amount": amount,
                "msg": f"[{acc_alias}] 계좌로 {amount:,.0f}원 입금 (신규 투입 및 타 계좌 잉여금)"
            })
            
    # Generate Withdrawal Instructions from surplus accounts
    for acc_id, surplus in surplus_available.items():
        if internal_transfers_needed <= 0:
            break
        
        withdraw_amount = min(surplus, internal_transfers_needed)
        if withdraw_amount > 0:
            acc_alias = next(a['account_alias'] for a in accounts if a['id'] == acc_id)
            transfer_plan.append({
                "account_id": acc_id,
                "account_alias": acc_alias,
                "type": "WITHDRAW",
                "amount": withdraw_amount,
                "msg": f"[{acc_alias}] 계좌에서 {withdraw_amount:,.0f}원 출금 (타 계좌 매수 자금 지원용)"
            })
            internal_transfers_needed -= withdraw_amount
    # 7. Projected Assets
    simulated = []
    for a in assets:
        aid = str(a['id'])
        current_val = portfolio_assets.get(aid, {}).get('eval_amt_krw', 0.0)
        current_qty = portfolio_assets.get(aid, {}).get('qty', 0.0)
        
        qty_diff = 0.0
        for t in trade_plan:
            if str(t['asset_id']) == aid:
                if t['type'] == 'BUY':
                    current_val += t['total_krw']
                    qty_diff += t['qty']
                else:
                    current_val -= t['total_krw']
                    qty_diff -= t['qty']
                    
        simulated.append({
            "asset_id": aid,
            "asset_name": a['name'],
            "projected_val": current_val,
            "current_qty": current_qty,
            "qty_diff": qty_diff,
            "target_weight": a.get('target_weight', 0.0)
        })
        
    return trade_plan, transfer_plan, simulated, True, "리밸런싱 계산 완료"
