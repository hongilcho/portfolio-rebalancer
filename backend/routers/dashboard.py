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
from logic.dividend_fetcher import calculate_adjusted_holding_prices

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
    all_trades = batch_data.get("trade_history", [])

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
        usd_krw=usd_krw,
        price_data=prices,
        all_trades=all_trades
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
    usd_krw: Optional[float] = None,
    all_trades: Optional[List[Dict[str, Any]]] = None,
    price_data: Optional[List[Dict[str, Any]]] = None
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
        if all_trades is None:
            all_trades = batch_data.get("trade_history", [])
        if accounts is None:
            accounts = [a for a in all_accounts if str(a.get("portfolio_id") or "default") == str(portfolio_id)]
        if assets is None:
            assets = [a for a in all_assets if str(a.get("portfolio_id") or "default") == str(portfolio_id)]
    
    if price_map is None:
        price_data, price_map = market_service.get_prices()
    elif price_data is None:
        price_data = market_service.price_data or []
    if usd_krw is None:
        usd_krw = market_service.usd_krw

    price_usd_map = {str(item['id']): float(item.get('price_usd') or 0.0) for item in (price_data or [])}

    trades_by_holding: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    if all_trades:
        for t in all_trades:
            trades_by_holding.setdefault((str(t.get('account_id', '')), str(t.get('asset_id', ''))), []).append(t)

    holdings_by_acc: Dict[str, List[Dict[str, Any]]] = {}
    for h in all_holdings:
        holdings_by_acc.setdefault(str(h['account_id']), []).append(h)
    
    # 1. Account-level calculations
    asset_dict_by_id = {str(a['id']): a for a in assets}
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
            asset_meta = asset_dict_by_id.get(aid, {})
            qty = float(h['quantity'])
            h_trades = trades_by_holding.get((acc_id, aid))

            # 배당금 단가 차감 (Adjusted Cost Basis) 계산 (계좌 과세유형별 세후 배당 반영 및 정밀 시계열 수량 추적)
            adj_info = calculate_adjusted_holding_prices(h, asset_meta, usd_krw, account_type=acc_type, trades=h_trades)
            avg_p_krw = adj_info["avg_price"]
            curr_p = float(price_map.get(aid, avg_p_krw if avg_p_krw > 0 else 0))
            
            eval_val = qty * curr_p
            buy_amt = qty * avg_p_krw
            
            stock_eval += eval_val
            stock_buy_total += buy_amt
            
            if h.get('is_risk_asset', True):
                risk_stock_eval += eval_val
            else:
                safe_stock_eval += eval_val
                
            eval_profit_krw = eval_val - buy_amt
            eval_profit_pct = (eval_profit_krw / buy_amt * 100) if buy_amt > 0 else 0.0
            
            is_deposit = bool(h.get('is_deposit', False))
            is_gold = "금" in h.get('asset_name', '') or h.get('ticker') == 'M04020000'
            unit_str = "건" if is_deposit else ("g" if is_gold else "주")
            
            is_us = (h.get('market') == 'US')
            curr_p_usd = float(price_usd_map.get(aid, 0.0))
            if curr_p_usd <= 0 and usd_krw and usd_krw > 0:
                curr_p_usd = curr_p / usd_krw

            if is_us:
                avg_p_usd = adj_info["avg_price_usd"]
            else:
                avg_p_usd = 0.0

            eval_val_usd = qty * curr_p_usd
            buy_amt_usd = qty * avg_p_usd
            eval_profit_usd = eval_val_usd - buy_amt_usd
            eval_profit_pct_usd = (eval_profit_usd / buy_amt_usd * 100) if buy_amt_usd > 0 else 0.0

            # 배당금 집계 (Total Return - 정밀 시계열 수량 기반)
            if "total_dividend_profit" in adj_info:
                if is_us:
                    div_profit_usd = float(adj_info["total_dividend_profit"])
                    div_profit_krw = div_profit_usd * usd_krw
                else:
                    div_profit_krw = float(adj_info["total_dividend_profit"])
                    div_profit_usd = (div_profit_krw / usd_krw) if usd_krw > 0 else 0.0
            else:
                cum_div_unit = float(adj_info.get("cumulative_dividend", 0.0))
                if is_us:
                    div_profit_usd = qty * cum_div_unit
                    div_profit_krw = div_profit_usd * usd_krw
                else:
                    div_profit_krw = qty * cum_div_unit
                    div_profit_usd = (div_profit_krw / usd_krw) if usd_krw > 0 else 0.0

            if is_us:
                total_profit_usd = eval_profit_usd + div_profit_usd
                total_profit_pct_usd = (total_profit_usd / buy_amt_usd * 100) if buy_amt_usd > 0 else 0.0
            else:
                total_profit_usd = 0.0
                total_profit_pct_usd = 0.0

            total_profit_krw = eval_profit_krw + div_profit_krw
            total_profit_pct = (total_profit_krw / buy_amt * 100) if buy_amt > 0 else 0.0

            # 매입환율 및 환차익/환차손 분해 계산
            buy_fx_rate = adj_info["buy_fx_rate"]

            if is_us:
                fx_profit_krw = buy_amt_usd * (usd_krw - buy_fx_rate)
                fx_profit_pct = ((usd_krw - buy_fx_rate) / buy_fx_rate * 100) if buy_fx_rate > 0 else 0.0
                pure_stock_profit_krw = eval_profit_usd * usd_krw
                pure_stock_profit_pct = eval_profit_pct_usd
            else:
                fx_profit_krw = 0.0
                fx_profit_pct = 0.0
                pure_stock_profit_krw = eval_profit_krw
                pure_stock_profit_pct = eval_profit_pct

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
                "profit_krw": round(total_profit_krw, 0),
                "profit_pct": total_profit_pct,
                "eval_profit_krw": round(eval_profit_krw, 0),
                "eval_profit_pct": round(eval_profit_pct, 2),
                "dividend_profit_krw": round(div_profit_krw, 0),
                "dividend_profit_usd": round(div_profit_usd, 2),
                "dividend_details": adj_info.get("dividend_details", []),
                "total_profit_krw": round(total_profit_krw, 0),
                "total_profit_pct": total_profit_pct,
                "avg_price_usd": round(avg_p_usd, 2) if is_us else 0.0,
                "current_price_usd": round(curr_p_usd, 2) if is_us else 0.0,
                "eval_amount_usd": round(eval_val_usd, 2) if is_us else 0.0,
                "buy_amount_usd": round(buy_amt_usd, 2) if is_us else 0.0,
                "profit_usd": round(total_profit_usd if is_us else 0.0, 2),
                "profit_pct_usd": total_profit_pct_usd if is_us else 0.0,
                "eval_profit_usd": round(eval_profit_usd, 2) if is_us else 0.0,
                "eval_profit_pct_usd": round(eval_profit_pct_usd, 2) if is_us else 0.0,
                "total_profit_usd": round(total_profit_usd, 2) if is_us else 0.0,
                "total_profit_pct_usd": total_profit_pct_usd if is_us else 0.0,
                "buy_fx_rate": round(buy_fx_rate, 2) if is_us else 0.0,
                "fx_profit_krw": round(fx_profit_krw, 0) if is_us else 0.0,
                "fx_profit_pct": round(fx_profit_pct, 2) if is_us else 0.0,
                "pure_stock_profit_krw": round(pure_stock_profit_krw, 0),
                "pure_stock_profit_pct": round(pure_stock_profit_pct, 2),
                "is_risk_asset": bool(h.get('is_risk_asset', True)),
                "is_deposit": is_deposit,
                "deposit_principal": float(h.get('deposit_principal') or 0.0),
                "interest_rate": float(h.get('interest_rate') or 0.0),
                "start_date": h.get('start_date', ''),
                "maturity_date": h.get('maturity_date', ''),
                "tax_rate": float(h.get('tax_rate') if h.get('tax_rate') is not None else 15.4),
                "lock_rebalance_sell": bool(h.get('lock_rebalance_sell', True) if h.get('lock_rebalance_sell') is not None else True),
                "is_dividend_cost_deduct": False,
                "original_avg_price": avg_p_krw,
                "original_avg_price_usd": avg_p_usd,
                "cumulative_dividend": adj_info["cumulative_dividend"],
                "gross_cumulative_dividend": adj_info.get("gross_cumulative_dividend", 0.0),
                "dividend_tax_rate": adj_info.get("tax_rate", 0.0),
                "dividend_tax_amount": adj_info.get("tax_amount", 0.0),
                "is_tax_deducted": adj_info.get("is_tax_deducted", False),
                "dividend_count": adj_info["dividend_count"],
                "first_buy_date": adj_info["first_buy_date"]
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
        
        acc_eval_profit_krw = stock_eval - stock_buy_total
        acc_eval_profit_pct = (acc_eval_profit_krw / stock_buy_total * 100) if stock_buy_total > 0 else 0.0
        acc_div_profit_krw = sum(h.get('dividend_profit_krw', 0.0) for h in holding_details)
        acc_total_profit_krw = acc_eval_profit_krw + acc_div_profit_krw
        acc_total_profit_pct = (acc_total_profit_krw / stock_buy_total * 100) if stock_buy_total > 0 else 0.0
        
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
            "profit_krw": acc_total_profit_krw,
            "profit_pct": acc_total_profit_pct,
            "eval_profit_krw": acc_eval_profit_krw,
            "eval_profit_pct": acc_eval_profit_pct,
            "dividend_profit_krw": acc_div_profit_krw,
            "total_profit_krw": acc_total_profit_krw,
            "total_profit_pct": acc_total_profit_pct,
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
            acc_type = acc.get('account_type', '')
            h_trades = trades_by_holding.get((str(acc['id']), aid))
            adj_info = calculate_adjusted_holding_prices(h, asset_meta, usd_krw, account_type=acc_type, trades=h_trades)
            avg_p_krw = adj_info["avg_price"]
            avg_p_usd = adj_info["avg_price_usd"]
            
            if aid not in portfolio_assets:
                portfolio_assets[aid] = {
                    "asset_id": aid,
                    "name": h['asset_name'],
                    "ticker": h['ticker'],
                    "market": h.get('market', 'KR'),
                    "is_risk_asset": bool(h.get('is_risk_asset', True)),
                    "quantity": 0.0,
                    "buy_amt_krw": 0.0,
                    "buy_amt_usd": 0.0,
                    "eval_amt_krw": 0.0,
                    "dividend_krw": 0.0,
                    "dividend_usd": 0.0,
                    "include_in_rebalance": bool(asset_meta.get('include_in_rebalance', True)),
                    "is_dividend_cost_deduct": False,
                    "original_avg_price": avg_p_krw,
                    "original_avg_price_usd": avg_p_usd,
                    "cumulative_dividend": adj_info["cumulative_dividend"],
                    "gross_cumulative_dividend": adj_info.get("gross_cumulative_dividend", 0.0),
                    "dividend_tax_rate": adj_info.get("tax_rate", 0.0),
                    "dividend_tax_amount": adj_info.get("tax_amount", 0.0),
                    "is_tax_deducted": adj_info.get("is_tax_deducted", False),
                    "dividend_count": adj_info["dividend_count"],
                    "first_buy_date": adj_info["first_buy_date"]
                }
            qty = float(h['quantity'])
            curr_p = float(price_map.get(aid, 0.0))
            if curr_p <= 0:
                curr_p = avg_p_krw if avg_p_krw > 0 else 0.0

            portfolio_assets[aid]['quantity'] += qty
            portfolio_assets[aid]['buy_amt_krw'] += qty * avg_p_krw
            portfolio_assets[aid]['buy_amt_usd'] += qty * avg_p_usd
            portfolio_assets[aid]['eval_amt_krw'] += qty * curr_p
            
            # 배당금 집계 (계좌별 세금 및 시계열 수량 반영 누적)
            is_us_h = (h.get('market') == 'US')
            if "total_dividend_profit" in adj_info:
                if is_us_h:
                    d_usd = float(adj_info["total_dividend_profit"])
                    d_krw = d_usd * usd_krw
                else:
                    d_krw = float(adj_info["total_dividend_profit"])
                    d_usd = (d_krw / usd_krw) if usd_krw > 0 else 0.0
            else:
                c_div = float(adj_info.get("cumulative_dividend", 0.0))
                if is_us_h:
                    d_usd = qty * c_div
                    d_krw = d_usd * usd_krw
                else:
                    d_krw = qty * c_div
                    d_usd = (d_krw / usd_krw) if usd_krw > 0 else 0.0

            portfolio_assets[aid]['dividend_usd'] += d_usd
            portfolio_assets[aid]['dividend_krw'] += d_krw

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
                    "dividend_krw": 0.0,
                    "dividend_usd": 0.0,
                    "is_deposit": True,
                    "account_no": a.get('account_no', ''),
                    "maturity_date": a.get('maturity_date', ''),
                    "interest_rate": float(a.get('interest_rate') or 0.0),
                    "include_in_rebalance": bool(a.get('include_in_rebalance', True))
                }

    total_stock_eval = sum(d['eval_amt_krw'] for d in portfolio_assets.values() if d['quantity'] > 0)
    rebalance_stock_eval = sum(d['eval_amt_krw'] for d in portfolio_assets.values() if d['quantity'] > 0 and d.get('include_in_rebalance', True))
    total_stock_buy = sum(d['buy_amt_krw'] for d in portfolio_assets.values() if d['quantity'] > 0)
    total_eval_profit = total_stock_eval - total_stock_buy
    total_dividend_profit = sum(d.get('dividend_krw', 0.0) for d in portfolio_assets.values() if d['quantity'] > 0)
    total_stock_profit = total_eval_profit + total_dividend_profit
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
        
        is_deposit = bool(a.get('is_deposit', False))
        
        # 1번 탭 대시보드 현황: 비활성화 종목 또는 실제 보유 수량이 0 이하인 자산(예금 제외)은 표에서 제외
        if not is_deposit and data['quantity'] <= 0:
            continue
        if not is_active:
            continue
        
        eval_profit_krw = data['eval_amt_krw'] - data['buy_amt_krw']
        eval_profit_pct = (eval_profit_krw / data['buy_amt_krw'] * 100) if data['buy_amt_krw'] > 0 else 0.0
        div_profit_krw = data.get('dividend_krw', 0.0)
        div_profit_usd = data.get('dividend_usd', 0.0)
        
        total_profit_krw = eval_profit_krw + div_profit_krw
        total_profit_pct = (total_profit_krw / data['buy_amt_krw'] * 100) if data['buy_amt_krw'] > 0 else 0.0
        
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
        
        if is_us and data.get('buy_amt_usd', 0.0) > 0:
            buy_amount_usd = data['buy_amt_usd']
            avg_price_usd = (buy_amount_usd / data['quantity']) if data['quantity'] > 0 else 0.0
            weighted_buy_fx = (data['buy_amt_krw'] / buy_amount_usd) if buy_amount_usd > 0 else usd_krw
        else:
            avg_price_usd = (calc_avg_price / usd_krw) if (usd_krw and usd_krw > 0) else 0.0
            buy_amount_usd = data['quantity'] * avg_price_usd
            weighted_buy_fx = usd_krw

        eval_amount_usd = data['quantity'] * curr_price_usd
        eval_profit_usd = eval_amount_usd - buy_amount_usd
        eval_profit_pct_usd = (eval_profit_usd / buy_amount_usd * 100) if buy_amount_usd > 0 else 0.0
        total_profit_usd = eval_profit_usd + div_profit_usd
        total_profit_pct_usd = (total_profit_usd / buy_amount_usd * 100) if buy_amount_usd > 0 else 0.0

        if is_us:
            fx_profit_krw = buy_amount_usd * (usd_krw - weighted_buy_fx)
            fx_profit_pct = ((usd_krw - weighted_buy_fx) / weighted_buy_fx * 100) if weighted_buy_fx > 0 else 0.0
            pure_stock_profit_krw = eval_profit_usd * usd_krw
            pure_stock_profit_pct = eval_profit_pct_usd
        else:
            fx_profit_krw = 0.0
            fx_profit_pct = 0.0
            pure_stock_profit_krw = eval_profit_krw
            pure_stock_profit_pct = eval_profit_pct

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
            "profit_krw": round(total_profit_krw, 0),
            "profit_pct": total_profit_pct,
            "eval_profit_krw": round(eval_profit_krw, 0),
            "eval_profit_pct": round(eval_profit_pct, 2),
            "dividend_profit_krw": round(div_profit_krw, 0),
            "dividend_profit_usd": round(div_profit_usd, 2),
            "total_profit_krw": round(total_profit_krw, 0),
            "total_profit_pct": total_profit_pct,
            "avg_price_usd": round(avg_price_usd, 2) if is_us else 0.0,
            "current_price_usd": round(curr_price_usd, 2) if is_us else 0.0,
            "eval_amount_usd": round(eval_amount_usd, 2) if is_us else 0.0,
            "buy_amount_usd": round(buy_amount_usd, 2) if is_us else 0.0,
            "profit_usd": round(total_profit_usd, 2) if is_us else 0.0,
            "profit_pct_usd": total_profit_pct_usd if is_us else 0.0,
            "eval_profit_usd": round(eval_profit_usd, 2) if is_us else 0.0,
            "eval_profit_pct_usd": round(eval_profit_pct_usd, 2) if is_us else 0.0,
            "total_profit_usd": round(total_profit_usd, 2) if is_us else 0.0,
            "total_profit_pct_usd": total_profit_pct_usd if is_us else 0.0,
            "buy_fx_rate": round(weighted_buy_fx, 2) if is_us else 0.0,
            "fx_profit_krw": round(fx_profit_krw, 0) if is_us else 0.0,
            "fx_profit_pct": round(fx_profit_pct, 2) if is_us else 0.0,
            "pure_stock_profit_krw": round(pure_stock_profit_krw, 0),
            "pure_stock_profit_pct": round(pure_stock_profit_pct, 2),
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
            "account_no": a.get('account_no', ''),
            "is_dividend_cost_deduct": False,
            "original_avg_price": calc_avg_price,
            "original_avg_price_usd": round(avg_price_usd, 2) if is_us else 0.0,
            "cumulative_dividend": data.get('cumulative_dividend', 0.0),
            "gross_cumulative_dividend": data.get('gross_cumulative_dividend', 0.0),
            "dividend_tax_rate": data.get('dividend_tax_rate', 0.0),
            "dividend_tax_amount": data.get('dividend_tax_amount', 0.0),
            "is_tax_deducted": bool(data.get('is_tax_deducted', False)),
            "dividend_count": data.get('dividend_count', 0),
            "first_buy_date": data.get('first_buy_date', '')
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
    total_dividend_usd = sum(r.get('dividend_profit_usd', 0.0) for r in us_stock_rows)
    total_stock_eval_profit_usd = total_stock_eval_usd - total_stock_buy_usd
    total_stock_eval_return_usd = (total_stock_eval_profit_usd / total_stock_buy_usd * 100) if total_stock_buy_usd > 0 else 0.0
    total_stock_profit_usd = total_stock_eval_profit_usd + total_dividend_usd
    total_stock_return_usd = (total_stock_profit_usd / total_stock_buy_usd * 100) if total_stock_buy_usd > 0 else 0.0
    
    total_fx_profit_krw = sum(r.get('fx_profit_krw', 0.0) for r in us_stock_rows)
    total_pure_stock_profit_krw = sum(r.get('pure_stock_profit_krw', 0.0) for r in us_stock_rows)
    weighted_buy_fx_rate = (sum(r['buy_amount'] for r in us_stock_rows) / total_stock_buy_usd) if total_stock_buy_usd > 0 else usd_krw
    total_fx_profit_pct = ((usd_krw - weighted_buy_fx_rate) / weighted_buy_fx_rate * 100) if weighted_buy_fx_rate > 0 else 0.0

    kr_stock_rows = [r for r in stock_summary_rows if r.get('market') != 'US' and r.get('quantity', 0) > 0]
    total_stock_eval_krw_only = sum(r['eval_amount'] for r in kr_stock_rows)
    total_stock_buy_krw_only = sum(r['buy_amount'] for r in kr_stock_rows)
    krw_dividend_krw = sum(r.get('dividend_profit_krw', 0.0) for r in kr_stock_rows)
    total_stock_eval_profit_krw_only = total_stock_eval_krw_only - total_stock_buy_krw_only
    total_stock_eval_return_krw_only = (total_stock_eval_profit_krw_only / total_stock_buy_krw_only * 100) if total_stock_buy_krw_only > 0 else 0.0
    total_stock_profit_krw_only = total_stock_eval_profit_krw_only + krw_dividend_krw
    total_stock_return_krw_only = (total_stock_profit_krw_only / total_stock_buy_krw_only * 100) if total_stock_buy_krw_only > 0 else 0.0
    
    return {
        "kpi": {
            "total_stock_buy": total_stock_buy,
            "total_stock_eval": total_stock_eval,
            "rebalance_stock_eval": rebalance_stock_eval,
            "total_eval_profit": round(total_eval_profit, 0),
            "total_eval_return": round((total_eval_profit / total_stock_buy * 100) if total_stock_buy > 0 else 0.0, 2),
            "total_dividend_profit": round(total_dividend_profit, 0),
            "total_stock_profit": round(total_stock_profit, 0),
            "total_stock_return": total_stock_return,
            "total_portfolio_eval": total_portfolio_eval,
            "usd_summary": {
                "stock_eval_usd": round(total_stock_eval_usd, 2),
                "stock_buy_usd": round(total_stock_buy_usd, 2),
                "stock_eval_profit_usd": round(total_stock_eval_profit_usd, 2),
                "stock_eval_return_usd": total_stock_eval_return_usd,
                "stock_dividend_usd": round(total_dividend_usd, 2),
                "stock_profit_usd": round(total_stock_profit_usd, 2),
                "stock_return_usd": total_stock_return_usd,
                "cash_usd": round(total_usd_cash, 2),
                "total_eval_usd": round(total_stock_eval_usd + total_usd_cash, 2),
                "total_buy_usd": round(total_stock_buy_usd, 2),
                "weighted_buy_fx_rate": round(weighted_buy_fx_rate, 2),
                "total_fx_profit_krw": round(total_fx_profit_krw, 0),
                "total_fx_profit_pct": round(total_fx_profit_pct, 2),
                "pure_stock_profit_krw": round(total_pure_stock_profit_krw, 0)
            },
            "krw_summary": {
                "stock_eval_krw": round(total_stock_eval_krw_only, 0),
                "stock_buy_krw": round(total_stock_buy_krw_only, 0),
                "stock_eval_profit_krw": round(total_stock_eval_profit_krw_only, 0),
                "stock_eval_return_krw": total_stock_eval_return_krw_only,
                "stock_dividend_krw": round(krw_dividend_krw, 0),
                "stock_profit_krw": round(total_stock_profit_krw_only, 0),
                "stock_return_krw": total_stock_return_krw_only,
                "cash_krw": round(total_krw_cash, 0),
                "total_eval_krw": round(total_stock_eval_krw_only + total_krw_cash, 0),
                "total_buy_krw": round(total_stock_buy_krw_only, 0)
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
