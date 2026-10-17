"""Audited CMA income, never external flows or historical NAV rewrites."""
from psycopg2.extras import Json, RealDictCursor
from data.repositories.nh_notices import checkpoint, lock_scope
from data.repositories.bookkeeping import begin, finish, plain
from logic.cma_interest import amount, fingerprint, interest_preview, moment, stable_return
from logic import cma_policy
from logic.cma_reconciliation import reconcile,require_receipt,require_initial_receipt


def scope(c, pid, aid):
    lock_scope(c, pid, [aid])
    c.execute('SELECT id,account_type,deposit_krw,deposit_usd FROM accounts WHERE id=%s AND portfolio_id=%s', (aid,pid))
    account = c.fetchone()
    if not account or account['account_type'] != 'CMA':
        raise ValueError('현재 포트폴리오의 CMA 계좌를 선택해주세요.')
    return account, fingerprint(checkpoint(c,[aid]))


def read_book(db, pid, aid):
    with db.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        account, token = scope(c,pid,aid)
        c.execute('SELECT MAX(event_date) AS day FROM portfolio_cma.income WHERE account_id=%s', (aid,))
        last=c.fetchone()['day']
        c.execute('SELECT recognized_on FROM portfolio_cma.openings WHERE account_id=%s AND reversed_at IS NULL', (aid,))
        opening=c.fetchone()
        return dict(account=plain(account), book_token=token,
            source_start=str(last or opening['recognized_on']) if last or opening else None)


def record_observation(db, pid, aid, evidence, expected_token, *, reconciliation=None):
    """Persist only normalized fields from the trusted server-side provider."""
    with db.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        _, token = scope(c,pid,aid)
        if token != expected_token:
            raise ValueError('NH 조회 중 장부가 바뀌었습니다. 최신 장부로 다시 확인해주세요.')
        safe = {k:evidence.get(k) for k in ('observed_at','state','cash_krw','sweep_krw','total_krw','withdrawable_krw')}
        # Provider data cannot inject a receipt. Only the server's reconciler
        # supplies this independent argument; no HTTP endpoint accepts it.
        safe['reconciliation']=reconciliation
        now = moment(safe['observed_at'])
        ident = db.new_id()
        c.execute('''INSERT INTO portfolio_cma.observations(id,portfolio_id,account_id,observed_at,book_token,evidence)
            VALUES(%s,%s,%s,%s,%s,%s)''', (ident,pid,aid,now,token,Json(safe)))
        conn.commit()
        return dict(id=ident, account_id=aid, book_token=token, **safe)


def observation(c, pid, aid, ident):
    c.execute('SELECT * FROM portfolio_cma.observations WHERE id=%s AND portfolio_id=%s AND account_id=%s', (ident,pid,aid))
    row = c.fetchone()
    if not row:
        raise ValueError('현재 CMA 계좌의 조회 기록을 확인해주세요.')
    return {**row['evidence'], 'book_token':row['book_token'], 'id':row['id']}


def preview(db, pid, aid, ident, now):
    with db.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        account, token = scope(c,pid,aid)
        obs = observation(c,pid,aid,ident)
        if token != obs['book_token']:
            raise ValueError('조회 후 장부가 바뀌었습니다. 잔고를 다시 확인해주세요.')
        return dict(observation_id=ident, book_token=token, **interest_preview(account,obs,now))


