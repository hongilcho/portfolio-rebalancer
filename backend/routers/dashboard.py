import os
import math
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List

from data.data_manager import get_accounts, get_assets, get_holdings_by_account
from backend.services import market_service

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/summary")
def get_dashboard_summary():
    """
    포트폴리오 대시보드 종합 데이터 집계 API
    """
    accounts = get_accounts()
    assets = get_assets()
    
    usd_krw = market_service.get_usd_krw_rate()
    price_map = market_service.get_prices_map(assets)
    
    # 1. Account-level calculations
    account_summaries = []
    total_portfolio_eval = 0.0
    
    for acc in accounts:
        acc_id = str(acc['id'])
        acc_no = acc['account_no']
        acc_alias = acc['account_alias']
        acc_type = acc['account_type']
        
        dep_krw = float(acc.get('deposit_krw', 0.0))
        dep_usd = float(acc.get('deposit_usd', 0.0))
        dep_usd_krw = dep_usd * usd_krw
        total_deposit = dep_krw + dep_usd_krw
        
        acc_holdings = get_holdings_by_account(acc['id'])
        
        stock_eval = 0.0
        stock_buy_total = 0.0
        risk_stock_eval = 0.0
        safe_stock_eval = 0.0
        
        holding_details = []
        for h in acc_holdings:
            aid = str(h['asset_id'])
            qty = float(h['quantity'])
            avg_p_krw = float(h['avg_price'])
            curr_p = float(price_map.get(aid, avg_p_krw if avg_p_krw > 0 else 0))
            
            eval_val = qty * curr_p
            buy_amt = qty * avg_p_krw
            
            stock_eval += eval_val
            stock_buy_total += buy_amt
            
            if h.get('is_risk_asset', True):
                risk_stock_eval += eval_val
            else:
                safe_stock_eval += eval_val
                
            profit_krw = eval_val - buy_amt
            profit_pct = (profit_krw / buy_amt * 100) if buy_amt > 0 else 0.0
            
            is_gold = "금" in h.get('asset_name', '') or h.get('ticker') == 'M04020000'
            unit_str = "g" if is_gold else "주"
            
            holding_details.append({
                "asset_id": h['asset_id'],
                "asset_name": h['asset_name'],
                "ticker": h['ticker'],
                "market": h.get('market', 'KR'),
                "quantity": qty,
                "unit": unit_str,
                "avg_price": avg_p_krw,
                "current_price": curr_p,
                "eval_amount": eval_val,
                "buy_amount": buy_amt,
                "profit_krw": profit_krw,
                "profit_pct": profit_pct,
                "is_risk_asset": bool(h.get('is_risk_asset', True))
            })
            
        total_acc_val = total_deposit + stock_eval
        total_portfolio_eval += total_acc_val
        risk_pct = (risk_stock_eval / total_acc_val * 100) if total_acc_val > 0 else 0.0
        
        annual_limit = float(acc.get("annual_limit", 0.0))
        tax_limit = float(acc.get("tax_limit", 0.0))
        principal_val = stock_buy_total + dep_krw + dep_usd_krw
        
        annual_limit_pct = min(1.0, principal_val / annual_limit) if annual_limit > 0 else 0.0
        tax_limit_pct = min(1.0, principal_val / tax_limit) if tax_limit > 0 else 0.0
        
        acc_profit_krw = stock_eval - stock_buy_total
        acc_profit_pct = (acc_profit_krw / stock_buy_total * 100) if stock_buy_total > 0 else 0.0
        
        account_summaries.append({
            "id": acc_id,
            "account_no": acc_no,
            "account_alias": acc_alias,
            "account_type": acc_type,
            "deposit_krw": dep_krw,
            "deposit_usd": dep_usd,
            "total_deposit_krw": total_deposit,
            "stock_eval": stock_eval,
            "stock_buy_total": stock_buy_total,
            "total_val": total_acc_val,
            "profit_krw": acc_profit_krw,
            "profit_pct": acc_profit_pct,
            "risk_eval": risk_stock_eval,
            "safe_eval": safe_stock_eval,
            "risk_pct": risk_pct,
            "annual_limit": annual_limit,
            "tax_limit": tax_limit,
            "principal_val": principal_val,
            "annual_limit_pct": annual_limit_pct,
            "tax_limit_pct": tax_limit_pct,
            "priority": int(acc.get('priority', 99)),
            "limit_preference": acc.get('limit_preference', 'ANNUAL'),
            "holdings": holding_details
        })
        
    # 2. Portfolio-wide aggregated asset summary
    portfolio_assets = {}
    total_krw_cash = sum(float(a['deposit_krw']) for a in accounts)
    total_usd_cash = sum(float(a['deposit_usd']) for a in accounts)
    
    for acc in accounts:
        acc_holdings = get_holdings_by_account(acc['id'])
        for h in acc_holdings:
            aid = str(h['asset_id'])
            if aid not in portfolio_assets:
                portfolio_assets[aid] = {
                    "asset_id": aid,
                    "name": h['asset_name'],
                    "ticker": h['ticker'],
                    "market": h.get('market', 'KR'),
                    "is_risk_asset": bool(h.get('is_risk_asset', True)),
                    "quantity": 0.0,
                    "buy_amt_krw": 0.0,
                    "eval_amt_krw": 0.0,
                }
            qty = float(h['quantity'])
            avg_p_krw = float(h['avg_price'])
            curr_p = float(price_map.get(aid, avg_p_krw if avg_p_krw > 0 else 0))
            
            portfolio_assets[aid]['quantity'] += qty
            portfolio_assets[aid]['buy_amt_krw'] += qty * avg_p_krw
            portfolio_assets[aid]['eval_amt_krw'] += qty * curr_p

    total_stock_eval = sum(d['eval_amt_krw'] for d in portfolio_assets.values() if d['quantity'] > 0)
    total_stock_buy = sum(d['buy_amt_krw'] for d in portfolio_assets.values() if d['quantity'] > 0)
    total_stock_profit = total_stock_eval - total_stock_buy
    total_stock_return = (total_stock_profit / total_stock_buy * 100) if total_stock_buy > 0 else 0.0
    
    target_weight_map = {str(a['id']): float(a.get('target_weight', 0.0)) for a in assets}
    
    stock_summary_rows = []
    max_drift_abs = 0.0
    
    for a in assets:
        aid = str(a['id'])
        data = portfolio_assets.get(aid, {
            "asset_id": aid,
            "name": a['name'],
            "ticker": a['ticker'],
            "market": a['market'],
            "is_risk_asset": bool(a.get('is_risk_asset', True)),
            "quantity": 0.0,
            "buy_amt_krw": 0.0,
            "eval_amt_krw": 0.0
        })
        
        profit_krw = data['eval_amt_krw'] - data['buy_amt_krw']
        profit_pct = (profit_krw / data['buy_amt_krw'] * 100) if data['buy_amt_krw'] > 0 else 0.0
        
        weight_pct = (data['eval_amt_krw'] / total_stock_eval * 100) if total_stock_eval > 0 else 0.0
        target_w = target_weight_map.get(aid, 0.0)
        drift_pct = weight_pct - target_w
        
        if abs(drift_pct) > max_drift_abs:
            max_drift_abs = abs(drift_pct)
            
        is_gold = "금" in data['name'] or data.get('ticker') == 'M04020000'
        unit_str = "g" if is_gold else "주"
        
        stock_summary_rows.append({
            "asset_id": aid,
            "name": data['name'],
            "ticker": data['ticker'],
            "market": data['market'],
            "is_risk_asset": data['is_risk_asset'],
            "quantity": data['quantity'],
            "unit": unit_str,
            "avg_price": (data['buy_amt_krw'] / data['quantity']) if data['quantity'] > 0 else 0.0,
            "current_price": float(price_map.get(aid, 0.0)),
            "eval_amount": data['eval_amt_krw'],
            "buy_amount": data['buy_amt_krw'],
            "profit_krw": profit_krw,
            "profit_pct": profit_pct,
            "weight_pct": weight_pct,
            "target_weight_pct": target_w,
            "drift_pct": drift_pct
        })
        
    stock_summary_rows.sort(key=lambda x: x['weight_pct'], reverse=True)
    
    scale_max = round(max_drift_abs * 3.5, 1) if max_drift_abs > 0 else 1.0
    
    cash_summary = {
        "krw_cash": total_krw_cash,
        "usd_cash": total_usd_cash,
        "usd_cash_krw": total_usd_cash * usd_krw,
        "total_cash_krw": total_krw_cash + (total_usd_cash * usd_krw)
    }
    
    return {
        "kpi": {
            "total_stock_buy": total_stock_buy,
            "total_stock_eval": total_stock_eval,
            "total_stock_profit": total_stock_profit,
            "total_stock_return": total_stock_return,
            "total_portfolio_eval": total_portfolio_eval
        },
        "stock_assets": stock_summary_rows,
        "cash_assets": cash_summary,
        "accounts": account_summaries,
        "account_summaries": account_summaries,
        "drift_scale_max": scale_max,
        "usd_krw": usd_krw,
        "rate_source": market_service.rate_source
    }
