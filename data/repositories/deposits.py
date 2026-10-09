"""Audited current deposit registration/correction; never invent cash movements."""
import json
from types import SimpleNamespace
from psycopg2.extras import RealDictCursor
from data.repositories import assets, bookkeeping

FIELDS = ('name','ticker','market','deposit_principal','interest_rate','start_date',
          'maturity_date','early_termination_rate','tax_rate','is_deposit','account_no')


def save(db, pid, request):
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        scope='deposit:'+request['asset_id']
        existing=bookkeeping.begin(c,scope,request['request_id'],dict(request,portfolio_id=pid))
        if existing is not None:
            conn.rollback()
            return existing
        c.execute('SELECT id FROM portfolios WHERE id=%s FOR UPDATE',(pid,))
        if not c.fetchone():raise ValueError('포트폴리오를 찾을 수 없습니다.')
        c.execute('SELECT * FROM assets WHERE id=%s FOR UPDATE',(request['asset_id'],))
        before=c.fetchone()
        if before and (before['portfolio_id']!=pid or not before['is_deposit']):
            raise ValueError('현재 포트폴리오의 예금을 선택해주세요.')
        config=request['asset']
        common=dict(config,is_deposit=True,market='KR',allowed_accounts=[],is_risk_asset=False)
        if before:
            # Retain allocation metadata; only the deposit contract is corrected here.
            common.update(target_weight=before['target_weight'],is_active=before['is_active'],
                          include_in_rebalance=before['include_in_rebalance'])
            ok,message=assets.update_asset(db,asset_id=request['asset_id'],transaction=conn,
                                           bookkeeping_write=True,**common)
        else:
            local=SimpleNamespace(connect=db.connect,new_id=lambda:request['asset_id'],invalidate=db.invalidate)
            ok,message=assets.add_asset(local,portfolio_id=pid,transaction=conn,
                                        bookkeeping_write=True,**common)
        if not ok:raise ValueError(message)
        c.execute('SELECT * FROM assets WHERE id=%s',(request['asset_id'],))
        after=c.fetchone()
        result=dict(success=True,message='예금 장부에 현재 원금·계약 조건과 정정 사유를 저장했습니다.',
                    asset_id=request['asset_id'],portfolio_id=pid,before=bookkeeping.plain(before),
                    after=bookkeeping.plain(after),reason=request['reason'])
        bookkeeping.finish(c,scope,request['request_id'],result)
        conn.commit();db.invalidate()
        return result
    except Exception:
        conn.rollback();raise
    finally:conn.close()


def undo(db,pid,asset_id,request_id):
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SELECT id FROM portfolios WHERE id=%s FOR UPDATE',(pid,))
        c.execute('SELECT * FROM assets WHERE id=%s AND portfolio_id=%s FOR UPDATE',(asset_id,pid))
        current=c.fetchone()
        scope='deposit:'+asset_id
        c.execute('SELECT result FROM bookkeeping_requests WHERE scope=%s AND request_id=%s',(scope,request_id))
        row=c.fetchone()
        if not row:raise ValueError('예금 장부 기록을 찾을 수 없습니다.')
        result=bookkeeping.plain(row['result']) if isinstance(row['result'],dict) else json.loads(row['result'])
        if result.get('reversed'):conn.rollback();return {'success':True,'message':'이미 취소한 기록입니다.'}
        if result['portfolio_id']!=pid:raise ValueError('현재 포트폴리오의 기록이 아닙니다.')
        c.execute("""SELECT request_id FROM bookkeeping_requests WHERE scope=%s
            AND COALESCE(result->>'reversed','false')='false' ORDER BY sequence DESC LIMIT 1""",(scope,))
        if c.fetchone()['request_id']!=request_id or not current or any(str(current.get(k))!=str(result['after'].get(k)) for k in FIELDS):
            raise ValueError('후속 예금 변경이 있습니다. 최신 정정부터 취소해주세요.')
        old=result['before']
        if old:
            c.execute('UPDATE assets SET '+','.join(k+'=%s' for k in FIELDS)+' WHERE id=%s',
                      (*[old[k] for k in FIELDS],asset_id))
        else:
            # Retain the master and receipt rather than deleting audit evidence.
            c.execute('UPDATE assets SET deposit_principal=0 WHERE id=%s',(asset_id,))
        result['reversed']=True;result['message']='이미 취소한 예금 요청입니다. 다시 반영하지 않았습니다.'
        bookkeeping.finish(c,scope,request_id,result)
        conn.commit();db.invalidate();return {'success':True,'message':'예금 원금·조건을 이전 상태로 복원했습니다.'}
    except Exception:conn.rollback();raise
    finally:conn.close()


def history(db,pid):
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        c.execute("""SELECT request_id,created_at,result FROM bookkeeping_requests
            WHERE scope LIKE 'deposit:%' AND result->>'portfolio_id'=%s ORDER BY sequence DESC LIMIT 20""",(pid,))
        return list(c.fetchall())
    finally:conn.close()