def commit(db, pid, request, now):
    """Cash plus receipt/journal atomically; same request recovers lost responses."""
    cma_policy.require_writes()
    request = plain(request)
    aid = request['account_id']
    conn = db.connect()
    try:
        c = conn.cursor(cursor_factory=RealDictCursor)
        account, token = scope(c,pid,aid)
        key = 'CMA_INCOME:'+pid
        saved = begin(c,key,request['request_id'],request)
        if saved is not None:
            conn.rollback()
            return saved
        if request.get('confirmed_movements') is not True:
            raise ValueError('매매·입출금·이체가 장부에 반영되었고 차액이 이자임을 확인해주세요.')
        obs = observation(c,pid,aid,request['observation_id'])
        if token != obs['book_token'] or token != request['book_token']:
            raise ValueError('확인 후 장부가 바뀌었습니다. CMA 이자를 다시 검토해주세요.')
        proposal = interest_preview(account,obs,now)
        if proposal.get('can_apply') is False:
            if proposal.get('status')=='INITIAL_BALANCE_REVIEW':
                raise ValueError('초기 누적 차액이 포함되어 있습니다. 당일 이자와 분리해 검토해주세요.')
            raise ValueError('은행 이자 명세와 입출금 대조가 완료되지 않아 반영하지 않습니다.')
        delta = amount(proposal['interest_krw'])
        # A manual checkbox cannot turn an unknown cash gap into income either.
        require_receipt(obs.get('reconciliation'),pid=pid,aid=aid,token=token,observation=obs,delta=delta)
        if request.get('automatic'):
            c.execute('SELECT * FROM portfolio_cma.settings WHERE account_id=%s AND portfolio_id=%s FOR UPDATE', (aid,pid))
            policy = c.fetchone()
            paid_items=(obs.get('reconciliation') or {}).get('paid_items') or [dict(amount_krw=str(delta))]
            if (not policy or not policy['enabled'] or not policy['auto_apply'] or not policy['movements_confirmed']
                    or any(amount(item['amount_krw'])>amount(policy['max_auto_interest']) for item in paid_items)):
                raise ValueError('현재 자동 반영 설정으로 이자를 반영할 수 없습니다.')
            c.execute('''SELECT * FROM portfolio_cma.observations WHERE account_id=%s AND id<>%s
                ORDER BY observed_at DESC LIMIT 1''', (aid,obs['id']))
            prior = c.fetchone()
            previous = {**prior['evidence'],'book_token':prior['book_token']} if prior else None
            if not stable_return(previous,obs):
                raise ValueError('현금 반환 상태를 두 번 확인한 뒤 자동 반영합니다.')
        if amount(request['interest_krw']) != delta:
            raise ValueError('이자 차액이 미리보기와 다릅니다.')
        proof=obs.get('reconciliation') or {}
        items=proof.get('paid_items') if proof.get('status')=='MATCHED' else None
        if items is None:items=[dict(event_date=proposal['event_date'],amount_krw=str(delta))] if delta else []
        if sum((amount(i['amount_krw']) for i in items),amount(0))!=delta:
            raise ValueError('지급일별 이자 합계가 현재 장부 차액과 다릅니다.')
        for item in items:
            c.execute('SELECT id FROM portfolio_cma.income WHERE account_id=%s AND event_date=%s', (aid,item['event_date']))
            if c.fetchone():
                raise ValueError('이 계좌의 해당 지급일 CMA 이자는 이미 처리했습니다. 반영 이력을 확인해주세요.')
        result = dict(account_id=aid, event_date=proposal['event_date'], interest_krw=str(delta),
                      before_cash=proposal['book_krw'], after_cash=proposal['broker_krw'],
                      external_flow_created=False, saved=bool(delta))
        if delta:
            c.execute('UPDATE accounts SET deposit_krw=deposit_krw+%s WHERE id=%s', (delta,aid))
            after_token = fingerprint(checkpoint(c,[aid]))
            result['paid_items']=items;result['income_ids']=[]
            running=amount(proposal['book_krw'])
            for item in items:
                ident=db.new_id();value=amount(item['amount_krw']);after=running+value
                c.execute('''INSERT INTO portfolio_cma.income(id,portfolio_id,account_id,request_id,observation_id,
                    event_date,amount_krw,before_cash,after_cash,after_token,details)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (ident,pid,aid,request['request_id'],obs['id'],item['event_date'],value,running,after,after_token,Json(item)))
                running=after;result['income_ids'].append(ident)
            result['income_id']=result['income_ids'][-1]
        finish(c,key,request['request_id'],result)
        conn.commit()
        db.invalidate()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def undo(db, pid, aid, ident):
    cma_policy.require_writes()
    conn = db.connect()
    try:
        c = conn.cursor(cursor_factory=RealDictCursor)
        _, token = scope(c,pid,aid)
        c.execute('SELECT * FROM portfolio_cma.income WHERE id=%s AND portfolio_id=%s AND account_id=%s FOR UPDATE', (ident,pid,aid))
        row = c.fetchone()
        if not row:
            raise ValueError('CMA 이자 반영 기록을 찾을 수 없습니다.')
        if row['reversed_at']:
            conn.rollback()
            return dict(reversed=True)
        c.execute('SELECT observation_id FROM portfolio_cma.income WHERE account_id=%s AND reversed_at IS NULL ORDER BY sequence DESC LIMIT 1', (aid,))
        if c.fetchone()['observation_id'] != row['observation_id'] or token != row['after_token']:
            raise ValueError('이자 반영 이후 장부 변경이 있습니다. 현재 장부를 확인해주세요.')
        c.execute('''SELECT amount_krw FROM portfolio_cma.income WHERE account_id=%s AND observation_id=%s AND reversed_at IS NULL''', (aid,row['observation_id']))
        total=sum((amount(r['amount_krw']) for r in c.fetchall()),amount(0))
        c.execute('UPDATE accounts SET deposit_krw=deposit_krw-%s WHERE id=%s', (total,aid))
        c.execute('UPDATE portfolio_cma.income SET reversed_at=CURRENT_TIMESTAMP WHERE account_id=%s AND observation_id=%s', (aid,row['observation_id']))
        # An intentional reversal must not be automatically re-inferred next day.
        c.execute('UPDATE portfolio_cma.settings SET auto_apply=FALSE WHERE account_id=%s', (aid,))
        conn.commit(); db.invalidate()
        return dict(reversed=True)
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


def initialize_interest(db,pid,request,now):
    """One reviewed opening-income entry; no fabricated historical payment date.

    Only the prior difference is posted. The statement's dated payments remain
    pending and are posted separately from a fresh observation after this write.
    """
    cma_policy.require_writes()
    request=plain(request);aid=request['account_id'];conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor);account,token=scope(c,pid,aid)
        key='CMA_OPENING:'+pid;saved=begin(c,key,request['request_id'],request)
        if saved is not None:conn.rollback();return saved
        if request.get('confirmed_initial_interest') is not True or len(str(request.get('reason','')).strip())<10:
            raise ValueError('이전 누적 차액이 이자임을 확인하고 초기 정리 사유를 남겨주세요.')
        obs=observation(c,pid,aid,request['observation_id'])
        if token!=obs['book_token'] or token!=request['book_token']:
            raise ValueError('초기 이자 확인 후 장부가 바뀌었습니다. 다시 조회해주세요.')
        proposal=interest_preview(account,obs,now);proof=obs.get('reconciliation') or {}
        paid=amount(proof.get('paid_interest_krw'));prior=amount(proof.get('prior_difference_krw'))
        require_initial_receipt(proof,pid=pid,aid=aid,token=token,observation=obs,delta=paid)
        if (paid<0 or prior<=0 or amount(request['initial_interest_krw'])!=prior
            or amount(proposal['interest_krw'])!=paid+prior):
            raise ValueError('초기 누적 이자와 지급일별 이자를 분리해 확인해주세요.')
        c.execute('SELECT id FROM portfolio_cma.openings WHERE account_id=%s', (aid,))
        if c.fetchone():raise ValueError('이미 초기 누적 이자를 처리한 계좌입니다. 기존 기록을 확인해주세요.')
        before=amount(account['deposit_krw']);after=before+prior
        c.execute('UPDATE accounts SET deposit_krw=deposit_krw+%s WHERE id=%s', (prior,aid))
        after_token=fingerprint(checkpoint(c,[aid]));ident=db.new_id()
        details=dict(kind='INITIAL_ACCUMULATED_INTEREST',historical_payment_dates=None,
            pending_paid_items=proof.get('paid_items'),pending_paid_interest_krw=str(paid),
            statement_digest=proof['statement_digest'],ledger_digest=proof['ledger_digest'],
            broker_cash_krw=proof['closing_cash_krw'],source_start=proof['source_start'])
        c.execute('''INSERT INTO portfolio_cma.openings(id,portfolio_id,account_id,request_id,observation_id,
            recognized_on,amount_krw,before_cash,after_cash,after_token,reason,details)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (ident,pid,aid,request['request_id'],obs['id'],proposal['event_date'],prior,before,after,
             after_token,request['reason'].strip(),Json(details)))
        result=dict(opening_id=ident,account_id=aid,initial_interest_krw=str(prior),pending_paid_interest_krw=str(paid),
            before_cash=str(before),after_cash=str(after),historical_payment_dates=None,external_flow_created=False,saved=True)
        finish(c,key,request['request_id'],result);conn.commit();db.invalidate();return result
    except Exception:
        conn.rollback();raise
    finally:conn.close()


