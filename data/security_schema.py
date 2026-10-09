"""Opt-in owner-preserving hardening of the exact application table set."""
import os

APP_TABLES = ["accounts","assets","bookkeeping_requests","crypto_holdings","holdings","ledger_adjustments","market_cache","nh_notice_batches","nh_notice_items","performance_close_jobs","performance_flows","performance_snapshot_revisions","performance_snapshots","performance_tracking","portfolios","rebalance_plan_links","rebalance_plans","trade_history","usd_cash_events","usd_cash_state"]
SECURITY_SQL = r"""DO $security$
DECLARE
    names text[] := ARRAY['accounts','assets','bookkeeping_requests','crypto_holdings','holdings','ledger_adjustments','market_cache','nh_notice_batches','nh_notice_items','performance_close_jobs','performance_flows','performance_snapshot_revisions','performance_snapshots','performance_tracking','portfolios','rebalance_plan_links','rebalance_plans','trade_history','usd_cash_events','usd_cash_state'];
    item record;
    col record;
    api_role text;
    snapshot jsonb;
BEGIN
    IF current_user <> 'postgres' THEN
        RAISE EXCEPTION 'Security migration requires the confirmed postgres owner role';
    END IF;
    IF (SELECT count(*) FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role')) <> 3 THEN
        RAISE EXCEPTION 'Expected Supabase API roles are missing';
    END IF;
    IF (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relname=ANY(names) AND c.relkind='r'
        AND pg_get_userbyid(c.relowner)='postgres') <> cardinality(names) THEN
        RAISE EXCEPTION 'Expected application tables or postgres ownership differ; no changes committed';
    END IF;
    IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p') AND NOT c.relname=ANY(names)
        AND (has_any_column_privilege('anon',c.oid,'SELECT')
             OR has_any_column_privilege('authenticated',c.oid,'SELECT')
             OR has_any_column_privilege('service_role',c.oid,'SELECT'))) THEN
        RAISE EXCEPTION 'Additional API-accessible public tables require separate review';
    END IF;
    IF EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('v','m')
        AND (has_any_column_privilege('anon',c.oid,'SELECT')
             OR has_any_column_privilege('authenticated',c.oid,'SELECT')
             OR has_any_column_privilege('service_role',c.oid,'SELECT'))) THEN
        RAISE EXCEPTION 'Public API-readable views require separate review';
    END IF;
    IF EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.prosecdef
        AND (has_function_privilege('anon',p.oid,'EXECUTE')
             OR has_function_privilege('authenticated',p.oid,'EXECUTE')
             OR has_function_privilege('service_role',p.oid,'EXECUTE'))) THEN
        RAISE EXCEPTION 'Public API-executable SECURITY DEFINER functions require separate review';
    END IF;
    IF EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='portfolio_security'
        AND pg_get_userbyid(nspowner)<>'postgres') THEN
        RAISE EXCEPTION 'Security snapshot schema has unexpected ownership';
    END IF;
END $security$;

CREATE SCHEMA IF NOT EXISTS portfolio_security AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA portfolio_security FROM PUBLIC, anon, authenticated, service_role;
CREATE TABLE IF NOT EXISTS portfolio_security.migrations(
    version text PRIMARY KEY, snapshot jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
DO $audit$
BEGIN
    IF (SELECT pg_get_userbyid(relowner) FROM pg_class
        WHERE oid='portfolio_security.migrations'::regclass) <> 'postgres' THEN
        RAISE EXCEPTION 'Security snapshot table has unexpected ownership';
    END IF;
END $audit$;
REVOKE ALL ON TABLE portfolio_security.migrations FROM PUBLIC, anon, authenticated, service_role;
ALTER TABLE portfolio_security.migrations ENABLE ROW LEVEL SECURITY;

DO $apply$
DECLARE
    names text[] := ARRAY['accounts','assets','bookkeeping_requests','crypto_holdings','holdings','ledger_adjustments','market_cache','nh_notice_batches','nh_notice_items','performance_close_jobs','performance_flows','performance_snapshot_revisions','performance_snapshots','performance_tracking','portfolios','rebalance_plan_links','rebalance_plans','trade_history','usd_cash_events','usd_cash_state'];
    item record;
    col record;
    api_role text;
    snapshot jsonb;
BEGIN
    SELECT jsonb_agg(jsonb_build_object(
        'schema',n.nspname,'name',c.relname,'kind',c.relkind,
        'owner',pg_get_userbyid(c.relowner),
        'rls',c.relrowsecurity,'force',c.relforcerowsecurity,
        'grants',COALESCE((SELECT jsonb_agg(jsonb_build_object(
            'grantor',pg_get_userbyid(x.grantor),
            'grantee',CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,
            'privilege',x.privilege_type,'grantable',x.is_grantable))
            FROM aclexplode(COALESCE(c.relacl,acldefault(
                CASE WHEN c.relkind='S' THEN 'S'::"char" ELSE 'r'::"char" END,c.relowner))) x),'[]'::jsonb),
        'columns',COALESCE((SELECT jsonb_agg(jsonb_build_object('name',a.attname,'grants',
            COALESCE((SELECT jsonb_agg(jsonb_build_object('grantor',pg_get_userbyid(x.grantor),
                'grantee',CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,
                'privilege',x.privilege_type,'grantable',x.is_grantable))
             FROM aclexplode(a.attacl) x),'[]'::jsonb)))
            FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
            AND a.attacl IS NOT NULL),'[]'::jsonb)))
    INTO snapshot
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND (
        (c.relkind='r' AND c.relname=ANY(names)) OR
        (c.relkind='S' AND EXISTS(SELECT 1 FROM pg_depend d
            JOIN pg_class t ON t.oid=d.refobjid JOIN pg_namespace tn ON tn.oid=t.relnamespace
            WHERE d.classid='pg_class'::regclass AND d.refclassid='pg_class'::regclass
            AND d.objid=c.oid AND d.deptype IN ('a','i')
            AND tn.nspname='public' AND t.relname=ANY(names)))
    );
    IF EXISTS(SELECT 1 FROM jsonb_array_elements(snapshot) obj WHERE obj->>'owner'<>'postgres') THEN
        RAISE EXCEPTION 'An attached sequence has unexpected ownership';
    END IF;
    IF EXISTS(
        SELECT 1 FROM jsonb_array_elements(snapshot) obj,
        LATERAL jsonb_array_elements(obj->'grants') g
        WHERE g->>'grantee' IN ('PUBLIC','anon','authenticated','service_role')
        AND g->>'grantor'<>'postgres'
    ) OR EXISTS(
        SELECT 1 FROM jsonb_array_elements(snapshot) obj,
        LATERAL jsonb_array_elements(obj->'columns') cols,
        LATERAL jsonb_array_elements(cols->'grants') g
        WHERE g->>'grantee' IN ('PUBLIC','anon','authenticated','service_role')
        AND g->>'grantor'<>'postgres'
    ) THEN
        RAISE EXCEPTION 'A non-owner grant chain requires separate rollback review';
    END IF;
    INSERT INTO portfolio_security.migrations(version,snapshot)
    VALUES('20261009_app_private_v1',snapshot) ON CONFLICT(version) DO NOTHING;

    FOR item IN SELECT obj FROM jsonb_array_elements(snapshot) obj LOOP
        IF item.obj->>'kind'='S' THEN
            EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %I.%I FROM PUBLIC, anon, authenticated, service_role',
                item.obj->>'schema',item.obj->>'name');
        ELSE
            EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %I.%I FROM PUBLIC, anon, authenticated, service_role',
                item.obj->>'schema',item.obj->>'name');
            FOR col IN SELECT a.attname FROM pg_attribute a
                WHERE a.attrelid=format('%I.%I',item.obj->>'schema',item.obj->>'name')::regclass
                AND a.attnum>0 AND NOT a.attisdropped AND a.attacl IS NOT NULL LOOP
                EXECUTE format('REVOKE ALL PRIVILEGES (%I) ON TABLE %I.%I FROM PUBLIC, anon, authenticated, service_role',
                    col.attname,item.obj->>'schema',item.obj->>'name');
            END LOOP;
            EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',item.obj->>'schema',item.obj->>'name');
        END IF;
    END LOOP;

    FOREACH api_role IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
        FOR item IN SELECT obj FROM jsonb_array_elements(snapshot) obj LOOP
            IF item.obj->>'kind'='S' THEN
                IF has_sequence_privilege(api_role,format('%I.%I',item.obj->>'schema',item.obj->>'name'),'USAGE,SELECT,UPDATE') THEN
                    RAISE EXCEPTION 'Residual sequence access for %; migration rolled back',api_role;
                END IF;
            ELSE
                IF has_table_privilege(api_role,format('%I.%I',item.obj->>'schema',item.obj->>'name'),
                        'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER' ||
                        CASE WHEN current_setting('server_version_num')::integer>=170000 THEN ',MAINTAIN' ELSE '' END)
                   OR has_any_column_privilege(api_role,format('%I.%I',item.obj->>'schema',item.obj->>'name'),'SELECT')
                   OR has_any_column_privilege(api_role,format('%I.%I',item.obj->>'schema',item.obj->>'name'),'INSERT')
                   OR has_any_column_privilege(api_role,format('%I.%I',item.obj->>'schema',item.obj->>'name'),'UPDATE')
                   OR has_any_column_privilege(api_role,format('%I.%I',item.obj->>'schema',item.obj->>'name'),'REFERENCES') THEN
                    RAISE EXCEPTION 'Residual table or column access for %; migration rolled back',api_role;
                END IF;
            END IF;
        END LOOP;
    END LOOP;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role')
        AND rolsuper) THEN
        RAISE EXCEPTION 'Unexpected superuser API role requires separate review';
    END IF;
END $apply$;
"""

def initialize(cursor):
    if os.getenv("PORTFOLIO_DB_SECURITY_ENABLED", "0").lower() not in ("1", "true", "on"):
        return
    cursor.execute(SECURITY_SQL)
