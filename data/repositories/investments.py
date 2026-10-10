"""Workflow metadata linked atomically to existing financial repositories."""
from datetime import datetime, timezone
import hashlib
import json
from psycopg2.extras import Json, RealDictCursor
from logic.investment_execution import build_steps, closing_progress,plan_budget,funding_details
from data.repositories.bookkeeping import plain
from data.repositories.nh_notices import lock_scope
S = 'portfolio_execution.'

def lock_cycle(c, pid, ident):
    c.execute('SELECT * FROM '+S+'cycles WHERE id=%s AND portfolio_id=%s FOR UPDATE', (ident,pid))
    cycle=c.fetchone()
    if not cycle: raise ValueError('현재 포트폴리오의 투자 과정을 선택해주세요.')
    return cycle

def load_sources(c, refs):
    found={}
    queries={
      'TRADE':'''SELECT t.*,a.portfolio_id,s.market,s.name AS asset_name FROM trade_history t
        JOIN accounts a ON a.id=t.account_id JOIN assets s ON s.id=t.asset_id WHERE t.id=ANY(%s)''',
      'USD':'''SELECT e.*,a.portfolio_id FROM usd_cash_events e JOIN accounts a ON a.id=e.account_id WHERE e.id=ANY(%s)''',
      'NOTICE':'''SELECT n.*,b.created_at AS recorded_at FROM nh_notice_items n JOIN nh_notice_batches b ON b.id=n.batch_id WHERE n.id=ANY(%s)'''}
    for kind,query in queries.items():
        ids=[ident for k,ident in refs if k==kind]
        if not ids: continue
        c.execute(query,(ids,))
        for row in c.fetchall():
            data=dict(row)
            if kind=='TRADE':
                data.update(kind=row['trade_type'],currency='USD' if row['market']=='US' else 'KRW',
                    amount=float(row['quantity'])*float(row['price']),event_date=str(row['trade_date']),voided=False)
            elif kind=='USD':
                data.update(currency='USD',amount=str(row['usd_amount']),voided=row['reversed_at'] is not None)
            else:
                payload=row['payload']
                if not payload.get('external',True) and not payload.get('cross_portfolio'):
                    source=payload.get('source_account_id') if row['kind']=='DEPOSIT' else row['account_id']
                    dest=row['account_id'] if row['kind']=='DEPOSIT' else payload.get('destination_account_id')
                    data.update(kind='TRANSFER',account_id=source,destination_account_id=dest)
                data.update(currency='KRW',amount=payload.get('krw_amount'),voided=row['reversed_at'] is not None,
                    cash_applied=bool(payload.get('apply_cash',True)))
            found[(kind,row['id'])]=data
    return found

def source(c,kind,ident):
    row=load_sources(c,[(kind,ident)]).get((kind,ident))
    if not row or row.get('voided'): raise ValueError('기록이 없거나 취소되었습니다. 최신 기록을 확인해주세요.')
    if kind=='NOTICE':
        if row.get('linked_trade_id'): return source(c,'TRADE',row['linked_trade_id'])
        if row.get('linked_usd_event_id'): return source(c,'USD',row['linked_usd_event_id'])
        if not row['cash_applied']: raise ValueError('잔고에 반영되지 않은 과거 기록은 신규 자금 준비 완료로 연결하지 않습니다.')
    if kind=='USD' and row.get('trade_id'): return source(c,'TRADE',row['trade_id'])
    return kind,ident,row

def matches(step,fact,pid):
    return (fact['portfolio_id']==pid and step['kind']==fact['kind']
      and step['account_id']==fact['account_id'] and step['currency']==fact['currency']
      and (step['kind'] not in ('BUY','SELL') or step['asset_id']==fact.get('asset_id'))
      and (step['kind']!='TRANSFER' or step.get('destination_account_id')==fact.get('destination_account_id')))

