"""Pure trade accounting used for cash movements and history replay."""

import math


def trade_sort_key(trade):
    # BIGSERIAL assigned during migration cannot recover historical input order.
    # Keep the old UUID order for rows without recorded cash movements.
    legacy = trade.get("cash_delta_krw") is None or trade.get("cash_delta_usd") is None
    return (
        str(trade.get("trade_date", "")),
        0 if trade.get("trade_type") == "INIT" else 1,
        0 if legacy else 1,
        0 if legacy else (trade.get("trade_sequence") or 0),
        str(trade.get("id", "")),
    )


def cash_movement(trade_type, quantity, price, currency, exchange_rate, krw, usd):
    """Return the actual (KRW, USD) deltas, preserving the settlement policy."""
    if trade_type == "INIT":
        return 0.0, 0.0
    amount = quantity * price
    if currency == "USD":
        if trade_type == "BUY" and usd >= amount:
            return 0.0, -amount
        if trade_type == "SELL" and usd > 0:
            return 0.0, amount
        amount *= exchange_rate
    delta = -amount if trade_type == "BUY" else amount
    if trade_type == "BUY" and krw + delta < -1e-9:
        raise ValueError("매수에 필요한 예수금이 부족합니다.")
    return delta, 0.0


def replay_holding(trades):
    """Rebuild cost basis; reject histories that would silently oversell."""
    qty = avg_krw = avg_usd = buy_fx = 0.0
    ordered = sorted(trades, key=trade_sort_key)
    for trade in ordered:
        kind = trade["trade_type"]
        amount = float(trade["quantity"])
        price = float(trade["price"])
        currency = trade.get("currency") or ("USD" if trade.get("market") == "US" else "KRW")
        fx = float(trade.get("exchange_rate") or 1.0) if currency == "USD" else 1.0
        if kind not in {"INIT", "BUY", "SELL"}:
            raise ValueError("지원하지 않는 거래 유형이 이력에 있습니다.")
        if not all(math.isfinite(v) and v >= 0 for v in (amount, price, fx)):
            raise ValueError("거래 이력의 수량·단가·환율을 확인해주세요.")
        unit_krw = price * fx
        if kind == "INIT":
            qty, avg_krw = amount, unit_krw
            avg_usd, buy_fx = (price, fx) if currency == "USD" else (0.0, 0.0)
        elif kind == "BUY":
            next_qty = qty + amount
            cost_krw = qty * avg_krw + amount * unit_krw
            if currency == "USD":
                cost_usd = qty * avg_usd + amount * price
                avg_usd = cost_usd / next_qty if next_qty else 0.0
                buy_fx = cost_krw / cost_usd if cost_usd else fx
            else:
                avg_usd = buy_fx = 0.0
            avg_krw = cost_krw / next_qty if next_qty else 0.0
            qty = next_qty
        else:
            if amount > qty + 1e-9:
                raise ValueError("삭제 후 남은 매도 거래의 보유 수량이 부족합니다. 관련 매도도 함께 선택해주세요.")
            qty = max(0.0, qty - amount)
            if qty == 0:
                avg_krw = avg_usd = buy_fx = 0.0
    return qty, avg_krw, avg_usd, buy_fx
