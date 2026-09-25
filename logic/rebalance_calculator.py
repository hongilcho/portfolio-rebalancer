"""
포트폴리오 리밸런싱 계산 엔진 (Rebalance Calculator)
=====================================================
사용자가 설정한 목표 비중(Target Weight)과 현재 자산 평가액을 비교하여,
최적의 매매 계획(Trade Plan)과 계좌 간 현금 이체 계획(Transfer Plan)을 도출합니다.

주요 특징 및 제약조건:
1. 3가지 리밸런싱 시나리오:
   - NEW_CASH: 신규 자금 투입 시 매도 없이 매수만으로 목표 비중에 최대한 근접
   - DRIFT: 현재 비중과 목표 비중 간 괴리율이 임계치(기본 5%)를 초과한 자산이 있을 때만 트리거
   - PERIODIC: 정기 리밸런싱 (비중 초과분 매도 후 부족분 매수)
2. 절세 계좌 우선순위 매칭:
   - 매수: 사용자 지정 우선순위(priority 낮은 번호 우선: 예: 연금/ISA 우선 매수)
   - 매도: 일반과세 계좌 -> 절세 계좌 순 역순 매도 (비과세/과세이연 혜택 보호)
3. 연금 규정 및 특수 자산 보호:
   - IRP 계좌 위험자산(주식형 등) 비중 70% 한도 자동 검증 및 초과 매수 방지
   - 정기예금 등 매도 잠금(`lock_rebalance_sell=True`) 자산 매도 제외
4. 계좌 간 자금 이동 최적화:
   - 매매 체결 후 각 계좌의 예수금 과부족을 정밀 계산하여 이체 지시서(`transfer_plan`) 생성
"""

