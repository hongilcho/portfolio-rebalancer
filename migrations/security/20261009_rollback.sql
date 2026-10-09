-- DRAFT: apply only after separate production approval.
-- Keep Data API disabled. Restores only the saved settings, never financial rows.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='60s';
SELECT pg_advisory_xact_lock(424242);
DO $rollback$
DECLARE
    saved jsonb;
    obj jsonb;
    grant_row jsonb;
    col jsonb;
    target text;
    recipient text;
    privilege text;
    current_column record;
BEGIN
    IF current_user<>'postgres' THEN RAISE EXCEPTION 'Rollback requires postgres'; END IF;
    SELECT snapshot INTO saved FROM portfolio_security.migrations
        WHERE version='20261009_app_private_v1' FOR UPDATE;
    IF saved IS NULL THEN RAISE EXCEPTION 'No matching security snapshot exists'; END IF;
    FOR obj IN SELECT value FROM jsonb_array_elements(saved) LOOP
        target:=format('%I.%I',obj->>'schema',obj->>'name');
        IF NOT EXISTS(SELECT 1 FROM pg_class WHERE oid=to_regclass(target)
            AND pg_get_userbyid(relowner)=obj->>'owner' AND relkind::text=obj->>'kind') THEN
            RAISE EXCEPTION 'Object % changed since the snapshot; review before rollback',target;
        END IF;
        EXECUTE format('REVOKE ALL PRIVILEGES ON %s %s FROM PUBLIC, anon, authenticated, service_role',
            CASE WHEN obj->>'kind'='S' THEN 'SEQUENCE' ELSE 'TABLE' END,target);
        IF obj->>'kind'<>'S' THEN
            FOR current_column IN SELECT attname FROM pg_attribute
                WHERE attrelid=target::regclass AND attnum>0 AND NOT attisdropped AND attacl IS NOT NULL LOOP
                EXECUTE format('REVOKE ALL PRIVILEGES (%I) ON TABLE %s FROM PUBLIC, anon, authenticated, service_role',
                    current_column.attname,target);
            END LOOP;
            EXECUTE format('ALTER TABLE %s %s ROW LEVEL SECURITY',target,
                CASE WHEN (obj->>'rls')::boolean THEN 'ENABLE' ELSE 'DISABLE' END);
            EXECUTE format('ALTER TABLE %s %s ROW LEVEL SECURITY',target,
                CASE WHEN (obj->>'force')::boolean THEN 'FORCE' ELSE 'NO FORCE' END);
        END IF;
        FOR grant_row IN SELECT value FROM jsonb_array_elements(obj->'grants')
            WHERE value->>'grantee' IN ('PUBLIC','anon','authenticated','service_role') LOOP
            recipient:=CASE WHEN grant_row->>'grantee'='PUBLIC' THEN 'PUBLIC'
                ELSE format('%I',grant_row->>'grantee') END;
            privilege:=grant_row->>'privilege';
            IF privilege NOT IN ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','USAGE','MAINTAIN') THEN
                RAISE EXCEPTION 'Unexpected privilege in security snapshot';
            END IF;
            EXECUTE format('GRANT %s ON %s %s TO %s%s',privilege,
                CASE WHEN obj->>'kind'='S' THEN 'SEQUENCE' ELSE 'TABLE' END,target,recipient,
                CASE WHEN (grant_row->>'grantable')::boolean THEN ' WITH GRANT OPTION' ELSE '' END);
        END LOOP;
        FOR col IN SELECT value FROM jsonb_array_elements(obj->'columns') LOOP
            FOR grant_row IN SELECT value FROM jsonb_array_elements(col->'grants')
                WHERE value->>'grantee' IN ('PUBLIC','anon','authenticated','service_role') LOOP
                recipient:=CASE WHEN grant_row->>'grantee'='PUBLIC' THEN 'PUBLIC'
                    ELSE format('%I',grant_row->>'grantee') END;
                privilege:=grant_row->>'privilege';
                IF privilege NOT IN ('SELECT','INSERT','UPDATE','REFERENCES') THEN
                    RAISE EXCEPTION 'Unexpected column privilege in snapshot';
                END IF;
                EXECUTE format('GRANT %s (%I) ON TABLE %s TO %s%s',privilege,col->>'name',target,recipient,
                    CASE WHEN (grant_row->>'grantable')::boolean THEN ' WITH GRANT OPTION' ELSE '' END);
            END LOOP;
        END LOOP;
    END LOOP;
    DELETE FROM portfolio_security.migrations WHERE version='20261009_app_private_v1';
END $rollback$;

COMMIT;
