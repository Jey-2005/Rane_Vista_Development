-- RANE VISTA - initial schema
-- Applied by vista/db/migrations.py inside the configured schema (search_path is set by the runner).

CREATE TABLE IF NOT EXISTS role (
    code        VARCHAR(32) PRIMARY KEY,
    name        VARCHAR(64) NOT NULL,
    rank        INT NOT NULL
);

CREATE TABLE IF NOT EXISTS permission (
    code        VARCHAR(64) PRIMARY KEY,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_permission (
    role_code       VARCHAR(32) NOT NULL REFERENCES role(code) ON DELETE CASCADE,
    permission_code VARCHAR(64) NOT NULL REFERENCES permission(code) ON DELETE CASCADE,
    PRIMARY KEY (role_code, permission_code)
);

CREATE TABLE IF NOT EXISTS station (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(32) NOT NULL UNIQUE,
    name        VARCHAR(120) NOT NULL,
    plant       VARCHAR(80),
    line        VARCHAR(80),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_user (
    id                   SERIAL PRIMARY KEY,
    username             VARCHAR(64) NOT NULL,
    full_name            VARCHAR(120) NOT NULL,
    employee_code        VARCHAR(32),
    role_code            VARCHAR(32) NOT NULL REFERENCES role(code),
    password_hash        TEXT NOT NULL,
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    all_stations         BOOLEAN NOT NULL DEFAULT FALSE,
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
    failed_attempts      INT NOT NULL DEFAULT 0,
    locked_until         TIMESTAMPTZ,
    last_login_at        TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by           INT REFERENCES app_user(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_app_user_username ON app_user (lower(username));
CREATE UNIQUE INDEX IF NOT EXISTS ux_app_user_empcode ON app_user (employee_code) WHERE employee_code IS NOT NULL;

-- Station access, enforced in the service layer (ADMIN role / all_stations bypass)
CREATE TABLE IF NOT EXISTS user_station (
    user_id    INT NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    station_id INT NOT NULL REFERENCES station(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, station_id)
);

CREATE TABLE IF NOT EXISTS job (
    id           SERIAL PRIMARY KEY,
    station_id   INT NOT NULL REFERENCES station(id),
    code         VARCHAR(64) NOT NULL,
    name         VARCHAR(160) NOT NULL,
    description  TEXT,
    part_number  VARCHAR(64),
    status       VARCHAR(16) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','RELEASED','ARCHIVED')),
    revision     INT NOT NULL DEFAULT 0,
    released_at  TIMESTAMPTZ,
    released_by  INT REFERENCES app_user(id),
    settings     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by   INT REFERENCES app_user(id),
    updated_by   INT REFERENCES app_user(id),
    UNIQUE (station_id, code)
);

CREATE TABLE IF NOT EXISTS job_variant (
    id            SERIAL PRIMARY KEY,
    job_id        INT NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    code          VARCHAR(32) NOT NULL,
    name          VARCHAR(80) NOT NULL,
    part_number   VARCHAR(64),
    barcode_regex TEXT,
    sort_order    INT NOT NULL DEFAULT 0,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (job_id, code)
);

CREATE TABLE IF NOT EXISTS detection (
    id          SERIAL PRIMARY KEY,
    station_id  INT NOT NULL REFERENCES station(id),
    job_id      INT REFERENCES job(id) ON DELETE CASCADE,          -- NULL = station-wide detection
    name        VARCHAR(120) NOT NULL,
    group_name  VARCHAR(80) NOT NULL DEFAULT '',
    det_type    VARCHAR(16) NOT NULL CHECK (det_type IN ('OBJECT','ACTIVITY','BUTTON','QUALITY')),
    sensor      VARCHAR(16) NOT NULL DEFAULT 'DEPTH' CHECK (sensor IN ('DEPTH','IR','COLOR','VISION')),
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    params      JSONB NOT NULL DEFAULT '{}'::jsonb,   -- user-tunable thresholds
    model       JSONB NOT NULL DEFAULT '{}'::jsonb,   -- taught geometry / statistics
    sort_order  INT NOT NULL DEFAULT 0,
    taught_at   TIMESTAMPTZ,
    taught_by   INT REFERENCES app_user(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_detection_name ON detection (station_id, COALESCE(job_id, 0), lower(name));

-- Binary teaching data (reference arrays, QC class samples)
CREATE TABLE IF NOT EXISTS detection_sample (
    id           BIGSERIAL PRIMARY KEY,
    detection_id INT NOT NULL REFERENCES detection(id) ON DELETE CASCADE,
    kind         VARCHAR(24) NOT NULL,             -- REFS | QC
    class_name   VARCHAR(80),
    data         BYTEA NOT NULL,
    meta         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_detection_sample_det ON detection_sample (detection_id, kind);

CREATE TABLE IF NOT EXISTS step (
    id            SERIAL PRIMARY KEY,
    job_id        INT NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    parent_id     INT REFERENCES step(id) ON DELETE CASCADE,
    sort_order    INT NOT NULL DEFAULT 0,
    step_type     VARCHAR(32) NOT NULL,
    name          VARCHAR(160) NOT NULL,
    detection_id  INT REFERENCES detection(id) ON DELETE SET NULL,
    variant_codes TEXT[] NOT NULL DEFAULT '{}',    -- empty = all variants
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    instruction   TEXT,
    params        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_step_job ON step (job_id, parent_id, sort_order);

CREATE TABLE IF NOT EXISTS calibration (
    id          SERIAL PRIMARY KEY,
    station_id  INT NOT NULL REFERENCES station(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by  INT REFERENCES app_user(id),
    rms_px      REAL,
    data        JSONB NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_calibration_active ON calibration (station_id) WHERE is_active;

CREATE TABLE IF NOT EXISTS app_setting (
    station_id INT NOT NULL REFERENCES station(id),
    key        VARCHAR(64) NOT NULL,
    value      JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by INT REFERENCES app_user(id),
    PRIMARY KEY (station_id, key)
);

CREATE TABLE IF NOT EXISTS inspection_run (
    id            UUID PRIMARY KEY,
    station_id    INT NOT NULL REFERENCES station(id),
    job_id        INT NOT NULL REFERENCES job(id),
    job_revision  INT NOT NULL,
    variant_code  VARCHAR(32),
    barcode       VARCHAR(128),
    operator_id   INT REFERENCES app_user(id),
    started_at    TIMESTAMPTZ NOT NULL,
    finished_at   TIMESTAMPTZ,
    result        VARCHAR(12) NOT NULL DEFAULT 'RUNNING' CHECK (result IN ('RUNNING','PASS','FAIL','ABORTED')),
    cycle_time_ms INT,
    ng_count      INT NOT NULL DEFAULT 0,
    forced_count  INT NOT NULL DEFAULT 0,
    remarks       TEXT
);
CREATE INDEX IF NOT EXISTS ix_run_barcode ON inspection_run (barcode);
CREATE INDEX IF NOT EXISTS ix_run_station_started ON inspection_run (station_id, started_at DESC);

CREATE TABLE IF NOT EXISTS inspection_step_result (
    id             BIGSERIAL PRIMARY KEY,
    run_id         UUID NOT NULL REFERENCES inspection_run(id) ON DELETE CASCADE,
    step_id        INT,
    step_name      VARCHAR(160) NOT NULL,
    step_path      VARCHAR(400),
    step_type      VARCHAR(32),
    detection_name VARCHAR(120),
    started_at     TIMESTAMPTZ,
    finished_at    TIMESTAMPTZ,
    duration_ms    INT,
    result         VARCHAR(12) NOT NULL CHECK (result IN ('OK','NG','SKIPPED','FORCED','INFO')),
    qc_class       VARCHAR(80),
    score          REAL,
    value          TEXT,
    evidence_path  TEXT,
    actor_id       INT REFERENCES app_user(id)
);
CREATE INDEX IF NOT EXISTS ix_step_result_run ON inspection_step_result (run_id);

-- Append-only audit trail (UPDATE/DELETE revoked from the application role, see sql/admin)
CREATE TABLE IF NOT EXISTS audit_log (
    id           BIGSERIAL PRIMARY KEY,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    station_code VARCHAR(32),
    user_id      INT,
    username     VARCHAR(64),
    action       VARCHAR(64) NOT NULL,
    entity       VARCHAR(64),
    entity_id    VARCHAR(64),
    details      JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_log (ts DESC);

-- ------------------------------------------------------------------ seed data
INSERT INTO role (code, name, rank) VALUES
  ('ADMIN','Administrator',100), ('QUALITY','Quality approver',80),
  ('ENGINEER','Process engineer',60), ('SUPERVISOR','Line supervisor',40),
  ('OPERATOR','Operator',10)
ON CONFLICT (code) DO NOTHING;

INSERT INTO permission (code, description) VALUES
  ('RUN_INSPECTION','Run inspections at the station'),
  ('OVERRIDE_STEP','Force a step or accept an NG result (supervisor override)'),
  ('VIEW_REPORTS','View traceability reports and dashboards'),
  ('EXPORT_REPORTS','Export reports to Excel / CSV'),
  ('EDIT_JOBS','Create and edit jobs, variants and steps'),
  ('TEACH_DETECTIONS','Create, teach and finetune detections'),
  ('RELEASE_JOBS','Release a job revision to production'),
  ('CALIBRATE','Calibrate the workstation'),
  ('MANAGE_HARDWARE','Configure camera, projector and scanner'),
  ('MANAGE_USERS','Manage users and station access'),
  ('VIEW_AUDIT','View the audit trail'),
  ('MANAGE_SETTINGS','Change station settings')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permission (role_code, permission_code)
SELECT 'ADMIN', code FROM permission
ON CONFLICT DO NOTHING;

INSERT INTO role_permission (role_code, permission_code) VALUES
  ('QUALITY','RUN_INSPECTION'),('QUALITY','OVERRIDE_STEP'),('QUALITY','VIEW_REPORTS'),
  ('QUALITY','EXPORT_REPORTS'),('QUALITY','RELEASE_JOBS'),('QUALITY','VIEW_AUDIT'),
  ('ENGINEER','RUN_INSPECTION'),('ENGINEER','VIEW_REPORTS'),('ENGINEER','EXPORT_REPORTS'),
  ('ENGINEER','EDIT_JOBS'),('ENGINEER','TEACH_DETECTIONS'),('ENGINEER','CALIBRATE'),
  ('ENGINEER','MANAGE_HARDWARE'),
  ('SUPERVISOR','RUN_INSPECTION'),('SUPERVISOR','OVERRIDE_STEP'),('SUPERVISOR','VIEW_REPORTS'),
  ('SUPERVISOR','EXPORT_REPORTS'),
  ('OPERATOR','RUN_INSPECTION')
ON CONFLICT DO NOTHING;
