"""Clone only this app's data from a READ ONLY Supabase snapshot to loopback.
No server startup imports here. Never print credentials or asset values.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone
import psycopg2
from psycopg2 import sql
from backup_database import connection_settings

ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/'backups/local_validation/pgsql/bin'
DIRECTORY=ROOT/'backups/local_rehearsal'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
TABLES=set('accounts assets bookkeeping_requests crypto_holdings holdings ledger_adjustments market_cache nh_notice_batches nh_notice_items performance_close_jobs performance_flows performance_snapshot_revisions performance_snapshots performance_tracking portfolios rebalance_plan_links rebalance_plans trade_history usd_cash_events usd_cash_state'.split())
LOCAL=dict(host='127.0.0.1',port=55438,user='ledger_qa',password='',passfile='NUL',sslmode='disable',connect_timeout=5)


def fingerprint(cursor,schema,table):
    cursor.execute(sql.SQL('SELECT to_jsonb(t) FROM {}.{} t').format(sql.Identifier(schema),sql.Identifier(table)))
    rows=sorted(json.dumps(row[0],sort_keys=True,separators=(',',':'),default=str) for row in cursor.fetchall())
    return {'rows':len(rows),'sha256':hashlib.sha256('\n'.join(rows).encode()).hexdigest()}


def pg_environment(settings):
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
    mapping={'host':'PGHOST','port':'PGPORT','user':'PGUSER','password':'PGPASSWORD','dbname':'PGDATABASE','sslmode':'PGSSLMODE','connect_timeout':'PGCONNECT_TIMEOUT','options':'PGOPTIONS','passfile':'PGPASSFILE'}
    env.update({mapping[k]:str(v) for k,v in settings.items() if k in mapping})
    env['PGPASSFILE']='NUL'
    return env


def main():
    settings=connection_settings()
    if settings.get('user')!='postgres.skeihahzseeyglvlprbe':raise RuntimeError('Configured connection is not the approved project')
    if ' 17.' not in subprocess.check_output([str(BIN/'pg_dump.exe'),'--version'],text=True):raise RuntimeError('PostgreSQL 17 dump tool required')
    DIRECTORY.mkdir(parents=True,exist_ok=False)
    archive=DIRECTORY/'application.dump'
    metadata={'source_project':'skeihahzseeyglvlprbe','source_read_only':True,'captured_at_utc':datetime.now(timezone.utc).isoformat(),'tables':{}}
    print('Opening READ ONLY production snapshot.',flush=True)
    with psycopg2.connect(**settings) as source:
        source.set_session(isolation_level='REPEATABLE READ',readonly=True)
        with source.cursor() as c:
            c.execute('SHOW transaction_read_only')
            if c.fetchone()[0]!='on':raise RuntimeError('Source transaction must be READ ONLY')
            c.execute('SHOW server_version');metadata['source_version']=c.fetchone()[0]
            metadata['serialization']={}
            for setting in ('TimeZone','extra_float_digits','DateStyle'):
                c.execute('SHOW '+setting);metadata['serialization'][setting]=c.fetchone()[0]
            c.execute("SELECT table_schema,table_name FROM information_schema.tables WHERE table_schema IN ('public','portfolio_execution','portfolio_security') AND table_type='BASE TABLE' ORDER BY 1,2")
            tables=c.fetchall()
            if any(s=='public' and t not in TABLES for s,t in tables):raise RuntimeError('Unexpected public tables require separate review')
            if not TABLES.issubset({t for s,t in tables if s=='public'}):raise RuntimeError('Expected app tables missing')
            c.execute('SELECT pg_export_snapshot()');snapshot=c.fetchone()[0]
            for schema,table in tables:metadata['tables'][schema+'.'+table]=fingerprint(c,schema,table)
            args=[str(BIN/'pg_dump.exe'),'--format=custom','--no-password','--no-owner','--no-privileges','--lock-wait-timeout=10s','--snapshot='+snapshot,'--file='+str(archive)]
            for schema in sorted({s for s,t in tables}):args.append('--schema='+schema)
            with (DIRECTORY/'dump.log').open('wb') as log:
                subprocess.run(args,env=pg_environment(settings),stdout=log,stderr=log,check=True,timeout=180)
        source.rollback()
    metadata['archive_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
    (DIRECTORY/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print('Production snapshot closed. All following DB work is local.',flush=True)
    name='portfolio_rehearsal_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    if not name.startswith('portfolio_rehearsal_'):raise RuntimeError('Local DB name guard')
    admin=psycopg2.connect(**LOCAL,dbname='postgres');admin.autocommit=True
    try:
        with admin.cursor() as c:c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    finally:admin.close()
    with psycopg2.connect(**LOCAL,dbname=name) as empty,empty.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        if cursor.fetchone()[0]!=0:raise RuntimeError('New local database must be empty')
        cursor.execute('DROP SCHEMA public')
    with (DIRECTORY/'restore.log').open('wb') as log:
        subprocess.run([str(BIN/'pg_restore.exe'),'--no-password','--no-owner','--no-privileges','--exit-on-error','--single-transaction','--dbname='+name,str(archive)],env=pg_environment({**LOCAL,'dbname':name}),stdout=log,stderr=log,check=True,timeout=180)
    with psycopg2.connect(**LOCAL,dbname=name) as conn,conn.cursor() as c:
        for setting,value in metadata['serialization'].items():c.execute('SELECT set_config(%s,%s,true)',(setting,value))
        for key,expected in metadata['tables'].items():
            if fingerprint(c,*key.split('.'))!=expected:raise RuntimeError('Restored data differs from snapshot')
    metadata['local_database']=name
    metadata['all_table_values_match']=True
    metadata['archive_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
    (DIRECTORY/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    pointer=ROOT/'backups/local_rehearsal/current.json'
    pointer.write_text(json.dumps({'directory':str(DIRECTORY.relative_to(ROOT)),'database':name,'captured_at_utc':metadata['captured_at_utc']},indent=2),encoding='utf-8')
    print('Local copy verified:',len(metadata['tables']),'tables; every row fingerprint matches.')
    print('Local database:',name)
    print('Ignored archive:',DIRECTORY.relative_to(ROOT))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Clone stopped safely:',type(error).__name__)
        raise SystemExit(1)
