"""Closed investment -> separate KRW recovery plan. Never move financial cash here."""
from decimal import Decimal,ROUND_FLOOR
from psycopg2.extras import RealDictCursor,Json
from logic.investment_execution import can_transfer_out,is_cma_account,build_return_steps
from logic.usd_cost import number
from data.repositories.bookkeeping import plain
from data.repositories.nh_notices import lock_scope
from data.repositories.investments import preview_token

def options(c,pid,cycle_id):
    c.execute('SELECT id,name,status,plan_id FROM portfolio_execution.cycles WHERE id=%s AND portfolio_id=%s',(cycle_id,pid))
    cycle=c.fetchone()
    if not cycle or cycle['status']!='CLOSED':raise ValueError('종료한 투자를 선택해주세요.')
    c.execute('SELECT payload FROM rebalance_plans WHERE id=%s',(cycle['plan_id'],))
    if c.fetchone()['payload'].get('plan_type')=='CASH_RETURN':raise ValueError('매수 투자를 종료한 후 현금 회수 계획을 만들어주세요.')
    c.execute('SELECT payload FROM portfolio_execution.steps WHERE cycle_id=%s',(cycle_id,))
    used={str(aid) for row in c.fetchall() for aid in (row['payload'].get('account_id'),row['payload'].get('destination_account_id')) if aid}
    c.execute('SELECT id,account_alias,account_type,deposit_krw,deposit_usd FROM accounts WHERE portfolio_id=%s ORDER BY account_alias',(pid,))
    accounts=[dict(row) for row in c.fetchall()]
    return dict(cycle=dict(cycle),accounts=[dict(a,transfer_allowed=can_transfer_out(a)) for a in accounts if str(a['id']) in used],
        cma_accounts=[a for a in accounts if is_cma_account(a)])

def read(db,pid,cycle_id):
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        result=options(c,pid,cycle_id)
        c.execute("""SELECT p.id,p.name,cy.id AS cycle_id,cy.status FROM rebalance_plans p LEFT JOIN portfolio_execution.cycles cy ON cy.plan_id=p.id
          WHERE p.portfolio_id=%s AND p.payload->>'plan_type'='CASH_RETURN' AND p.payload->>'source_cycle_id'=%s AND NOT p.archived ORDER BY p.created_at DESC""",(pid,cycle_id))
        result['plans']=[dict(row) for row in c.fetchall()];return result

def calculate(c,pid,cycle_id,request):
    result=options(c,pid,cycle_id)
    destination=next((a for a in result['cma_accounts'] if str(a['id'])==request['destination_account_id']),None)
    if not destination:raise ValueError('현재 포트폴리오의 CMA 회수 계좌를 선택해주세요.')
    accounts={str(a['id']):a for a in result['accounts']};lines=[]
    for aid,keep in request['keep_amounts'].items():
        account=accounts.get(aid);keep=number(keep)
        if not account or not account['transfer_allowed'] or aid==str(destination['id']):
            raise ValueError('회수 대상이 아닌 계좌입니다. 절세계좌는 예수금을 유지합니다.')
        available=max(Decimal(0),number(account['deposit_krw'] or 0))
        if keep<0 or keep>available:raise ValueError('남길 금액은 현재 원화 예수금 범위 안에서 지정해주세요.')
        amount=(available-keep).quantize(Decimal('1'),rounding=ROUND_FLOOR)
        if amount>0:lines.append(dict(account_id=aid,account_alias=account['account_alias'],amount_krw=str(amount),
            keep_krw=str(available-amount)))
    if not lines:raise ValueError('회수할 원화 금액이 없습니다.')
    plan=dict(plan_type='CASH_RETURN',source_cycle_id=cycle_id,destination_account_id=request['destination_account_id'],
        destination_alias=destination['account_alias'],return_plan=lines,trade_plan=[],
        transfer_plan=[dict(msg=line['account_alias']+' → '+destination['account_alias']+' '+line['amount_krw']+'원') for line in lines],
        scenario='PERIODIC',new_cash_krw=0,drift_threshold=0)
    build_return_steps(plan,result['accounts']+result['cma_accounts'])
    snapshot=dict(accounts=result['accounts'],destination=destination,source_cycle_id=cycle_id)
    token=preview_token(plan,snapshot)
    return dict(plan=plan,preview_token=token,total_krw=sum(float(line['amount_krw']) for line in lines))

def prepare(db,pid,cycle_id,request):
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        return calculate(c,pid,cycle_id,request)

def create(db,pid,cycle_id,request):
    request=plain(request)
    if not request['name'].strip():raise ValueError('회수 계획 이름을 입력해주세요.')
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        lock_scope(c,pid,[])
        c.execute("SELECT id,payload FROM rebalance_plans WHERE portfolio_id=%s AND payload->>'plan_type'='CASH_RETURN' AND payload->>'source_cycle_id'=%s AND payload->'return_request'->>'request_id'=%s",(pid,cycle_id,request['request_id']))
        prior=c.fetchone()
        if prior:
            if prior['payload']['return_request']!=request:raise ValueError('같은 회수 계획 요청의 내용이 바뀌었습니다.')
            return dict(id=prior['id'])
        result=calculate(c,pid,cycle_id,request)
        if not request.get('preview_token') or result['preview_token']!=request['preview_token']:
            raise ValueError('잔고 또는 회수 설정이 바뀌었습니다. 회수 계획을 다시 확인해주세요.')
        plan=result['plan'];plan['return_request']=request
        c.execute('SELECT COALESCE(MAX(trade_sequence),0) AS cutoff FROM trade_history');cutoff=c.fetchone()['cutoff']
        ident=db.new_id()
        c.execute('INSERT INTO rebalance_plans(id,portfolio_id,name,payload,cutoff) VALUES(%s,%s,%s,%s,%s)',
            (ident,pid,request['name'].strip(),Json(plan),cutoff))
        conn.commit();return dict(id=ident)
