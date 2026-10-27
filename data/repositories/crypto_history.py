"""Analysis journal and insert-once daily crypto valuations. No cash/trade writes."""
from datetime import datetime,timezone
import json
from psycopg2.extras import Json,RealDictCursor

from logic import crypto_history as policy

SCOPE='crypto-history-basis'


def lock(c):c.execute("SELECT pg_advisory_xact_lock(hashtext('crypto-holdings-history'))")


def holdings(c):
    c.execute('SELECT owner,symbol,quantity::double precision AS quantity,avg_price::double precision AS avg_price FROM crypto_holdings ORDER BY owner,symbol')
    return policy.book([dict(r) for r in c.fetchall()])


def events(c):
    c.execute('SELECT result FROM bookkeeping_requests WHERE scope=%s AND result IS NOT NULL ORDER BY sequence',(SCOPE,))
    return [r['result'] if isinstance(r['result'],dict) else json.loads(r['result']) for r in c.fetchall()]


def append(c,ident,event):
    payload={k:event[k] for k in ('fingerprint','confirmed_start','confirmed_through') if k in event}
    c.execute('SELECT payload FROM bookkeeping_requests WHERE scope=%s AND request_id=%s',(SCOPE,ident))
    prior=c.fetchone()
    if prior:
        if prior['payload']!=payload:raise ValueError('같은 복원 기준 번호의 내용이 다릅니다.')
        return
    c.execute('''INSERT INTO bookkeeping_requests(scope,request_id,payload,result) VALUES(%s,%s,%s,%s)
        ON CONFLICT(scope,request_id) DO NOTHING''',(SCOPE,ident,Json(payload),Json(event)))


def changed(c,ctx):
    """Called within the existing holding-edit transaction, after the update."""
    rows=holdings(c);saved=events(c)
    if not saved or saved[-1]['fingerprint']!=policy.fingerprint(rows):
        append(c,ctx.new_id(),policy.basis_event(rows,datetime.now(timezone.utc)))


def state(ctx):
    with ctx.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        result=dict(holdings=holdings(c),events=events(c))
        c.execute('SELECT snapshot_date FROM portfolio_analytics.crypto_snapshots ORDER BY snapshot_date')
        result['dates']={str(r['snapshot_date']) for r in c.fetchall()}
        conn.rollback()
    return result


def observe(ctx,expected,at):
    with ctx.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        lock(c);rows=holdings(c);saved=events(c)
        if policy.fingerprint(rows)!=expected:raise ValueError('조회 후 가상자산 장부가 변경되었습니다.')
        if saved:
            if saved[-1]['fingerprint']!=expected:raise ValueError('가상자산 변경 이력과 현재 장부가 다릅니다.')
            return saved[-1]
        event=policy.basis_event(rows,at);append(c,ctx.new_id(),event);conn.commit();return event


def capture(ctx,day,payload,expected_current,now=None):
    if policy.cutoff(day)>policy.moment(now or datetime.now(timezone.utc)):
        raise ValueError('아직 도달하지 않은 평가 시각입니다.')
    with ctx.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        lock(c)
        if policy.fingerprint(holdings(c))!=expected_current:raise ValueError('수집 중 보유 정보가 변경되었습니다.')
        seed=policy.basis_at(events(c),day)
        if not seed or seed['fingerprint']!=payload['holdings_fingerprint']:
            raise ValueError('평가 시점의 보유 근거가 변경되었습니다.')
        c.execute('''INSERT INTO portfolio_analytics.crypto_snapshots(snapshot_date,valuation_at,payload)
            VALUES(%s,%s,%s) ON CONFLICT(snapshot_date) DO NOTHING''',
            (day,payload['valuation_at'],Json(payload)))
        saved=c.rowcount==1;conn.commit();return saved


def apply_restore(ctx,manifest,now=None):
    """Explicit operator action only; a graph GET never calls this function."""
    seed=manifest['basis'];start=seed['confirmed_start'];end=seed['confirmed_through']
    expected=seed['fingerprint']
    now=now or datetime.now(timezone.utc)
    if policy.cutoff(end)>policy.moment(now):raise ValueError('아직 도달하지 않은 평가 시각입니다.')
    quotes={r['date']:r['payload']['prices'] for r in manifest['records']}
    rebuilt=policy.restore(seed['holdings'],quotes,start,end,seed['at'])
    if rebuilt!=manifest:raise ValueError('복원 자료의 수량·원가·시세·계산 결과를 다시 확인해주세요.')
    inserted=0
    with ctx.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        lock(c)
        if policy.fingerprint(holdings(c))!=expected:raise ValueError('복원 기준과 현재 장부가 다릅니다. 적용하지 않았습니다.')
        saved=events(c)
        candidate=policy.basis_event(seed['holdings'],now,start=start,end=end)
        # Reject a user attestation which contradicts an actual saved edit.
        for day in policy.days(start,end):policy.basis_at(saved+[candidate],day)
        ident='confirmed-'+start+'-'+end+'-'+expected[:16]
        append(c,ident,candidate)
        for row in manifest['records']:
            c.execute('''INSERT INTO portfolio_analytics.crypto_snapshots(snapshot_date,valuation_at,payload)
                VALUES(%s,%s,%s) ON CONFLICT(snapshot_date) DO NOTHING''',
                (row['date'],row['payload']['valuation_at'],Json(row['payload'])))
            inserted+=c.rowcount
        conn.commit()
    return dict(inserted=inserted,preserved=len(manifest['records'])-inserted,holdings_changed=False)
