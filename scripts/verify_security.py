"""Synthetic security regression; no credential files, remote DBs, or HTTP."""
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for key in list(os.environ):
    if key.startswith("PG"):
        os.environ.pop(key,None)
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES="0",SUPABASE_URL="",
    APP_PASSWORD="synthetic-security-only",APP_SESSION_SECRET="synthetic-security-session-secret-32",
    PORTFOLIO_DB_SECURITY_ENABLED="0",PERFORMANCE_CLOSE_SCHEDULER_ENABLED="0",
    NAMUH_APP_KEY="",NAMUH_APP_SECRET="")
import psycopg2
from psycopg2 import sql
from data.security_schema import APP_TABLES, SECURITY_SQL
from data.repository_context import RepositoryContext
from data import schema
from data.repositories import trades

conn=psycopg2.connect(host="127.0.0.1",port=55438,dbname="postgres",user="ledger_qa",
    password="",passfile="NUL",sslmode="disable",connect_timeout=3)
cur=conn.cursor()
results=[]
class Lease:
    def cursor(self,*args,**kwargs): return conn.cursor(*args,**kwargs)
    def commit(self): pass  # All test writes remain inside the outer rollback.
    def rollback(self): raise AssertionError("Unexpected domain transaction rollback")
    def close(self): pass
lease=Lease()
ctx=RepositoryContext(lambda:lease,lambda:uuid4().hex,lambda:None,lambda:1400)
def role(name):cur.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(name)))
def denied(statement):
    cur.execute("SAVEPOINT denied_check")
    try:
        cur.execute(statement)
        raise AssertionError("Unauthorized statement succeeded")
    except psycopg2.Error as exc:
        assert exc.pgcode=="42501",exc.pgcode
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT denied_check")
        cur.execute("RELEASE SAVEPOINT denied_check")
def expect_abort(reason):
    cur.execute("SAVEPOINT failed_migration")
    try:
        cur.execute(SECURITY_SQL)
        raise AssertionError("Migration should fail closed")
    except psycopg2.Error as exc:
        assert reason in str(exc),str(exc)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT failed_migration")
        cur.execute("RELEASE SAVEPOINT failed_migration")
def settings_snapshot():
    cur.execute("""SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,c.relacl::text,
        (SELECT jsonb_agg(jsonb_build_array(a.attname,a.attacl::text) ORDER BY a.attnum)
         FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','S') ORDER BY c.relname""")
    # ACL entry ordering is not a permission; preserve every grant option.
    def acl(value):
        return None if value is None else tuple(sorted(value[1:-1].split(',')))
    return [(name,rls,force,acl(grants),[(column,acl(rights)) for column,rights in columns])
            for name,rls,force,grants,columns in cur.fetchall()]
