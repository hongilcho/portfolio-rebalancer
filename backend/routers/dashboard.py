"""
포트폴리오 대시보드 API 라우터 (Dashboard Router)
==================================================
단일 포트폴리오의 종합 자산 평가, 계좌별 잔고/수익률, 자산군별 비중,
목표 비중 대비 괴리율 현황을 고속으로 산출하여 제공합니다.

주요 특징:
1. 단일 번들 통신(/api/dashboard/bundle):
   - 프론트엔드가 대시보드를 그리기 위해 필요한 5가지 데이터(포트폴리오 목록, 대시보드 요약,
     자산 목록, 계좌 목록, 실시간 시세/환율)를 단 1회의 HTTP 요청으로 통합 반환하여 왕복 지연시간(RTT) 최소화.
2. PostgreSQL 1회 배치 쿼리:
   - `get_overview_batch_data()`를 통해 N+1 쿼리 문제를 원천 차단하고 0.05~0.1초 내 연산 완료.
"""

from fastapi import APIRouter
from typing import Dict, Any, List, Optional

from data.data_manager import get_overview_batch_data
from backend.services import market_service

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/bundle")
def get_dashboard_bundle(portfolio_id: str = "default", force_refresh: bool = False):
    """
    대시보드 초기 렌더링에 필요한 모든 데이터를 단 1회의 HTTP 요청으로 제공하는 통합 번들 API.

    Args:
        portfolio_id (str): 대상 포트폴리오 ID (기본값: 'default')
        force_refresh (bool): 시세 강제 새로고침 여부 (기본값: False)

    Returns:
        dict: portfolios, dashboard, assets, accounts, prices_data, usd_krw, rate_source
    """
    batch_data = get_overview_batch_data()
    portfolios = batch_data.get("portfolios", [])
    all_accounts = batch_data.get("accounts", [])
    all_assets = batch_data.get("assets", [])
    all_holdings = batch_data.get("holdings", [])

    p_accounts = [a for a in all_accounts if str(a.get("portfolio_id") or "default") == str(portfolio_id)]
    p_assets = [a for a in all_assets if str(a.get("portfolio_id") or "default") == str(portfolio_id)]

    prices, price_map = market_service.get_prices(force_refresh=force_refresh)
    usd_krw = market_service.usd_krw
    rate_source = market_service.rate_source

    dash = get_dashboard_summary(
        portfolio_id=portfolio_id,
        accounts=p_accounts,
        assets=p_assets,
        all_holdings=all_holdings,
        price_map=price_map,
        usd_krw=usd_krw
    )

    p_asset_ids = {str(a["id"]) for a in p_assets}
    p_prices = [p for p in prices if str(p["id"]) in p_asset_ids]

    return {
        "portfolios": portfolios,
        "dashboard": dash,
        "assets": p_assets,
        "accounts": p_accounts,
        "prices_data": {
            "prices": p_prices,
            "price_map": price_map,
            "usd_krw": usd_krw,
            "rate_source": rate_source
        },
        "usd_krw": usd_krw,
        "rate_source": rate_source
    }