import math
import copy
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
    포트폴리오 리밸런싱 알고리즘을 수행하여 최적의 매매 및 현금 이체 계획을 산출합니다.

    Args:
        assets (List[dict]): 자산 마스터 목록 (목표비중, 허용계좌, 위험자산여부, 매도잠금여부 등)
        portfolio_assets (Dict[str, dict]): 자산 ID별 현재 보유수량 및 원화 평가금액 집계
        accounts (List[dict]): 계좌 마스터 목록 (우선순위, 계좌유형, 보유예수금, 납입한도 등)
        holdings (List[dict]): 계좌별 실제 보유 종목 및 수량, 평균단가 목록
        price_map (Dict[str, float]): 자산 ID별 원화 실시간 시세 매핑
        total_krw_cash (float): 포트폴리오 내 모든 계좌의 원화 환산 현금 총액
        usd_krw_rate (float): 달러-원 기준 환율
        scenario (str): 리밸런싱 시나리오 ("NEW_CASH", "DRIFT", "PERIODIC")
        new_cash_krw (float): 신규 투입 현금 (NEW_CASH 시나리오 시 필수)
        drift_threshold (float): 허용 괴리율 임계치 (%) (DRIFT 시나리오 시 기준값)

    Returns:
        Tuple[List[dict], List[dict], List[dict], bool, str]:
            - trade_plan: 계좌별 매매 계획 리스트 (계좌, 종목, 매수/매도, 수량, 단가, 예상손익 등)
            - transfer_plan: 계좌 간 현금 입출금 이체 지시서 리스트
            - simulated_assets: 리밸런싱 완료 후 자산별 예상 비중 및 평가액 시뮬레이션
            - success: 리밸런싱 계산 성공 여부 (bool)
            - msg: 상태 및 안내 메시지 (str)
    """
    # Normalize price_map keys to string to prevent lookup failures
    price_map = {str(k): float(v) for k, v in price_map.items()}

    # 1. Total Current Value
    rebalance_assets = [a for a in assets if a.get('include_in_rebalance', True)]
    rebalance_asset_ids = {str(a['id']) for a in rebalance_assets}
    
    rebalance_asset_krw = sum(d['eval_amt_krw'] for aid, d in portfolio_assets.items() if str(aid) in rebalance_asset_ids)
    total_cash_krw = total_krw_cash + new_cash_krw
    
    total_rebalance_portfolio_krw = rebalance_asset_krw + total_cash_krw
    if total_rebalance_portfolio_krw <= 0:
        return [], [], [], False, "리밸런싱 대상 포트폴리오 총액이 0원입니다."

    # Sort accounts by user priority (lowest number = highest priority)
    # Default to 99 if not set.
    sorted_accounts = copy.deepcopy(sorted(accounts, key=lambda x: int(x.get('priority', 99))))
    
    # 2. Check Drift Condition (if scenario == "DRIFT")
    if scenario == "DRIFT":
        needs_rebalance = False
        for aid in rebalance_asset_ids:
            data = portfolio_assets.get(aid, {'eval_amt_krw': 0.0})
            current_w = (data['eval_amt_krw'] / rebalance_asset_krw * 100) if rebalance_asset_krw > 0 else 0
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
        current_qty = portfolio_assets.get(aid, {}).get('qty', 0)
        current_price = price_map.get(aid, 0.0)
        current_price_krw = current_price
        
        inc_rebalance = bool(a.get('include_in_rebalance', True))
        if not inc_rebalance:
            targets[aid] = {
                "target_qty": current_qty,
                "diff_qty": 0,
                "current_qty": current_qty,
                "price": current_price,
                "price_krw": current_price_krw,
                "is_risk": a['is_risk_asset'],
                "allowed_accounts": a.get('allowed_accounts', []),
                "include_in_rebalance": False
            }
            continue

        t_weight = a.get('target_weight', 0) / 100.0
        t_value = total_rebalance_portfolio_krw * t_weight

        if current_price_krw > 0:
            target_qty = math.floor(t_value / current_price_krw)
        else:
            target_qty = current_qty

        diff_qty = target_qty - current_qty

        # Scenario constraint
        if scenario == "NEW_CASH" and diff_qty < 0:
            diff_qty = 0 # No selling allowed

        # Deposit lock constraint: locked deposits are excluded from rebalance selling
        is_deposit = bool(a.get('is_deposit', False))
        lock_sell = bool(a.get('lock_rebalance_sell', True) if a.get('lock_rebalance_sell') is not None else True)
        if is_deposit and lock_sell and diff_qty < 0:
            diff_qty = 0

        targets[aid] = {
            "target_qty": target_qty,
            "diff_qty": diff_qty,
            "current_qty": current_qty,
            "price": current_price,
            "price_krw": current_price_krw,
            "is_risk": a['is_risk_asset'],
            "allowed_accounts": a.get('allowed_accounts', []),
            "include_in_rebalance": True
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
                    acc_avg_price = acc_holdings[0].get('avg_price', 0.0) if acc_holdings else 0.0
                    cost_basis = sell_amt * acc_avg_price
                    total_krw = sell_amt * t_data["price"]
                    realized_profit_krw = total_krw - cost_basis
                    realized_profit_pct = ((t_data["price"] - acc_avg_price) / acc_avg_price * 100.0) if acc_avg_price > 0 else 0.0

                    trade_plan.append({
                        "account_id": acc['id'],
                        "account_alias": acc['account_alias'],
                        "asset_id": aid,
                        "asset_name": next(a['name'] for a in assets if str(a['id']) == aid),
                        "type": "SELL",
                        "qty": sell_amt,
                        "price": t_data["price"],
                        "avg_price": acc_avg_price,
                        "cost_basis_krw": cost_basis,
                        "total_krw": total_krw,
                        "realized_profit_krw": realized_profit_krw,
                        "realized_profit_pct": realized_profit_pct
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
            if not t.get("include_in_rebalance", True):
                continue
            price = t["price_krw"]
            if price <= 0: continue
            
            t_weight = next((a['target_weight'] for a in assets if str(a['id']) == aid), 0) / 100.0
            orig_target_val = total_rebalance_portfolio_krw * t_weight
            
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
            "target_weight": a.get('target_weight', 0.0) if a.get('include_in_rebalance', True) else 0.0,
            "include_in_rebalance": bool(a.get('include_in_rebalance', True))
        })
        
    return trade_plan, transfer_plan, simulated, True, "리밸런싱 계산 완료"

def compute_realized_summary(trade_plan: List[dict]) -> dict:
    """
    리밸런싱 매도 계획(SELL)에 대한 예상 실현 손익 집계를 산출합니다.

    Args:
        trade_plan (List[dict]): 리밸런싱 매매 계획 목록

    Returns:
        dict: 매도 존재 여부, 매도 종목 수, 총 매도대금, 총 매입원가, 총 실현손익금, 총 수익률(%)
    """
    sell_trades = [t for t in trade_plan if t.get('type') == 'SELL']
    total_sell_amount = sum(float(t.get('total_krw', 0.0)) for t in sell_trades)
    total_cost_basis = sum(float(t.get('cost_basis_krw', 0.0)) for t in sell_trades)
    total_realized_profit = sum(float(t.get('realized_profit_krw', 0.0)) for t in sell_trades)
    total_realized_return_pct = ((total_realized_profit / total_cost_basis) * 100.0) if total_cost_basis > 0 else 0.0
    return {
        "has_sell": len(sell_trades) > 0,
        "sell_count": len(sell_trades),
        "total_sell_amount": total_sell_amount,
        "total_cost_basis": total_cost_basis,
        "total_realized_profit": total_realized_profit,
        "total_realized_return_pct": total_realized_return_pct
    }

