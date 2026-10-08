"""Audited, previewed ledger corrections. Never send broker orders."""
from datetime import date,datetime
import json
from psycopg2.extras import RealDictCursor,Json
from data.repositories import nh_notices,forex
from logic.ledger_reconciliation import serial,digest,adjustment_delta,history_plan,correct_payload


def read_state(c,pid,aid,lock=False):
    suffix=' FOR UPDATE' if lock else ''
    c.execute('SELECT id FROM portfolios WHERE id=%s'+suffix,(pid,))
    if not c.fetchone():raise ValueError('포트폴리오를 찾을 수 없습니다.')
    c.execute('SELECT * FROM performance_tracking WHERE portfolio_id=%s'+suffix,(pid,));tracking=c.fetchone()
    c.execute('SELECT id FROM accounts WHERE id=%s AND portfolio_id=%s'+suffix,(aid,pid))
    if not c.fetchone():raise ValueError('현재 포트폴리오의 계좌를 선택해주세요.')
    state=nh_notices.checkpoint(c,[aid])[aid]
    c.execute('SELECT * FROM performance_snapshots WHERE portfolio_id=%s ORDER BY snapshot_date'+suffix,(pid,));snapshots=c.fetchall()
    c.execute('SELECT id FROM ledger_adjustments WHERE portfolio_id=%s AND reversed_at IS NULL ORDER BY sequence',(pid,))
    return state,tracking,snapshots,[r['id'] for r in c.fetchall()]


def validate(c,pid,p,before,tracking):
    today=datetime.now(forex.KST).date()
    if date.fromisoformat(p['event_date'])>today:raise ValueError('미래 날짜는 등록할 수 없습니다.')
    if len(p['reason'].strip())<3:raise ValueError('정정 사유를 입력해주세요.')
    if p['first_buy_date'] and date.fromisoformat(p['first_buy_date'])>today:raise ValueError('배당 산정 시작일은 미래일 수 없습니다.')
    if p['kind']=='PAST_WITHDRAWAL' and p['amount']<=0:raise ValueError('누락된 출금 금액을 입력해주세요.')
    if p['kind']=='PAST_WITHDRAWAL' and (not tracking or p['event_date']>=str(tracking['baseline_date'])):
        raise ValueError('과거 출금 누락 보정은 성과 기준일 이전 출금에 사용합니다. 이후 출금은 입출금 기록으로 등록해주세요.')
    if p['kind']=='PAST_WITHDRAWAL':
        c.execute("SELECT request,reason FROM ledger_adjustments WHERE account_id=%s AND event_date=%s AND kind='PAST_WITHDRAWAL' AND reversed_at IS NULL",(p['account_id'],p['event_date']))
        if any(r['reason']==p['reason'] and r['request']['proposal']['amount']==p['amount'] for r in c.fetchall()):
            raise ValueError('같은 날짜·금액·사유의 과거 출금 정정이 이미 있습니다. 기존 기록을 먼저 확인해주세요.')
    if p['kind']=='HOLDING':
        c.execute('SELECT * FROM assets WHERE id=%s AND portfolio_id=%s',(p['asset_id'],pid));asset=c.fetchone()
        if not asset or asset['is_deposit']:raise ValueError('현재 포트폴리오의 주식·ETF·금 종목을 선택해주세요.')
        allowed=asset.get('allowed_accounts') or []
        if isinstance(allowed,str):allowed=json.loads(allowed)
        if allowed and p['account_id'] not in allowed:raise ValueError('이 종목의 허용 계좌를 확인해주세요.')
        if asset['market']=='KR' and p['quantity']>0 and p['avg_price']<=0:raise ValueError('확인한 원화 매입단가가 필요합니다.')
        if asset['market']=='US' and (p['avg_price_usd']<=0 or p['buy_fx_rate']<=0) and p['quantity']>0:
            raise ValueError('미국 자산은 달러 매입단가와 확인한 매입환율이 필요합니다.')
    else:
        key='deposit_usd' if p['currency']=='USD' else 'deposit_krw'
        target=float(before['cash'][key] or 0)+adjustment_delta(p,before)
        if target<0:raise ValueError('정정 후 예수금이 음수가 됩니다.')
        if p['currency']=='USD' and target>0 and p['usd_average_rate']<=0:
            raise ValueError('달러 잔고 정정에는 확인한 평균 취득환율이 필요합니다.')


