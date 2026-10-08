"""Short database leases work with transaction pooling and overlapping deployments.

No network calls run inside a DB transaction. A stale worker cannot publish.
Frozen ledger/FX/partial prices survive a restart; unobserved past ledgers are
explicitly missing rather than reconstructed from today's balances.
"""
from datetime import timedelta
from psycopg2.extras import RealDictCursor, Json


class LeaseLost(RuntimeError):
    pass


def tracking(ctx):
    with ctx.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('''SELECT t.portfolio_id,t.close_started_on,t.created_at,
            (SELECT MAX(snapshot_date) FROM performance_close_jobs j WHERE j.portfolio_id=t.portfolio_id) AS last_job_date
            FROM performance_tracking t''')
        return list(c.fetchall())


def schedule(ctx, pid, days, today):
    if not days:
        return
    with ctx.connect() as conn, conn.cursor() as c:
        c.execute('SELECT portfolio_id FROM performance_tracking WHERE portfolio_id=%s FOR UPDATE',(pid,))
        for day in days:
            past = day < today
            c.execute('''INSERT INTO performance_close_jobs(portfolio_id,snapshot_date,state,error)
                VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING''', (pid, day,
                'missed' if past else 'pending', '서버 미실행: 당시 장부·환율이 없어 과거 평가액을 만들지 않습니다.' if past else ''))
        conn.commit()


def claim(ctx, now, pid=None):
    token = ctx.new_id()
    with ctx.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        # Lock tracking before job rows, matching finish, retry and ledger correction.
        # Probe without locks, then revalidate under locks; another worker may win.
        c.execute('''SELECT portfolio_id FROM performance_close_jobs WHERE
            state IN ('pending','retry','running') AND next_attempt_at<=%s
            AND (lease_until IS NULL OR lease_until<=%s) AND (%s IS NULL OR portfolio_id=%s)
            ORDER BY snapshot_date DESC,portfolio_id LIMIT 1''',(now,now,pid,pid))
        candidate=c.fetchone()
        if not candidate:return None
        c.execute('SELECT portfolio_id FROM performance_tracking WHERE portfolio_id=%s FOR UPDATE SKIP LOCKED',(candidate['portfolio_id'],))
        if not c.fetchone():return None
        c.execute('''SELECT * FROM performance_close_jobs WHERE
            state IN ('pending','retry','running') AND next_attempt_at<=%s
            AND (lease_until IS NULL OR lease_until<=%s) AND portfolio_id=%s
            ORDER BY snapshot_date DESC FOR UPDATE SKIP LOCKED LIMIT 1''',(now,now,candidate['portfolio_id']))
        job=c.fetchone()
        if not job:return None
        c.execute('''UPDATE performance_close_jobs SET state='running',attempts=attempts+1,
            lease_token=%s,lease_until=%s,updated_at=%s WHERE portfolio_id=%s AND snapshot_date=%s''',
            (token, now+timedelta(minutes=10), now, job['portfolio_id'], job['snapshot_date']))
        conn.commit()
        return {**job, 'lease_token': token}


def progress(ctx, job, inputs, now):
    with ctx.connect() as conn, conn.cursor() as c:
        c.execute('''UPDATE performance_close_jobs SET inputs=%s,lease_until=%s,updated_at=%s
            WHERE portfolio_id=%s AND snapshot_date=%s AND lease_token=%s AND lease_until>%s AND state='running' ''',
            (Json(inputs), now+timedelta(minutes=10), now, job['portfolio_id'], job['snapshot_date'], job['lease_token'], now))
        if not c.rowcount:
            raise LeaseLost('종가 수집 작업이 다른 서버로 인계되었습니다.')
        conn.commit()


def fail(ctx, job, now, message, missed=False):
    with ctx.connect() as conn, conn.cursor() as c:
        c.execute('''UPDATE performance_close_jobs SET state=%s,error=%s,next_attempt_at=%s,
            lease_token=NULL,lease_until=NULL,updated_at=%s
            WHERE portfolio_id=%s AND snapshot_date=%s AND lease_token=%s AND state='running' ''',
            ('missed' if missed else 'retry', message[:500], now+timedelta(minutes=5), now,
             job['portfolio_id'], job['snapshot_date'], job['lease_token']))
        conn.commit()