def financial_digest():
    rows=[]
    for name in sorted(APP_TABLES):
        cur.execute(sql.SQL("SELECT to_jsonb(t) FROM public.{} t").format(sql.Identifier(name)))
        rows.append((name,sorted(json.dumps(row[0],sort_keys=True,default=str) for row in cur.fetchall())))
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()
try:
    cur.execute("SET LOCAL statement_timeout='15s'")
    cur.execute("SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=ANY(%s)",(APP_TABLES,))
    assert not cur.fetchall(),"Existing application QA objects found; do not reuse"
    cur.execute("SELECT 1 FROM pg_namespace WHERE nspname='portfolio_security'")
    assert not cur.fetchall(),"Existing security snapshot found; do not reuse"
    for name in ["postgres","anon","authenticated","service_role"]:
        cur.execute("SELECT rolbypassrls,rolsuper FROM pg_roles WHERE rolname=%s",(name,))
        existing=cur.fetchone()
        if existing is None:
            cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER {}").format(
                sql.Identifier(name),sql.SQL("BYPASSRLS" if name in ("postgres","service_role") else "NOBYPASSRLS")))
        elif name=="postgres":
            assert existing==(True,False),"Synthetic postgres must mirror Supabase's non-superuser bypass owner"
    cur.execute("GRANT CREATE ON DATABASE postgres TO postgres")
    cur.execute("GRANT USAGE,CREATE ON SCHEMA public TO postgres")
    role("postgres")
    # Mirror Supabase's public defaults, then initialize the actual app schema.
    cur.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon,authenticated,service_role")
    cur.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon,authenticated,service_role")
    schema._do_init_db_schema(ctx,lease,cur)
    cur.execute("INSERT INTO accounts(id,account_no,account_alias,account_type,deposit_krw,portfolio_id) VALUES('qa','QA-SEC','synthetic','GENERAL',10000,'default')")
    cur.execute("""INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id)
        VALUES('qa_asset','synthetic','QA_SEC','KR','["qa"]','default')""")
    cur.execute("GRANT SELECT(notes) ON accounts TO anon WITH GRANT OPTION")
    cur.execute((ROOT/"migrations/security/20261009_inspect.sql").read_text(encoding="utf-8"))
    assert len(cur.fetchall())==8
    original=settings_snapshot()
    digest=financial_digest()
    cur.execute("CREATE TABLE public.qa_unreviewed_table(id integer)")
    expect_abort("Additional API-accessible public tables")
    cur.execute("DROP TABLE public.qa_unreviewed_table")
    cur.execute("CREATE VIEW public.qa_exposed_view AS SELECT 1 AS x")
    expect_abort("views require separate review")
    cur.execute("DROP VIEW public.qa_exposed_view")
    cur.execute("CREATE FUNCTION public.qa_exposed_function() RETURNS integer LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'")
    expect_abort("SECURITY DEFINER functions require separate review")
    cur.execute("DROP FUNCTION public.qa_exposed_function()")
    role("ledger_qa");cur.execute("GRANT postgres TO anon");role("postgres")
    expect_abort("Residual")
    role("ledger_qa");cur.execute("REVOKE postgres FROM anon");role("postgres")
    assert settings_snapshot()==original
    results.append("Unexpected public views, definer RPCs, and inherited owner access abort with no partial changes")

    cur.execute(SECURITY_SQL)
    cur.execute("SELECT snapshot FROM portfolio_security.migrations WHERE version='20261009_app_private_v1'")
    saved=cur.fetchone()[0]
    cur.execute(SECURITY_SQL)
    cur.execute("SELECT snapshot FROM portfolio_security.migrations WHERE version='20261009_app_private_v1'")
    assert cur.fetchone()[0]==saved
    assert financial_digest()==digest
    results.append("Actual 20-table schema hardens twice without changing any synthetic financial rows or replacing the saved snapshot")

    for client in ("anon","authenticated","service_role"):
        role(client)
        for statement in ("SELECT * FROM public.accounts","INSERT INTO public.accounts(id,account_no,account_alias,account_type) VALUES('bad','BAD','bad','GENERAL')",
                          "UPDATE public.accounts SET deposit_krw=0","DELETE FROM public.accounts","TRUNCATE public.accounts",
                          "SELECT * FROM portfolio_security.migrations"):
            denied(statement)
        denied("SELECT nextval('public.trade_history_trade_sequence_seq')")
    results.append("All three API roles denied reads/writes/TRUNCATE/column grants/sequence use/private snapshot access")

    role("postgres");cur.execute("SAVEPOINT normal_trade")
    success,message=trades.execute_trade(ctx,"2026-01-02","qa","qa_asset","BUY",1,100,"KRW",1)
    assert success,message
    cur.execute("SELECT id FROM trade_history WHERE account_id='qa'")
    ident=cur.fetchone()[0]
    success,message=trades.delete_trades(ctx,[ident])
    assert success,message
    cur.execute("ROLLBACK TO SAVEPOINT normal_trade");cur.execute("RELEASE SAVEPOINT normal_trade")
    assert financial_digest()==digest
    results.append("Confirmed owner role maintains real repository BUY, cash update, and trade cancellation")

    os.environ["PORTFOLIO_DB_SECURITY_ENABLED"]="1"
    schema._do_init_db_schema(ctx,lease,cur)
    assert financial_digest()==digest
    results.append("Repeated actual startup schema + opt-in security remains functional")

    text=(ROOT/"migrations/security/20261009_rollback.sql").read_text(encoding="utf-8")
    body=text[text.index("DO $rollback$"):text.index("\nCOMMIT;")]
    cur.execute(body)
    assert settings_snapshot()==original
    assert financial_digest()==digest
    results.append("Rollback restores exact table/sequence/column ACLs, grant options, and RLS flags without changing financial rows")
    print(json.dumps({"environment":"synthetic localhost:55438 only; all objects, roles, grants rolled back","checks":results},indent=2))
finally:
    conn.rollback()
    conn.close()
