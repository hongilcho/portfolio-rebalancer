import json
"""Performance bookkeeping only; external-flow records never adjust actual cash."""
from datetime import datetime, timezone, timedelta
from psycopg2.extras import RealDictCursor, Json
from logic.period_performance import report_periods, report_daily


def today():
    return (datetime.now(timezone.utc)+timedelta(hours=9)).date()


def capture(ctx, pid, value, payload, *, start=False):
    # Old clients must never overwrite a closing snapshot with a live quote.
    if not start:
        return False
    day=today()
    with ctx.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        # Serialize initial registration and same-day writes by portfolio.
        c.execute('SELECT id FROM portfolios WHERE id=%s FOR UPDATE', (pid,))
        if not c.fetchone():
            raise ValueError('포트폴리오를 찾을 수 없습니다.')
        c.execute('SELECT * FROM performance_tracking WHERE portfolio_id=%s FOR UPDATE', (pid,))
        tracking=c.fetchone()
        if start:
            if tracking:
                raise ValueError('이미 시작 기준이 등록되어 있습니다.')
            if value<=0:
                raise ValueError('시작 평가액이 양수여야 합니다.')
            c.execute('''INSERT INTO performance_tracking(portfolio_id,baseline_date,baseline_value,baseline_payload,close_started_on)
                VALUES(%s,%s,%s,%s,%s)''', (pid,day,value,Json(payload),day))
        elif not tracking:
            return False
        c.execute('SELECT value_krw FROM performance_snapshots WHERE portfolio_id=%s AND snapshot_date=%s', (pid,day))
        prior=c.fetchone()
        if prior and abs(float(prior['value_krw'])-value)>1e-6:
            # Later same-day balances may contain a new, not-yet-recorded flow.
            c.execute('''UPDATE performance_tracking SET confirmed_through=LEAST(confirmed_through,%s)
                WHERE portfolio_id=%s AND confirmed_through IS NOT NULL''', (day-timedelta(days=1),pid))
        c.execute('''INSERT INTO performance_snapshots(portfolio_id,snapshot_date,value_krw,payload,record_kind)
            VALUES(%s,%s,%s,%s,'baseline')''', (pid,day,value,Json(payload)))
        conn.commit()
        return True


def read(ctx, pid):
    with ctx.connect() as conn, conn.cursor() as c:
        c.execute('''SELECT json_build_object(
            'tracking',(SELECT row_to_json(t) FROM (SELECT portfolio_id,baseline_date,baseline_value,created_at,
                revision,confirmed_revision,confirmed_through,close_started_on FROM performance_tracking WHERE portfolio_id=%s) t),
            'snapshots',COALESCE((SELECT json_agg(s ORDER BY snapshot_date) FROM
                (SELECT portfolio_id,snapshot_date,value_krw,recorded_at,record_kind,valuation_at,previous_close_date,
                    payload->>'ledger_at' AS ledger_at,payload->'fx' AS fx,payload->>'baseline_kind' AS baseline_kind,
                    (SELECT json_agg(p.value) FROM jsonb_each(CASE WHEN record_kind IN ('close','baseline')
                        AND jsonb_typeof(payload->'prices')='object' THEN payload->'prices' ELSE '{}'::jsonb END) p) AS closes
                    FROM performance_snapshots WHERE portfolio_id=%s) s),'[]'::json),
            'close_jobs',COALESCE((SELECT json_agg(j ORDER BY snapshot_date DESC) FROM
                (SELECT snapshot_date,state,attempts,error,updated_at FROM performance_close_jobs WHERE portfolio_id=%s ORDER BY snapshot_date DESC LIMIT 10) j),'[]'::json),
            'missed_close_count',(SELECT COUNT(*) FROM performance_close_jobs WHERE portfolio_id=%s AND state='missed'),
            'ledger_checks',COALESCE((SELECT json_agg(json_build_object('key',h->>'key','date',h->>'date','decision',h->>'decision')) FROM ledger_adjustments l CROSS JOIN LATERAL jsonb_array_elements(l.history) h WHERE l.portfolio_id=%s AND l.reversed_at IS NULL AND h->>'decision'='UNKNOWN'),'[]'::json),
            'flows',COALESCE((SELECT json_agg(f ORDER BY event_date DESC,recorded_at DESC) FROM performance_flows f WHERE portfolio_id=%s),'[]'::json))''', (pid,pid,pid,pid,pid,pid))
        result=c.fetchone()[0]
    # SQL JSON dates are ISO strings; calculations keep real dates.
    from datetime import date
    tracking=result['tracking']
    if tracking:
        for key in ('baseline_date','confirmed_through','close_started_on'):
            if tracking[key]: tracking[key]=date.fromisoformat(tracking[key])
    for item in result['snapshots']:
        item['snapshot_date']=date.fromisoformat(item['snapshot_date'])
        if item['previous_close_date']:
            item['previous_close_date']=date.fromisoformat(item['previous_close_date'])
    for item in result['flows']:
        item['event_date']=date.fromisoformat(item['event_date'])
    corrections=[{'history':result.pop('ledger_checks',[])}]
    result['reports']=report_periods(tracking,result['snapshots'],result['flows'])
    result['daily_reports']=report_daily(tracking,result['snapshots'],result['flows'])
    from logic.ledger_reconciliation import mask_uncertain
    return mask_uncertain(result,corrections)


