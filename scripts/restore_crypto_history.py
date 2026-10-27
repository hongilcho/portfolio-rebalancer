"""Explicit prepare/apply tool; preparation never connects to an app database.

Private holdings/manifest files belong under ignored backups/. Applying a remote
manifest additionally requires --allow-remote and a DSN in an explicit env var.
Never loads .env/secrets files, prints credentials, or overwrites a prior record.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['PORTFOLIO_LOAD_CONFIG_FILES']='0'
from logic.crypto_history import days,fingerprint,restore


def prepare(rows,start,end,quotes=None,provider=None,confirmed_at=None):
    from logic.market_providers.crypto_history import UpbitHistory
    provider=provider or UpbitHistory()
    if quotes is None:
        quotes={}
        symbols={h['symbol'].upper() for h in rows if float(h['quantity'])>0}
        for day in days(start,end):
            quotes[str(day)]=provider.prices(day,symbols)
            time.sleep(.25)  # At most eight candle requests/second even with fast responses.
    return restore(rows,quotes,start,end,confirmed_at or datetime.now(timezone.utc))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','apply'))
    parser.add_argument('--holdings-file',type=Path)
    parser.add_argument('--start',default='2026-10-05')
    parser.add_argument('--through')
    parser.add_argument('--confirmed-unchanged',action='store_true')
    parser.add_argument('--quotes-file',type=Path)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--dsn-env',default='CRYPTO_HISTORY_DATABASE_URL')
    parser.add_argument('--allow-remote',action='store_true')
    args=parser.parse_args()
    if args.action=='prepare':
        if not args.confirmed_unchanged or not args.holdings_file or not args.through:
            parser.error('보유 수량·원가 불변 확인, 보유 파일과 확인 종료일이 필요합니다.')
        output=args.manifest.resolve()
        if (ROOT/'backups').resolve() not in output.parents:parser.error('비공개 복원 파일은 backups 아래에 저장해주세요.')
        if output.exists():parser.error('기존 복원 파일은 보존합니다. 새 파일 이름을 사용해주세요.')
        rows=json.loads(args.holdings_file.read_text(encoding='utf8'))
        quotes=json.loads(args.quotes_file.read_text(encoding='utf8')) if args.quotes_file else None
        result=prepare(rows,args.start,args.through,quotes)
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('x',encoding='utf8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps({'action':'PREPARED_ONLY','days':len(result['records']),
            'start':args.start,'through':args.through,'basis_fingerprint':fingerprint(rows),'db_writes':0}))
        return
    import psycopg2
    from psycopg2.extensions import parse_dsn
    from data.repository_context import RepositoryContext
    from data.repositories.crypto_history import apply_restore
    dsn=os.environ.get(args.dsn_env)
    if not dsn:parser.error('명시한 DB 환경변수가 없습니다. 비공개 설정 파일은 자동으로 읽지 않습니다.')
    host=parse_dsn(dsn).get('host','')
    if host not in ('127.0.0.1','localhost','::1') and not args.allow_remote:
        parser.error('원격 DB 적용에는 별도의 --allow-remote 지정과 운영 반영 승인이 필요합니다.')
    manifest=json.loads(args.manifest.read_text(encoding='utf8'))
    class Connection:
        def __init__(self):self.raw=psycopg2.connect(dsn,connect_timeout=10)
        def __getattr__(self,name):return getattr(self.raw,name)
        def __enter__(self):return self
        def __exit__(self,*exc):self.raw.close()
    ctx=RepositoryContext(Connection,lambda:str(uuid.uuid4()),lambda:None)
    print(json.dumps(apply_restore(ctx,manifest)))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'status':'NOT_APPLIED_OR_NOT_CONFIRMED','error_type':type(exc).__name__}))
        raise SystemExit(1)
