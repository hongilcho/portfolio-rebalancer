"""Explicit admin-only repair for the three reviewed legacy holdings.

Not imported by application startup or exposed through HTTP. No schema/holding/
cash/history writes. Prepare a private manifest first; apply only after approval.
Connection comes only from the named process environment, never config files.
"""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from psycopg2.extras import RealDictCursor
from data.repositories import realized_openings as repo
from data.repositories.nh_notices import lock_scope
from logic import realized_opening as policy

REPAIR='legacy-realized-three-2026-10-17'
TARGETS=(('해외ETF직투계좌','VT','US'),('해외ETF직투계좌','PDBC','US'),('금현물계좌','M04020000','KR'))


def lookup(c):
    rows=[]
    for alias,ticker,market in TARGETS:
        c.execute('''SELECT h.*,a.portfolio_id,a.account_alias,s.ticker,s.market
            FROM holdings h JOIN accounts a ON a.id=h.account_id JOIN assets s ON s.id=h.asset_id
            WHERE a.account_alias=%s AND UPPER(TRIM(s.ticker))=%s AND s.market=%s
              AND s.portfolio_id=a.portfolio_id AND NOT COALESCE(s.is_deposit,FALSE)''',(alias,ticker,market))
        found=c.fetchall()
        if len(found)!=1:raise ValueError('지정한 세 종목을 유일하게 확인할 수 없습니다. 적용하지 않았습니다.')
        rows.append(found[0])
    return rows


def prepare(db):
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        items=[]
        for h in lookup(c):
            if any(p['account_id']==h['account_id'] and p['asset_id']==h['asset_id'] for p in repo.load(c,h['portfolio_id'])):
                raise ValueError('이미 등록된 기준이 있습니다. 기존 작업 파일로 결과를 확인해주세요.')
            rows=repo.history(c,h)
            opening=policy.create(h['portfolio_id'],h,rows,REPAIR)  # validate without writing
            items.append(dict(portfolio_id=h['portfolio_id'],account_id=h['account_id'],asset_id=h['asset_id'],
                book_token=policy.token(h,rows),quantity=opening['quantity'],avg_krw=opening['avg_krw'],
                avg_usd=opening['avg_usd'],ticker=h['ticker'],account_alias=h['account_alias']))
        return dict(repair=REPAIR,positions=items)
    finally:conn.close()


def apply(db,manifest,rollback=False):
    if manifest.get('repair')!=REPAIR or len(manifest.get('positions',[]))!=3:
        raise ValueError('이번 세 종목의 사전 확인 파일만 사용할 수 있습니다.')
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        def validate():
            actual={(str(h['portfolio_id']),str(h['account_id']),str(h['asset_id'])) for h in lookup(c)}
            requested=[(str(h['portfolio_id']),str(h['account_id']),str(h['asset_id'])) for h in manifest['positions']]
            if len(set(requested))!=3 or set(requested)!=actual:
                raise ValueError('대상은 사전 확인한 세 종목으로 제한됩니다.')
        validate()
        groups=defaultdict(list)
        for p in manifest['positions']:groups[p['portfolio_id']].append(p)
        for pid,items in sorted(groups.items()):lock_scope(c,pid,sorted({p['account_id'] for p in items}))
        validate()
        for pid,items in sorted(groups.items()):
            if rollback:
                for p in items:
                    baseline=REPAIR+'/'+p['account_id']+'/'+p['asset_id']
                    repo.revoke(db,pid,dict(request_id='undo:'+policy.digest(baseline)[:48],baseline_id=baseline),transaction=conn)
            else:
                repo.commit(db,pid,dict(request_id=REPAIR,positions=[{k:p[k] for k in
                    ('account_id','asset_id','book_token')} for p in items]),transaction=conn)
        conn.commit();db.invalidate()
        return dict(status='reverted' if rollback else 'applied',positions=3,financial_rows_changed=0)
    except Exception:conn.rollback();raise
    finally:conn.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group(required=True)
    for mode in ('prepare','apply','rollback'):modes.add_argument('--'+mode,type=Path)
    parser.add_argument('--connection-env',choices=('SUPABASE_SESSION_URL','SUPABASE_URL'),default='SUPABASE_SESSION_URL')
    args=parser.parse_args()
    dsn=os.environ.get(args.connection_env)
    if not dsn:parser.error('지정한 환경변수가 없습니다. 인증정보를 명령줄에 입력하지 마세요.')
    import psycopg2
    from data.repository_context import RepositoryContext
    db=RepositoryContext(lambda:psycopg2.connect(dsn,connect_timeout=10,
        options='-c statement_timeout=15000 -c lock_timeout=10000'),lambda:str(uuid.uuid4()),lambda:None)
    try:
        if args.prepare:
            result=prepare(db)
            fd=os.open(args.prepare,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
            print('사전 확인 완료: 대상 3종목. DB 쓰기 없음. 비공개 작업 파일을 보관하세요.')
        else:
            path=args.apply or args.rollback
            result=apply(db,json.loads(path.read_text(encoding='utf-8')),rollback=bool(args.rollback))
            print(json.dumps(result))
    except Exception:
        print('작업에 실패했습니다. DB 변경은 롤백되었습니다. 인증정보 보호를 위해 오류 원문은 출력하지 않습니다.',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