def add_flow(ctx,pid,data):
    with ctx.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SELECT * FROM performance_tracking WHERE portfolio_id=%s FOR UPDATE', (pid,))
        t=c.fetchone()
        if not t or not t['baseline_date']<=data['event_date']<=today():
            raise ValueError('시작 기준 등록 이후부터 오늘까지의 실제 외부 입출금만 기록해주세요.')
        c.execute('SELECT id FROM accounts WHERE id=%s AND portfolio_id=%s', (data['account_id'],pid))
        if not c.fetchone():
            raise ValueError('선택한 포트폴리오의 계좌만 사용할 수 있습니다.')
        amount=data['native_amount']*(data['exchange_rate'] if data['currency']=='USD' else 1)
        signed=amount if data['direction']=='DEPOSIT' else -amount
        c.execute('SELECT * FROM performance_flows WHERE portfolio_id=%s AND request_id=%s', (pid,data['request_id']))
        existing=c.fetchone()
        if existing:
            if existing['voided']:
                raise ValueError('이 요청으로 기록된 입출금은 취소되어 있습니다. 기존 기록을 확인해주세요.')
            same=(existing['event_date']==data['event_date'] and existing['account_id']==data['account_id'] and
                  existing['currency']==data['currency'] and float(existing['native_amount'])==data['native_amount'] and
                  abs(float(existing['amount_krw'])-signed)<1e-6 and existing['notes']==data['notes'])
            if not same: raise ValueError('같은 요청 번호에 다른 내용이 있습니다. 새 입력으로 다시 기록해주세요.')
            return existing['id']
        ident=ctx.new_id()
        c.execute('''INSERT INTO performance_flows(id,portfolio_id,account_id,request_id,event_date,amount_krw,
            currency,native_amount,exchange_rate,notes) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (ident,pid,data['account_id'],data['request_id'],data['event_date'],signed,data['currency'],
             data['native_amount'],data['exchange_rate'] if data['currency']=='USD' else 1,data['notes']))
        c.execute('UPDATE performance_tracking SET revision=revision+1 WHERE portfolio_id=%s', (pid,))
        conn.commit()
        return ident


def void_flow(ctx,pid,ident,voided):
    with ctx.connect() as conn, conn.cursor() as c:
        c.execute('SELECT portfolio_id FROM performance_tracking WHERE portfolio_id=%s FOR UPDATE', (pid,))
        c.execute('SELECT id FROM nh_notice_items WHERE performance_flow_id=%s AND reversed_at IS NULL', (ident,))
        if c.fetchone():
            raise ValueError('예수금과 연결된 입출금은 NH 알림 가져오기의 반영 이력에서 묶음 취소해주세요.')
        c.execute("SELECT result FROM bookkeeping_requests WHERE result->>'flow_id'=%s",(ident,))
        for row in c.fetchall():
            value=row['result'] if isinstance(row,dict) else row[0]
            linked=value if isinstance(value,dict) else json.loads(value)
            if linked.get('created_flow') or not linked.get('reversed'):
                raise ValueError('달러 잔고와 함께 반영한 입출금은 5번 탭 달러 기록에서 함께 취소해주세요.')
        c.execute('UPDATE performance_flows SET voided=%s WHERE id=%s AND portfolio_id=%s AND voided<>%s', (voided,ident,pid,voided))
        if c.rowcount:
            c.execute('UPDATE performance_tracking SET revision=revision+1 WHERE portfolio_id=%s', (pid,))
        conn.commit()


def confirm(ctx,pid,revision,through,value):
    with ctx.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SELECT revision FROM performance_tracking WHERE portfolio_id=%s FOR UPDATE', (pid,))
        t=c.fetchone()
        if not t: raise ValueError('시작 기준을 먼저 등록해주세요.')
        c.execute('SELECT snapshot_date,value_krw FROM performance_snapshots WHERE portfolio_id=%s ORDER BY snapshot_date DESC LIMIT 1', (pid,))
        snapshot=c.fetchone()
        if t['revision']!=revision or not snapshot or snapshot['snapshot_date']!=through or abs(float(snapshot['value_krw'])-value)>1e-6:
            raise ValueError('확인 중 평가액이나 입출금 기록이 바뀌었습니다. 최신 내역을 확인한 뒤 다시 확인해주세요.')
        c.execute('UPDATE performance_tracking SET confirmed_revision=revision,confirmed_through=%s WHERE portfolio_id=%s', (through,pid))
        conn.commit()
