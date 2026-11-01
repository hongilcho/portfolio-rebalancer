from typing import List, Dict, Any
from logic.trade_accounting import trade_sort_key

def calculate_holding_dividends_from_history(
    trades: List[Dict[str, Any]],
    div_records: List[Dict[str, Any]],
    start_date: str = '',
    tax_rate: float = 0.0,
    is_us: bool = False
) -> Dict[str, Any]:
    """
    매매 기록(trade_history)을 시계열로 역추적하여 각 배당락일(Ex-Dividend Date) 당시에
    실제로 보유하고 있던 수량(holding_quantity)을 산출하고, 세후 실수령 배당금을 정밀 계산합니다.

    1. 배당락일(ex_date) 기준 주주명부에 등재되려면 배당락일 장 시작 전(즉 전일 장마감 기준) 보유해야 함.
    2. 따라서 trade_date < ex_date 인 거래 내역만 해당 배당락일의 보유 수량 산정에 반영.
    3. INIT(스냅샷) 및 이후 BUY/SELL을 종합하여 정확한 잔고를 복원.
    """
    qualifying_divs = [d for d in div_records if not start_date or d['date'] >= start_date]
    total_gross = 0.0
    total_net = 0.0
    total_tax = 0.0
    history = []

    sorted_trades = sorted(trades, key=trade_sort_key)

    for d in qualifying_divs:
        ex_date = d['date']
        amt = float(d['amount'])

        # 배당락일 전 거래 내역 필터링
        prior_trades = [t for t in sorted_trades if str(t.get('trade_date', '')) < ex_date]
        if not prior_trades:
            continue

        init_trades = [t for t in prior_trades if t.get('trade_type') == 'INIT']
        if init_trades:
            latest_init = init_trades[-1]
            qty_at_ex = float(latest_init.get('quantity') or 0.0)
            init_date = str(latest_init.get('trade_date', ''))
            for t in prior_trades:
                if str(t.get('trade_date', '')) > init_date:
                    t_type = t.get('trade_type', '')
                    if t_type == 'BUY':
                        qty_at_ex += float(t.get('quantity') or 0.0)
                    elif t_type == 'SELL':
                        qty_at_ex -= float(t.get('quantity') or 0.0)
        else:
            qty_at_ex = sum(
                float(t.get('quantity') or 0.0) if t.get('trade_type') == 'BUY' else -float(t.get('quantity') or 0.0)
                for t in prior_trades if t.get('trade_type') in ('BUY', 'SELL')
            )

        qty_at_ex = max(0.0, qty_at_ex)
        if qty_at_ex > 0:
            gross = qty_at_ex * amt
            tax = round(gross * tax_rate, 4 if is_us else 1)
            net = max(0.0, gross - tax)
            total_gross += gross
            total_net += net
            total_tax += tax
            history.append({
                'ex_date': ex_date,
                'amount_per_share': amt,
                'holding_quantity': qty_at_ex,
                'gross_amount': round(gross, 4 if is_us else 1),
                'tax_amount': round(tax, 4 if is_us else 1),
                'net_amount': round(net, 4 if is_us else 1)
            })

    return {
        'total_gross': round(total_gross, 4 if is_us else 1),
        'total_net': round(total_net, 4 if is_us else 1),
        'total_tax': round(total_tax, 4 if is_us else 1),
        'count': len(history),
        'history': history
    }
