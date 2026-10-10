"""Account-locked USD cost journal. Callers own transactions for trade hooks."""
import json
import math
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

from psycopg2.extras import RealDictCursor
from logic.usd_cost import number, positive, average, receive, spend
from data.repositories import bookkeeping

KST = timezone(timedelta(hours=9))
HOLDING_FIELDS = ('quantity', 'avg_price', 'avg_price_usd', 'buy_fx_rate',
                  'original_avg_price', 'original_avg_price_usd')


def encoded(value):
    return json.dumps(value, default=lambda obj: str(obj), ensure_ascii=False)


def event_time(value):
    moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=KST)
    moment = moment.astimezone(KST)
    if moment.date() > datetime.now(KST).date():
        raise ValueError('미래의 환전·매매 기록은 등록할 수 없습니다.')
    return moment


def load_state(cursor, account_id):
    cursor.execute('SELECT * FROM usd_cash_state WHERE account_id = %s FOR UPDATE', (str(account_id),))
    return cursor.fetchone()


def enabled(cursor, account_id):
    cursor.execute('SELECT account_id FROM usd_cash_state WHERE account_id = %s', (str(account_id),))
    return bool(cursor.fetchone())


def validate_state(state, account, moment):
    if not math.isclose(float(state['usd_balance']), float(account['deposit_usd'] or 0), abs_tol=1e-5, rel_tol=0):
        raise ValueError('달러 잔고와 원가 기록이 다릅니다. 5번 탭 장부 확인 및 정정에서 실제 달러 잔고와 평균 취득환율을 확인해주세요.')
    if moment.date() < date.fromisoformat(str(state['last_event_date'])):
        raise ValueError('이전 날짜의 기록은 추가할 수 없습니다. 이후 기록부터 순서대로 취소해주세요.')


def snapshot(state, holding=None, asset_id=None):
    return dict(usd_balance=str(state['usd_balance']), cost_krw=str(state['cost_krw']),
                last_event_date=str(state['last_event_date']), asset_id=asset_id,
                holding={key: float(holding.get(key) or 0) for key in HOLDING_FIELDS} if holding else None)


def save_state(cursor, account_id, usd, cost, day):
    cursor.execute('UPDATE usd_cash_state SET usd_balance = %s, cost_krw = %s, last_event_date = %s WHERE account_id = %s',
                   (usd, cost, str(day), str(account_id)))