def attach(c,db,pid,link,kind,ident,channel='MANUAL'):
    if not link: return None
    cycle=lock_cycle(c,pid,link['cycle_id'])
    if cycle['status']!='ACTIVE' or cycle['revision']!=link['revision']:
        raise ValueError('투자 과정이 중단·종료되었거나 계획이 변경되었습니다. 저장 전 다시 확인해주세요.')
    c.execute('SELECT payload FROM '+S+'steps WHERE id=%s AND cycle_id=%s',(link['step_id'],cycle['id']))
    row=c.fetchone()
    if not row: raise ValueError('선택한 투자 작업을 찾을 수 없습니다.')
    step=row['payload']
    if step.get('status')=='EXCLUDED':
        raise ValueError('제외한 투자 작업입니다. 목표를 다시 확인하거나 5번에서 연결 없이 기록해주세요.')
    kind,ident,fact=source(c,kind,ident)
    if not matches(step,fact,pid): raise ValueError('실제 기록의 계좌·종목·통화·방향이 투자 작업과 다릅니다. 연결 대상을 확인해주세요.')
    c.execute('''SELECT r.step_id,r.id AS result_id FROM portfolio_execution.record_links l
      JOIN portfolio_execution.results r ON r.id=l.result_id
      WHERE l.record_kind=%s AND l.record_id=%s AND l.released_at IS NULL''',(kind,ident))
    prior=c.fetchone()
    if prior:
        if prior['step_id']==step['id']:
            if link.get('confirmation_id'):
                from data.repositories.execution_confirmations import validate
                saved=validate(c,pid,link,fact)
                duplicate={**saved['result_payload'],'ledger_status':'DUPLICATE','voided':True,'duplicate_result_id':prior['result_id']}
                c.execute('UPDATE '+S+'attempts SET status=%s WHERE id=%s',('RECORDED',saved['id']))
                c.execute('UPDATE '+S+'results SET payload=%s WHERE id=%s',(Json(duplicate),saved['result_id']))
            return {'linked':True,'existing':True}
        raise ValueError('이미 다른 투자 작업에 연결된 기록입니다. 기존 연결을 확인해주세요.')
    if kind=='TRADE':
        c.execute('SELECT cutoff FROM rebalance_plans WHERE id=%s FOR UPDATE',(cycle['plan_id'],))
        if fact['trade_sequence']<=c.fetchone()['cutoff']:
            raise ValueError('계획 저장 후 등록한 거래만 연결할 수 있습니다.')
        c.execute('SELECT plan_id,line_no FROM rebalance_plan_links WHERE trade_id=%s',(ident,))
        old=c.fetchone()
        if old and (old['plan_id']!=cycle['plan_id'] or old['line_no']!=step['line_no']):
            raise ValueError('다른 리밸런싱 계획에 이미 연결된 매매입니다.')
        c.execute('INSERT INTO rebalance_plan_links(plan_id,line_no,trade_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',
          (cycle['plan_id'],step['line_no'],ident))
    elif fact.get('recorded_at') is None or fact['recorded_at']<cycle['created_at']:
        raise ValueError('투자 시작 이전 기록입니다. 이미 확보된 자금은 시작 설정에 반영해주세요.')
    confirmed=None
    if link.get('confirmation_id'):
        from data.repositories.execution_confirmations import validate
        confirmed=validate(c,pid,link,fact)
        channel='MOCK_API'
    attempt,result=(confirmed['id'],confirmed['result_id']) if confirmed else (db.new_id(),db.new_id())
    if not confirmed: c.execute('INSERT INTO '+S+'attempts(id,step_id,source,request_key,status,evidence) VALUES(%s,%s,%s,%s,%s,%s)',
      (attempt,step['id'],channel,'record:'+kind+':'+ident+':'+attempt,'RECORDED',Json(plain({'record_kind':kind,'record_id':ident,'revision':cycle['revision']}))))
    evidence=plain(dict(id=result,step_id=step['id'],kind=fact['kind'],account_id=fact['account_id'],asset_id=fact.get('asset_id'),
       currency=fact['currency'],quantity=fact.get('quantity'),amount=fact.get('amount'),price=fact.get('price'),
       event_date=str(fact['event_date']),exchange_rate=fact.get('exchange_rate',fact.get('fx_rate')),krw_amount=fact.get('krw_amount'),ledger_status='RECORDED',source=channel,record_kind=kind,record_id=ident))
    if confirmed:
        c.execute('UPDATE '+S+'attempts SET status=%s WHERE id=%s',('RECORDED',attempt))
        c.execute('UPDATE '+S+'results SET payload=%s WHERE id=%s',(Json(evidence),result))
    else: c.execute('INSERT INTO '+S+'results(id,attempt_id,step_id,payload) VALUES(%s,%s,%s,%s)',(result,attempt,step['id'],Json(evidence)))
    c.execute('INSERT INTO '+S+'record_links(id,result_id,record_kind,record_id) VALUES(%s,%s,%s,%s)',(db.new_id(),result,kind,ident))
    return {'linked':True,'result_id':result}

