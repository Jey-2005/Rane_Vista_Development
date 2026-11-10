"""Data-access layer. Every SQL statement is parameterised.

Authorisation is enforced one level up in `vista.services` - repositories are dumb.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

from vista.db.database import Database


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StationRepo:
    def __init__(self, db: Database):
        self.db = db

    def ensure(self, code: str, name: str) -> dict:
        row = self.db.fetchone("SELECT * FROM station WHERE code = %s", (code,))
        if row:
            return row
        return self.db.fetchone(
            "INSERT INTO station (code, name) VALUES (%s, %s) "
            "ON CONFLICT (code) DO UPDATE SET name = station.name RETURNING *", (code, name))

    def list(self) -> list[dict]:
        return self.db.fetchall("SELECT * FROM station ORDER BY code")

    def update(self, station_id: int, name: str, plant: str, line: str) -> None:
        self.db.execute("UPDATE station SET name=%s, plant=%s, line=%s WHERE id=%s", (name, plant, line, station_id))


class UserRepo:
    def __init__(self, db: Database):
        self.db = db

    def count(self) -> int:
        return self.db.fetchone("SELECT count(*) AS n FROM app_user")["n"]

    def by_login(self, login: str) -> dict | None:
        return self.db.fetchone(
            "SELECT * FROM app_user WHERE lower(username) = lower(%s) OR employee_code = %s", (login, login))

    def by_id(self, user_id: int) -> dict | None:
        return self.db.fetchone("SELECT * FROM app_user WHERE id = %s", (user_id,))

    def list(self) -> list[dict]:
        return self.db.fetchall(
            "SELECT u.id, u.username, u.full_name, u.employee_code, u.role_code, u.is_active, u.all_stations, "
            "u.locked_until, u.last_login_at, u.must_change_password, "
            "COALESCE(array_agg(s.code ORDER BY s.code) FILTER (WHERE s.code IS NOT NULL), '{}') AS stations "
            "FROM app_user u LEFT JOIN user_station us ON us.user_id = u.id "
            "LEFT JOIN station s ON s.id = us.station_id GROUP BY u.id ORDER BY u.username")

    def create(self, username: str, full_name: str, employee_code: str | None, role_code: str,
               password_hash: str, all_stations: bool, created_by: int | None, must_change: bool = True) -> int:
        row = self.db.fetchone(
            "INSERT INTO app_user (username, full_name, employee_code, role_code, password_hash, all_stations, "
            "created_by, must_change_password) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (username, full_name, employee_code or None, role_code, password_hash, all_stations, created_by, must_change))
        return row["id"]

    def update(self, user_id: int, full_name: str, employee_code: str | None, role_code: str,
               is_active: bool, all_stations: bool) -> None:
        self.db.execute(
            "UPDATE app_user SET full_name=%s, employee_code=%s, role_code=%s, is_active=%s, all_stations=%s, "
            "updated_at=now() WHERE id=%s",
            (full_name, employee_code or None, role_code, is_active, all_stations, user_id))

    def set_password(self, user_id: int, password_hash: str, must_change: bool) -> None:
        self.db.execute(
            "UPDATE app_user SET password_hash=%s, must_change_password=%s, failed_attempts=0, locked_until=NULL, "
            "updated_at=now() WHERE id=%s", (password_hash, must_change, user_id))

    def register_failure(self, user_id: int, max_attempts: int, lock_minutes: int) -> None:
        self.db.execute(
            "UPDATE app_user SET failed_attempts = failed_attempts + 1, "
            "locked_until = CASE WHEN failed_attempts + 1 >= %s THEN now() + make_interval(mins => %s) "
            "ELSE locked_until END WHERE id = %s", (max_attempts, lock_minutes, user_id))

    def register_success(self, user_id: int) -> None:
        self.db.execute(
            "UPDATE app_user SET failed_attempts=0, locked_until=NULL, last_login_at=now() WHERE id=%s", (user_id,))

    def unlock(self, user_id: int) -> None:
        self.db.execute("UPDATE app_user SET failed_attempts=0, locked_until=NULL WHERE id=%s", (user_id,))

    def permissions(self, role_code: str) -> set[str]:
        rows = self.db.fetchall("SELECT permission_code FROM role_permission WHERE role_code=%s", (role_code,))
        return {r["permission_code"] for r in rows}

    def roles(self) -> list[dict]:
        return self.db.fetchall("SELECT * FROM role ORDER BY rank DESC")

    def permission_matrix(self) -> tuple[list[dict], list[dict], set[tuple[str, str]]]:
        roles = self.roles()
        perms = self.db.fetchall("SELECT * FROM permission ORDER BY code")
        pairs = {(r["role_code"], r["permission_code"]) for r in self.db.fetchall("SELECT * FROM role_permission")}
        return roles, perms, pairs

    def has_station_access(self, user_id: int, station_id: int) -> bool:
        row = self.db.fetchone(
            "SELECT (u.all_stations OR u.role_code = 'ADMIN' OR EXISTS ("
            " SELECT 1 FROM user_station us WHERE us.user_id = u.id AND us.station_id = %s)) AS ok "
            "FROM app_user u WHERE u.id = %s", (station_id, user_id))
        return bool(row and row["ok"])

    def set_stations(self, user_id: int, station_ids: list[int]) -> None:
        with self.db.tx() as conn:
            conn.execute("DELETE FROM user_station WHERE user_id=%s", (user_id,))
            for sid in station_ids:
                conn.execute("INSERT INTO user_station (user_id, station_id) VALUES (%s,%s)", (user_id, sid))


class SettingsRepo:
    def __init__(self, db: Database, station_id: int):
        self.db = db
        self.station_id = station_id

    def all(self) -> dict[str, Any]:
        rows = self.db.fetchall("SELECT key, value FROM app_setting WHERE station_id=%s", (self.station_id,))
        return {r["key"]: r["value"] for r in rows}

    def set(self, key: str, value: Any, user_id: int | None) -> None:
        self.db.execute(
            "INSERT INTO app_setting (station_id, key, value, updated_by) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (station_id, key) DO UPDATE SET value=EXCLUDED.value, updated_at=now(), "
            "updated_by=EXCLUDED.updated_by", (self.station_id, key, Jsonb(value), user_id))


class JobRepo:
    def __init__(self, db: Database, station_id: int):
        self.db = db
        self.station_id = station_id

    # jobs ---------------------------------------------------------------------
    def list(self, include_archived: bool = False) -> list[dict]:
        q = "SELECT * FROM job WHERE station_id=%s"
        if not include_archived:
            q += " AND status <> 'ARCHIVED'"
        return self.db.fetchall(q + " ORDER BY code", (self.station_id,))

    def released(self) -> list[dict]:
        return self.db.fetchall("SELECT * FROM job WHERE station_id=%s AND status='RELEASED' ORDER BY code",
                                (self.station_id,))

    def get(self, job_id: int) -> dict | None:
        return self.db.fetchone("SELECT * FROM job WHERE id=%s AND station_id=%s", (job_id, self.station_id))

    def create(self, code: str, name: str, part_number: str, description: str, user_id: int) -> int:
        row = self.db.fetchone(
            "INSERT INTO job (station_id, code, name, part_number, description, created_by, updated_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (self.station_id, code, name, part_number, description, user_id, user_id))
        return row["id"]

    def update(self, job_id: int, name: str, part_number: str, description: str, settings: dict, user_id: int) -> None:
        self.db.execute(
            "UPDATE job SET name=%s, part_number=%s, description=%s, settings=%s, updated_at=now(), updated_by=%s, "
            "status = CASE WHEN status='RELEASED' THEN 'DRAFT' ELSE status END WHERE id=%s AND station_id=%s",
            (name, part_number, description, Jsonb(settings), user_id, job_id, self.station_id))

    def mark_draft(self, job_id: int, user_id: int) -> None:
        """Any edit to a released job puts it back to DRAFT until it is re-released (change control)."""
        self.db.execute(
            "UPDATE job SET status='DRAFT', updated_at=now(), updated_by=%s WHERE id=%s AND status='RELEASED'",
            (user_id, job_id))

    def release(self, job_id: int, user_id: int) -> int:
        row = self.db.fetchone(
            "UPDATE job SET status='RELEASED', revision=revision+1, released_at=now(), released_by=%s "
            "WHERE id=%s AND station_id=%s RETURNING revision", (user_id, job_id, self.station_id))
        return row["revision"]

    def archive(self, job_id: int, user_id: int) -> None:
        self.db.execute("UPDATE job SET status='ARCHIVED', updated_at=now(), updated_by=%s WHERE id=%s",
                        (user_id, job_id))

    # variants -----------------------------------------------------------------
    def variants(self, job_id: int) -> list[dict]:
        return self.db.fetchall("SELECT * FROM job_variant WHERE job_id=%s ORDER BY sort_order, code", (job_id,))

    def save_variants(self, job_id: int, variants: list[dict]) -> None:
        with self.db.tx() as conn:
            keep = [v["code"] for v in variants]
            conn.execute("DELETE FROM job_variant WHERE job_id=%s AND NOT (code = ANY(%s))", (job_id, keep))
            for i, v in enumerate(variants):
                conn.execute(
                    "INSERT INTO job_variant (job_id, code, name, part_number, barcode_regex, sort_order, is_active) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (job_id, code) DO UPDATE SET name=EXCLUDED.name, "
                    "part_number=EXCLUDED.part_number, barcode_regex=EXCLUDED.barcode_regex, "
                    "sort_order=EXCLUDED.sort_order, is_active=EXCLUDED.is_active",
                    (job_id, v["code"], v["name"], v.get("part_number") or None, v.get("barcode_regex") or None,
                     i, v.get("is_active", True)))

    # steps --------------------------------------------------------------------
    def steps(self, job_id: int) -> list[dict]:
        return self.db.fetchall(
            "SELECT s.*, d.name AS detection_name, d.det_type FROM step s "
            "LEFT JOIN detection d ON d.id = s.detection_id WHERE s.job_id=%s "
            "ORDER BY s.parent_id NULLS FIRST, s.sort_order, s.id", (job_id,))

    def create_step(self, job_id: int, parent_id: int | None, step_type: str, name: str, sort_order: int,
                    params: dict, detection_id: int | None = None) -> int:
        row = self.db.fetchone(
            "INSERT INTO step (job_id, parent_id, step_type, name, sort_order, params, detection_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (job_id, parent_id, step_type, name, sort_order, Jsonb(params), detection_id))
        return row["id"]

    def update_step(self, step_id: int, name: str, detection_id: int | None, variant_codes: list[str],
                    enabled: bool, instruction: str, params: dict) -> None:
        self.db.execute(
            "UPDATE step SET name=%s, detection_id=%s, variant_codes=%s, enabled=%s, instruction=%s, params=%s, "
            "updated_at=now() WHERE id=%s",
            (name, detection_id, variant_codes, enabled, instruction, Jsonb(params), step_id))

    def delete_step(self, step_id: int) -> None:
        self.db.execute("DELETE FROM step WHERE id=%s", (step_id,))

    def reorder(self, ordering: list[tuple[int, int | None, int]]) -> None:
        """ordering: (step_id, parent_id, sort_order) for every step of the job."""
        with self.db.tx() as conn:
            for sid, pid, order in ordering:
                conn.execute("UPDATE step SET parent_id=%s, sort_order=%s WHERE id=%s", (pid, order, sid))

    def duplicate(self, job_id: int, new_code: str, new_name: str, user_id: int) -> int:
        """Deep copy of a job (variants, job-specific detections incl. teaching, steps)."""
        with self.db.tx() as conn:
            src = conn.execute("SELECT * FROM job WHERE id=%s", (job_id,)).fetchone()
            new_id = conn.execute(
                "INSERT INTO job (station_id, code, name, description, part_number, settings, created_by, updated_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (src["station_id"], new_code, new_name, src["description"], src["part_number"],
                 Jsonb(src["settings"]), user_id, user_id)).fetchone()["id"]
            conn.execute(
                "INSERT INTO job_variant (job_id, code, name, part_number, barcode_regex, sort_order, is_active) "
                "SELECT %s, code, name, part_number, barcode_regex, sort_order, is_active FROM job_variant "
                "WHERE job_id=%s", (new_id, job_id))
            det_map: dict[int, int] = {}
            for d in conn.execute("SELECT * FROM detection WHERE job_id=%s", (job_id,)).fetchall():
                nid = conn.execute(
                    "INSERT INTO detection (station_id, job_id, name, group_name, det_type, sensor, enabled, params, "
                    "model, sort_order, taught_at, taught_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (d["station_id"], new_id, d["name"], d["group_name"], d["det_type"], d["sensor"], d["enabled"],
                     Jsonb(d["params"]), Jsonb(d["model"]), d["sort_order"], d["taught_at"], d["taught_by"])
                ).fetchone()["id"]
                det_map[d["id"]] = nid
                conn.execute(
                    "INSERT INTO detection_sample (detection_id, kind, class_name, data, meta) "
                    "SELECT %s, kind, class_name, data, meta FROM detection_sample WHERE detection_id=%s",
                    (nid, d["id"]))
            step_map: dict[int, int] = {}
            rows = conn.execute("SELECT * FROM step WHERE job_id=%s ORDER BY id", (job_id,)).fetchall()
            pending = list(rows)
            while pending:  # parents before children
                progressed = False
                for s in list(pending):
                    if s["parent_id"] is not None and s["parent_id"] not in step_map:
                        continue
                    nid = conn.execute(
                        "INSERT INTO step (job_id, parent_id, sort_order, step_type, name, detection_id, variant_codes, "
                        "enabled, instruction, params) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (new_id, step_map.get(s["parent_id"]), s["sort_order"], s["step_type"], s["name"],
                         det_map.get(s["detection_id"], s["detection_id"]), s["variant_codes"], s["enabled"],
                         s["instruction"], Jsonb(s["params"]))).fetchone()["id"]
                    step_map[s["id"]] = nid
                    pending.remove(s)
                    progressed = True
                if not progressed:
                    break
        return new_id


class DetectionRepo:
    def __init__(self, db: Database, station_id: int):
        self.db = db
        self.station_id = station_id

    def list_for(self, job_id: int | None) -> list[dict]:
        """Station-wide detections + the job-specific detections of job_id."""
        return self.db.fetchall(
            "SELECT * FROM detection WHERE station_id=%s AND (job_id IS NULL OR job_id=%s) "
            "ORDER BY job_id NULLS FIRST, group_name, sort_order, name", (self.station_id, job_id))

    def get(self, det_id: int) -> dict | None:
        return self.db.fetchone("SELECT * FROM detection WHERE id=%s AND station_id=%s", (det_id, self.station_id))

    def create(self, job_id: int | None, name: str, group_name: str, det_type: str, sensor: str,
               params: dict) -> int:
        row = self.db.fetchone(
            "INSERT INTO detection (station_id, job_id, name, group_name, det_type, sensor, params) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (self.station_id, job_id, name, group_name, det_type, sensor, Jsonb(params)))
        return row["id"]

    def update_props(self, det_id: int, name: str, group_name: str, sensor: str, enabled: bool,
                     params: dict) -> None:
        self.db.execute(
            "UPDATE detection SET name=%s, group_name=%s, sensor=%s, enabled=%s, params=%s, updated_at=now() "
            "WHERE id=%s AND station_id=%s", (name, group_name, sensor, enabled, Jsonb(params), det_id, self.station_id))

    def save_model(self, det_id: int, model: dict, user_id: int, refs_blob: bytes | None,
                   qc_samples: list[tuple[str, bytes, dict]] | None) -> None:
        with self.db.tx() as conn:
            conn.execute(
                "UPDATE detection SET model=%s, taught_at=now(), taught_by=%s, updated_at=now() WHERE id=%s",
                (Jsonb(model), user_id, det_id))
            if refs_blob is not None:
                conn.execute("DELETE FROM detection_sample WHERE detection_id=%s AND kind='REFS'", (det_id,))
                conn.execute("INSERT INTO detection_sample (detection_id, kind, data) VALUES (%s,'REFS',%s)",
                             (det_id, refs_blob))
            if qc_samples is not None:
                conn.execute("DELETE FROM detection_sample WHERE detection_id=%s AND kind='QC'", (det_id,))
                for cls, data, meta in qc_samples:
                    conn.execute(
                        "INSERT INTO detection_sample (detection_id, kind, class_name, data, meta) "
                        "VALUES (%s,'QC',%s,%s,%s)", (det_id, cls, data, Jsonb(meta)))

    def clear_teaching(self, det_id: int) -> None:
        with self.db.tx() as conn:
            conn.execute("UPDATE detection SET model='{}'::jsonb, taught_at=NULL, taught_by=NULL WHERE id=%s",
                         (det_id,))
            conn.execute("DELETE FROM detection_sample WHERE detection_id=%s", (det_id,))

    def samples(self, det_id: int) -> list[dict]:
        return self.db.fetchall(
            "SELECT id, kind, class_name, data, meta FROM detection_sample WHERE detection_id=%s ORDER BY id", (det_id,))

    def delete(self, det_id: int) -> None:
        self.db.execute("DELETE FROM detection WHERE id=%s AND station_id=%s", (det_id, self.station_id))

    def usage(self, det_id: int) -> list[dict]:
        return self.db.fetchall(
            "SELECT s.name AS step_name, j.code AS job_code FROM step s JOIN job j ON j.id=s.job_id "
            "WHERE s.detection_id=%s", (det_id,))


class CalibrationRepo:
    def __init__(self, db: Database, station_id: int):
        self.db = db
        self.station_id = station_id

    def active(self) -> dict | None:
        return self.db.fetchone("SELECT * FROM calibration WHERE station_id=%s AND is_active", (self.station_id,))

    def save(self, data: dict, rms_px: float, user_id: int) -> int:
        with self.db.tx() as conn:
            conn.execute("UPDATE calibration SET is_active=FALSE WHERE station_id=%s AND is_active",
                         (self.station_id,))
            return conn.execute(
                "INSERT INTO calibration (station_id, created_by, rms_px, data, is_active) "
                "VALUES (%s,%s,%s,%s,TRUE) RETURNING id",
                (self.station_id, user_id, rms_px, Jsonb(data))).fetchone()["id"]


class RunRepo:
    def __init__(self, db: Database, station_id: int):
        self.db = db
        self.station_id = station_id

    def start(self, run_id: uuid.UUID, job_id: int, revision: int, operator_id: int, started_at: datetime) -> None:
        self.db.execute(
            "INSERT INTO inspection_run (id, station_id, job_id, job_revision, operator_id, started_at) "
            "VALUES (%s,%s,%s,%s,%s,%s)", (run_id, self.station_id, job_id, revision, operator_id, started_at))

    def update_identity(self, run_id: uuid.UUID, barcode: str | None, variant_code: str | None) -> None:
        self.db.execute("UPDATE inspection_run SET barcode=COALESCE(%s, barcode), "
                        "variant_code=COALESCE(%s, variant_code) WHERE id=%s", (barcode, variant_code, run_id))

    def finish(self, run_id: uuid.UUID, result: str, finished_at: datetime, cycle_ms: int, ng: int, forced: int,
               remarks: str | None) -> None:
        self.db.execute(
            "UPDATE inspection_run SET result=%s, finished_at=%s, cycle_time_ms=%s, ng_count=%s, forced_count=%s, "
            "remarks=%s WHERE id=%s", (result, finished_at, cycle_ms, ng, forced, remarks, run_id))

    def add_step_result(self, run_id: uuid.UUID, r: dict) -> None:
        self.db.execute(
            "INSERT INTO inspection_step_result (run_id, step_id, step_name, step_path, step_type, detection_name, "
            "started_at, finished_at, duration_ms, result, qc_class, score, value, evidence_path, actor_id) "
            "VALUES (%(run_id)s,%(step_id)s,%(step_name)s,%(step_path)s,%(step_type)s,%(detection_name)s,"
            "%(started_at)s,%(finished_at)s,%(duration_ms)s,%(result)s,%(qc_class)s,%(score)s,%(value)s,"
            "%(evidence_path)s,%(actor_id)s)", {**r, "run_id": run_id})

    def last_pass_for_barcode(self, barcode: str) -> dict | None:
        return self.db.fetchone(
            "SELECT id, started_at, result FROM inspection_run WHERE barcode=%s AND result='PASS' "
            "ORDER BY started_at DESC LIMIT 1", (barcode,))

    def close_dangling(self) -> int:
        """Runs left RUNNING by a crash/power cut are closed as ABORTED at startup."""
        return self.db.execute(
            "UPDATE inspection_run SET result='ABORTED', remarks='Closed at startup (application stopped mid-run)', "
            "finished_at=now() WHERE station_id=%s AND result='RUNNING'", (self.station_id,))

    # reporting ----------------------------------------------------------------
    def search(self, date_from: datetime, date_to: datetime, barcode: str = "", result: str = "",
               job_id: int | None = None, limit: int = 2000) -> list[dict]:
        q = ("SELECT r.*, j.code AS job_code, j.name AS job_name, u.username AS operator "
             "FROM inspection_run r JOIN job j ON j.id=r.job_id LEFT JOIN app_user u ON u.id=r.operator_id "
             "WHERE r.station_id=%s AND r.started_at >= %s AND r.started_at < %s")
        params: list[Any] = [self.station_id, date_from, date_to]
        if barcode:
            q += " AND r.barcode ILIKE %s"
            params.append(f"%{barcode}%")
        if result:
            q += " AND r.result = %s"
            params.append(result)
        if job_id:
            q += " AND r.job_id = %s"
            params.append(job_id)
        q += " ORDER BY r.started_at DESC LIMIT %s"
        params.append(limit)
        return self.db.fetchall(q, params)

    def step_results(self, run_id) -> list[dict]:
        return self.db.fetchall(
            "SELECT * FROM inspection_step_result WHERE run_id=%s ORDER BY started_at NULLS LAST, id", (run_id,))

    def step_results_for_runs(self, run_ids: list) -> list[dict]:
        if not run_ids:
            return []
        return self.db.fetchall(
            "SELECT * FROM inspection_step_result WHERE run_id = ANY(%s) ORDER BY run_id, id", (run_ids,))

    def kpis(self, since: datetime) -> dict:
        return self.db.fetchone(
            "SELECT count(*) FILTER (WHERE result IN ('PASS','FAIL')) AS total, "
            "count(*) FILTER (WHERE result='PASS') AS pass, count(*) FILTER (WHERE result='FAIL') AS fail, "
            "count(*) FILTER (WHERE result='PASS' AND ng_count=0 AND forced_count=0) AS first_pass, "
            "count(*) FILTER (WHERE result='ABORTED') AS aborted, "
            "avg(cycle_time_ms) FILTER (WHERE result='PASS') AS avg_cycle_ms "
            "FROM inspection_run WHERE station_id=%s AND started_at >= %s", (self.station_id, since))

    def hourly(self, since: datetime) -> list[dict]:
        return self.db.fetchall(
            "SELECT date_trunc('hour', started_at) AS hour, count(*) FILTER (WHERE result='PASS') AS pass, "
            "count(*) FILTER (WHERE result='FAIL') AS fail FROM inspection_run "
            "WHERE station_id=%s AND started_at >= %s GROUP BY 1 ORDER BY 1", (self.station_id, since))

    def ng_pareto(self, since: datetime, limit: int = 10) -> list[dict]:
        return self.db.fetchall(
            "SELECT sr.step_name, count(*) AS n FROM inspection_step_result sr "
            "JOIN inspection_run r ON r.id = sr.run_id WHERE r.station_id=%s AND r.started_at >= %s "
            "AND sr.result IN ('NG','FORCED') GROUP BY sr.step_name ORDER BY n DESC LIMIT %s",
            (self.station_id, since, limit))

    def step_durations(self, since: datetime, limit: int = 15) -> list[dict]:
        return self.db.fetchall(
            "SELECT sr.step_name, avg(sr.duration_ms) AS avg_ms, count(*) AS n FROM inspection_step_result sr "
            "JOIN inspection_run r ON r.id = sr.run_id WHERE r.station_id=%s AND r.started_at >= %s "
            "AND sr.duration_ms IS NOT NULL AND sr.result IN ('OK','NG') "
            "GROUP BY sr.step_name ORDER BY avg_ms DESC LIMIT %s", (self.station_id, since, limit))


class AuditRepo:
    def __init__(self, db: Database, station_code: str):
        self.db = db
        self.station_code = station_code

    def log(self, user_id: int | None, username: str | None, action: str, entity: str = "",
            entity_id: Any = "", details: dict | None = None) -> None:
        self.db.execute(
            "INSERT INTO audit_log (station_code, user_id, username, action, entity, entity_id, details) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (self.station_code, user_id, username, action, entity, str(entity_id) if entity_id != "" else None,
             Jsonb(json.loads(json.dumps(details or {}, default=str)))))

    def search(self, date_from: datetime, date_to: datetime, text: str = "", limit: int = 5000) -> list[dict]:
        q = "SELECT * FROM audit_log WHERE ts >= %s AND ts < %s"
        params: list[Any] = [date_from, date_to]
        if text:
            q += " AND (action ILIKE %s OR username ILIKE %s OR entity ILIKE %s OR details::text ILIKE %s)"
            like = f"%{text}%"
            params += [like, like, like, like]
        q += " ORDER BY ts DESC LIMIT %s"
        params.append(limit)
        return self.db.fetchall(q, params)


# ============================================================================ redesign additions
import base64 as _b64  # noqa: E402
import gzip as _gzip  # noqa: E402

PACKAGE_FORMAT = "rane-vista-job"
PACKAGE_VERSION = 1


class JobCatalogRepo:
    """Job card data, Arkite-style job properties and job packages (File > Open / Save)."""

    def __init__(self, db: Database, station_id: int):
        self.db = db
        self.station_id = station_id

    def summaries(self, include_archived: bool = False) -> list[dict]:
        q = ("SELECT j.id, j.code, j.name, j.status, j.revision, j.product_identifier, j.part_number, "
             "j.expected_cycle_s, j.updated_at, j.released_at, (j.image_png IS NOT NULL) AS has_image, "
             "(SELECT count(*) FROM job_variant v WHERE v.job_id = j.id AND v.is_active) AS variants, "
             "(SELECT count(*) FROM step s WHERE s.job_id = j.id) AS steps, "
             "(SELECT count(*) FROM detection d WHERE d.job_id = j.id) AS detections, "
             "(SELECT count(*) FROM detection d WHERE d.job_id = j.id AND d.taught_at IS NULL AND d.enabled) "
             "  AS untaught, "
             "(SELECT max(r.started_at) FROM inspection_run r WHERE r.job_id = j.id) AS last_run "
             "FROM job j WHERE j.station_id = %s")
        if not include_archived:
            q += " AND j.status <> 'ARCHIVED'"
        return self.db.fetchall(q + " ORDER BY j.code", (self.station_id,))

    def update_props(self, job_id: int, name: str, product_identifier: str, part_number: str, description: str,
                     expected_cycle_s: int, user_id: int) -> None:
        self.db.execute(
            "UPDATE job SET name=%s, product_identifier=%s, part_number=%s, description=%s, expected_cycle_s=%s, "
            "updated_at=now(), updated_by=%s, status = CASE WHEN status='RELEASED' THEN 'DRAFT' ELSE status END "
            "WHERE id=%s AND station_id=%s",
            (name, product_identifier or None, part_number or None, description or None, expected_cycle_s, user_id,
             job_id, self.station_id))

    def set_image(self, job_id: int, png: bytes | None, user_id: int) -> None:
        self.db.execute("UPDATE job SET image_png=%s, updated_at=now(), updated_by=%s WHERE id=%s AND station_id=%s",
                        (png, user_id, job_id, self.station_id))

    def image(self, job_id: int) -> bytes | None:
        row = self.db.fetchone("SELECT image_png FROM job WHERE id=%s AND station_id=%s", (job_id, self.station_id))
        return bytes(row["image_png"]) if row and row["image_png"] else None

    # ------------------------------------------------------------------ packages
    def export_package(self, job_id: int) -> bytes:
        job = self.db.fetchone("SELECT * FROM job WHERE id=%s AND station_id=%s", (job_id, self.station_id))
        if job is None:
            raise ValueError("Job not found")
        dets = self.db.fetchall("SELECT * FROM detection WHERE job_id=%s ORDER BY id", (job_id,))
        station_dets = {d["id"]: d["name"] for d in self.db.fetchall(
            "SELECT id, name FROM detection WHERE station_id=%s AND job_id IS NULL", (self.station_id,))}
        det_names = {d["id"]: d["name"] for d in dets}
        out_dets = []
        for d in dets:
            samples = self.db.fetchall("SELECT kind, class_name, data, meta FROM detection_sample WHERE detection_id=%s "
                                       "ORDER BY id", (d["id"],))
            out_dets.append({k: d[k] for k in ("name", "group_name", "det_type", "sensor", "enabled", "params", "model",
                                               "sort_order")} | {
                "samples": [{"kind": s["kind"], "class_name": s["class_name"], "meta": s["meta"],
                             "data": _b64.b64encode(bytes(s["data"])).decode()} for s in samples]})
        steps = []
        for s in self.db.fetchall("SELECT * FROM step WHERE job_id=%s ORDER BY id", (job_id,)):
            ref = None
            if s["detection_id"] in det_names:
                ref = {"scope": "job", "name": det_names[s["detection_id"]]}
            elif s["detection_id"] in station_dets:
                ref = {"scope": "station", "name": station_dets[s["detection_id"]]}
            steps.append({k: s[k] for k in ("id", "parent_id", "sort_order", "step_type", "name", "variant_codes",
                                            "enabled", "instruction", "params")} | {"detection_ref": ref})
        pkg = {
            "format": PACKAGE_FORMAT, "version": PACKAGE_VERSION, "exported_at": _now().isoformat(),
            "job": {k: job[k] for k in ("code", "name", "description", "part_number", "product_identifier",
                                        "expected_cycle_s", "settings", "revision")}
            | {"image_png": _b64.b64encode(bytes(job["image_png"])).decode() if job["image_png"] else None},
            "variants": [{k: v[k] for k in ("code", "name", "part_number", "barcode_regex", "sort_order", "is_active")}
                         for v in self.db.fetchall("SELECT * FROM job_variant WHERE job_id=%s", (job_id,))],
            "detections": out_dets, "steps": steps,
        }
        return _gzip.compress(json.dumps(pkg, default=str).encode("utf-8"))

    def import_package(self, blob: bytes, user_id: int, new_code: str | None = None) -> tuple[int, list[str]]:
        try:
            pkg = json.loads(_gzip.decompress(blob).decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("Not a RANE VISTA job package") from exc
        if pkg.get("format") != PACKAGE_FORMAT or int(pkg.get("version", 0)) > PACKAGE_VERSION:
            raise ValueError("Unsupported job package format or version")
        warnings: list[str] = []
        j = pkg["job"]
        code = (new_code or j["code"])[:64]
        with self.db.tx() as conn:
            if conn.execute("SELECT 1 FROM job WHERE station_id=%s AND code=%s", (self.station_id, code)).fetchone():
                raise ValueError(f"A job with code {code} already exists on this station")
            img = _b64.b64decode(j["image_png"]) if j.get("image_png") else None
            job_id = conn.execute(
                "INSERT INTO job (station_id, code, name, description, part_number, product_identifier, "
                "expected_cycle_s, settings, image_png, created_by, updated_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (self.station_id, code, j["name"], j.get("description"), j.get("part_number"),
                 j.get("product_identifier"), j.get("expected_cycle_s") or 60, Jsonb(j.get("settings") or {}), img,
                 user_id, user_id)).fetchone()["id"]
            for v in pkg.get("variants", []):
                conn.execute("INSERT INTO job_variant (job_id, code, name, part_number, barcode_regex, sort_order, "
                             "is_active) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                             (job_id, v["code"], v["name"], v.get("part_number"), v.get("barcode_regex"),
                              v.get("sort_order", 0), v.get("is_active", True)))
            det_ids: dict[str, int] = {}
            for d in pkg.get("detections", []):
                did = conn.execute(
                    "INSERT INTO detection (station_id, job_id, name, group_name, det_type, sensor, enabled, params, "
                    "model, sort_order, taught_at, taught_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    "CASE WHEN %s THEN now() END, %s) RETURNING id",
                    (self.station_id, job_id, d["name"], d["group_name"], d["det_type"], d["sensor"], d["enabled"],
                     Jsonb(d["params"]), Jsonb(d["model"]), d.get("sort_order", 0), bool(d.get("model")),
                     user_id)).fetchone()["id"]
                det_ids[d["name"]] = did
                for s in d.get("samples", []):
                    conn.execute("INSERT INTO detection_sample (detection_id, kind, class_name, data, meta) "
                                 "VALUES (%s,%s,%s,%s,%s)", (did, s["kind"], s["class_name"],
                                                             _b64.b64decode(s["data"]), Jsonb(s.get("meta") or {})))
            station = {r["name"]: r["id"] for r in conn.execute(
                "SELECT id, name FROM detection WHERE station_id=%s AND job_id IS NULL", (self.station_id,)).fetchall()}
            id_map: dict[int, int] = {}
            pending = list(pkg.get("steps", []))
            while pending:
                progressed = False
                for s in list(pending):
                    if s["parent_id"] is not None and s["parent_id"] not in id_map:
                        continue
                    ref, det_id = s.get("detection_ref"), None
                    if ref:
                        det_id = (det_ids if ref["scope"] == "job" else station).get(ref["name"])
                        if det_id is None:
                            warnings.append(f"Step '{s['name']}': station detection '{ref['name']}' not found")
                    id_map[s["id"]] = conn.execute(
                        "INSERT INTO step (job_id, parent_id, sort_order, step_type, name, detection_id, variant_codes,"
                        " enabled, instruction, params) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (job_id, id_map.get(s["parent_id"]), s["sort_order"], s["step_type"], s["name"], det_id,
                         s.get("variant_codes") or [], s.get("enabled", True), s.get("instruction"),
                         Jsonb(s.get("params") or {}))).fetchone()["id"]
                    pending.remove(s)
                    progressed = True
                if not progressed:
                    warnings.append("Some steps could not be placed in the tree (broken parent links)")
                    break
        if pkg.get("detections"):
            warnings.append("Detection teaching depends on the fixture layout - verify or re-teach before release.")
        return job_id, warnings


PROCESS_CATALOGUE = [
    {"code": "JOB_SELECTION", "name": "Job selection", "trigger": "STATION_START",
     "description": "How the job for the next part is chosen.",
     "params": {"mode": "OPERATOR_SELECT", "start_on_scan": True, "remember_last_job": True},
     "flow": ["Wait for operator job choice or barcode scan", "Find released job (barcode pattern when automatic)",
              "Load job revision and its detections", "Hand over to the inspection cycle"]},
    {"code": "INSPECTION_CYCLE", "name": "Inspection cycle", "trigger": "JOB_LOADED",
     "description": "Runs the job steps for every part and decides PASS / FAIL.",
     "params": {"auto_restart": True, "result_display_ms": 3000, "overtime_warning": True},
     "flow": ["Start run (new run id, operator, revision)", "Execute job steps", "Show PASS / FAIL on screen and bench",
              "Record result, restart for the next part"]},
    {"code": "BARCODE_CHECK", "name": "Barcode duplicate check", "trigger": "BARCODE_SCANNED",
     "description": "Prevents re-inspecting a part that already passed.",
     "params": {"duplicate_policy": "BLOCK"},
     "flow": ["Read scanned barcode", "Look up last PASS of this barcode", "Block, warn or allow per policy"]},
    {"code": "EVIDENCE", "name": "Evidence capture", "trigger": "STEP_COMPLETED",
     "description": "Stores stamped images of checks for traceability.",
     "params": {"save_pass_evidence": True, "evidence_retention_days": 365},
     "flow": ["Capture frame at the decision moment", "Stamp station, time and barcode",
              "Save JPEG and link it to the step result", "Purge images older than the retention period"]},
    {"code": "RESET", "name": "Station reset", "trigger": "RESET_BUTTON",
     "description": "The station-wide RESET virtual button aborts the running inspection.",
     "params": {}, "flow": ["Detect press on RESET button", "Abort run (recorded as ABORTED)", "Restart cycle"]},
]


class ProcessRepo:
    def __init__(self, db: Database, station_id: int):
        self.db = db
        self.station_id = station_id

    def ensure(self) -> None:
        for i, p in enumerate(PROCESS_CATALOGUE):
            self.db.execute(
                "INSERT INTO station_process (station_id, code, name, description, start_trigger, params, sort_order) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (station_id, code) DO NOTHING",
                (self.station_id, p["code"], p["name"], p["description"], p["trigger"], Jsonb(p["params"]), i))

    def list(self) -> list[dict]:
        rows = self.db.fetchall("SELECT * FROM station_process WHERE station_id=%s ORDER BY sort_order",
                                (self.station_id,))
        cat = {p["code"]: p for p in PROCESS_CATALOGUE}
        for r in rows:
            c = cat.get(r["code"], {})
            r["params"] = {**c.get("params", {}), **(r["params"] or {})}
            r["flow"] = c.get("flow", [])
        return rows

    def save(self, code: str, enabled: bool, params: dict, user_id: int) -> None:
        self.db.execute("UPDATE station_process SET enabled=%s, params=%s, updated_at=now(), updated_by=%s "
                        "WHERE station_id=%s AND code=%s", (enabled, Jsonb(params), user_id, self.station_id, code))