def append_event(db, cursor, account_id, kind, moment, amount, krw_amount, fx,
                 delta_krw, delta_usd, before, after, notes='', trade_id=None, asset_id=None):
    ident = db.new_id()
    cursor.execute('''
        INSERT INTO usd_cash_events
        (id, account_id, kind, occurred_at, event_date, usd_amount, krw_amount, fx_rate,
         cash_delta_krw, cash_delta_usd, before_state, after_state, notes, trade_id, trade_reference, asset_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (ident, str(account_id), kind, None if kind in ('BUY', 'SELL') else moment.isoformat(), str(moment.date()),
          amount, krw_amount, fx, float(delta_krw), float(delta_usd), encoded(before), encoded(after),
          notes, trade_id, trade_id, asset_id))
    return ident


def get_ledgers(db, portfolio_id=None):
    conn = db.connect()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        sql = '''SELECT s.*, a.deposit_usd AS actual_usd, a.account_alias FROM usd_cash_state s
                 JOIN accounts a ON a.id = s.account_id'''
        scoped = portfolio_id and portfolio_id != 'all'
        cursor.execute(sql + (' WHERE a.portfolio_id = %s' if scoped else ''),
                       (portfolio_id,) if scoped else ())
        states = [dict(row) for row in cursor.fetchall()]
        for state in states:
            state['average_rate'] = float(average(state['usd_balance'], state['cost_krw']))
            state['balance_difference'] = float(state['actual_usd'] or 0) - float(state['usd_balance'])
            state['needs_reconciliation'] = abs(state['balance_difference']) > 1e-5
        return states
    finally:
        conn.close()


def get_events(db, account_id=None):
    conn = db.connect()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT * FROM usd_cash_events' + (' WHERE account_id = %s' if account_id is not None else '') + ' ORDER BY sequence DESC',
                       (str(account_id),) if account_id is not None else ())
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def record_cash_event(db, account_id, kind, occurred_at, usd_amount=0, krw_amount=0, rate=0, notes='', transaction=None):
    """Opening never changes holdings; exchange amounts are net cash movements."""
    conn = transaction if transaction is not None else db.connect()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        moment = event_time(occurred_at)
        cursor.execute('SELECT deposit_krw, deposit_usd FROM accounts WHERE id = %s FOR UPDATE', (str(account_id),))
        account = cursor.fetchone()
        if not account:
            raise ValueError('존재하지 않는 계좌입니다.')
        state = load_state(cursor, account_id)
        delta_krw = delta_usd = Decimal(0)
        if kind == 'OPENING':
            if state:
                raise ValueError('이미 달러 원가 추적을 시작한 계좌입니다.')
            usd, fx = number(account['deposit_usd'] or 0), positive(rate)
            if usd < 0:
                raise ValueError('달러 잔고가 음수입니다.')
            cost, amount, krw = usd * fx, usd, usd * fx
            before = None
            cursor.execute('INSERT INTO usd_cash_state (account_id, usd_balance, cost_krw, last_event_date) VALUES (%s, %s, %s, %s)',
                           (str(account_id), usd, cost, str(moment.date())))
        else:
            if not state:
                raise ValueError('달러 시작 잔액의 기준환율을 먼저 등록해주세요.')
            before = snapshot(state)
            if moment.date() < date.fromisoformat(str(state['last_event_date'])):
                raise ValueError('이전 날짜의 기록은 추가할 수 없습니다. 이후 기록부터 순서대로 취소해주세요.')
            if kind == 'RECONCILE':
                usd, fx = number(account['deposit_usd'] or 0), positive(rate)
                if usd < 0:
                    raise ValueError('달러 잔고가 음수입니다.')
                cost, amount, krw = usd * fx, usd, usd * fx
            else:
                validate_state(state, account, moment)
                amount = positive(usd_amount)
                if kind in ('EXCHANGE_IN', 'EXCHANGE_OUT'):
                    krw = positive(krw_amount)
                    fx = krw / amount
                elif kind in ('DEPOSIT', 'WITHDRAW'):
                    fx = positive(rate) if kind == 'DEPOSIT' else average(state['usd_balance'], state['cost_krw'])
                    krw = amount * fx
                else:
                    raise ValueError('지원하지 않는 달러 거래 유형입니다.')
                if kind in ('EXCHANGE_IN', 'DEPOSIT'):
                    usd, cost = receive(state['usd_balance'], state['cost_krw'], amount, krw)
                    delta_usd = amount
                    delta_krw = -krw if kind == 'EXCHANGE_IN' else Decimal(0)
                else:
                    usd, cost, _ = spend(state['usd_balance'], state['cost_krw'], amount)
                    delta_usd = -amount
                    delta_krw = krw if kind == 'EXCHANGE_OUT' else Decimal(0)
                if number(account['deposit_krw'] or 0) + delta_krw < 0:
                    raise ValueError('환전에 필요한 원화 예수금이 부족합니다. 실제 원화 잔고를 먼저 확인해주세요.')
                cursor.execute('UPDATE accounts SET deposit_krw = deposit_krw + %s, deposit_usd = %s WHERE id = %s',
                               (float(delta_krw), float(usd), str(account_id)))
            save_state(cursor, account_id, usd, cost, moment.date())
        after = snapshot(dict(usd_balance=usd, cost_krw=cost, last_event_date=moment.date()))
        if kind == 'OPENING':
            cursor.execute("SELECT h.* FROM holdings h JOIN assets a ON a.id=h.asset_id WHERE h.account_id=%s AND a.market='US' ORDER BY h.asset_id", (str(account_id),))
            after['opening_holdings'] = [dict(row) for row in cursor.fetchall()]
        append_event(db, cursor, account_id, kind, moment, amount, krw, fx, delta_krw, delta_usd, before, after, notes)
        if transaction is None: conn.commit()
        return True, '달러 원가 기록이 저장되었습니다.'
    except Exception as error:
        if transaction is None: conn.rollback()
        return False, str(error)
    finally:
        if transaction is None: conn.close()


def execute_managed_trade(db, cursor, account_id, asset_id, trade_id, state, account,
                          trade_date, kind, quantity, price, reference_rate):
    if kind not in ('BUY', 'SELL'):
        raise ValueError('추적 중인 미국 자산의 수량·원가는 매수·매도 기록으로 관리해주세요.')
    moment = event_time(str(trade_date) + 'T12:00:00+09:00')
    validate_state(state, account, moment)
    amount = positive(quantity) * positive(price)
    cursor.execute('SELECT * FROM holdings WHERE account_id = %s AND asset_id = %s', (str(account_id), str(asset_id)))
    holding = cursor.fetchone()
    before = snapshot(state, holding, str(asset_id))
    old_qty = number((holding or {}).get('quantity') or 0)
    if kind == 'BUY':
        fx = average(state['usd_balance'], state['cost_krw'])
        usd, cost, assigned = spend(state['usd_balance'], state['cost_krw'], amount)
        if fx <= 0:
            raise ValueError('달러 취득원가를 확인해주세요.')
        qty = old_qty + number(quantity)
        old = holding or {}
        old_usd = positive(old.get('original_avg_price_usd') or old.get('avg_price_usd') or 0) if old_qty else Decimal(0)
        old_krw = positive(old.get('original_avg_price') or old.get('avg_price') or 0) if old_qty else Decimal(0)
        total_usd = old_qty * old_usd + amount
        avg_usd, avg_krw = total_usd / qty, (old_qty * old_krw + assigned) / qty
        buy_fx = avg_krw / avg_usd
        original_krw, original_usd = avg_krw, avg_usd
        delta_usd = -amount
    else:
        if number(quantity) > old_qty:
            raise ValueError('매도할 보유 수량이 부족합니다.')
        fx = positive(reference_rate)
        assigned = amount * fx
        usd, cost = receive(state['usd_balance'], state['cost_krw'], amount, assigned)
        qty = old_qty - number(quantity)
        avg_usd, avg_krw, buy_fx = (number(holding[key] or 0) if qty else Decimal(0)
                                  for key in ('avg_price_usd', 'avg_price', 'buy_fx_rate'))
        original_krw = number(holding.get('original_avg_price') or 0)
        original_usd = number(holding.get('original_avg_price_usd') or 0)
        delta_usd = amount
    cursor.execute('''INSERT INTO trade_history
        (id, trade_date, account_id, asset_id, trade_type, quantity, price, currency, exchange_rate, cash_delta_krw, cash_delta_usd)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'USD', %s, 0, %s)''',
        (trade_id, str(trade_date), str(account_id), str(asset_id), kind, quantity, price, float(fx), float(delta_usd)))
    cursor.execute('UPDATE accounts SET deposit_usd = %s WHERE id = %s', (float(usd), str(account_id)))
    cursor.execute('''INSERT INTO holdings
        (id, account_id, asset_id, quantity, avg_price, avg_price_usd, buy_fx_rate, original_avg_price, original_avg_price_usd)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT(account_id, asset_id) DO UPDATE SET quantity=EXCLUDED.quantity,
        avg_price=EXCLUDED.avg_price, avg_price_usd=EXCLUDED.avg_price_usd, buy_fx_rate=EXCLUDED.buy_fx_rate,
        original_avg_price=EXCLUDED.original_avg_price, original_avg_price_usd=EXCLUDED.original_avg_price_usd''',
        (db.new_id(), str(account_id), str(asset_id), float(qty), float(avg_krw), float(avg_usd), float(buy_fx),
         float(original_krw), float(original_usd)))
    save_state(cursor, account_id, usd, cost, moment.date())
    cursor.execute('SELECT * FROM holdings WHERE account_id = %s AND asset_id = %s', (str(account_id), str(asset_id)))
    after = snapshot(dict(usd_balance=usd, cost_krw=cost, last_event_date=moment.date()), cursor.fetchone(), str(asset_id))
    notes = '계좌 달러 평균 취득환율 적용' if kind == 'BUY' else '매도대금 수취기준환율 적용 (실제 환전 아님)'
    append_event(db, cursor, account_id, kind, moment, amount, assigned, fx, 0, delta_usd, before, after, notes, trade_id, str(asset_id))


def reverse_latest(cursor, account_id, event_id):
    cursor.execute('SELECT deposit_krw, deposit_usd FROM accounts WHERE id = %s FOR UPDATE', (str(account_id),))
    account = cursor.fetchone()
    state = load_state(cursor, account_id)
    cursor.execute('SELECT * FROM usd_cash_events WHERE account_id = %s AND reversed_at IS NULL ORDER BY sequence DESC LIMIT 1 FOR UPDATE', (str(account_id),))
    event = cursor.fetchone()
    if not event or event['id'] != event_id:
        raise ValueError('환전·매매 기록은 해당 계좌의 가장 최근 기록부터 취소해주세요.')
    cursor.execute('SELECT usd_event_id,after_state FROM ledger_adjustments WHERE account_id=%s AND reversed_at IS NULL',(str(account_id),))
    for correction in cursor.fetchall():
        checkpoint=correction['after_state']
        if isinstance(checkpoint,str):checkpoint=json.loads(checkpoint)
        if correction['usd_event_id']==event_id or event['sequence']<=checkpoint['usd_sequence']:
            raise ValueError('장부 정정 이전 환전·달러 기록은 직접 취소할 수 없습니다. 정정부터 취소하거나 새 정정으로 처리해주세요.')
    if not state or not account:
        raise ValueError('달러 원가 기록을 찾을 수 없습니다.')
    validate_state(state, account, event_time(str(event['event_date']) + 'T12:00:00+09:00'))
    after = event['after_state'] if isinstance(event['after_state'], dict) else json.loads(event['after_state'])
    before = event['before_state'] if isinstance(event['before_state'], dict) or event['before_state'] is None else json.loads(event['before_state'])
    if after.get('asset_id'):
        cursor.execute('SELECT * FROM holdings WHERE account_id = %s AND asset_id = %s', (str(account_id), after['asset_id']))
        holding = cursor.fetchone() or {}
        if any(not math.isclose(float(holding.get(key) or 0), float(after['holding'][key]), rel_tol=0, abs_tol=1e-6) for key in HOLDING_FIELDS):
            raise ValueError('보유 원가가 기록 이후 변경되었습니다. 잔고를 확인해주세요.')
        restore = (before or {}).get('holding') or dict.fromkeys(HOLDING_FIELDS, 0)
        cursor.execute('UPDATE holdings SET ' + ', '.join(key + ' = %s' for key in HOLDING_FIELDS) + ' WHERE account_id = %s AND asset_id = %s',
                       (*[restore[key] for key in HOLDING_FIELDS], str(account_id), after['asset_id']))
    if number(account['deposit_krw'] or 0) - number(event['cash_delta_krw']) < 0:
        raise ValueError('취소에 필요한 원화 예수금이 부족합니다.')
    cursor.execute('UPDATE accounts SET deposit_krw = deposit_krw - %s, deposit_usd = deposit_usd - %s WHERE id = %s',
                   (event['cash_delta_krw'], event['cash_delta_usd'], str(account_id)))
    if before is None:
        cursor.execute('DELETE FROM usd_cash_state WHERE account_id = %s', (str(account_id),))
    else:
        save_state(cursor, account_id, number(before['usd_balance']), number(before['cost_krw']), before['last_event_date'])
    cursor.execute('UPDATE usd_cash_events SET reversed_at = CURRENT_TIMESTAMP WHERE id = %s', (event_id,))
    if event.get('trade_id'):
        cursor.execute('DELETE FROM trade_history WHERE id = %s', (event['trade_id'],))


def undo_event(db, account_id, event_id):
    from data.repositories.nh_notices import lock_scope
    conn = db.connect()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT portfolio_id FROM accounts WHERE id=%s',(str(account_id),))
        owner = cursor.fetchone()
        if not owner: raise ValueError('계좌를 찾을 수 없습니다.')
        lock_scope(cursor,owner['portfolio_id'],[account_id])
        cursor.execute("SELECT request_id,result FROM bookkeeping_requests WHERE scope=%s AND result->>'event_id'=%s FOR UPDATE",
                       ('forex:'+account_id,event_id))
        receipt = cursor.fetchone()
        result = receipt['result'] if receipt and isinstance(receipt['result'],dict) else json.loads(receipt['result']) if receipt else None
        if result and result.get('reversed'):
            conn.rollback()
            return True,'이미 취소한 기록입니다. 추가 잔고 변경은 없습니다.'
        cursor.execute('SELECT id FROM nh_notice_items WHERE linked_usd_event_id=%s AND reversed_at IS NULL', (event_id,))
        if cursor.fetchone():
            raise ValueError('NH 알림으로 반영한 환전은 알림 가져오기의 반영 이력에서 묶음 취소해주세요.')
        reverse_latest(cursor, account_id, event_id)
        if result:
            if result.get('created_flow'):
                cursor.execute('UPDATE performance_flows SET voided=TRUE WHERE id=%s',(result['flow_id'],))
                cursor.execute('UPDATE performance_tracking SET revision=revision+1 WHERE portfolio_id=%s',(owner['portfolio_id'],))
            result['reversed'] = True
            result['message'] = '이미 저장한 뒤 취소한 요청입니다. 다시 반영하지 않았습니다.'
            bookkeeping.finish(cursor,'forex:'+account_id,receipt['request_id'],result)
        conn.commit()
        return True, '기록을 취소하고 달러 잔고·원가와 연결된 성과 기록을 복원했습니다.'
    except Exception as error:
        conn.rollback()
        return False, str(error)
    finally:
        conn.close()


def record_manual_event(db, account_id, payload):
    """Cash, cost and an external flow share one transaction and retry receipt."""
    from data.repositories.nh_notices import lock_scope
    conn = db.connect()
    try:
        c = conn.cursor(cursor_factory=RealDictCursor)
        scope = 'forex:' + account_id
        previous = bookkeeping.begin(c,scope,payload['request_id'],payload)
        if previous is not None:
            conn.rollback()
            return previous
        tracks,_ = lock_scope(c,payload['portfolio_id'],[account_id])
        kind = payload['kind']
        track = tracks[payload['portfolio_id']]
        day = event_time(payload['occurred_at']).date()
        cash_transfer = kind in ('DEPOSIT','WITHDRAW')
        if cash_transfer and payload['flow_mode'] != 'INCOME':
            if (track and day < track['baseline_date']) or (not track and payload['flow_mode']=='ALREADY_RECORDED'):
                raise ValueError('외부 달러 입출금은 성과 시작 기준 이후에 등록해주세요. 이전 잔고는 장부 정정으로 등록할 수 있습니다.')
        if payload['flow_mode'] == 'INCOME' and kind == 'WITHDRAW':
            raise ValueError('달러 출금은 외부 투자자금 출금으로 기록해주세요.')
        ok,message = record_cash_event(db,account_id,kind,payload['occurred_at'],
            payload['usd_amount'],payload['krw_amount'],payload['rate'],payload['notes'],transaction=conn)
        if not ok: raise ValueError(message)
        c.execute('SELECT id FROM usd_cash_events WHERE account_id=%s ORDER BY sequence DESC LIMIT 1',(account_id,))
        event_id = c.fetchone()['id']
        flow_id = None
        if cash_transfer and track and payload['flow_mode'] != 'INCOME':
            signed = positive(payload['usd_amount']) * positive(payload['rate']) * (1 if kind=='DEPOSIT' else -1)
            if payload['flow_mode'] == 'ALREADY_RECORDED':
                flow_id = payload.get('existing_flow_id')
                c.execute("""SELECT id FROM performance_flows WHERE id=%s AND portfolio_id=%s
                    AND account_id=%s AND event_date=%s AND currency='USD' AND NOT voided
                    AND native_amount=%s AND amount_krw=%s""",
                    (flow_id,payload['portfolio_id'],account_id,str(day),payload['usd_amount'],signed))
                if not c.fetchone(): raise ValueError('연결할 기존 달러 입출금 기록의 계좌·날짜·금액·평가환율을 확인해주세요.')
                c.execute("SELECT request_id FROM bookkeeping_requests WHERE result->>'flow_id'=%s AND COALESCE(result->>'reversed','false')='false'",(flow_id,))
                if c.fetchone(): raise ValueError('이 입출금 기록은 이미 달러 잔고에 연결되어 있습니다.')
            else:
                c.execute("""SELECT id FROM performance_flows WHERE portfolio_id=%s AND account_id=%s
                    AND event_date=%s AND currency='USD' AND native_amount=%s AND amount_krw=%s AND NOT voided""",
                    (payload['portfolio_id'],account_id,str(day),payload['usd_amount'],signed))
                if c.fetchone() and not payload.get('duplicate_confirmed'):
                    raise ValueError('같은 달러 입출금 성과 기록이 있습니다. 기존 기록을 연결하거나 별도 실제 입출금임을 확인해주세요.')
                flow_id = db.new_id()
                c.execute("""INSERT INTO performance_flows
                    (id,portfolio_id,account_id,request_id,event_date,amount_krw,currency,native_amount,exchange_rate,notes)
                    VALUES(%s,%s,%s,%s,%s,%s,'USD',%s,%s,%s)""",
                    (flow_id,payload['portfolio_id'],account_id,payload['request_id'],str(day),signed,
                     payload['usd_amount'],payload['rate'],payload['notes']))
                c.execute('UPDATE performance_tracking SET revision=revision+1 WHERE portfolio_id=%s',(payload['portfolio_id'],))
        result = dict(success=True,message='달러 잔고·원가'+('와 외부 입출금 기록을 함께' if flow_id else '를')+' 저장했습니다.',
                      event_id=event_id,flow_id=flow_id,performance_not_started=bool(cash_transfer and not track),created_flow=bool(flow_id and payload['flow_mode']=='EXTERNAL'))
        if payload.get('execution'):
            from data.repositories.investments import attach
            attach(c,db,payload['portfolio_id'],payload['execution'],'USD',event_id)
        bookkeeping.finish(c,scope,payload['request_id'],result)
        conn.commit()
        db.invalidate()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