def undo_initial_interest(db,pid,aid,ident):
    cma_policy.require_writes();conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor);_,token=scope(c,pid,aid)
        c.execute('SELECT * FROM portfolio_cma.openings WHERE id=%s AND portfolio_id=%s AND account_id=%s FOR UPDATE',(ident,pid,aid))
        row=c.fetchone()
        if not row:raise ValueError('초기 이자 기록을 찾을 수 없습니다.')
        if row['reversed_at']:conn.rollback();return dict(reversed=True)
        if token!=row['after_token']:raise ValueError('초기 정리 이후 장부 변경이 있습니다. 후속 기록부터 확인해주세요.')
        c.execute('UPDATE accounts SET deposit_krw=deposit_krw-%s WHERE id=%s',(amount(row['amount_krw']),aid))
        c.execute('UPDATE portfolio_cma.openings SET reversed_at=CURRENT_TIMESTAMP WHERE id=%s',(ident,))
        c.execute('UPDATE portfolio_cma.settings SET auto_apply=FALSE WHERE account_id=%s',(aid,))
        conn.commit();db.invalidate();return dict(reversed=True)
    except Exception:conn.rollback();raise
    finally:conn.close()


def configure(db, pid, aid, settings):
    if settings['auto_apply']:
        cma_policy.require_writes()
        if not cma_policy.automatic_ready():
            raise ValueError('실제 NH 이자 명세 대조 프로필을 검증하기 전에는 자동 반영을 활성화할 수 없습니다.')
    if amount(settings['max_auto_interest']) < 0:
        raise ValueError('이자 상한은 0 이상이어야 합니다.')
    if settings['auto_apply'] and (not settings['movements_confirmed'] or amount(settings['max_auto_interest']) <= 0):
        raise ValueError('자동 반영은 모든 자금 이동의 장부 반영과 1일 이자 상한을 확인한 뒤 설정해주세요.')
    with db.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        scope(c,pid,aid)
        c.execute('''INSERT INTO portfolio_cma.settings(account_id,portfolio_id,enabled,auto_apply,max_auto_interest,movements_confirmed)
            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(account_id) DO UPDATE SET
            enabled=EXCLUDED.enabled,auto_apply=EXCLUDED.auto_apply,max_auto_interest=EXCLUDED.max_auto_interest,
            movements_confirmed=EXCLUDED.movements_confirmed''',
            (aid,pid,settings['enabled'],settings['auto_apply'],amount(settings['max_auto_interest']),settings['movements_confirmed']))
        conn.commit()
    return dict(saved=True)


