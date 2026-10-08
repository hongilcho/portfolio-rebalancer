"""Confirmed NH bookkeeping batches: one transaction, scoped cash and audited undo."""
import json
from datetime import date, datetime
from psycopg2.extras import Json, RealDictCursor
from data.repositories import forex, trades
from logic.usd_cost import number, positive, receive


def plain(value):
    return json.loads(json.dumps(value, default=str))


def checkpoint(c, accounts):
    result = {}
    for aid in accounts:
        c.execute('SELECT deposit_krw,deposit_usd FROM accounts WHERE id=%s', (aid,))
        cash = dict(c.fetchone())
        c.execute('SELECT * FROM usd_cash_state WHERE account_id=%s', (aid,))
        state = c.fetchone()
        c.execute('SELECT * FROM holdings WHERE account_id=%s ORDER BY asset_id', (aid,))
        holdings = c.fetchall()
        c.execute('SELECT COALESCE(MAX(trade_sequence),0) AS n FROM trade_history WHERE account_id=%s', (aid,))
        trade_sequence = c.fetchone()['n']
        c.execute('SELECT COALESCE(MAX(sequence),0) AS n FROM usd_cash_events WHERE account_id=%s AND reversed_at IS NULL', (aid,))
        usd_sequence = c.fetchone()['n']
        c.execute('SELECT COALESCE(MAX(sequence),0) AS n FROM nh_notice_items WHERE account_id=%s AND reversed_at IS NULL', (aid,))
        result[aid] = dict(cash=cash,state=state,holdings=holdings,trade_sequence=trade_sequence,
                           usd_sequence=usd_sequence,notice_sequence=c.fetchone()['n'])
    return plain(result)


def lock_scope(c, pid, ids):
    c.execute('SELECT id FROM portfolios WHERE id=%s FOR UPDATE', (pid,))
    if not c.fetchone(): raise ValueError('포트폴리오를 찾을 수 없습니다.')
    c.execute('SELECT * FROM performance_tracking WHERE portfolio_id=%s FOR UPDATE', (pid,))
    track = c.fetchone()
    for aid in sorted(ids):
        c.execute('SELECT id FROM accounts WHERE id=%s AND portfolio_id=%s FOR UPDATE', (aid,pid))
        if not c.fetchone(): raise ValueError('현재 포트폴리오의 계좌를 선택해주세요.')
    return track


def deposit(db,c,pid,row,track):
    amount = positive(row['krw_amount'])
    day = date.fromisoformat(row['event_date'])
    flow_id, created = row.get('existing_flow_id'), False
    if row['external']:
        if not track or day < track['baseline_date']:
            raise ValueError('6번 탭에서 시작 기준을 등록하고 기준일 이후의 입금을 기록해주세요.')
        c.execute('''SELECT id FROM performance_flows WHERE portfolio_id=%s AND account_id=%s
            AND event_date=%s AND currency='KRW' AND amount_krw=%s AND NOT voided''', (pid,row['account_id'],day,amount))
        matches = [r['id'] for r in c.fetchall()]
        if flow_id:
            if flow_id not in matches: raise ValueError('연결할 기존 입금 기록의 계좌·날짜·금액을 확인해주세요.')
            c.execute('SELECT id FROM nh_notice_items WHERE performance_flow_id=%s AND reversed_at IS NULL', (flow_id,))
            if c.fetchone(): raise ValueError('이 입금 기록은 이미 예수금 반영 여부를 처리했습니다.')
        else:
            if matches and not row['duplicate_confirmed']:
                raise ValueError('같은 입금 기록이 있습니다. 기존 기록을 연결하거나 별도 입금임을 확인해주세요.')
            flow_id, created = db.new_id(), True
            c.execute('''INSERT INTO performance_flows(id,portfolio_id,account_id,request_id,event_date,
                amount_krw,currency,native_amount,exchange_rate,notes)
                VALUES(%s,%s,%s,%s,%s,%s,'KRW',%s,1,%s)''',
                (flow_id,pid,row['account_id'],db.new_id(),day,amount,amount,row.get('notes') or 'NH 입금 알림 확인'))
            c.execute('UPDATE performance_tracking SET revision=revision+1 WHERE portfolio_id=%s', (pid,))
    elif flow_id:
        raise ValueError('내부 이체에는 외부 입금 기록을 연결할 수 없습니다.')
    delta = amount if row['apply_cash'] else number(0)
    source = row.get('source_account_id')
    if not row['external']:
        if not source or source == row['account_id'] or not row['apply_cash']:
            raise ValueError('내부 이체의 출금 계좌를 선택해주세요.')
        c.execute('SELECT deposit_krw FROM accounts WHERE id=%s', (source,))
        if number(c.fetchone()['deposit_krw'] or 0) < amount: raise ValueError('내부 이체의 출금 계좌 원화가 부족합니다.')
        c.execute('UPDATE accounts SET deposit_krw=deposit_krw-%s WHERE id=%s', (amount,source))
    if delta:
        c.execute('UPDATE accounts SET deposit_krw=deposit_krw+%s WHERE id=%s', (delta,row['account_id']))
    return dict(flow_id=flow_id,created_flow=created,delta_krw=str(delta),delta_usd='0')