def _setup(c,pid,request):
    c.execute('SELECT * FROM rebalance_plans WHERE id=%s AND portfolio_id=%s',(request['plan_id'],pid))
    plan=c.fetchone()
    if not plan or plan['archived']: raise ValueError('진행할 저장 계획을 선택해주세요.')
    c.execute('SELECT * FROM accounts WHERE portfolio_id=%s ORDER BY id',(pid,));accounts=[dict(a) for a in c.fetchall()]
    c.execute('SELECT * FROM assets WHERE portfolio_id=%s',(pid,));assets=[dict(a) for a in c.fetchall()]
    c.execute('''SELECT l.line_no,t.quantity,t.id FROM rebalance_plan_links l JOIN trade_history t ON t.id=l.trade_id
      WHERE l.plan_id=%s''',(plan['id'],))
    existing=sorted(c.fetchall(),key=lambda r:(r['line_no'],r['id']));quantities={}
    if plan['payload'].get('plan_type')=='CASH_RETURN':
        c.execute("SELECT status FROM portfolio_execution.cycles WHERE id=%s AND portfolio_id=%s",(plan['payload']['source_cycle_id'],pid))
        source_cycle=c.fetchone()
        if not source_cycle or source_cycle['status']!='CLOSED':raise ValueError('종료한 투자에서 만든 회수 계획을 선택해주세요.')
    for row in existing: quantities[row['line_no']]=quantities.get(row['line_no'],0)+float(row['quantity'])
    steps=build_steps(plan['payload'],accounts,assets,request,quantities)
    budget=plan_budget(plan['payload'])
    snapshot=dict(accounts=[{key:a.get(key) for key in ('id','deposit_krw','deposit_usd')} for a in accounts],
        plan=dict(id=plan['id'],payload=plan['payload'],cutoff=plan['cutoff']),linked_trades=existing)
    return plan,steps,budget,existing,snapshot

def preview_token(steps,snapshot=None):
    basis=steps if snapshot is None else dict(steps=steps,snapshot=snapshot)
    return hashlib.sha256(json.dumps(plain(basis),sort_keys=True,separators=(',',':')).encode()).hexdigest()

def start_plans(db,pid):
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SELECT id,name,payload,created_at FROM rebalance_plans p WHERE portfolio_id=%s AND NOT archived AND NOT EXISTS(SELECT 1 FROM portfolio_execution.cycles cy WHERE cy.plan_id=p.id) ORDER BY created_at DESC LIMIT 25',(pid,))
        return {'plans':c.fetchall()}

def prepare(db,pid,request):
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        plan,steps,budget,_,snapshot=_setup(c,pid,request)
        return {'plan_id':plan['id'],'name':plan['name'],'budget_krw':budget,'steps':steps,'setup':request,'funding_details':funding_details(steps),'preview_token':preview_token(steps,snapshot)}