def read(db, pid):
    with db.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('''SELECT a.id,a.account_alias,a.deposit_krw,s.enabled,s.auto_apply,s.max_auto_interest,s.movements_confirmed
            FROM accounts a LEFT JOIN portfolio_cma.settings s ON s.account_id=a.id
            WHERE a.portfolio_id=%s AND a.account_type='CMA' ORDER BY a.account_alias''', (pid,))
        accounts = c.fetchall()
        c.execute('SELECT * FROM portfolio_cma.income WHERE portfolio_id=%s ORDER BY sequence DESC LIMIT 30', (pid,))
        income = c.fetchall()
        c.execute('SELECT COALESCE(SUM(amount_krw),0) AS total FROM portfolio_cma.income WHERE portfolio_id=%s AND reversed_at IS NULL', (pid,))
        total = str(c.fetchone()['total'])
        c.execute('SELECT * FROM portfolio_cma.openings WHERE portfolio_id=%s ORDER BY created_at DESC', (pid,))
        openings=c.fetchall()
        initial_total=str(sum((amount(r['amount_krw']) for r in openings if not r['reversed_at']),amount(0)))
        c.execute('''SELECT c.account_id,a.account_alias,c.event_date,c.slot,c.state,c.updated_at FROM portfolio_cma.checks c
            JOIN accounts a ON a.id=c.account_id WHERE a.portfolio_id=%s ORDER BY c.event_date DESC,c.slot DESC LIMIT 30''', (pid,))
        return dict(accounts=accounts,income=income,checks=c.fetchall(),openings=openings,
            initial_interest_total_krw=initial_total,interest_total_krw=str(amount(total)+amount(initial_total)))


