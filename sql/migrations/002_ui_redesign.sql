-- 002: fields and tables behind the redesigned Jobs / Processes screens

ALTER TABLE job ADD COLUMN IF NOT EXISTS product_identifier VARCHAR(64);
ALTER TABLE job ADD COLUMN IF NOT EXISTS expected_cycle_s INT NOT NULL DEFAULT 60;
ALTER TABLE job ADD COLUMN IF NOT EXISTS image_png BYTEA;

-- Station processes (Arkite "Processes" tab): built-in automation that wraps every job
CREATE TABLE IF NOT EXISTS station_process (
    id            SERIAL PRIMARY KEY,
    station_id    INT NOT NULL REFERENCES station(id),
    code          VARCHAR(32) NOT NULL,
    name          VARCHAR(80) NOT NULL,
    description   TEXT,
    start_trigger VARCHAR(24) NOT NULL,
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    params        JSONB NOT NULL DEFAULT '{}'::jsonb,
    sort_order    INT NOT NULL DEFAULT 0,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by    INT REFERENCES app_user(id),
    UNIQUE (station_id, code)
);

INSERT INTO permission (code, description) VALUES
  ('MANAGE_PROCESSES', 'Configure station processes (job selection, cycle, barcode, evidence, reset)')
ON CONFLICT (code) DO NOTHING;
INSERT INTO role_permission (role_code, permission_code) VALUES
  ('ADMIN', 'MANAGE_PROCESSES'), ('ENGINEER', 'MANAGE_PROCESSES')
ON CONFLICT DO NOTHING;