def create(db,pid,request):
    request=plain(request)
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SELECT id FROM accounts WHERE portfolio_id=%s',(pid,));ids=[r['id'] for r in c.fetchall()]
        lock_scope(c,pid,ids)
        c.execute('SELECT id,payload FROM '+S+'cycles WHERE portfolio_id=%s AND request_id=%s',(pid,request['request_id']))
        prior=c.fetchone()
        if prior:
            if prior['payload']!=request: raise ValueError('같은 시작 요청의 내용이 바뀌었습니다. 기존 투자 과정을 확인해주세요.')
            return {'id':prior['id']}
        c.execute("SELECT id FROM "+S+"cycles WHERE portfolio_id=%s AND status<>'CLOSED'",(pid,))
        if c.fetchone(): raise ValueError('진행 중이거나 일시 중단한 투자가 있습니다. 먼저 이어가거나 종료해주세요.')
        c.execute('SELECT id FROM '+S+'cycles WHERE plan_id=%s',(request['plan_id'],))
        if c.fetchone(): raise ValueError('이미 투자에 사용한 계획입니다. 새 계획을 저장해주세요.')
        c.execute('SELECT id FROM rebalance_plans WHERE id=%s AND portfolio_id=%s FOR UPDATE',(request['plan_id'],pid))
        plan,steps,_,existing,snapshot=_setup(c,pid,request)
        if not request.get('preview_token') or request['preview_token']!=preview_token(steps,snapshot):
            raise ValueError('시작 안내가 없거나 잔고·계획이 변경되었습니다. 실행 안내를 다시 확인해주세요.')
        ident=db.new_id()
        c.execute('INSERT INTO '+S+'cycles(id,portfolio_id,plan_id,name,request_id,payload) VALUES(%s,%s,%s,%s,%s,%s)',
           (ident,pid,plan['id'],request.get('name') or plan['name'],request['request_id'],Json(request)))
        keymap={step['key']:db.new_id() for step in steps}
        for ordinal,step in enumerate(steps):
            step=dict(step,id=keymap[step['key']],execution_mode='MANUAL',depends_on=[keymap[key] for key in step['depends_on']])
            c.execute('INSERT INTO '+S+'steps(id,cycle_id,ordinal,kind,payload) VALUES(%s,%s,%s,%s,%s)',
               (step['id'],ident,ordinal,step['kind'],Json(step)))
        for row in existing:
            attach(c,db,pid,dict(cycle_id=ident,step_id=keymap[f"trade:{row['line_no']}"],revision=1),'TRADE',row['id'],'EXISTING')
        conn.commit();return {'id':ident}

def _read(c,pid,cycle_id):
    c.execute('''SELECT cy.*,p.name AS portfolio_name,pl.payload AS plan_payload FROM portfolio_execution.cycles cy
      JOIN portfolios p ON p.id=cy.portfolio_id JOIN rebalance_plans pl ON pl.id=cy.plan_id
      WHERE cy.id=%s AND cy.portfolio_id=%s''',(cycle_id,pid))
    row=c.fetchone()
    if not row: raise ValueError('투자 과정을 찾을 수 없습니다.')
    cycle=dict(row);plan=cycle.pop('plan_payload');cycle['budget_krw']=plan_budget(plan)
    cycle['plan_type']=plan.get('plan_type','INVESTMENT');cycle['source_cycle_id']=plan.get('source_cycle_id')
    c.execute('SELECT payload FROM '+S+'steps WHERE cycle_id=%s ORDER BY ordinal',(cycle_id,));cycle['steps']=[r['payload'] for r in c.fetchall()]
    c.execute('''SELECT r.payload,l.record_kind,l.record_id FROM portfolio_execution.results r
      JOIN portfolio_execution.steps s ON s.id=r.step_id LEFT JOIN portfolio_execution.record_links l ON l.result_id=r.id
      WHERE s.cycle_id=%s AND l.released_at IS NULL''',(cycle_id,));linked=c.fetchall()
    facts=load_sources(c,[(r['record_kind'],r['record_id']) for r in linked if r['record_kind']]);cycle['results']=[]
    for item in linked:
        result=dict(item['payload']);fact=facts.get((item['record_kind'],item['record_id']))
        if item['record_kind'] is None and result['ledger_status']=='RECORDED': continue  # explicitly released connection
        result['voided']=result.get('voided',False) or bool(item['record_kind']) and (not fact or fact.get('voided',False))
        if fact and not result['voided']:
            result.update(quantity=fact.get('quantity'),amount=fact.get('amount'),event_date=str(fact['event_date']))
        cycle['results'].append(result)
    return cycle