@router.get("/summary")
def get_dashboard_summary(
    portfolio_id: str = "default",
    accounts: Optional[List[Dict[str, Any]]] = None,
    assets: Optional[List[Dict[str, Any]]] = None,
    all_holdings: Optional[List[Dict[str, Any]]] = None,
    price_map: Optional[Dict[str, float]] = None,
    usd_krw: Optional[float] = None
):
    """
    포트폴리오 대시보드 종합 데이터 집계 API (portfolio_id 기준 필터링)
    - accounts, assets, all_holdings, price_map, usd_krw 전달 시 DB 재조회 없이 인메모리 고속 연산 수행
    - 파라미터 미전달 시 단 1회의 PostgreSQL 배치 조회로 0.1초 내 연산 완료
    """
    if accounts is None or assets is None or all_holdings is None:
        batch_data = get_overview_batch_data()
        all_accounts = batch_data.get("accounts", [])
        all_assets = batch_data.get("assets", [])
        if all_holdings is None:
            all_holdings = batch_data.get("holdings", [])
        if accounts is None:
            accounts = [a for a in all_accounts if str(a.get("portfolio_id") or "default") == str(portfolio_id)]
        if assets is None:
            assets = [a for a in all_assets if str(a.get("portfolio_id") or "default") == str(portfolio_id)]
    
    price_data = None
    if price_map is None:
        price_data, price_map = market_service.get_prices()
    else:
        price_data = market_service.price_data or []
    if usd_krw is None:
        usd_krw = market_service.usd_krw

    price_usd_map = {str(item['id']): float(item.get('price_usd') or 0.0) for item in (price_data or [])}

    holdings_by_acc: Dict[str, List[Dict[str, Any]]] = {}
    for h in all_holdings:
        holdings_by_acc.setdefault(str(h['account_id']), []).append(h)
    
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
        
        acc_holdings = holdings_by_acc.get(acc_id, [])
        
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
            
            is_deposit = bool(h.get('is_deposit', False))
            is_gold = "금" in h.get('asset_name', '') or h.get('ticker') == 'M04020000'
            unit_str = "건" if is_deposit else ("g" if is_gold else "주")
            
            is_us = (h.get('market') == 'US')
            curr_p_usd = float(price_usd_map.get(aid, 0.0))
            if curr_p_usd <= 0 and usd_krw and usd_krw > 0:
                curr_p_usd = curr_p / usd_krw
            avg_p_usd = (avg_p_krw / usd_krw) if (usd_krw and usd_krw > 0) else 0.0
            eval_val_usd = qty * curr_p_usd
            buy_amt_usd = qty * avg_p_usd
            profit_usd = eval_val_usd - buy_amt_usd
            profit_pct_usd = (profit_usd / buy_amt_usd * 100) if buy_amt_usd > 0 else 0.0

            holding_details.append({
                "asset_id": h['asset_id'],
                "asset_name": h['asset_name'],
                "ticker": h['ticker'],
                "market": h.get('market', 'KR'),
                "is_us": is_us,
                "quantity": qty,
                "unit": unit_str,
                "avg_price": avg_p_krw,
                "current_price": curr_p,
                "eval_amount": eval_val,
                "buy_amount": buy_amt,
                "profit_krw": profit_krw,
                "profit_pct": profit_pct,
                "avg_price_usd": round(avg_p_usd, 2) if is_us else 0.0,
                "current_price_usd": round(curr_p_usd, 2) if is_us else 0.0,
                "eval_amount_usd": round(eval_val_usd, 2) if is_us else 0.0,
                "buy_amount_usd": round(buy_amt_usd, 2) if is_us else 0.0,
                "profit_usd": round(profit_usd, 2) if is_us else 0.0,
                "profit_pct_usd": round(profit_pct_usd, 2) if is_us else 0.0,
                "is_risk_asset": bool(h.get('is_risk_asset', True)),
                "is_deposit": is_deposit,
                "deposit_principal": float(h.get('deposit_principal') or 0.0),
                "interest_rate": float(h.get('interest_rate') or 0.0),
                "start_date": h.get('start_date', ''),
                "maturity_date": h.get('maturity_date', ''),
                "tax_rate": float(h.get('tax_rate') if h.get('tax_rate') is not None else 15.4),
                "lock_rebalance_sell": bool(h.get('lock_rebalance_sell', True) if h.get('lock_rebalance_sell') is not None else True)
            })
            
        total_acc_val = total_deposit + stock_eval
        total_portfolio_eval += total_acc_val
        risk_pct = (risk_stock_eval / total_acc_val * 100) if total_acc_val > 0 else 0.0
        
        annual_limit = float(acc.get("annual_limit", 0.0))
        tax_limit = float(acc.get("tax_limit", 0.0))
        principal_val = stock_buy_total + dep_krw + dep_usd_krw
        is_limit_exhausted = bool(acc.get("is_limit_exhausted", False))
        
        raw_annual_pct = min(1.0, principal_val / annual_limit) if annual_limit > 0 else 0.0
        raw_tax_pct = min(1.0, principal_val / tax_limit) if tax_limit > 0 else 0.0
        
        annual_limit_pct = 1.0 if is_limit_exhausted else raw_annual_pct
        tax_limit_pct = 1.0 if is_limit_exhausted else raw_tax_pct
        can_exhaust_limit = bool((annual_limit > 0 and raw_annual_pct >= 0.96) or (tax_limit > 0 and raw_tax_pct >= 0.96) or is_limit_exhausted)
        
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
            "is_limit_exhausted": is_limit_exhausted,
            "can_exhaust_limit": can_exhaust_limit,
            "priority": int(acc.get('priority', 99)),
            "limit_preference": acc.get('limit_preference', 'ANNUAL'),
            "holdings": holding_details
        })
        
    # 2. Portfolio-wide aggregated asset summary
    asset_dict_by_id = {str(a['id']): a for a in assets}
    portfolio_assets = {}
    total_krw_cash = sum(float(a['deposit_krw']) for a in accounts)
    total_usd_cash = sum(float(a['deposit_usd']) for a in accounts)
    
    for acc in accounts:
        acc_holdings = holdings_by_acc.get(str(acc['id']), [])
        for h in acc_holdings:
            aid = str(h['asset_id'])
            asset_meta = asset_dict_by_id.get(aid, {})
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
                    "include_in_rebalance": bool(asset_meta.get('include_in_rebalance', True))
                }
            qty = float(h['quantity'])
            avg_p_krw = float(h['avg_price'])
            curr_p = float(price_map.get(aid, 0.0))
            if curr_p <= 0:
                curr_p = avg_p_krw if avg_p_krw > 0 else 0.0
            
            portfolio_assets[aid]['quantity'] += qty
            portfolio_assets[aid]['buy_amt_krw'] += qty * avg_p_krw
            portfolio_assets[aid]['eval_amt_krw'] += qty * curr_p

    # Add pure deposit assets directly from assets table
    for a in assets:
        if a.get('is_deposit'):
            aid = str(a['id'])
            principal = float(a.get('deposit_principal') or 0.0)
            if principal > 0:
                curr_p = float(price_map.get(aid, principal))
                portfolio_assets[aid] = {
                    "asset_id": aid,
                    "name": a['name'],
                    "ticker": a.get('ticker') or a['name'],
                    "market": a.get('market', 'KR'),
                    "is_risk_asset": False,
                    "quantity": 1.0,
                    "buy_amt_krw": principal,
                    "eval_amt_krw": curr_p,
                    "is_deposit": True,
                    "account_no": a.get('account_no', ''),
                    "maturity_date": a.get('maturity_date', ''),
                    "interest_rate": float(a.get('interest_rate') or 0.0),
                    "include_in_rebalance": bool(a.get('include_in_rebalance', True))
                }

    total_stock_eval = sum(d['eval_amt_krw'] for d in portfolio_assets.values() if d['quantity'] > 0)
    rebalance_stock_eval = sum(d['eval_amt_krw'] for d in portfolio_assets.values() if d['quantity'] > 0 and d.get('include_in_rebalance', True))
    total_stock_buy = sum(d['buy_amt_krw'] for d in portfolio_assets.values() if d['quantity'] > 0)
    total_stock_profit = total_stock_eval - total_stock_buy
    total_stock_return = (total_stock_profit / total_stock_buy * 100) if total_stock_buy > 0 else 0.0
    total_portfolio_eval = total_krw_cash + (total_usd_cash * usd_krw) + total_stock_eval

    target_weight_map = {str(a['id']): float(a.get('target_weight', 0.0)) for a in assets}
    
    stock_summary_rows = []
    max_drift_abs = 0.0
    
    for a in assets:
        aid = str(a['id'])
        is_active = a.get('is_active', True)
        include_in_rebal = bool(a.get('include_in_rebalance', True))
        data = portfolio_assets.get(aid, {
            "asset_id": aid,
            "name": a['name'],
            "ticker": a['ticker'],
            "market": a['market'],
            "is_risk_asset": bool(a.get('is_risk_asset', True)),
            "quantity": 0.0,
            "buy_amt_krw": 0.0,
            "eval_amt_krw": 0.0,
            "include_in_rebalance": include_in_rebal
        })
        
        # If asset is inactive and has no holdings, do not display in Dashboard Tab 1
        if not is_active and data['quantity'] <= 0:
            continue
        
        profit_krw = data['eval_amt_krw'] - data['buy_amt_krw']
        profit_pct = (profit_krw / data['buy_amt_krw'] * 100) if data['buy_amt_krw'] > 0 else 0.0
        
        if include_in_rebal:
            weight_pct = (data['eval_amt_krw'] / rebalance_stock_eval * 100) if rebalance_stock_eval > 0 else 0.0
            target_w = target_weight_map.get(aid, 0.0)
            drift_pct = weight_pct - target_w
            if abs(drift_pct) > max_drift_abs:
                max_drift_abs = abs(drift_pct)
        else:
            weight_pct = 0.0
            target_w = 0.0
            drift_pct = 0.0
            
        is_deposit = bool(a.get('is_deposit', False))
        is_gold = "금" in data['name'] or data.get('ticker') == 'M04020000'
        unit_str = "건" if is_deposit else ("g" if is_gold else "주")
        
        calc_avg_price = (data['buy_amt_krw'] / data['quantity']) if data['quantity'] > 0 else 0.0
        curr_price_val = float(price_map.get(aid, 0.0))
        if curr_price_val <= 0:
            curr_price_val = calc_avg_price
            
        # USD metrics
        is_us = (data.get('market') == 'US')
        curr_price_usd = float(price_usd_map.get(aid, 0.0))
        if curr_price_usd <= 0 and usd_krw and usd_krw > 0:
            curr_price_usd = curr_price_val / usd_krw
        avg_price_usd = (calc_avg_price / usd_krw) if (usd_krw and usd_krw > 0) else 0.0
        eval_amount_usd = data['quantity'] * curr_price_usd
        buy_amount_usd = data['quantity'] * avg_price_usd
        profit_usd = eval_amount_usd - buy_amount_usd
        profit_pct_usd = (profit_usd / buy_amount_usd * 100) if buy_amount_usd > 0 else 0.0

        stock_summary_rows.append({
            "asset_id": aid,
            "name": data['name'],
            "ticker": data['ticker'],
            "market": data['market'],
            "is_us": is_us,
            "is_risk_asset": data['is_risk_asset'],
            "quantity": data['quantity'],
            "unit": unit_str,
            "avg_price": calc_avg_price,
            "current_price": curr_price_val,
            "eval_amount": data['eval_amt_krw'],
            "buy_amount": data['buy_amt_krw'],
            "profit_krw": profit_krw,
            "profit_pct": profit_pct,
            "avg_price_usd": round(avg_price_usd, 2) if is_us else 0.0,
            "current_price_usd": round(curr_price_usd, 2) if is_us else 0.0,
            "eval_amount_usd": round(eval_amount_usd, 2) if is_us else 0.0,
            "buy_amount_usd": round(buy_amount_usd, 2) if is_us else 0.0,
            "profit_usd": round(profit_usd, 2) if is_us else 0.0,
            "profit_pct_usd": round(profit_pct_usd, 2) if is_us else 0.0,
            "weight_pct": weight_pct,
            "target_weight_pct": target_w,
            "drift_pct": drift_pct,
            "include_in_rebalance": include_in_rebal,
            "is_deposit": is_deposit,
            "deposit_principal": float(a.get('deposit_principal') or 0.0),
            "interest_rate": float(a.get('interest_rate') or 0.0),
            "start_date": a.get('start_date', ''),
            "maturity_date": a.get('maturity_date', ''),
            "tax_rate": float(a.get('tax_rate') if a.get('tax_rate') is not None else 15.4),
            "lock_rebalance_sell": bool(a.get('lock_rebalance_sell', True) if a.get('lock_rebalance_sell') is not None else True),
            "account_no": a.get('account_no', '')
        })
        
    stock_summary_rows.sort(key=lambda x: (not x['include_in_rebalance'], -x['weight_pct'], -x['eval_amount']))
    
    scale_max = round(max_drift_abs * 3.5, 1) if max_drift_abs > 0 else 1.0
    
    cash_summary = {
        "krw_cash": total_krw_cash,
        "usd_cash": total_usd_cash,
        "usd_cash_krw": total_usd_cash * usd_krw,
        "total_cash_krw": total_krw_cash + (total_usd_cash * usd_krw)
    }

    # Dual currency KPI aggregations
    us_stock_rows = [r for r in stock_summary_rows if r.get('market') == 'US' and r.get('quantity', 0) > 0]
    total_stock_eval_usd = sum(r['eval_amount_usd'] for r in us_stock_rows)
    total_stock_buy_usd = sum(r['buy_amount_usd'] for r in us_stock_rows)
    total_stock_profit_usd = total_stock_eval_usd - total_stock_buy_usd
    total_stock_return_usd = (total_stock_profit_usd / total_stock_buy_usd * 100) if total_stock_buy_usd > 0 else 0.0
    
    kr_stock_rows = [r for r in stock_summary_rows if r.get('market') != 'US' and r.get('quantity', 0) > 0]
    total_stock_eval_krw_only = sum(r['eval_amount'] for r in kr_stock_rows)
    total_stock_buy_krw_only = sum(r['buy_amount'] for r in kr_stock_rows)
    total_stock_profit_krw_only = total_stock_eval_krw_only - total_stock_buy_krw_only
    total_stock_return_krw_only = (total_stock_profit_krw_only / total_stock_buy_krw_only * 100) if total_stock_buy_krw_only > 0 else 0.0
    
    return {
        "kpi": {
            "total_stock_buy": total_stock_buy,
            "total_stock_eval": total_stock_eval,
            "rebalance_stock_eval": rebalance_stock_eval,
            "total_stock_profit": total_stock_profit,
            "total_stock_return": total_stock_return,
            "total_portfolio_eval": total_portfolio_eval,
            "usd_summary": {
                "stock_eval_usd": round(total_stock_eval_usd, 2),
                "stock_buy_usd": round(total_stock_buy_usd, 2),
                "stock_profit_usd": round(total_stock_profit_usd, 2),
                "stock_return_usd": round(total_stock_return_usd, 2),
                "cash_usd": round(total_usd_cash, 2),
                "total_eval_usd": round(total_stock_eval_usd + total_usd_cash, 2),
                "total_buy_usd": round(total_stock_buy_usd + total_usd_cash, 2)
            },
            "krw_summary": {
                "stock_eval_krw": round(total_stock_eval_krw_only, 0),
                "stock_buy_krw": round(total_stock_buy_krw_only, 0),
                "stock_profit_krw": round(total_stock_profit_krw_only, 0),
                "stock_return_krw": round(total_stock_return_krw_only, 2),
                "cash_krw": round(total_krw_cash, 0),
                "total_eval_krw": round(total_stock_eval_krw_only + total_krw_cash, 0),
                "total_buy_krw": round(total_stock_buy_krw_only + total_krw_cash, 0)
            }
        },
        "stock_assets": stock_summary_rows,
        "cash_assets": cash_summary,
        "accounts": account_summaries,
        "account_summaries": account_summaries,
        "drift_scale_max": scale_max,
        "usd_krw": usd_krw,
        "rate_source": market_service.rate_source
    }