def finish(ctx, job, value, payload, now):
    pid, day = job['portfolio_id'], job['snapshot_date']
    with ctx.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        # Same lock order as flow confirmation and explicit correction.
        c.execute('SELECT * FROM performance_tracking WHERE portfolio_id=%s FOR UPDATE', (pid,))
        track = c.fetchone()
        c.execute('SELECT * FROM performance_close_jobs WHERE portfolio_id=%s AND snapshot_date=%s FOR UPDATE', (pid, day))
        current = c.fetchone()
        if not current or current['lease_token'] != job['lease_token'] or current['state'] != 'running' or current['lease_until'] <= now:
            raise LeaseLost('만료된 작업은 평가액을 저장할 수 없습니다.')
        c.execute('''SELECT COALESCE(SUM(amount_krw),0) FROM performance_flows
            WHERE portfolio_id=%s AND NOT voided AND event_date BETWEEN %s AND %s''', (pid, track['baseline_date'], day))
        net = float(c.fetchone()['coalesce'])
        payload = {**payload, 'performance_at_capture': {'net_flow_krw': net,
            'profit_krw': value-float(track['baseline_value'])-net, 'flow_revision': track['revision']}}
        c.execute('''INSERT INTO performance_snapshot_revisions(portfolio_id,snapshot_date,value_krw,payload,record_kind,recorded_at)
            SELECT portfolio_id,snapshot_date,value_krw,payload,record_kind,recorded_at FROM performance_snapshots
            WHERE portfolio_id=%s AND snapshot_date=%s''', (pid, day))
        c.execute('''INSERT INTO performance_snapshots(portfolio_id,snapshot_date,value_krw,payload,record_kind,valuation_at,previous_close_date)
            VALUES(%s,%s,%s,%s,'close',%s,%s) ON CONFLICT(portfolio_id,snapshot_date) DO UPDATE SET
            value_krw=EXCLUDED.value_krw,payload=EXCLUDED.payload,record_kind='close',valuation_at=EXCLUDED.valuation_at,
            previous_close_date=EXCLUDED.previous_close_date,recorded_at=CURRENT_TIMESTAMP''',
            (pid, day, value, Json(payload), payload['valuation_at'], payload['previous_close_date']))
        c.execute('''UPDATE performance_tracking SET confirmed_through=LEAST(confirmed_through,%s)
            WHERE portfolio_id=%s AND confirmed_through IS NOT NULL''', (day-timedelta(days=1), pid))
        c.execute('''UPDATE performance_close_jobs SET state='complete',inputs=NULL,error='',
            lease_token=NULL,lease_until=NULL,updated_at=%s WHERE portfolio_id=%s AND snapshot_date=%s''', (now, pid, day))
        conn.commit()


def request_today(ctx, pid, day, now, batch):
    """Explicit same-day correction reuses frozen FX/closes, retaining an audit."""
    with ctx.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SELECT portfolio_id FROM performance_tracking WHERE portfolio_id=%s FOR UPDATE', (pid,))
        c.execute('SELECT * FROM performance_close_jobs WHERE portfolio_id=%s AND snapshot_date=%s FOR UPDATE', (pid, day))
        job = c.fetchone()
        if not job:
            return False
        if job['state'] == 'running' and job['lease_until'] and job['lease_until'] > now:
            raise ValueError('종가 수집 중입니다. 완료 후 다시 확인해주세요.')
        inputs = job['inputs']
        if job['state'] == 'complete':
            c.execute('SELECT payload FROM performance_snapshots WHERE portfolio_id=%s AND snapshot_date=%s AND record_kind=\'close\'', (pid, day))
            snapshot = c.fetchone()
            if not snapshot:
                raise ValueError('종가 기록을 찾을 수 없습니다.')
            inputs = {**snapshot['payload'], 'ledger': batch, 'ledger_at': now.isoformat(),
                      'correction': True}
        # Retrying pending collection keeps the original ledger. User can reflect
        # a late trade after it completes, with the explicit same-day correction.
        c.execute('''UPDATE performance_close_jobs SET state='pending',inputs=%s,next_attempt_at=%s,
            lease_token=NULL,lease_until=NULL,error='' WHERE portfolio_id=%s AND snapshot_date=%s''',
            (Json(inputs) if inputs else None, now, pid, day))
        conn.commit()
        return True