def preview(db,pid,p):
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        before,track,snapshots,active=read_state(c,pid,p['account_id'])
        validate(c,pid,p,before,track)
        rows=history_plan(p,before,track,snapshots)
        return dict(token=digest([p,before,track,snapshots,active]),before=before,delta=adjustment_delta(p,before),history=rows)
    finally:conn.close()


def update_history(c,pid,p,before,track,snapshots,decisions,keys=None):
    plan=history_plan(p,before,track,snapshots,keys);entries=[]
    if set(decisions)-{r['key'] for r in plan}:raise ValueError('확인한 평가 기록 목록이 변경되었습니다.')
    for r in plan:
        decision=decisions.get(r['key'],'UNKNOWN')
        entry=dict(key=r['key'],date=r['date'],decision=decision)
        if decision=='ERROR':
            if not r['can_correct']:raise ValueError(r['error'] or '보정 근거가 부족합니다.')
            old=track if r['key']=='baseline' else next(s for s in snapshots if str(s['snapshot_date'])==r['key'])
            payload=old['baseline_payload'] if r['key']=='baseline' else old['payload']
            fixed,_=correct_payload(payload,p,adjustment_delta(p,before))[0]
            entry.update(before=serial(old),after_value=r['corrected_value'],after_payload=fixed)
            if r['key']=='baseline':
                c.execute('UPDATE performance_tracking SET baseline_value=%s,baseline_payload=%s WHERE portfolio_id=%s',(r['corrected_value'],Json(fixed),pid))
            else:
                c.execute('''INSERT INTO performance_snapshot_revisions(portfolio_id,snapshot_date,value_krw,payload,record_kind,recorded_at)
                    SELECT portfolio_id,snapshot_date,value_krw,payload,record_kind,recorded_at FROM performance_snapshots WHERE portfolio_id=%s AND snapshot_date=%s''',(pid,r['key']))
                c.execute('UPDATE performance_snapshots SET value_krw=%s,payload=%s WHERE portfolio_id=%s AND snapshot_date=%s',(r['corrected_value'],Json(fixed),pid,r['key']))
        entries.append(entry)
    return entries