def policies(db):
    with db.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('''SELECT s.* FROM portfolio_cma.settings s JOIN accounts a ON a.id=s.account_id
            WHERE s.enabled AND a.account_type='CMA' AND a.portfolio_id=s.portfolio_id''')
        return c.fetchall()


def reconciliation_for(db,pid,aid,book,evidence):
    statement=evidence.get('statement')
    if not isinstance(statement,dict) or statement.get('profile') not in cma_policy.VALIDATED_STATEMENT_PROFILES:
        return {'status':'STATEMENT_REQUIRED'}
    # Actual statement collection/normalization is not guessed. When a verified
    # provider supplies it, booked cash movements come from the existing READ
    # ONLY activity repository, never from the provider or HTTP request.
    from data.repositories.activity import read_page
    from datetime import date
    day=moment(evidence['observed_at']).date();start=date.fromisoformat(statement['start_date'])
    page=read_page(db,pid,start,day,aid,page_size=100)
    if page['pages']!=1:return {'status':'LEDGER_UNVERIFIED'}
    moves=[]
    for row in page['items']:
        detail=row.get('detail') or {}
        if row['category']!='CASH' or row.get('currency')!='KRW' or detail.get('cash_applied') is not True:
            return {'status':'LEDGER_UNVERIFIED'}
        kind=row['kind']
        if kind=='INTERNAL_TRANSFER':
            delta=amount(detail.get('delta_krw'))
            if not delta or abs(delta)!=amount(row['amount']):return {'status':'LEDGER_UNVERIFIED'}
            kind='DEPOSIT' if delta>0 else 'WITHDRAW'
        if kind not in ('DEPOSIT','WITHDRAW'):return {'status':'LEDGER_UNVERIFIED'}
        moves.append(dict(id=row['id'],event_date=row['event_date'],kind=kind,amount_krw=str(amount(row['amount']))))
    with db.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('''SELECT event_date,amount_krw,reversed_at FROM portfolio_cma.income
            WHERE portfolio_id=%s AND account_id=%s AND event_date>=%s AND event_date<=%s''', (pid,aid,start,day))
        booked=plain(c.fetchall())
    return reconcile(statement,moves,pid=pid,aid=aid,book_token=book['book_token'],
        book_cash=book['account']['deposit_krw'],observation=evidence,booked_income=booked)


def claim_check(db, aid, day, slot):
    # Durable slot consumption BEFORE broker access. A failed/crashed request
    # is not retried in this slot by another worker or on server restart.
    with db.connect() as conn, conn.cursor() as c:
        c.execute('''INSERT INTO portfolio_cma.checks(account_id,event_date,slot,state)
            VALUES(%s,%s,%s,'CHECKING') ON CONFLICT(account_id,event_date,slot) DO NOTHING''', (aid,day,slot))
        claimed = bool(c.rowcount)
        conn.commit()
        return claimed


def check_slots(db, aid, day):
    with db.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SELECT slot,state FROM portfolio_cma.checks WHERE account_id=%s AND event_date=%s', (aid,day))
        return c.fetchall()


def finish_check(db, aid, day, slot, state):
    with db.connect() as conn, conn.cursor() as c:
        c.execute('UPDATE portfolio_cma.checks SET state=%s,updated_at=CURRENT_TIMESTAMP WHERE account_id=%s AND event_date=%s AND slot=%s', (state,aid,day,slot))
        conn.commit()


def previous_observation(db, aid, ident):
    with db.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('''SELECT * FROM portfolio_cma.observations WHERE account_id=%s AND id<>%s
            ORDER BY observed_at DESC LIMIT 1''', (aid,ident))
        row = c.fetchone()
        return {**row['evidence'],'book_token':row['book_token']} if row else None