def exchange(db,c,row):
    aid = row['account_id']
    moment = forex.event_time(row.get('occurred_at') or row['event_date']+'T00:00:00+09:00')
    c.execute('SELECT deposit_krw,deposit_usd FROM accounts WHERE id=%s', (aid,))
    cash = c.fetchone()
    state = forex.load_state(c,aid)
    if not state: raise ValueError('달러 시작 기준환율을 먼저 등록해주세요. 기존 달러 원가를 임의로 추정하지 않습니다.')
    forex.validate_state(state,cash,moment)
    krw,usd = positive(row['krw_amount']),positive(row['usd_amount'])
    if number(cash['deposit_krw'] or 0) < krw:
        raise ValueError('환전 전 원화 예수금이 부족합니다. 입금 알림을 먼저 추가하거나 원화 예수금을 조정해주세요.')
    balance,cost = receive(state['usd_balance'],state['cost_krw'],usd,krw)
    before = forex.snapshot(state)
    forex.save_state(c,aid,balance,cost,moment.date())
    c.execute('UPDATE accounts SET deposit_krw=deposit_krw-%s,deposit_usd=%s WHERE id=%s', (krw,balance,aid))
    event_id = forex.append_event(db,c,aid,'EXCHANGE_IN',moment,usd,krw,krw/usd,-krw,usd,before,
        forex.snapshot(dict(usd_balance=balance,cost_krw=cost,last_event_date=moment.date())),
        'NH 환전 알림 · 고시환율 '+str(row.get('quoted_rate') or '미제공'))
    if not row.get('occurred_at'):
        c.execute('UPDATE usd_cash_events SET occurred_at=NULL WHERE id=%s', (event_id,))
    return dict(usd_event_id=event_id,delta_krw=str(-krw),delta_usd=str(usd))


