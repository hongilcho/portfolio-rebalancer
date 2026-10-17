"""Analysis-only openings stored in the existing private request audit journal."""
from psycopg2.extras import RealDictCursor
from logic import realized_opening as policy
from logic.realized_gains import calculate
from data.repositories import bookkeeping
from data.repositories.nh_notices import lock_scope


def load(c,pid):
    c.execute('SELECT result FROM bookkeeping_requests WHERE scope=%s AND result IS NOT NULL ORDER BY sequence',(policy.SCOPE+pid,))
    return policy.active([r['result'] for r in c.fetchall()])


def positions(c,pid):
    c.execute('SELECT h.*,s.market FROM holdings h JOIN accounts a ON a.id=h.account_id JOIN assets s ON s.id=h.asset_id WHERE a.portfolio_id=%s AND s.portfolio_id=%s AND NOT COALESCE(s.is_deposit,FALSE)',(pid,pid))
    return c.fetchall()


def history(c,h):
    c.execute('SELECT * FROM trade_history WHERE account_id=%s AND asset_id=%s',(h['account_id'],h['asset_id']))
    return c.fetchall()


def replay(c,account_id,asset_id,rows,deleting=()):
    """Use the confirmed book seed when rebuilding later trades, never old overlap.

    The seed is in memory only. Covered history stays immutable while it is used;
    an obsolete/edited opening is never silently used to rewrite holdings.
    """
    from logic.trade_accounting import replay_holding
    c.execute('SELECT portfolio_id FROM accounts WHERE id=%s',(account_id,))
    account=c.fetchone()
    opening=next((p for p in load(c,account['portfolio_id']) if p['account_id']==str(account_id)
                  and p['asset_id']==str(asset_id)),None) if account else None
    if not opening:return replay_holding(rows)
    if policy.validity(opening,rows):
        raise ValueError('실현손익 계산 기준과 과거 기록이 다릅니다. 기존 기록을 보존한 상태로 별도 점검해주세요.')
    if set(map(str,deleting)) & set(opening['covered_trades']):
        raise ValueError('보존 중인 과거 기록입니다. 5번 탭의 장부 정정을 이용하거나 별도 점검해주세요.')
    usd=float(opening['avg_usd']);krw=float(opening['avg_krw'])
    seed=dict(id='confirmed-opening',trade_date=opening['date'],trade_type='INIT',
              quantity=float(opening['quantity']),price=usd if usd else krw,
              currency='USD' if usd else 'KRW',exchange_rate=krw/usd if usd else 1)
    return replay_holding([seed]+[r for r in rows if str(r['id']) not in opening['covered_trades']])


def preview(db,pid):
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        openings=load(c,pid);by_pair={(p['account_id'],p['asset_id']):p for p in openings}
        candidates=[];saved=[];unsupported=[]
        for h in positions(c,pid):
            pair=(str(h['account_id']),str(h['asset_id']));rows=history(c,h)
            p=by_pair.get(pair)
            if p:
                saved.append({**{k:v for k,v in p.items() if k!='covered_trades'},
                    'warning':policy.validity(p,rows),
                    'can_revoke':not any(t['trade_type']=='SELL' and str(t['id']) not in p['covered_trades'] for t in rows)})
                continue
            if float(h['quantity'] or 0)<=0:continue
            report=calculate(rows,[h])
            if not report['warnings']:continue
            item=dict(account_id=pair[0],asset_id=pair[1],quantity=h['quantity'],
                avg_krw=h.get('original_avg_price') or h.get('avg_price'),
                avg_usd=h.get('original_avg_price_usd') or h.get('avg_price_usd'),book_token=policy.token(h,rows))
            if any(t['trade_type']=='SELL' for t in rows):unsupported.append(item)
            else:candidates.append(item)
        return dict(candidates=candidates,openings=saved,unsupported=unsupported)
    finally:conn.close()


def commit(db,pid,payload,now=None,transaction=None):
    conn=transaction if transaction is not None else db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor);scope=policy.SCOPE+pid
        existing=bookkeeping.begin(c,scope,payload['request_id'],payload)
        if existing is not None:
            if transaction is None:conn.commit()
            return existing
        requested=payload['positions']
        if not 1<=len(requested)<=100:raise ValueError('기준을 확정할 종목을 선택해주세요.')
        pairs=[(str(p['account_id']),str(p['asset_id'])) for p in requested]
        if len(set(pairs))!=len(pairs):raise ValueError('같은 종목을 중복 선택할 수 없습니다.')
        lock_scope(c,pid,sorted({p[0] for p in pairs}))
        old={(p['account_id'],p['asset_id']):p for p in load(c,pid)}
        holdings={(str(h['account_id']),str(h['asset_id'])):h for h in positions(c,pid)}
        created=[]
        for request,pair in zip(requested,pairs):
            h=holdings.get(pair)
            if not h:raise ValueError('현재 포트폴리오의 보유 종목을 선택해주세요.')
            if pair in old:raise ValueError('이미 확정된 계산 기준이 있습니다. 기존 기준을 확인해주세요.')
            rows=history(c,h)
            if policy.token(h,rows)!=request['book_token']:
                raise ValueError('조회 후 장부가 변경되었습니다. 새로 조회하여 확인해주세요.')
            created.append(policy.create(pid,h,rows,payload['request_id'],now))
        result=dict(kind='REALIZED_OPENING',positions=created,holdings_changed=False,cash_changed=False)
        bookkeeping.finish(c,scope,payload['request_id'],result)
        if transaction is None:conn.commit();db.invalidate()
        return result
    except Exception:
        if transaction is None:conn.rollback()
        raise
    finally:
        if transaction is None:conn.close()


def revoke(db,pid,payload,transaction=None):
    conn=transaction if transaction is not None else db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor);scope=policy.SCOPE+pid
        existing=bookkeeping.begin(c,scope,payload['request_id'],payload)
        if existing is not None:
            if transaction is None:conn.commit()
            return existing
        # Same portfolio/account lock order as trade writes and opening capture.
        c.execute('SELECT id FROM accounts WHERE portfolio_id=%s ORDER BY id',(pid,))
        lock_scope(c,pid,[str(a['id']) for a in c.fetchall()])
        opening=next((p for p in load(c,pid) if p['id']==payload['baseline_id']),None)
        if not opening:raise ValueError('현재 포트폴리오의 유효한 계산 기준을 찾을 수 없습니다.')
        rows=history(c,opening)
        if any(t['trade_type']=='SELL' and str(t['id']) not in opening['covered_trades'] for t in rows):
            raise ValueError('이 기준을 사용한 매도 손익이 있어 기준만 취소할 수 없습니다. 실제 거래 입력은 계속 사용할 수 있습니다.')
        result=dict(kind='REALIZED_OPENING_REVOKED',baseline_id=opening['id'],holdings_changed=False,cash_changed=False)
        bookkeeping.finish(c,scope,payload['request_id'],result)
        if transaction is None:conn.commit();db.invalidate()
        return result
    except Exception:
        if transaction is None:conn.rollback()
        raise
    finally:
        if transaction is None:conn.close()