def read(db,pid,cycle_id=None):
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        if cycle_id: return _read(c,pid,cycle_id)
        c.execute("SELECT id,name,status,created_at FROM "+S+"cycles WHERE portfolio_id=%s ORDER BY created_at DESC LIMIT 25",(pid,))
        history=[dict(r) for r in c.fetchall()];current=next((r for r in history if r['status']!='CLOSED'),None)
        return {'cycle':_read(c,pid,current['id']) if current else None,'history':history}

def link_existing(db,pid,cycle_id,request):
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        lock_scope(c,pid,[])
        result=attach(c,db,pid,dict(cycle_id=cycle_id,step_id=request['step_id'],revision=request['revision']),
            request['record_kind'],request['record_id'],'EXISTING')
        conn.commit();return result

def unlink(db,pid,cycle_id,result_id):
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        lock_scope(c,pid,[]);cycle=lock_cycle(c,pid,cycle_id)
        if cycle['status']=='CLOSED': raise ValueError('종료한 투자의 연결은 변경하지 않습니다. 기록 정정은 5번 탭에서 처리해주세요.')
        c.execute('''SELECT l.* FROM portfolio_execution.record_links l JOIN portfolio_execution.results r ON r.id=l.result_id
          JOIN portfolio_execution.steps s ON s.id=r.step_id WHERE r.id=%s AND s.cycle_id=%s AND l.released_at IS NULL''',(result_id,cycle_id))
        link=c.fetchone()
        if not link: raise ValueError('연결된 기록을 찾을 수 없습니다.')
        c.execute("UPDATE "+S+"record_links SET released_at=CURRENT_TIMESTAMP,release_reason='USER_UNLINK' WHERE id=%s",(link['id'],))
        if link['record_kind']=='TRADE': c.execute('DELETE FROM rebalance_plan_links WHERE plan_id=%s AND trade_id=%s',(cycle['plan_id'],link['record_id']))
        conn.commit();return {'success':True}

def set_status(db,pid,cycle_id,status,reason=''):
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        lock_scope(c,pid,[]);cycle=lock_cycle(c,pid,cycle_id)
        if cycle['status']=='CLOSED' and status=='CLOSED': return {'success':True}
        if cycle['status']=='CLOSED' and status!='CLOSED': raise ValueError('종료한 투자는 재개하지 않습니다. 새 계획으로 시작해주세요.')
        if status=='CLOSED':
            current=_read(c,pid,cycle_id)
            progress=closing_progress(current)
            if progress['remaining_steps'] and not reason.strip():
                raise ValueError('남은 작업이나 확인 대기 기록이 있습니다. 미실행 종료 이유를 입력해주세요.')
            report=plain({'cycle':current,**progress,'reason':reason,'closed_at':datetime.now(timezone.utc).isoformat()})
            c.execute('UPDATE '+S+'cycles SET status=%s,report=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s',(status,Json(report),cycle_id))
        else: c.execute('UPDATE '+S+'cycles SET status=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s',(status,cycle_id))
        conn.commit();return {'success':True}

