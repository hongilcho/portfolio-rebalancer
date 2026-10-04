"""Pure per-holding valuation using already calculated dividend results."""


def dividend_profits(adjustment, quantity, is_us, usd_krw):
    """Return unrounded KRW/USD dividends, including legacy unit-only inputs."""
    if 'total_dividend_profit' in adjustment:
        amount = float(adjustment['total_dividend_profit'])
    else:
        amount = quantity * float(adjustment.get('cumulative_dividend', 0.0))
    if is_us:
        return amount * usd_krw, amount
    return amount, amount / usd_krw if usd_krw > 0 else 0.0


def calculate_holding_valuation(h, adj_info, price_map, price_usd_map, usd_krw):
    """Produce account holding fields without cash, fetching or input mutation."""
    aid = str(h['asset_id'])
    qty = float(h['quantity'])

    avg_p_krw = adj_info["avg_price"]
    curr_p = float(price_map.get(aid, avg_p_krw if avg_p_krw > 0 else 0))

    eval_val = qty * curr_p
    buy_amt = qty * avg_p_krw

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

    div_profit_krw, div_profit_usd = dividend_profits(adj_info, qty, is_us, usd_krw)

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

    return {
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
    }
