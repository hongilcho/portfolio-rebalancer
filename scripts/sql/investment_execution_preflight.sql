-- Metadata only; no asset rows, connection strings, or passwords.
-- Run through the same database role as Render, before and after deployment.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';

SELECT current_user AS app_role,
       current_setting('server_version_num') AS server_version_num,
       has_database_privilege(current_user, current_database(), 'CREATE') AS can_create_schema,
       to_regnamespace('portfolio_execution') IS NOT NULL AS execution_schema_exists,
       to_regclass('portfolio_security.migrations') IS NOT NULL AS security_snapshot_exists,
       (SELECT count(*) FROM pg_roles
        WHERE rolname IN ('anon','authenticated','service_role')) AS expected_api_role_count,
       (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind='r') AS public_table_count;

WITH expected(name) AS (
    VALUES ('cycles'),('steps'),('attempts'),('results'),('record_links')
)
SELECT e.name AS expected_table, c.oid IS NOT NULL AS exists,
       pg_get_userbyid(c.relowner) AS table_owner,
       c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS force_rls,
       (SELECT count(*) FROM pg_policy p WHERE p.polrelid=c.oid) AS policy_count
FROM expected e
LEFT JOIN pg_namespace n ON n.nspname='portfolio_execution'
LEFT JOIN pg_class c ON c.relnamespace=n.oid AND c.relname=e.name AND c.relkind='r'
ORDER BY e.name;

SELECT n.nspname AS schema_name, pg_get_userbyid(n.nspowner) AS schema_owner,
       r.rolname AS api_role, r.rolsuper AS superuser, r.rolbypassrls AS bypass_rls,
       has_schema_privilege(r.oid,n.oid,'USAGE') AS schema_usage,
       has_schema_privilege(r.oid,n.oid,'CREATE') AS schema_create
FROM pg_namespace n CROSS JOIN pg_roles r
WHERE n.nspname='portfolio_execution'
  AND r.rolname IN ('anon','authenticated','service_role')
ORDER BY r.rolname;

SELECT c.relname AS table_name, r.rolname AS api_role,
       has_table_privilege(r.oid,c.oid,
         'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS any_table_access,
       has_any_column_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,REFERENCES') AS any_column_access
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN pg_roles r
WHERE n.nspname='portfolio_execution' AND c.relkind='r'
  AND r.rolname IN ('anon','authenticated','service_role')
ORDER BY c.relname,r.rolname;

-- Detect unexpected grants, including roles other than the three API roles.
SELECT c.relname AS table_name,
       CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS grantee,
       a.privilege_type, a.is_grantable
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
WHERE n.nspname='portfolio_execution' AND c.relkind='r'
  AND a.grantee<>c.relowner
ORDER BY c.relname,grantee,a.privilege_type;

ROLLBACK;