def commit(db,pid,payload):
    payload = plain(payload)
    conn = db.connect()
    try:
        c = conn.cursor(cursor_factory=RealDictCursor)
        rows = payload['rows']
        ids = sorted({r['account_id'] for r in rows} | {r['source_account_id'] for r in rows if r.get('source_account_id')})
        track = lock_scope(c,pid,ids)
        c.execute('SELECT * FROM nh_notice_batches WHERE portfolio_id=%s AND request_id=%s', (pid,payload['request_id']))
        existing = c.fetchone()
        if existing:
            if existing['payload'] != payload: raise ValueError('같은 저장 요청의 내용이 바뀌었습니다. 기존 저장 결과를 먼저 확인해주세요.')
            if existing['reversed_at']: raise ValueError('취소된 요청입니다. 새 알림 목록으로 다시 확인해주세요.')
            conn.rollback()
            return existing['result']
        for aid in ids:
            expected = payload['expected_cash'].get(aid)
            c.execute('SELECT deposit_krw,deposit_usd FROM accounts WHERE id=%s', (aid,))
            actual = c.fetchone()
            if not expected or any(abs(number(actual[k] or 0)-number(expected[k])) > number('0.000001') for k in ('deposit_krw','deposit_usd')):
                raise ValueError('확인 후 계좌 잔고가 변경되었습니다. 최신 잔고를 다시 확인해주세요.')
        before = checkpoint(c,ids)
        batch_id = db.new_id()
        c.execute('INSERT INTO nh_notice_batches(id,portfolio_id,request_id,payload,result,audit) VALUES(%s,%s,%s,%s,%s,%s)',
                  (batch_id,pid,payload['request_id'],Json(payload),Json({}),Json({})))
        results=[]
        for row in rows:
            day = date.fromisoformat(row['event_date'])
            if day > datetime.now(forex.KST).date(): raise ValueError('미래의 알림은 등록할 수 없습니다.')
            if row.get('occurred_at') and forex.event_time(row['occurred_at']).date() != day:
                raise ValueError('알림 날짜와 시각이 다릅니다.')
            if row['fingerprint']:
                c.execute('SELECT id FROM nh_notice_items WHERE portfolio_id=%s AND account_id=%s AND event_date=%s AND fingerprint=%s AND reversed_at IS NULL',
                          (pid,row['account_id'],day,row['fingerprint']))
                if c.fetchone() and not row['duplicate_confirmed']: raise ValueError('이미 반영한 알림입니다. 별도 거래인지 확인해주세요.')
            if row['kind']=='DEPOSIT':
                result=deposit(db,c,pid,row,track)
            elif row['kind']=='EXCHANGE_IN':
                c.execute("SELECT id FROM usd_cash_events WHERE account_id=%s AND event_date=%s AND kind='EXCHANGE_IN' AND usd_amount=%s AND krw_amount=%s AND reversed_at IS NULL",
                          (row['account_id'],day,row['usd_amount'],row['krw_amount']))
                if c.fetchone() and not row['duplicate_confirmed']: raise ValueError('동일한 환전 기록이 있습니다. 별도 환전인지 확인해주세요.')
                result=exchange(db,c,row)
            elif row['kind']=='BUY':
                ok,msg=trades.execute_trade(db,row['event_date'],row['account_id'],row['asset_id'],'BUY',row['quantity'],row['price'],
                    'KRW',1,'NAMUH_KAKAO',row['broker_order_no'],transaction=conn)
                if not ok: raise ValueError(msg)
                c.execute("SELECT id FROM trade_history WHERE account_id=%s AND trade_date=%s AND import_source='NAMUH_KAKAO' AND broker_order_no=%s", (row['account_id'],str(day),row['broker_order_no']))
                result=dict(trade_id=c.fetchone()['id'])
            else:
                value=number(row['krw_amount'])
                if value < 0: raise ValueError('원화 예수금은 0 이상이어야 합니다.')
                c.execute('SELECT deposit_krw FROM accounts WHERE id=%s', (row['account_id'],))
                old=number(c.fetchone()['deposit_krw'] or 0)
                c.execute('UPDATE accounts SET deposit_krw=%s WHERE id=%s', (value,row['account_id']))
                result=dict(delta_krw=str(value-old),delta_usd='0')
            item_id=db.new_id()
            c.execute('''INSERT INTO nh_notice_items(id,batch_id,portfolio_id,account_id,event_date,kind,fingerprint,payload,result,performance_flow_id,linked_trade_id,linked_usd_event_id)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (item_id,batch_id,pid,row['account_id'],day,row['kind'],row['fingerprint'],Json(row),Json(result),result.get('flow_id'),result.get('trade_id'),result.get('usd_event_id')))
            results.append(dict(id=item_id,kind=row['kind'],account_id=row['account_id'],**result))
        after=checkpoint(c,ids)
        result=plain(dict(batch_id=batch_id,items=results,balances={aid:after[aid]['cash'] for aid in ids}))
        c.execute('UPDATE nh_notice_batches SET result=%s,audit=%s WHERE id=%s', (Json(result),Json(dict(before=before,after=after)),batch_id))
        conn.commit()
        db.invalidate()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def undo(db,pid,batch_id):
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SELECT * FROM nh_notice_batches WHERE id=%s AND portfolio_id=%s', (batch_id,pid))
        batch=c.fetchone()
        if not batch: raise ValueError('반영 이력을 찾을 수 없습니다.')
        ids=sorted(batch['audit']['after'])
        lock_scope(c,pid,ids)
        c.execute('SELECT reversed_at FROM nh_notice_batches WHERE id=%s FOR UPDATE', (batch_id,))
        if c.fetchone()['reversed_at']:
            conn.rollback()
            return {'reversed':True}
        if checkpoint(c,ids)!=batch['audit']['after']:
            raise ValueError('이후 잔고·매매·환전 변경이 있습니다. 후속 거래부터 취소하고 잔고를 확인해주세요.')
        c.execute('SELECT * FROM nh_notice_items WHERE batch_id=%s ORDER BY sequence DESC', (batch_id,))
        items=c.fetchall()
        for item in items:
            row,result=item['payload'],item['result']
            if item['kind']=='BUY':
                ok,msg=trades.delete_trades(db,[result['trade_id']],transaction=conn)
                if not ok: raise ValueError(msg)
            elif item['kind']=='EXCHANGE_IN':
                forex.reverse_latest(c,item['account_id'],result['usd_event_id'])
            if result.get('created_flow'):
                c.execute('UPDATE performance_flows SET voided=TRUE WHERE id=%s', (result['flow_id'],))
                c.execute('UPDATE performance_tracking SET revision=revision+1 WHERE portfolio_id=%s', (pid,))
        for aid,old in batch['audit']['before'].items():
            c.execute('UPDATE accounts SET deposit_krw=%s,deposit_usd=%s WHERE id=%s', (old['cash']['deposit_krw'],old['cash']['deposit_usd'],aid))
            # Restore exact pre-import holdings, including legacy manually seeded costs.
            buys={r['asset_id'] for r in batch['payload']['rows'] if r['kind']=='BUY' and r['account_id']==aid}
            for asset_id in buys:
                prior=next((h for h in old['holdings'] if h['asset_id']==asset_id),None)
                if prior:
                    columns=[k for k in prior if k not in ('id','account_id','asset_id')]
                    c.execute('UPDATE holdings SET '+','.join(k+'=%s' for k in columns)+' WHERE account_id=%s AND asset_id=%s',
                              (*[prior[k] for k in columns],aid,asset_id))
                else:
                    c.execute('DELETE FROM holdings WHERE account_id=%s AND asset_id=%s',(aid,asset_id))
        c.execute('UPDATE nh_notice_items SET reversed_at=CURRENT_TIMESTAMP WHERE batch_id=%s', (batch_id,))
        c.execute('UPDATE nh_notice_batches SET reversed_at=CURRENT_TIMESTAMP WHERE id=%s', (batch_id,))
        conn.commit();db.invalidate()
        return {'reversed':True}
    except Exception:
        conn.rollback();raise
    finally:
        conn.close()


def read_context(db,pid,day):
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SELECT id,deposit_krw,deposit_usd FROM accounts WHERE portfolio_id=%s', (pid,))
        accounts=c.fetchall()
        c.execute('''SELECT f.*,EXISTS(SELECT 1 FROM nh_notice_items n WHERE n.performance_flow_id=f.id AND n.reversed_at IS NULL) AS cash_handled
            FROM performance_flows f WHERE portfolio_id=%s AND event_date=%s''', (pid,day))
        flows=c.fetchall()
        c.execute('SELECT account_id,fingerprint,payload FROM nh_notice_items WHERE portfolio_id=%s AND event_date=%s AND reversed_at IS NULL', (pid,day))
        notices=c.fetchall()
        c.execute('''SELECT t.* FROM trade_history t JOIN accounts a ON a.id=t.account_id
            WHERE a.portfolio_id=%s AND t.trade_date=%s''',(pid,str(day)))
        saved_trades=c.fetchall()
        c.execute("SELECT e.account_id,e.usd_amount,e.krw_amount FROM usd_cash_events e JOIN accounts a ON a.id=e.account_id WHERE a.portfolio_id=%s AND e.event_date=%s AND e.kind='EXCHANGE_IN' AND e.reversed_at IS NULL",(pid,day))
        exchanges=c.fetchall()
        c.execute('SELECT id,created_at,reversed_at,result FROM nh_notice_batches WHERE portfolio_id=%s ORDER BY created_at DESC LIMIT 10', (pid,))
        return dict(accounts=accounts,flows=flows,notices=notices,trades=saved_trades,exchanges=exchanges,batches=c.fetchall())
    finally:
        conn.close()
