"""Pure portfolio valuation from one request's supplied financial snapshot.

This module performs no DB, market-provider or cache IO. Preserve API rounding,
price fallbacks and cash-excluded dividend-inclusive returns at their boundaries.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from logic.holding_valuation import calculate_holding_valuation, dividend_profits


@dataclass(frozen=True)
class ValuationInputs:
    holdings_by_account: Dict[str, List[Dict[str, Any]]]
    trades_by_holding: Dict[Tuple[str, str], List[Dict[str, Any]]]
    price_usd_map: Dict[str, float]


def index_valuation_inputs(holdings, trades, prices):
    """Index a batch once, including when several portfolios share the request."""
    by_account = {}
    for holding in holdings:
        by_account.setdefault(str(holding['account_id']), []).append(holding)
    by_holding = {}
    for trade in trades or []:
        key = (str(trade.get('account_id', '')), str(trade.get('asset_id', '')))
        by_holding.setdefault(key, []).append(trade)
    usd_prices = {str(item['id']): float(item.get('price_usd') or 0.0) for item in prices or []}
    return ValuationInputs(by_account, by_holding, usd_prices)


def calculate_portfolio_summary(accounts, assets, inputs, adjustments, price_map, usd_krw):
    """Calculate account/asset/KPI views with already prepared dividend results."""
    price_usd_map = inputs.price_usd_map
    holdings_by_acc = inputs.holdings_by_account

    # 1. Account-level calculations
    account_summaries = []

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
            key = (acc_id, str(h['asset_id']))
            detail = calculate_holding_valuation(h, adjustments[key], price_map, price_usd_map, usd_krw)
            holding_details.append(detail)
            stock_eval += detail['eval_amount']
            stock_buy_total += detail['buy_amount']
            if detail['is_risk_asset']:
                risk_stock_eval += detail['eval_amount']
            else:
                safe_stock_eval += detail['eval_amount']

        total_acc_val = total_deposit + stock_eval
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

    portfolio_assets = aggregate_positions(accounts, assets, inputs, adjustments, price_map, usd_krw)
    total_krw_cash = sum(float(a['deposit_krw']) for a in accounts)
    total_usd_cash = sum(float(a['deposit_usd']) for a in accounts)

    total_stock_eval = sum(d['eval_amt_krw'] for d in portfolio_assets.values() if d['quantity'] > 0)
    rebalance_stock_eval = sum(d['eval_amt_krw'] for d in portfolio_assets.values() if d['quantity'] > 0 and d.get('include_in_rebalance', True))
    total_stock_buy = sum(d['buy_amt_krw'] for d in portfolio_assets.values() if d['quantity'] > 0)
    total_eval_profit = total_stock_eval - total_stock_buy
    total_dividend_profit = sum(d.get('dividend_krw', 0.0) for d in portfolio_assets.values() if d['quantity'] > 0)
    total_stock_profit = total_eval_profit + total_dividend_profit
    total_stock_return = (total_stock_profit / total_stock_buy * 100) if total_stock_buy > 0 else 0.0
    total_portfolio_eval = total_krw_cash + (total_usd_cash * usd_krw) + total_stock_eval

    stock_summary_rows, scale_max = build_asset_rows(
        assets, portfolio_assets, price_map, price_usd_map, usd_krw, rebalance_stock_eval,
    )

    cash_summary = {
        "krw_cash": total_krw_cash,
        "usd_cash": total_usd_cash,
        "usd_cash_krw": total_usd_cash * usd_krw,
        "total_cash_krw": total_krw_cash + (total_usd_cash * usd_krw)
    }

    usd_summary, krw_summary = currency_summaries(
        stock_summary_rows, total_usd_cash, total_krw_cash, usd_krw,
    )

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
            "usd_summary": usd_summary,
            "krw_summary": krw_summary
        },
        "stock_assets": stock_summary_rows,
        "cash_assets": cash_summary,
        "accounts": account_summaries,
        "account_summaries": account_summaries,
        "drift_scale_max": scale_max,
        "usd_krw": usd_krw,
    }


def aggregate_positions(accounts, assets, inputs, adjustments, price_map, usd_krw):
    """Aggregate raw costs, valuation and dividends; add independent deposits."""
    asset_dict_by_id = {str(a['id']): a for a in assets}
    holdings_by_acc = inputs.holdings_by_account
    portfolio_assets = {}

    for acc in accounts:
        acc_holdings = holdings_by_acc.get(str(acc['id']), [])
        for h in acc_holdings:
            aid = str(h['asset_id'])
            asset_meta = asset_dict_by_id.get(aid, {})
            adj_info = adjustments[(str(acc['id']), aid)]
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
            d_krw, d_usd = dividend_profits(adj_info, qty, is_us_h, usd_krw)

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

    return portfolio_assets


def build_asset_rows(assets, portfolio_assets, price_map, price_usd_map, usd_krw, rebalance_stock_eval):
    """Format per-asset results, retaining weighted FX and display precision."""
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

    return stock_summary_rows, scale_max


def currency_summaries(stock_summary_rows, total_usd_cash, total_krw_cash, usd_krw):
    """Keep native-currency stock returns separate from each currency's cash."""
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

    usd_summary = {
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
    }
    krw_summary = {
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
    return usd_summary, krw_summary