def apply_current(db,c,p,before,conn):
    aid=p['account_id'];day=datetime.now(forex.KST).date();trade_id=usd_id=None
    if p['kind']=='HOLDING':
        c.execute('SELECT market FROM assets WHERE id=%s',(p['asset_id'],));us=c.fetchone()['market']=='US'
        price=p['avg_price_usd'] if us else p['avg_price'];fx=p['buy_fx_rate'] if us else 1
        # INIT is an explicit quantity/cost anchor, never a broker purchase or a cash movement.
        prior=next((h for h in before['holdings'] if h['asset_id']==p['asset_id']),None)
        trade_id=db.new_id()
        c.execute('''INSERT INTO trade_history(id,trade_date,account_id,asset_id,trade_type,quantity,price,currency,exchange_rate,cash_delta_krw,cash_delta_usd)
            VALUES(%s,%s,%s,%s,'INIT',%s,%s,%s,%s,0,0)''',(trade_id,str(day),aid,p['asset_id'],p['quantity'],price,'USD' if us else 'KRW',fx))
        krw=round(price*fx,2) if us else price
        c.execute('''INSERT INTO holdings(id,account_id,asset_id,quantity,avg_price,avg_price_usd,buy_fx_rate,original_avg_price,original_avg_price_usd)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(account_id,asset_id) DO UPDATE SET
            quantity=EXCLUDED.quantity,avg_price=EXCLUDED.avg_price,avg_price_usd=EXCLUDED.avg_price_usd,buy_fx_rate=EXCLUDED.buy_fx_rate,
            original_avg_price=EXCLUDED.original_avg_price,original_avg_price_usd=EXCLUDED.original_avg_price_usd''',
            (db.new_id(),aid,p['asset_id'],p['quantity'],krw,price if us else 0,fx if us else 0,krw,price if us else 0))
        c.execute('UPDATE holdings SET first_buy_date=%s,manual_dividend_override=%s WHERE account_id=%s AND asset_id=%s',
            (p['first_buy_date'] or (prior or {}).get('first_buy_date') or '',p['manual_dividend_override'],aid,p['asset_id']))
    else:
        target=float(before['cash']['deposit_usd' if p['currency']=='USD' else 'deposit_krw'] or 0)+adjustment_delta(p,before)
        if p['currency']=='KRW':c.execute('UPDATE accounts SET deposit_krw=%s WHERE id=%s',(target,aid))
        else:
            cost=target*p['usd_average_rate']
            state=before['state']
            if state:
                forex.save_state(c,aid,target,cost,day)
            else:
                c.execute('INSERT INTO usd_cash_state(account_id,usd_balance,cost_krw,last_event_date) VALUES(%s,%s,%s,%s)',(aid,target,cost,str(day)))
            c.execute('UPDATE accounts SET deposit_usd=%s WHERE id=%s',(target,aid))
            usd_id=forex.append_event(db,c,aid,'RECONCILE',datetime.now(forex.KST),target,cost,p['usd_average_rate'],0,adjustment_delta(p,before),
                forex.snapshot(state or dict(usd_balance=before['cash']['deposit_usd'],cost_krw=0,last_event_date=day)),
                forex.snapshot(dict(usd_balance=target,cost_krw=cost,last_event_date=day)),p['reason'])
    return trade_id,usd_id