def candidates(db,pid,cycle_id,step_id):
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        cycle=_read(c,pid,cycle_id);step=next((s for s in cycle['steps'] if s['id']==step_id),None)
        if not step: raise ValueError('투자 작업을 찾을 수 없습니다.')
        c.execute('SELECT cutoff FROM rebalance_plans WHERE id=%s',(cycle['plan_id'],));cutoff=c.fetchone()['cutoff']
        if step['kind']=='BUY':
            c.execute("SELECT id FROM trade_history WHERE account_id=%s AND asset_id=%s AND trade_type='BUY' AND trade_sequence>%s ORDER BY trade_sequence DESC LIMIT 100",(step['account_id'],step['asset_id'],cutoff));kind='TRADE'
        elif step['kind']=='EXCHANGE_IN':
            c.execute("SELECT id FROM usd_cash_events WHERE account_id=%s AND kind='EXCHANGE_IN' AND reversed_at IS NULL AND recorded_at>=%s ORDER BY sequence DESC LIMIT 100",(step['account_id'],cycle['created_at']));kind='USD'
        else:
            c.execute("SELECT id FROM nh_notice_items WHERE portfolio_id=%s AND (account_id=%s OR payload->>'source_account_id'=%s OR payload->>'destination_account_id'=%s) AND reversed_at IS NULL ORDER BY sequence DESC LIMIT 100",(pid,step['account_id'],step['account_id'],step['account_id']));kind='NOTICE'
        refs=[(kind,r['id']) for r in c.fetchall()];facts=load_sources(c,refs)
        c.execute('SELECT record_kind,record_id FROM '+S+'record_links WHERE released_at IS NULL AND record_kind=%s AND record_id=ANY(%s)',(kind,[ident for _,ident in refs]))
        taken={(r['record_kind'],r['record_id']) for r in c.fetchall()}
        return {'items':[plain(dict(record_kind=k,record_id=i,**{key:value for key,value in fact.items() if key not in ('payload','before_state','after_state')}))
            for (k,i),fact in facts.items() if (k,i) not in taken and matches(step,fact,pid) and not fact.get('voided') and (k!='NOTICE' or fact['cash_applied']) and (k=='TRADE' or fact.get('recorded_at') and fact['recorded_at']>=cycle['created_at'])]}

