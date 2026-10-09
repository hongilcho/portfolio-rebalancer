-- Read-only metadata. No keys, connection strings, financial rows, or function bodies.
WITH roles AS (
    SELECT oid,rolname,rolsuper,rolbypassrls,rolinherit,rolcanlogin
    FROM pg_roles WHERE rolname IN ('postgres','anon','authenticated','service_role')
), sections AS (
    SELECT 'roles_and_schema' AS section, jsonb_agg(jsonb_build_object(
        'role',r.rolname,'superuser',r.rolsuper,'bypass_rls',r.rolbypassrls,
        'inherits',r.rolinherit,'can_login',r.rolcanlogin,
        'public_usage',has_schema_privilege(r.oid,'public','USAGE'),
        'public_create',has_schema_privilege(r.oid,'public','CREATE'))) AS metadata
    FROM roles r
    UNION ALL
    SELECT 'role_memberships',jsonb_agg(jsonb_build_object(
        'member',m.rolname,'parent',p.rolname,'inherit',a.inherit_option,'set_role',a.set_option))
    FROM pg_auth_members a JOIN pg_roles m ON m.oid=a.member JOIN pg_roles p ON p.oid=a.roleid
    WHERE m.rolname IN ('postgres','anon','authenticated','service_role')
    UNION ALL
    SELECT 'public_sequences',jsonb_agg(jsonb_build_object(
        'name',c.relname,'owner',pg_get_userbyid(c.relowner),'acl',c.relacl::text))
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relkind='S'
    UNION ALL
    SELECT 'public_column_grants',jsonb_agg(jsonb_build_object(
        'table',c.relname,'column',a.attname,'acl',a.attacl::text))
    FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND a.attnum>0 AND NOT a.attisdropped AND a.attacl IS NOT NULL
    UNION ALL
    SELECT 'public_policies',jsonb_agg(jsonb_build_object(
        'table',tablename,'policy',policyname,'roles',roles,'command',cmd,'permissive',permissive))
    FROM pg_policies WHERE schemaname='public'
    UNION ALL
    SELECT 'public_views',jsonb_agg(jsonb_build_object(
        'name',c.relname,'owner',pg_get_userbyid(c.relowner),'options',c.reloptions,'acl',c.relacl::text))
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relkind IN ('v','m')
    UNION ALL
    SELECT 'public_functions',jsonb_agg(jsonb_build_object(
        'name',p.proname,'arguments',pg_get_function_identity_arguments(p.oid),
        'owner',pg_get_userbyid(p.proowner),'security_definer',p.prosecdef,'acl',p.proacl::text,
        'anon_execute',has_function_privilege('anon',p.oid,'EXECUTE'),
        'authenticated_execute',has_function_privilege('authenticated',p.oid,'EXECUTE'),
        'service_execute',has_function_privilege('service_role',p.oid,'EXECUTE')))
    FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
    UNION ALL
    SELECT 'postgres_default_grants',jsonb_agg(jsonb_build_object(
        'schema',COALESCE(n.nspname,'GLOBAL'),'object_type',d.defaclobjtype,'acl',d.defaclacl::text))
    FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace
    WHERE pg_get_userbyid(d.defaclrole)='postgres'
      AND (d.defaclnamespace=0 OR n.nspname='public')
)
SELECT section,COALESCE(metadata,'[]'::jsonb) AS metadata FROM sections ORDER BY section;