def commit(db,pid,request):
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor);p=request['proposal'];aid=p['account_id']
        before,track,snapshots,active=read_state(c,pid,aid,True)
        c.execute('SELECT * FROM ledger_adjustments WHERE portfolio_id=%s AND request_id=%s',(pid,request['request_id']));existing=c.fetchone()
        if existing:
            if existing['request']!=request or existing['reversed_at']:raise ValueError('기존 정정 요청의 내용이 다르거나 취소되었습니다.')
            conn.rollback();return dict(id=existing['id'],saved=True)
        validate(c,pid,p,before,track)
        if request['token']!=digest([p,before,track,snapshots,active]):raise ValueError('미리보기 이후 장부·성과 기록이 변경되었습니다. 다시 확인해주세요.')
        c.execute('SELECT state FROM performance_close_jobs WHERE portfolio_id=%s FOR UPDATE',(pid,))
        if any(j['state']=='running' for j in c.fetchall()):raise ValueError('종가 수집 중입니다. 완료 후 정정해주세요.')
        history=update_history(c,pid,p,before,track,snapshots,request['decisions'])
        trade_id,usd_id=apply_current(db,c,p,before,conn)
        after=nh_notices.checkpoint(c,[aid])[aid];ident=db.new_id()
        c.execute('''INSERT INTO ledger_adjustments(id,portfolio_id,account_id,request_id,event_date,kind,reason,request,before_state,after_state,history,trade_id,usd_event_id)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (ident,pid,aid,request['request_id'],p['event_date'],p['kind'],p['reason'],Json(request),Json(before),Json(after),Json(history),trade_id,usd_id))
        after=nh_notices.checkpoint(c,[aid])[aid]
        c.execute('UPDATE ledger_adjustments SET after_state=%s WHERE id=%s',(Json(after),ident))
        c.execute('UPDATE performance_tracking SET revision=revision+1 WHERE portfolio_id=%s',(pid,))
        # A waiting worker must collect today's corrected ledger, not its pre-correction copy.
        c.execute("UPDATE performance_close_jobs SET inputs=NULL WHERE portfolio_id=%s AND snapshot_date=%s AND state IN ('pending','retry')",(pid,str(datetime.now(forex.KST).date())))
        conn.commit();db.invalidate();return dict(id=ident,saved=True)
    except Exception:conn.rollback();raise
    finally:conn.close()


def read(db,pid):
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SELECT id,account_id,event_date,kind,reason,history,created_at,reversed_at FROM ledger_adjustments WHERE portfolio_id=%s ORDER BY sequence DESC LIMIT 100',(pid,))
        rows=c.fetchall()
        for a in rows:a['history']=[{k:h[k] for k in ('key','date','decision')} for h in a['history']]
        return dict(adjustments=rows)

def review_preview(db,pid,ident):
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SELECT * FROM ledger_adjustments WHERE id=%s AND portfolio_id=%s AND reversed_at IS NULL',(ident,pid));a=c.fetchone()
        if not a:raise ValueError('정정 이력을 찾을 수 없습니다.')
        _,track,snapshots,active=read_state(c,pid,a['account_id'])
        keys={h['key'] for h in a['history'] if h['decision']=='UNKNOWN'}
        return dict(token=digest([a,track,snapshots,active]),history=history_plan(a['request']['proposal'],a['before_state'],track,snapshots,keys))
    finally:conn.close()


def review(db,pid,ident,request):
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SELECT account_id FROM ledger_adjustments WHERE id=%s AND portfolio_id=%s',(ident,pid));ref=c.fetchone()
        if not ref:raise ValueError('정정 이력을 찾을 수 없습니다.')
        _,track,snapshots,active=read_state(c,pid,ref['account_id'],True)
        c.execute('SELECT * FROM ledger_adjustments WHERE id=%s FOR UPDATE',(ident,));a=c.fetchone()
        if a['reversed_at']:raise ValueError('취소된 정정입니다.')
        prior=next((r for r in a['reviews'] if r['request_id']==request['request_id']),None)
        if prior:
            if prior!=request:raise ValueError('같은 확인 요청의 내용이 다릅니다.')
            conn.rollback();return dict(id=ident,saved=True)
        if request['token']!=digest([a,track,snapshots,active]):raise ValueError('성과 기록이 변경되었습니다. 다시 확인해주세요.')
        c.execute('SELECT state FROM performance_close_jobs WHERE portfolio_id=%s FOR UPDATE',(pid,))
        if any(j['state']=='running' for j in c.fetchall()):raise ValueError('종가 수집 중입니다. 완료 후 확인해주세요.')
        keys={h['key'] for h in a['history'] if h['decision']=='UNKNOWN'}
        updates=update_history(c,pid,a['request']['proposal'],a['before_state'],track,snapshots,request['decisions'],keys)
        history=[next((u for u in updates if u['key']==h['key']),h) for h in a['history']]
        c.execute('UPDATE ledger_adjustments SET history=%s,reviews=%s WHERE id=%s',(Json(history),Json(a['reviews']+[request]),ident))
        c.execute('UPDATE performance_tracking SET revision=revision+1 WHERE portfolio_id=%s',(pid,))
        conn.commit();db.invalidate();return dict(id=ident,saved=True)
    except Exception:conn.rollback();raise
    finally:conn.close()


def undo(db,pid,ident):
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SELECT account_id FROM ledger_adjustments WHERE id=%s AND portfolio_id=%s',(ident,pid));ref=c.fetchone()
        if not ref:raise ValueError('정정 이력을 찾을 수 없습니다.')
        current,track,snapshots,active=read_state(c,pid,ref['account_id'],True)
        c.execute('SELECT * FROM ledger_adjustments WHERE id=%s FOR UPDATE',(ident,));a=c.fetchone()
        if a['reversed_at']:conn.rollback();return {'reversed':True}
        if not active or active[-1]!=ident or serial(current)!=a['after_state']:
            raise ValueError('후속 장부 변경이 있습니다. 최신 정정부터 취소하거나 새 정정으로 처리해주세요.')
        c.execute('SELECT state FROM performance_close_jobs WHERE portfolio_id=%s FOR UPDATE',(pid,))
        if any(j['state']=='running' for j in c.fetchall()):raise ValueError('종가 수집 중입니다. 완료 후 취소해주세요.')
        for h in a['history']:
            if h['decision']!='ERROR':continue
            old=h['before']
            now=track if h['key']=='baseline' else next((s for s in snapshots if str(s['snapshot_date'])==h['key']),None)
            v=now['baseline_value'] if h['key']=='baseline' else now['value_krw'] if now else None
            p=now['baseline_payload'] if h['key']=='baseline' else now['payload'] if now else None
            if v is None or abs(float(v)-h['after_value'])>1e-6 or serial(p)!=h['after_payload']:
                raise ValueError('후속 성과 기록 변경이 있습니다. 기존 정정을 직접 취소할 수 없습니다.')
            if h['key']=='baseline':
                c.execute('UPDATE performance_tracking SET baseline_value=%s,baseline_payload=%s WHERE portfolio_id=%s',(old['baseline_value'],Json(old['baseline_payload']),pid))
            else:
                c.execute('''INSERT INTO performance_snapshot_revisions(portfolio_id,snapshot_date,value_krw,payload,record_kind,recorded_at)
                    SELECT portfolio_id,snapshot_date,value_krw,payload,record_kind,recorded_at FROM performance_snapshots WHERE portfolio_id=%s AND snapshot_date=%s''',(pid,h['key']))
                c.execute('UPDATE performance_snapshots SET value_krw=%s,payload=%s WHERE portfolio_id=%s AND snapshot_date=%s',(old['value_krw'],Json(old['payload']),pid,h['key']))
        before=a['before_state'];aid=a['account_id'];p=a['request']['proposal']
        if a['trade_id']:c.execute('DELETE FROM trade_history WHERE id=%s',(a['trade_id'],))
        if p['kind']=='HOLDING':
            old=next((h for h in before['holdings'] if h['asset_id']==p['asset_id']),None)
            if old:
                columns=[k for k in old if k not in ('id','account_id','asset_id')]
                c.execute('UPDATE holdings SET '+','.join(k+'=%s' for k in columns)+' WHERE account_id=%s AND asset_id=%s',(*[old[k] for k in columns],aid,p['asset_id']))
            else:c.execute('DELETE FROM holdings WHERE account_id=%s AND asset_id=%s',(aid,p['asset_id']))
        if a['usd_event_id']:
            c.execute('UPDATE usd_cash_events SET reversed_at=CURRENT_TIMESTAMP WHERE id=%s',(a['usd_event_id'],))
            state=before['state']
            if state:forex.save_state(c,aid,state['usd_balance'],state['cost_krw'],state['last_event_date'])
            else:c.execute('DELETE FROM usd_cash_state WHERE account_id=%s',(aid,))
        c.execute('UPDATE accounts SET deposit_krw=%s,deposit_usd=%s WHERE id=%s',(before['cash']['deposit_krw'],before['cash']['deposit_usd'],aid))
        c.execute('UPDATE ledger_adjustments SET reversed_at=CURRENT_TIMESTAMP WHERE id=%s',(ident,))
        c.execute('UPDATE performance_tracking SET revision=revision+1 WHERE portfolio_id=%s',(pid,))
        c.execute("UPDATE performance_close_jobs SET inputs=NULL WHERE portfolio_id=%s AND snapshot_date=%s AND state IN ('pending','retry')",(pid,str(datetime.now(forex.KST).date())))
        conn.commit();db.invalidate();return {'reversed':True}
    except Exception:conn.rollback();raise
    finally:conn.close()


def account(db,pid,aid):
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SELECT id FROM accounts WHERE id=%s AND portfolio_id=%s',(aid,pid))
        if not c.fetchone():raise ValueError('현재 포트폴리오의 계좌를 선택해주세요.')
        state=nh_notices.checkpoint(c,[aid])[aid]
        c.execute('SELECT baseline_date FROM performance_tracking WHERE portfolio_id=%s',(pid,))
        track=c.fetchone()
        return dict(state=state,baseline_date=track['baseline_date'] if track else None)
