"""Rehearse upgrade and logical restore in new loopback synthetic databases only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for key in list(os.environ):
    if key.startswith('PG'):
        os.environ.pop(key, None)
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0', SUPABASE_URL='',
    PORTFOLIO_DB_SECURITY_ENABLED='1', PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0',
    NAMUH_APP_KEY='', NAMUH_APP_SECRET='',APP_PASSWORD='qa-release-only',
    APP_SESSION_SECRET='synthetic-release-session-secret-not-for-production')
import psycopg2
from psycopg2 import sql
from data.repository_context import RepositoryContext
from data import schema
from data.security_schema import APP_TABLES
from data.investment_schema import TABLES
from data.repositories import plans, investments, trades
from backend.routers.investments import Setup
from backend.routers.trades import BatchTradeRequest

settings = dict(host='127.0.0.1', port=55438, user='ledger_qa', dbname='postgres',
    password='', passfile='NUL', sslmode='disable', connect_timeout=3)
prefix = 'investment_release_' + uuid4().hex[:10]
names = [prefix + suffix for suffix in ('_source', '_before', '_after')]
directory = ROOT / 'backups/local_validation/investment_release' / prefix
directory.mkdir(parents=True, exist_ok=False)
pg_bin = ROOT / 'backups/local_validation/pgsql/bin'
created_role = False
checks = []
environment = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
environment.update(PGHOST='127.0.0.1', PGPORT='55438', PGUSER='ledger_qa',
    PGPASSWORD='', PGPASSFILE='NUL', PGSSLMODE='disable')

def connect(name, owner=True):
    assert name in names
    conn = psycopg2.connect(**{**settings, 'dbname': name})
    if owner:
        with conn.cursor() as c:
            c.execute('SET ROLE postgres')
        conn.commit()
    return conn

def ctx(name):
    return RepositoryContext(lambda: connect(name), lambda: uuid4().hex, lambda: None, lambda: 1400)

def scalar(name, statement, args=()):
    with connect(name) as conn, conn.cursor() as c:
        c.execute(statement, args)
        return c.fetchone()[0]

def digest(name, namespace, tables):
    result = {}
    with connect(name) as conn, conn.cursor() as c:
        for table in tables:
            c.execute(sql.SQL('SELECT to_jsonb(t) FROM {}.{} t').format(
                sql.Identifier(namespace), sql.Identifier(table)))
            rows = sorted(json.dumps(row[0], sort_keys=True, default=str) for row in c.fetchall())
            result[table] = hashlib.sha256(json.dumps(rows).encode()).hexdigest()
    return result

def public_acl(name):
    with connect(name) as conn, conn.cursor() as c:
        c.execute("""SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,
          pg_get_userbyid(c.relowner),c.relacl::text FROM pg_class c
          JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='public' AND c.relname=ANY(%s) ORDER BY c.relname""", (APP_TABLES,))
        return c.fetchall()

def backup(name, filename):
    target = directory / filename
    environment['PGDATABASE'] = name
    with (directory / (filename+'.log')).open('wb') as log:
        subprocess.run([str(pg_bin/'pg_dump.exe'), '--no-password', '--format=custom',
            '--file='+str(target)], env=environment, stdout=log, stderr=log, check=True)
    return target

def restore(name, archive):
    environment['PGDATABASE'] = name
    with (directory/(name+'.restore.log')).open('wb') as log:
        subprocess.run([str(pg_bin/'pg_restore.exe'), '--no-password',
            '--exit-on-error', '--single-transaction', '--dbname='+name,
            str(archive)], env=environment, stdout=log, stderr=log, check=True)

try:
    admin = psycopg2.connect(**settings)
    admin.autocommit = True
    with admin.cursor() as c:
        c.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname='postgres'")
        role = c.fetchone()
        if role is None:
            c.execute('CREATE ROLE postgres NOLOGIN NOSUPERUSER BYPASSRLS')
            created_role = True
        else:
            assert role == (False, True), 'Unexpected existing QA owner role'
        for api_role in ('anon','authenticated','service_role'):
            c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (api_role,))
            assert c.fetchone(), 'Run the synthetic security setup first'
        for name in names:
            c.execute(sql.SQL('CREATE DATABASE {} OWNER postgres').format(sql.Identifier(name)))
    admin.close()
    source, before_db, after_db = names
    original_initialize = schema.initialize_execution
    try:
        # Before-upgrade state: identical public journal + security, no new schema.
        schema.initialize_execution = lambda cursor: None
        schema.init_db(ctx(source))
    finally:
        schema.initialize_execution = original_initialize
    with connect(source) as conn, conn.cursor() as c:
        c.execute("""INSERT INTO accounts(id,account_no,account_alias,account_type,deposit_krw,portfolio_id)
          VALUES('qa_cma','SYNTHETIC-CMA','Synthetic CMA','CMA',100000,'default'),
                ('qa_isa','SYNTHETIC-ISA','Synthetic ISA','ISA',100000,'default')""")
        c.execute("""INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id)
          VALUES('qa_bond','Synthetic bond','SYNTHETIC-BOND','KR','["qa_isa"]','default')""")
        conn.commit()
    day = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    old_trade = BatchTradeRequest(request_id='qa-before-upgrade',portfolio_id='default',
        trade_date=day,trades=[dict(account_id='qa_isa',asset_id='qa_bond',
            trade_type='BUY',quantity=1,price=9000,currency='KRW')]).model_dump(mode='json')
    trades.execute_batch(ctx(source), old_trade)
    financial_before = digest(source, 'public', APP_TABLES)
    security_before = scalar(source, 'SELECT snapshot FROM portfolio_security.migrations')
    acl_before = public_acl(source)
    assert scalar(source, "SELECT to_regnamespace('portfolio_execution')") is None
    before_archive = backup(source, 'before-upgrade.dump')
    restore(before_db, before_archive)
    assert digest(before_db, 'public', APP_TABLES) == financial_before
    assert scalar(before_db, "SELECT to_regnamespace('portfolio_execution')") is None
    checks.append('Before-upgrade logical backup restores all synthetic journal rows')

    schema.init_db(ctx(source))
    schema.init_db(ctx(source))
    assert digest(source, 'public', APP_TABLES) == financial_before
    assert public_acl(source) == acl_before
    assert scalar(source, 'SELECT snapshot FROM portfolio_security.migrations') == security_before
    checks.append('Repeated upgrade preserves 20 public tables, RLS/ACL and original security snapshot')
    preflight = (ROOT/'scripts/sql/investment_execution_preflight.sql').read_text(encoding='utf-8')
    for name in (before_db, source):
        with connect(name) as conn, conn.cursor() as c:
            c.execute(preflight.split('ROLLBACK;')[0])
            assert c.fetchall() == [], 'Unexpected grant outside owner'
            conn.rollback()
    checks.append('Read-only deployment SQL runs both before and after upgrade')
    payload = dict(scenario='NEW_CASH',new_cash_krw=0,drift_threshold=5,transfer_plan=[],
        trade_plan=[dict(account_id='qa_isa',asset_id='qa_bond',type='BUY',qty=2,price=9000,total_krw=18000)])
    plan = plans.save(ctx(source),'default','Synthetic upgrade investment',payload)
    setup = Setup(request_id='qa-upgrade-start',plan_id=plan,representative_account_id='qa_cma',
        usd_krw=1400).model_dump(mode='json')
    setup['preview_token'] = investments.prepare(ctx(source),'default',setup)['preview_token']
    cycle = investments.create(ctx(source),'default',setup)
    detail = investments.read(ctx(source),'default',cycle['id'])
    step = next(s for s in detail['steps'] if s['kind']=='BUY')
    new_trade = {**old_trade,'request_id':'qa-after-upgrade','trades':[dict(
        account_id='qa_isa',asset_id='qa_bond',trade_type='BUY',quantity=2,price=9000,
        currency='KRW',execution=dict(cycle_id=cycle['id'],step_id=step['id'],revision=1))]}
    receipt = trades.execute_batch(ctx(source),new_trade)
    investments.set_status(ctx(source),'default',cycle['id'],'CLOSED')
    closed = investments.read(ctx(source),'default',cycle['id'])
    assert closed['report']['remaining_steps']==[]
    journal = digest(source,'public',APP_TABLES)
    workflow = digest(source,'portfolio_execution',TABLES)
    after_archive = backup(source,'after-upgrade.dump')
    restore(after_db,after_archive)
    assert digest(after_db,'public',APP_TABLES)==journal
    assert digest(after_db,'portfolio_execution',TABLES)==workflow
    assert investments.read(ctx(after_db),'default',cycle['id'])==closed
    schema.init_db(ctx(after_db))
    assert digest(after_db,'public',APP_TABLES)==journal
    assert digest(after_db,'portfolio_execution',TABLES)==workflow
    checks.append('After-upgrade restore preserves journal, stable task IDs, links and frozen closed report')

    with connect(after_db) as conn, conn.cursor() as c:
        for role in ('anon','authenticated','service_role'):
            for table in ('public.accounts','portfolio_execution.cycles'):
                c.execute('SAVEPOINT denied')
                try:
                    c.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
                    c.execute(sql.SQL('SELECT * FROM {}.{} LIMIT 0').format(
                        *(sql.Identifier(part) for part in table.split('.'))))
                    raise AssertionError('Public API role read protected data after restore')
                except psycopg2.Error as error:
                    assert error.pgcode=='42501'
                finally:
                    c.execute('ROLLBACK TO SAVEPOINT denied')
    checks.append('Restored public journal and private workflow reject all three API roles')

    # Rehearse journal-only code rollback against the retained additional schema.
    import types
    original = subprocess.check_output(['git','show','1b5aeea:data/repositories/trades.py'],
        cwd=ROOT, text=True, encoding='utf-8')
    old_repository = types.ModuleType('synthetic_previous_trades')
    exec(compile(original,'synthetic_previous_trades','exec'),old_repository.__dict__)
    balances = digest(after_db,'public',['accounts','holdings'])
    old_receipt = old_repository.execute_batch(ctx(after_db),
        {**old_trade,'request_id':'qa-code-rollback-buy','trades':[{key:value for key,value in item.items() if key!='execution'} for item in old_trade['trades']]})
    ok, message = old_repository.delete_trades(ctx(after_db),old_receipt['trade_ids'])
    assert ok, message
    assert digest(after_db,'public',['accounts','holdings'])==balances
    assert digest(after_db,'portfolio_execution',TABLES)==workflow
    checks.append('Previous committed trade repository can record/cancel without altering retained workflow')

    manifest = dict(environment='synthetic loopback only', checks=checks,
        archives={p.name:dict(bytes=p.stat().st_size,
            sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            for p in (before_archive,after_archive)})
    (directory/'results.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2))
finally:
    admin = psycopg2.connect(**settings)
    admin.autocommit = True
    with admin.cursor() as c:
        for name in names:
            assert name.startswith('investment_release_')
            c.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))
        if created_role:
            c.execute('DROP ROLE postgres')
    admin.close()
