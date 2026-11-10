-- Run ONCE as a DBA (postgres) AFTER the application has created the schema (first start or --migrate).
-- Creates a dedicated application login so production stations do not use the postgres superuser.
-- Supply the password at execution time; never commit it:
--   psql -U postgres -d PDI_Inspection -v app_pw="'<strong-password>'" -f least_privilege_role.sql

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vista_app') THEN
    CREATE ROLE vista_app LOGIN;
  END IF;
END $$;
ALTER ROLE vista_app PASSWORD :app_pw;

GRANT CONNECT ON DATABASE "PDI_Inspection" TO vista_app;
GRANT USAGE ON SCHEMA pdi_inspection TO vista_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA pdi_inspection TO vista_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA pdi_inspection TO vista_app;

-- Audit trail is append-only for the application.
REVOKE UPDATE, DELETE, TRUNCATE ON pdi_inspection.audit_log FROM vista_app;
-- Inspection history must never be deleted by the application.
REVOKE DELETE, TRUNCATE ON pdi_inspection.inspection_run, pdi_inspection.inspection_step_result FROM vista_app;
-- Role/permission catalogue is maintained by migrations only.
REVOKE INSERT, UPDATE, DELETE ON pdi_inspection.role, pdi_inspection.permission, pdi_inspection.role_permission FROM vista_app;

-- Schema migrations (DDL) must be executed with the owner account:
--   temporarily set DB_USER/DB_PASSWORD to the owner in .env and run:  RANE_VISTA.exe --migrate