def revise(db,pid,cycle_id,request):
    """Rebuild remaining preparation from actual cash, retaining task IDs/facts."""
    from logic.investment_execution import positive
    from copy import deepcopy
    request=plain(request)
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        lock_scope(c,pid,[]);cycle=lock_cycle(c,pid,cycle_id)
        current=_read(c,pid,cycle_id)
        if current['plan_type']=='CASH_RETURN':raise ValueError('현금 회수 금액 변경은 회차를 종료하고 새 회수 계획을 만들어주세요.')
        old_steps={s['id']:s for s in current['steps']}
        prior=[change for step in old_steps.values() for change in step.get('goal_history',[]) if change['request_id']==request['request_id']]
        if prior:
            if any(change['request']!=request for change in prior): raise ValueError('같은 계획 변경 요청의 내용이 바뀌었습니다.')
            return {'revision':prior[0]['revision']}
        if cycle['status']=='CLOSED': raise ValueError('종료한 투자의 목표는 변경하지 않습니다.')
        if request['revision']!=cycle['revision']: raise ValueError('계획이 변경되었습니다. 최신 목표를 확인해주세요.')
        if any(not r['voided'] and r['ledger_status']!='RECORDED' for r in current['results']):
            raise ValueError('확인 대기 체결의 장부 반영 여부를 먼저 처리해주세요.')
        if len({r['step_id'] for r in request['changes']})!=len(request['changes']):
            raise ValueError('같은 작업의 목표는 한 번만 지정해주세요.')
        desired=deepcopy(old_steps)
        for item in request['changes']:
            step=desired.get(item['step_id'])
            if not step or step['kind'] not in ('BUY','DEPOSIT'):
                raise ValueError('매수 목표 또는 추가 입금 목표를 변경해주세요. 이체·환전 안내는 잔고로 다시 계산합니다.')
            field='target_quantity' if step['kind']=='BUY' else 'target_amount'
            if item.get('target') is not None: step[field]=str(positive(item['target']))
            step['status']=item.get('status','ACTIVE')
        posted={}
        for result in current['results']:
            if result['voided'] or result['ledger_status']!='RECORDED': continue
            step=old_steps[result['step_id']]
            value=float(result['quantity'] if step['kind']=='BUY' else result['amount'])
            posted[step['id']]=posted.get(step['id'],0)+value
        c.execute('SELECT payload FROM rebalance_plans WHERE id=%s FOR UPDATE',(cycle['plan_id'],))
        plan=deepcopy(c.fetchone()['payload']);quantities={}
        for step in desired.values():
            if step['kind']=='BUY':
                plan['trade_plan'][step['line_no']]['qty']=step['target_quantity']
                plan['trade_plan'][step['line_no']]['execution_excluded']=step.get('status')=='EXCLUDED'
                quantities[step['line_no']]=posted.get(step['id'],0)
        setup=dict(cycle['payload'])
        fund=next((s for s in desired.values() if s['kind']=='DEPOSIT'),None)
        setup['additional_cash_krw']=max(0,float(fund['target_amount'])-posted.get(fund['id'],0)) if fund and fund.get('status')!='EXCLUDED' else 0
        used={}
        for step in old_steps.values():
            if step['kind']=='TRANSFER': used[step['account_id']]=used.get(step['account_id'],0)+posted.get(step['id'],0)
        setup['source_limits']={aid:max(0,float(cap)-used.get(aid,0)) for aid,cap in setup.get('source_limits',{}).items()}
        c.execute('SELECT * FROM accounts WHERE portfolio_id=%s ORDER BY id',(pid,));accounts=[dict(a) for a in c.fetchall()]
        c.execute('SELECT * FROM assets WHERE portfolio_id=%s',(pid,));assets=[dict(a) for a in c.fetchall()]
        calculated=build_steps(plan,accounts,assets,setup,quantities)
        by_key={s['key']:s for s in old_steps.values()}
        ids={s['key']:by_key[s['key']]['id'] if s['key'] in by_key else db.new_id() for s in calculated}
        revision=cycle['revision']+1;new={};ordinal=len(old_steps)
        for step in calculated:
            ident=ids[step['key']];old=by_key.get(step['key'])
            value=posted.get(ident,0)
            # Funds/FX/transfers describe remaining preparation; displayed goals
            # include already recorded facts, while buy quantities are total goals.
            if step['kind']!='BUY': step['target_amount']=str(float(step['target_amount'])+value)
            new[ident]={**(old or {}),**step,'id':ident,'status':'ACTIVE','execution_mode':'MANUAL',
                'depends_on':[ids[key] for key in step['depends_on']]}
        for ident,old in old_steps.items():
            if ident not in new:
                field='target_quantity' if old['kind']=='BUY' else 'target_amount'
                value=posted.get(ident,0)
                new[ident]={**desired[ident],'status':'EXCLUDED'}
                if old['kind'] not in ('BUY','DEPOSIT') and value>0:
                    new[ident].update(target_amount=str(value),status='ACTIVE')
                elif old['kind']=='DEPOSIT' and value>=float(desired[ident][field])-1e-7:
                    new[ident]['status']='ACTIVE'
        for ident,step in new.items():
            before=old_steps.get(ident)
            change=dict(request_id=request['request_id'],request=request,revision=revision,
                before=before,after={k:v for k,v in step.items() if k!='goal_history'},reason=request['reason'],changed_at=datetime.now(timezone.utc).isoformat())
            # Avoid nested previous histories inside each saved change.
            change['before']={k:v for k,v in before.items() if k!='goal_history'} if before else None
            step['goal_history']=[*(before or {}).get('goal_history',[]),change]
            if before: c.execute('UPDATE '+S+'steps SET payload=%s WHERE id=%s',(Json(step),ident))
            else:
                c.execute('INSERT INTO '+S+'steps(id,cycle_id,ordinal,kind,payload) VALUES(%s,%s,%s,%s,%s)',
                    (ident,cycle_id,ordinal,step['kind'],Json(step)));ordinal+=1
        c.execute('UPDATE '+S+'cycles SET revision=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s',(revision,cycle_id))
        conn.commit();return {'revision':revision}
