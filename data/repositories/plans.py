"""Saved simulations and explicit links to actual journal trades."""
from psycopg2.extras import RealDictCursor, Json


def validate_lines(lines, accounts, assets):
    import math
    if not 1 <= len(lines) <= 500:
        raise ValueError('저장할 매매 계획은 1~500행이어야 합니다.')
    for line in lines:
        if line['account_id'] not in accounts or line['asset_id'] not in assets:
            raise ValueError('다른 포트폴리오의 계좌·종목은 사용할 수 없습니다.')
        if line['type'] not in ('BUY', 'SELL') or not math.isfinite(line['qty']) or line['qty'] <= 0:
            raise ValueError('계획의 방향·수량을 확인해주세요.')


def save(ctx, pid, name, payload):
    with ctx.connect() as conn, conn.cursor() as c:
        c.execute('SELECT id FROM accounts WHERE portfolio_id=%s', (pid,))
        accounts = {r[0] for r in c.fetchall()}
        c.execute('SELECT id FROM assets WHERE portfolio_id=%s', (pid,))
        assets = {r[0] for r in c.fetchall()}
        validate_lines(payload['trade_plan'], accounts, assets)
        c.execute('SELECT COALESCE(MAX(trade_sequence),0) FROM trade_history')
        cutoff = c.fetchone()[0]
        ident = ctx.new_id()
        c.execute('INSERT INTO rebalance_plans(id,portfolio_id,name,payload,cutoff) VALUES(%s,%s,%s,%s,%s)',
                  (ident,pid,name,Json(payload),cutoff))
        conn.commit()
        return ident


def read(ctx, pid):
    with ctx.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SELECT * FROM rebalance_plans WHERE portfolio_id=%s ORDER BY created_at DESC', (pid,))
        plans = [dict(r) for r in c.fetchall()]
        c.execute('''SELECT l.*,t.quantity,t.price,t.currency,t.exchange_rate,t.trade_date
            FROM rebalance_plan_links l JOIN rebalance_plans p ON p.id=l.plan_id
            JOIN trade_history t ON t.id=l.trade_id WHERE p.portfolio_id=%s''', (pid,))
        links = [dict(r) for r in c.fetchall()]
        c.execute('''SELECT t.*,a.account_alias,s.name AS asset_name FROM trade_history t
            JOIN accounts a ON a.id=t.account_id JOIN assets s ON s.id=t.asset_id
            WHERE a.portfolio_id=%s AND s.portfolio_id=%s AND t.trade_type IN ('BUY','SELL')
            AND NOT EXISTS(SELECT 1 FROM rebalance_plan_links l WHERE l.trade_id=t.id)
            ORDER BY t.trade_sequence DESC''', (pid,pid))
        candidates = [dict(r) for r in c.fetchall()]
        for p in plans:
            p['links'] = [r for r in links if r['plan_id']==p['id']]
        return {'plans':plans, 'candidates':candidates}


def guard_execution(c,plan_id,archive=False):
    c.execute('SELECT status FROM portfolio_execution.cycles WHERE plan_id=%s',(plan_id,))
    row=c.fetchone()
    if row:
        state=row['status'] if isinstance(row,dict) else row[0]
        if not archive or state!='CLOSED':
            raise ValueError('투자 실행에 사용 중인 계획입니다. 기록 연결·목표 변경은 8번 탭에서 처리해주세요.')


def link(ctx, pid, plan_id, line_no, trade_id):
    with ctx.connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SELECT * FROM rebalance_plans WHERE id=%s AND portfolio_id=%s FOR UPDATE', (plan_id,pid))
        plan = c.fetchone()
        if not plan or plan['archived'] or not 0 <= line_no < len(plan['payload']['trade_plan']):
            raise ValueError('진행 중인 계획과 매매 행을 확인해주세요.')
        guard_execution(c,plan_id)
        line = plan['payload']['trade_plan'][line_no]
        c.execute('''SELECT t.* FROM trade_history t JOIN accounts a ON a.id=t.account_id
            JOIN assets s ON s.id=t.asset_id WHERE t.id=%s AND a.portfolio_id=%s AND s.portfolio_id=%s FOR UPDATE OF t''', (trade_id,pid,pid))
        t = c.fetchone()
        if not t or t['trade_sequence'] <= plan['cutoff'] or (t['account_id'],t['asset_id'],t['trade_type']) != (line['account_id'],line['asset_id'],line['type']):
            raise ValueError('계획 저장 후 입력한 동일 계좌·종목·방향의 거래만 연결할 수 있습니다.')
        c.execute('SELECT plan_id,line_no FROM rebalance_plan_links WHERE trade_id=%s', (trade_id,))
        prior = c.fetchone()
        if prior:
            if prior['plan_id']==plan_id and prior['line_no']==line_no:
                return
            raise ValueError('이미 다른 계획 행에 연결된 거래입니다.')
        c.execute('INSERT INTO rebalance_plan_links VALUES(%s,%s,%s)', (plan_id,line_no,trade_id))
        conn.commit()


def unlink(ctx, pid, plan_id, trade_id):
    with ctx.connect() as conn, conn.cursor() as c:
        c.execute('SELECT id FROM rebalance_plans WHERE id=%s AND portfolio_id=%s FOR UPDATE',(plan_id,pid))
        if not c.fetchone(): raise ValueError('계획을 찾을 수 없습니다.')
        guard_execution(c,plan_id)
        c.execute('''DELETE FROM rebalance_plan_links l USING rebalance_plans p
            WHERE l.plan_id=p.id AND p.portfolio_id=%s AND p.id=%s AND l.trade_id=%s''', (pid,plan_id,trade_id))
        conn.commit()


def archive(ctx, pid, plan_id, archived):
    with ctx.connect() as conn, conn.cursor() as c:
        c.execute('SELECT id FROM rebalance_plans WHERE id=%s AND portfolio_id=%s FOR UPDATE',(plan_id,pid))
        if not c.fetchone(): raise ValueError('계획을 찾을 수 없습니다.')
        guard_execution(c,plan_id,archive=True)
        c.execute('UPDATE rebalance_plans SET archived=%s WHERE id=%s AND portfolio_id=%s', (archived,plan_id,pid))
        if not c.rowcount:
            raise ValueError('계획을 찾을 수 없습니다.')
        conn.commit()
