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
        c.execute('SELECT COALESCE(MAX(sequence),0) AS n FROM ledger_adjustments WHERE account_id=%s AND reversed_at IS NULL',(aid,))
        correction_sequence=c.fetchone()['n']
        if correction_sequence:result[aid]['correction_sequence']=correction_sequence
    return plain(result)


def lock_scope(c, pid, ids, peers=()):
    owners = {}
    for aid in ids:
        c.execute('SELECT portfolio_id FROM accounts WHERE id=%s', (aid,))
        account = c.fetchone()
        if not account or (aid not in peers and account['portfolio_id'] != pid):
            raise ValueError('현재 포트폴리오의 계좌를 선택해주세요.')
        owners[aid] = account['portfolio_id']
    tracks = {}
    # Both portfolios use the same lock order, including opposite-direction transfers.
    for owner in sorted(set(owners.values()) | {pid}):
        c.execute('SELECT id FROM portfolios WHERE id=%s FOR UPDATE', (owner,))
        if not c.fetchone(): raise ValueError('포트폴리오를 찾을 수 없습니다.')
        c.execute('SELECT * FROM performance_tracking WHERE portfolio_id=%s FOR UPDATE', (owner,))
        tracks[owner] = c.fetchone()
    for aid in sorted(ids):
        c.execute('SELECT id FROM accounts WHERE id=%s AND portfolio_id=%s FOR UPDATE', (aid,owners[aid]))
        if not c.fetchone(): raise ValueError('계좌 소속이 변경되었습니다. 다시 확인해주세요.')
    return tracks, owners


def cash_flow(db, c, pid, aid, day, signed, track, existing, duplicate, notes):
    # Historical bookkeeping remains visible, but must not alter post-baseline returns.
    if not track or day < track['baseline_date']:
        if existing: raise ValueError('성과 기준일 이전 기록에는 성과 입출금을 연결할 수 없습니다.')
        return dict(flow_id=None,created_flow=False,flow_portfolio_id=pid)
    c.execute('''SELECT id FROM performance_flows WHERE portfolio_id=%s AND account_id=%s
        AND event_date=%s AND currency='KRW' AND amount_krw=%s AND NOT voided''', (pid,aid,day,signed))
    matches = [r['id'] for r in c.fetchall()]
    if existing:
        if existing not in matches: raise ValueError('연결할 기존 입출금 기록의 계좌·날짜·금액을 확인해주세요.')
        c.execute('SELECT id FROM nh_notice_items WHERE performance_flow_id=%s AND reversed_at IS NULL', (existing,))
        if c.fetchone(): raise ValueError('이 입출금 기록은 이미 예수금 반영 여부를 처리했습니다.')
        return dict(flow_id=existing,created_flow=False,flow_portfolio_id=pid)
    if matches and not duplicate:
        raise ValueError('같은 입출금 기록이 있습니다. 기존 기록을 연결하거나 별도 거래임을 확인해주세요.')
    ident = db.new_id()
    c.execute('''INSERT INTO performance_flows(id,portfolio_id,account_id,request_id,event_date,
        amount_krw,currency,native_amount,exchange_rate,notes)
        VALUES(%s,%s,%s,%s,%s,%s,'KRW',%s,1,%s)''', (ident,pid,aid,db.new_id(),day,signed,abs(signed),notes))
    c.execute('UPDATE performance_tracking SET revision=revision+1 WHERE portfolio_id=%s', (pid,))
    return dict(flow_id=ident,created_flow=True,flow_portfolio_id=pid)


