"""Read-only moving-average sale accounting. Never moves portfolio cash.

Amounts are management performance, not a tax return. Gross security cost is
kept separate from acquisition expenses so the existing holding-price contract
does not change. Unknown expenses/basis remain unknown, never implicit zero.
"""
from collections import defaultdict
from decimal import Decimal
import json

from logic.trade_accounting import trade_sort_key
from logic.realized_opening import validity

ZERO = Decimal(0)


def known_total(rows, key):
    values=[r[key] for r in rows if r[key] is not None]
    return sum(values) if values or not rows else None


def number(value):
    result = Decimal(str(value or 0))
    if not result.is_finite():
        raise ValueError('손익 계산에 유효한 금액이 필요합니다.')
    return result


def document(value):
    return json.loads(value) if isinstance(value, str) else value or {}


def expense(trade, currency):
    costs = document(trade.get('trade_costs'))
    krw, usd = costs.get('krw'), costs.get('usd')
    known = krw is not None and (currency != 'USD' or usd is not None) and costs.get('status') not in ('ESTIMATED','DEFERRED')
    fx = number(trade.get('exchange_rate') or 1)
    return number(krw) + number(usd) * fx, known


def calculate(trades, holdings=(), start=None, end=None, account_id=None, asset_id=None, baselines=()):
    """Replay ALL history before filtering sales. Account/asset pools never mix."""
    groups = defaultdict(list)
    for t in trades:
        groups[(str(t['account_id']), str(t['asset_id']))].append(t)
    actual = {(str(h['account_id']), str(h['asset_id'])): number(h['quantity']) for h in holdings}
    openings={(str(p['account_id']),str(p['asset_id'])):p for p in baselines}
    for key in openings:groups.setdefault(key,[])
    sales, periods, warnings = [], [], []
    for (aid, sid), history in groups.items():
        if account_id and aid != str(account_id) or asset_id and sid != str(asset_id):
            continue
        qty = cost = cost_usd = acquisition_expenses = ZERO
        known, expenses_known, period = True, True, None
        expenses_available=True
        opening=openings.get((aid,sid));opening_invalid=False
        if opening:
            reason=validity(opening,history);opening_invalid=bool(reason)
            if reason:warnings.append(dict(account_id=aid,asset_id=sid,reason=reason))
            qty=number(opening['quantity']);cost=qty*number(opening['avg_krw']);cost_usd=qty*number(opening['avg_usd'])
            known=not opening_invalid;expenses_known=False
            expenses_available=False
            reference=history[0] if history else {}
            period=dict(id='opening:'+opening['id'],account_id=aid,asset_id=sid,
                asset_name=reference.get('asset_name',sid),ticker=reference.get('ticker',''),
                account_alias=reference.get('account_alias',aid),start_date=opening.get('first_buy_date'),
                calculation_start_date=opening['date'],end_date=None,sales=[],basis_adjusted=True,
                opening_id=opening['id'],dividend_scope='SINCE_CONFIRMED_BASELINE')
            history=[t for t in history if str(t['id']) not in opening['covered_trades']]
        for t in sorted(history, key=trade_sort_key):
            kind = t['trade_type']; amount = number(t['quantity']); price = number(t['price'])
            currency = t.get('currency') or ('USD' if t.get('market') == 'US' else 'KRW')
            fx = number(t.get('exchange_rate') or 1) if currency == 'USD' else Decimal(1)
            day = str(t['trade_date']); fee, fee_known = expense(t, currency)
            costs=document(t.get('trade_costs'))
            fee_available=costs.get('krw') is not None and (currency!='USD' or costs.get('usd') is not None) and costs.get('status')!='DEFERRED'
            if amount <= 0 or price < 0 or fx <= 0:
                warnings.append(dict(account_id=aid, asset_id=sid, reason='유효하지 않은 거래 이력'))
                known = False
                continue
            anchor = document(t.get('accounting_basis'))
            # A newly recorded sale can preserve a trusted book opening when old
            # purchase history was never imported. Never override complete replay.
            if kind == 'SELL' and not opening_invalid and anchor.get('source') == 'BOOK' and (not known or qty < amount):
                qty = number(anchor['quantity']); cost = qty * number(anchor['avg_krw'])
                cost_usd = qty * number(anchor.get('avg_usd'))
                acquisition_expenses, expenses_known, known = ZERO, False, True
                expenses_available=False
                warnings.append(dict(account_id=aid, asset_id=sid, reason='매도 당시 장부 원가 기준 · 이전 매입비용 미확인'))
            if kind in ('INIT', 'BUY'):
                if kind == 'INIT':
                    # INIT is an explicit cost baseline/correction, not income.
                    if period and qty:
                        period['basis_adjusted'] = True
                    qty = cost = cost_usd = acquisition_expenses = ZERO
                    known, expenses_known = True, False
                    expenses_available=False
                if period is None:
                    period = dict(id=t['id'], account_id=aid, asset_id=sid,
                                  asset_name=t.get('asset_name', sid), ticker=t.get('ticker', ''),
                                  account_alias=t.get('account_alias', aid), start_date=day,
                                  end_date=None, sales=[], basis_adjusted=False)
                qty += amount; cost += amount * price * fx
                if currency == 'USD': cost_usd += amount * price
                if kind == 'BUY':
                    acquisition_expenses += fee
                    expenses_known = expenses_known and fee_known
                    expenses_available=expenses_available and fee_available
                continue
            if kind != 'SELL': continue
            if period is None:
                period = dict(id=t['id'], account_id=aid, asset_id=sid,
                              asset_name=t.get('asset_name', sid), ticker=t.get('ticker', ''),
                              account_alias=t.get('account_alias', aid), start_date=None,
                              end_date=None, sales=[], basis_adjusted=bool(anchor))
            basis_known = known and qty >= amount and qty > 0
            ratio = amount / qty if basis_known else ZERO
            basis = cost * ratio if basis_known else None
            basis_usd = cost_usd * ratio if basis_known and currency == 'USD' else None
            allocated = acquisition_expenses * ratio if basis_known else None
            gross = amount * price * fx - basis if basis_known else None
            net = gross - allocated - fee if basis_known and expenses_known and fee_known else None
            estimated_net=gross-allocated-fee if basis_known and expenses_available and fee_available and net is None else None
            usd_profit = amount * price - basis_usd if basis_usd is not None else None
            fx_profit = basis_usd * fx - basis if basis_usd is not None else ZERO if basis_known else None
            row = dict(trade_id=t['id'], account_id=aid, asset_id=sid,
                       account_alias=t.get('account_alias', aid), asset_name=t.get('asset_name', sid),
                       ticker=t.get('ticker', ''), trade_date=day, currency=currency,
                       quantity=float(amount), price=float(price), exchange_rate=float(fx),
                       proceeds_krw=float(amount * price * fx), cost_basis_krw=float(basis) if basis is not None else None,
                       gross_profit_krw=float(gross) if gross is not None else None,
                       net_profit_krw=float(net) if net is not None else None,
                       estimated_net_profit_krw=float(estimated_net) if estimated_net is not None else None,
                       sale_cost_krw=float(fee) if fee_known else None,
                       allocated_buy_cost_krw=float(allocated) if expenses_known and allocated is not None else None,
                       price_profit_usd=float(usd_profit) if usd_profit is not None else None,
                       fx_profit_krw=float(fx_profit) if fx_profit is not None else None,
                       cost_basis_known=basis_known, costs_confirmed=expenses_known and fee_known,
                       status='CONFIRMED' if net is not None else 'COSTS_PENDING' if basis_known else 'BASIS_PENDING')
            sales.append(row); period['sales'].append(row)
            if basis_known:
                qty -= amount; cost -= basis; acquisition_expenses -= allocated
                if basis_usd is not None: cost_usd -= basis_usd
                if abs(qty) < Decimal('0.000000001'):
                    qty = cost = cost_usd = acquisition_expenses = ZERO
                    period.update(end_date=day, status='CLOSED', remaining_quantity=0)
                    periods.append(period); period = None
                    expenses_known = True
                    expenses_available=True
            else:
                known = False
        if period:
            period.update(status='OPEN' if known else 'REVIEW', remaining_quantity=float(qty) if known else None)
            periods.append(period)
        if (aid, sid) in actual and (not known or abs(qty - actual[(aid, sid)]) > Decimal('0.00001')):
            warnings.append(dict(account_id=aid,asset_id=sid,reason='매매 이력과 현재 보유 수량 대조 필요'))
    for period in periods:
        values=period['sales']
        period.update(gross_profit_krw=known_total(values,'gross_profit_krw'),
                      confirmed_net_profit_krw=known_total(values,'net_profit_krw'),
                      pending_count=sum(r['status']!='CONFIRMED' for r in values))
        period.pop('sales')
    selected=[r for r in sales if (not start or r['trade_date']>=str(start)) and (not end or r['trade_date']<=str(end))]
    return dict(sales=sorted(selected,key=lambda r:(r['trade_date'],r['trade_id']),reverse=True),
                periods=sorted(periods,key=lambda r:(r['end_date'] or '9999',r['start_date'] or ''),reverse=True),
                summary=dict(sell_count=len(selected),gross_profit_krw=known_total(selected,'gross_profit_krw'),
                             confirmed_net_profit_krw=known_total(selected,'net_profit_krw'),
                             pending_count=sum(r['status']!='CONFIRMED' for r in selected)),warnings=warnings)
