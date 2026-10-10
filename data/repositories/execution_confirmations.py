"""Internal synthetic adapter contract; no order submission or public API.

Keep externally confirmed facts before bookkeeping. Only MOCK_API is supported
here. A real broker adapter, credentials and order approval are future work.
"""
import hashlib
from psycopg2.extras import Json, RealDictCursor
from data.repositories.bookkeeping import plain
from data.repositories.nh_notices import lock_scope
from data.repositories import investments, trades
from backend.routers.trades import BatchTradeRequest


def preserve(db,pid,link,source_key,trade_date,trade,verified):
    if not source_key or len(source_key)>300:
        raise ValueError('모의 체결의 고유 원본 식별자가 필요합니다.')
    # Reuse the same input boundaries; adapter identity is never browser-supplied.
    row={**trade,'execution':link}
    batch=BatchTradeRequest(request_id='validation-only',portfolio_id=pid,trade_date=trade_date,trades=[row]).model_dump(mode='json')
    row=batch['trades'][0]
    evidence=plain(dict(link=link,source_key=source_key,trade_date=trade_date,trade=row,verified=bool(verified)))
    key='mock:'+hashlib.sha256((pid+':'+source_key).encode()).hexdigest()
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        lock_scope(c,pid,[]);cycle=investments.lock_cycle(c,pid,link['cycle_id'])
        c.execute('SELECT * FROM portfolio_execution.attempts WHERE request_key=%s FOR UPDATE',(key,))
        old=c.fetchone()
        if old:
            if old['evidence']!=evidence: raise ValueError('같은 원본 식별자의 체결 내용이 변경되었습니다. 원본을 확인해주세요.')
            return {'attempt_id':old['id']}
        if not 1<=link['revision']<=cycle['revision']:
            raise ValueError('실행 당시의 계획 버전을 확인해주세요.')
        # Late facts survive pause, closure and later plan versions. Preserving
        # evidence is not approval to post or execute another order.
        c.execute('SELECT payload FROM portfolio_execution.steps WHERE id=%s AND cycle_id=%s',(link['step_id'],cycle['id']))
        item=c.fetchone()
        fact=dict(portfolio_id=pid,kind=row['trade_type'],**{k:row[k] for k in ('account_id','asset_id','currency')})
        if not item or not investments.matches(item['payload'],fact,pid): raise ValueError('체결과 투자 작업이 다릅니다.')
        attempt,result=db.new_id(),db.new_id()
        c.execute('INSERT INTO portfolio_execution.attempts(id,step_id,source,request_key,status,evidence) VALUES(%s,%s,%s,%s,%s,%s)',
            (attempt,link['step_id'],'MOCK_API',key,'REVIEW',Json(evidence)))
        payload=plain(dict(id=result,step_id=link['step_id'],kind=row['trade_type'],account_id=row['account_id'],
            asset_id=row['asset_id'],currency=row['currency'],quantity=row['quantity'],amount=row['quantity']*row['price'],
            price=row['price'],event_date=trade_date,source='MOCK_API',ledger_status='PENDING' if verified else 'UNCERTAIN'))
        c.execute('INSERT INTO portfolio_execution.results(id,attempt_id,step_id,payload) VALUES(%s,%s,%s,%s)',
            (result,attempt,link['step_id'],Json(payload)))
        conn.commit();return {'attempt_id':attempt}


def post(db,pid,attempt_id,reviewed_revision=None):
    """Retry bookkeeping only. Confirmed execution is not repeated."""
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        lock_scope(c,pid,[])
        c.execute('''SELECT a.*,s.cycle_id FROM portfolio_execution.attempts a
            JOIN portfolio_execution.steps s ON s.id=a.step_id JOIN portfolio_execution.cycles cy ON cy.id=s.cycle_id
            WHERE a.id=%s AND cy.portfolio_id=%s''',(attempt_id,pid))
        attempt=c.fetchone()
        if not attempt or attempt['source']!='MOCK_API': raise ValueError('확인한 모의 실행을 선택해주세요.')
        if attempt['status']=='RECORDED': return {'recorded':True,'attempt_id':attempt_id}
        evidence=attempt['evidence']
        if not evidence['verified']: raise ValueError('체결 여부가 불명확합니다. 장부 반영과 실행 재전송을 중단합니다.')
        c.execute('SELECT revision FROM portfolio_execution.cycles WHERE id=%s',(attempt['cycle_id'],))
        revision=c.fetchone()['revision']
        if revision!=evidence['link']['revision'] and reviewed_revision!=revision:
            raise ValueError('계획 변경 후 도착한 체결입니다. 실제 결과를 보존했으며 최신 계획으로의 반영을 검토해주세요.')
        trade=dict(evidence['trade'])
        trade['execution']={**evidence['link'],'revision':revision,'confirmation_id':attempt_id}
        payload=dict(request_id='confirmed-'+attempt_id+'-r'+str(revision),portfolio_id=pid,trade_date=evidence['trade_date'],trades=[trade])
        if trade.get('import_source')=='NAMUH_KAKAO' and trade.get('broker_order_no'):
            c.execute('SELECT id FROM trade_history WHERE account_id=%s AND trade_date=%s AND import_source=%s AND broker_order_no=%s',(trade['account_id'],evidence['trade_date'],trade['import_source'],trade['broker_order_no']))
            existing=c.fetchone()
            if existing:
                result=investments.attach(c,db,pid,trade['execution'],'TRADE',existing['id'],'MOCK_API')
                conn.commit();return {**result,'recorded':True,'matched_existing':True}
    # No external call and no long transaction. Existing receipt and journal own
    # the atomic commit; attach promotes the existing result inside that commit.
    return trades.execute_batch(db,payload)


def validate(c,pid,link,fact):
    c.execute('''SELECT a.*,r.id AS result_id,r.payload AS result_payload FROM portfolio_execution.attempts a
        JOIN portfolio_execution.results r ON r.attempt_id=a.id WHERE a.id=%s FOR UPDATE OF a''',(link['confirmation_id'],))
    saved=c.fetchone()
    if not saved or saved['step_id']!=link['step_id'] or saved['source']!='MOCK_API' or not saved['evidence']['verified']:
        raise ValueError('장부에 반영할 확인된 실행 사실을 찾을 수 없습니다.')
    evidence=saved['evidence'];trade=evidence['trade']
    if (evidence['link']['cycle_id']!=link['cycle_id'] or fact['portfolio_id']!=pid
        or str(fact['trade_date'])!=evidence['trade_date']
        or any(str(fact[k])!=str(trade[k]) for k in ('account_id','asset_id','currency','trade_type'))
        or any(abs(float(fact[k])-float(trade[k]))>1e-8 for k in ('quantity','price'))):
        raise ValueError('확인된 체결 사실과 장부 기록이 다릅니다.')
    return saved
