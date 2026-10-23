"""Trade-associated costs and sale basis, within the caller's transaction."""
from decimal import Decimal
import json
from psycopg2.extras import Json
from logic.usd_cost import spend
from data.repositories import forex


def normalize(krw, usd, currency):
    result = {}
    for name, value in (('krw', krw), ('usd', usd)):
        if value is None: result[name] = None; continue
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > Decimal('1e12'):
            raise ValueError('수수료·세금은 0 이상의 유효한 금액이어야 합니다.')
        result[name] = str(amount)
    if currency == 'KRW':
        if usd is not None and Decimal(str(usd)) != 0:
            raise ValueError('국내 매매의 비용은 원화로 입력해주세요.')
        result['usd'] = '0'
    return result


def capture(c, account_id, asset_id):
    c.execute('SELECT * FROM holdings WHERE account_id=%s AND asset_id=%s', (str(account_id), str(asset_id)))
    h = c.fetchone()
    if not h: return None
    return dict(source='BOOK', quantity=str(h['quantity'] or 0),
                avg_krw=str(h.get('original_avg_price') or h.get('avg_price') or 0),
                avg_usd=str(h.get('original_avg_price_usd') or h.get('avg_price_usd') or 0))


def apply(c, trade_id, costs, basis=None):
    krw = Decimal(costs['krw'] or '0'); usd = Decimal(costs['usd'] or '0')
    if krw or usd:
        c.execute('SELECT * FROM trade_history WHERE id=%s', (trade_id,))
        t = c.fetchone(); aid = t['account_id']
        c.execute('SELECT deposit_krw,deposit_usd FROM accounts WHERE id=%s FOR UPDATE', (aid,))
        cash = c.fetchone()
        insufficient=(krw and krw > Decimal(str(cash['deposit_krw'] or 0))) or (usd and usd > Decimal(str(cash['deposit_usd'] or 0)))
        if insufficient and costs.get('status')=='ESTIMATED':
            # A provisional fee must not prevent recording a real filled trade.
            # Preserve the estimate; defer it to explicit cash reconciliation.
            costs={**costs,'status':'DEFERRED','estimated_krw':str(krw),'estimated_usd':str(usd),'krw':'0','usd':'0'}
            c.execute('UPDATE trade_history SET trade_costs=%s,accounting_basis=%s WHERE id=%s',
                      (Json(costs),Json(basis) if basis else None,trade_id))
            return
        if insufficient:
            raise ValueError('매매 후 비용을 반영할 예수금이 부족합니다. 5번 탭에서 잔고를 확인해주세요.')
        c.execute('UPDATE accounts SET deposit_krw=deposit_krw-%s,deposit_usd=deposit_usd-%s WHERE id=%s', (krw, usd, aid))
        state = forex.load_state(c, aid)
        if state and t['currency'] == 'USD':
            balance, cost, removed = spend(state['usd_balance'], state['cost_krw'], usd) if usd else (
                Decimal(str(state['usd_balance'])), Decimal(str(state['cost_krw'])), Decimal(0))
            forex.save_state(c, aid, balance, cost, t['trade_date'])
            c.execute('SELECT * FROM usd_cash_events WHERE trade_id=%s', (trade_id,)); event = c.fetchone()
            if not event: raise ValueError('달러 매매와 비용의 연결 기록을 확인해주세요.')
            after = event['after_state'] if isinstance(event['after_state'], dict) else json.loads(event['after_state'])
            after.update(usd_balance=str(balance), cost_krw=str(cost))
            sign = Decimal(1) if t['trade_type'] == 'BUY' else Decimal(-1)
            c.execute('''UPDATE usd_cash_events SET after_state=%s, cash_delta_krw=cash_delta_krw-%s,
                cash_delta_usd=cash_delta_usd-%s,usd_amount=usd_amount+%s,krw_amount=krw_amount+%s WHERE id=%s''',
                (Json(after), krw, usd, usd*sign, removed*sign, event['id']))
        c.execute('UPDATE trade_history SET cash_delta_krw=cash_delta_krw-%s,cash_delta_usd=cash_delta_usd-%s WHERE id=%s', (krw, usd, trade_id))
    c.execute('UPDATE trade_history SET trade_costs=%s,accounting_basis=%s WHERE id=%s',
              (Json(costs), Json(basis) if basis else None, trade_id))