def cash_notice(db, c, pid, row, tracks, owners):
    aid = row['account_id']
    day = date.fromisoformat(row['event_date'])
    amount = positive(row['krw_amount'])
    signed = amount if row['kind']=='DEPOSIT' else -amount
    peer = row.get('source_account_id') if row['kind']=='DEPOSIT' else row.get('destination_account_id')
    transfer = not row['external']
    if transfer:
        if not peer or peer==aid: raise ValueError('이체 상대 계좌를 선택해주세요.')
        cross = owners[peer]!=pid
        if cross and not row['duplicate_confirmed']:
            c.execute('''SELECT id FROM nh_notice_items WHERE portfolio_id=%s AND account_id=%s AND event_date=%s
                AND payload->>'peer_account_id'=%s AND CAST(payload->>'krw_amount' AS NUMERIC)=%s AND reversed_at IS NULL''',
                (pid,aid,day,peer,amount))
            if c.fetchone(): raise ValueError('같은 계좌 간 이체가 이미 반영되어 있습니다. 입금·출금 알림을 각각 등록하지 마세요.')
        if cross != bool(row.get('cross_portfolio')): raise ValueError('이체 구분과 상대 계좌의 포트폴리오를 확인해주세요.')
    else:
        if peer or row.get('cross_portfolio') or row.get('counterparty_flow_id'):
            raise ValueError('외부 입출금에는 이체 상대 계좌를 지정할 수 없습니다.')
        cross = False
    entries = [(aid,pid,signed,row.get('existing_flow_id'))]
    if transfer: entries.append((peer,owners[peer],-signed,row.get('counterparty_flow_id')))
    if transfer and not cross and any(e[3] for e in entries):
        raise ValueError('내부 이체에는 외부 입출금 기록을 연결할 수 없습니다.')
    result_entries = []
    for account,owner,delta,existing in entries:
        track = tracks[owner]
        if row['apply_cash'] and track and day < track['baseline_date']:
            raise ValueError('성과 기준일 이전 거래는 잔고에 이미 반영됨 · 기록만 저장으로 등록해주세요.')
        flow = cash_flow(db,c,owner,account,day,delta,track,existing,row['duplicate_confirmed'],
            row.get('notes') or ('포트폴리오 간 원화 이체' if cross else 'NH 입출금 알림 확인')) if (not transfer or cross) else dict(flow_id=None,created_flow=False)
        applied = delta if row['apply_cash'] else number(0)
        if applied:
            c.execute('SELECT deposit_krw FROM accounts WHERE id=%s', (account,))
            if number(c.fetchone()['deposit_krw'] or 0)+applied < 0:
                raise ValueError('출금 계좌의 원화 예수금이 부족합니다. 이미 반영된 거래인지 확인해주세요.')
            c.execute('UPDATE accounts SET deposit_krw=deposit_krw+%s WHERE id=%s', (applied,account))
        result_entries.append(dict(account_id=account,portfolio_id=owner,kind='DEPOSIT' if delta>0 else 'WITHDRAW',
                                   result=dict(**flow,delta_krw=str(applied),delta_usd='0')))
    return result_entries if cross else result_entries[:1]


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
        peers = {r.get('source_account_id') if r['kind']=='DEPOSIT' else r.get('destination_account_id') for r in rows if r['kind'] in ('DEPOSIT','WITHDRAW') and not r['external']} - {None,''}
        primary = {r['account_id'] for r in rows}
        ids = sorted(primary | peers)
        for aid in primary:
            c.execute('SELECT id FROM accounts WHERE id=%s AND portfolio_id=%s', (aid,pid))
            if not c.fetchone(): raise ValueError('현재 포트폴리오의 계좌를 선택해주세요.')
        tracks,owners = lock_scope(c,pid,ids,peers)
        c.execute('SELECT * FROM nh_notice_batches WHERE portfolio_id=%s AND request_id=%s', (pid,payload['request_id']))
        existing = c.fetchone()
        if existing:
            prior=plain(existing['payload'])
            for old_row in prior['rows']:
                for key,value in dict(destination_account_id=None,cross_portfolio=False,counterparty_flow_id=None,reported_available_krw=None).items():
                    old_row.setdefault(key,value)
            if prior != payload: raise ValueError('같은 저장 요청의 내용이 바뀌었습니다. 기존 저장 결과를 먼저 확인해주세요.')
            if existing['reversed_at']: raise ValueError('취소된 요청입니다. 새 알림 목록으로 다시 확인해주세요.')
            conn.rollback()
            return existing['result']
        if any(r['kind']=='KRW_ADJUST' for r in rows):
            raise ValueError('예수금 직접 덮어쓰기는 중단했습니다. 5번 탭의 장부 정정을 이용해주세요.')
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
            cash_entries = None
            if row['kind'] in ('DEPOSIT','WITHDRAW'):
                cash_entries=cash_notice(db,c,pid,row,tracks,owners)
                result=cash_entries[0]['result']
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
            entries=cash_entries or [dict(account_id=row['account_id'],portfolio_id=pid,kind=row['kind'],result=result)]
            for entry in entries:
                item_id=db.new_id()
                stored_row=dict(row,account_id=entry['account_id'],kind=entry['kind'])
                if len(entries)>1:
                    other=next(e for e in entries if e['account_id']!=entry['account_id'])
                    stored_row.update(transfer=True,peer_account_id=other['account_id'],
                        source_account_id=other['account_id'] if entry['kind']=='DEPOSIT' else None,
                        destination_account_id=other['account_id'] if entry['kind']=='WITHDRAW' else None)
                entry_result=entry['result']
                c.execute('''INSERT INTO nh_notice_items(id,batch_id,portfolio_id,account_id,event_date,kind,fingerprint,payload,result,performance_flow_id,linked_trade_id,linked_usd_event_id)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (item_id,batch_id,entry['portfolio_id'],entry['account_id'],day,entry['kind'],row['fingerprint'],Json(stored_row),Json(entry_result),entry_result.get('flow_id'),entry_result.get('trade_id'),entry_result.get('usd_event_id')))
                results.append(dict(id=item_id,kind=entry['kind'],account_id=entry['account_id'],**entry_result))
        after=checkpoint(c,ids)
        result=plain(dict(batch_id=batch_id,notice_count=len(rows),affected_portfolios=sorted(tracks),performance_portfolios=sorted(p for p,t in tracks.items() if t),items=results,balances={aid:after[aid]['cash'] for aid in ids}))
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
        c.execute('''SELECT * FROM nh_notice_batches b WHERE id=%s AND (portfolio_id=%s OR EXISTS(
            SELECT 1 FROM nh_notice_items n WHERE n.batch_id=b.id AND n.portfolio_id=%s))''', (batch_id,pid,pid))
        batch=c.fetchone()
        if not batch: raise ValueError('반영 이력을 찾을 수 없습니다.')
        ids=sorted(batch['audit']['after'])
        tracks,_ = lock_scope(c,batch['portfolio_id'],ids,ids)
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
                c.execute('UPDATE performance_tracking SET revision=revision+1 WHERE portfolio_id=%s', (result.get('flow_portfolio_id',pid),))
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
        return {'reversed':True,'affected_portfolios':sorted({r['portfolio_id'] for r in items}),'performance_portfolios':sorted(p for p,t in tracks.items() if t)}
    except Exception:
        conn.rollback();raise
    finally:
        conn.close()


def read_context(db,pid,day):
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SELECT portfolio_id,baseline_date FROM performance_tracking')
        trackings={r['portfolio_id']:r for r in c.fetchall()}
        c.execute('''SELECT a.id,a.portfolio_id,a.account_alias,a.deposit_krw,a.deposit_usd,p.name AS portfolio_name
            FROM accounts a JOIN portfolios p ON p.id=a.portfolio_id''')
        transfer_accounts=c.fetchall()
        c.execute('SELECT id,deposit_krw,deposit_usd FROM accounts WHERE portfolio_id=%s', (pid,))
        accounts=c.fetchall()
        c.execute('''SELECT f.*,EXISTS(SELECT 1 FROM nh_notice_items n WHERE n.performance_flow_id=f.id AND n.reversed_at IS NULL) AS cash_handled
            FROM performance_flows f WHERE event_date=%s''', (day,))
        all_flows=c.fetchall()
        flows=[f for f in all_flows if f['portfolio_id']==pid]
        c.execute('SELECT account_id,fingerprint,payload FROM nh_notice_items WHERE portfolio_id=%s AND event_date=%s AND reversed_at IS NULL', (pid,day))
        notices=c.fetchall()
        c.execute('''SELECT t.* FROM trade_history t JOIN accounts a ON a.id=t.account_id
            WHERE a.portfolio_id=%s AND t.trade_date=%s''',(pid,str(day)))
        saved_trades=c.fetchall()
        c.execute("SELECT e.account_id,e.usd_amount,e.krw_amount FROM usd_cash_events e JOIN accounts a ON a.id=e.account_id WHERE a.portfolio_id=%s AND e.event_date=%s AND e.kind='EXCHANGE_IN' AND e.reversed_at IS NULL",(pid,day))
        exchanges=c.fetchall()
        c.execute('''SELECT id,created_at,reversed_at,result FROM nh_notice_batches b WHERE portfolio_id=%s OR EXISTS(
            SELECT 1 FROM nh_notice_items n WHERE n.batch_id=b.id AND n.portfolio_id=%s) ORDER BY created_at DESC LIMIT 10''', (pid,pid))
        return dict(accounts=accounts,transfer_accounts=transfer_accounts,trackings=trackings,transfer_flows=all_flows,flows=flows,notices=notices,trades=saved_trades,exchanges=exchanges,batches=c.fetchall())
    finally:
        conn.close()
