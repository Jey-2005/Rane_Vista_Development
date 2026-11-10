"""Application context / service layer.

Holds repositories, the logged-in session and shared runtime objects. Every state-changing
service method checks permissions here (the UI only hides what the user cannot do; the check
that matters is in this layer) and writes the audit trail.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from vista.calibration.calibration import Calibration
from vista.core.config import AppConfig
from vista.core.security import (PermissionDenied, Session, hash_password, password_policy_errors,
                                 verify_password)
from vista.db.database import Database
from vista.db.repositories import (AuditRepo, CalibrationRepo, DetectionRepo, JobCatalogRepo, JobRepo, ProcessRepo,
                                   RunRepo, SettingsRepo, StationRepo, UserRepo)
from vista.engine.recorder import ResultRecorder
from vista.vision.detectors import decode_png, encode_png, pack_arrays, unpack_arrays
from vista.vision.engine import DetectionEngine

log = logging.getLogger(__name__)

SETTINGS_DEFAULTS = {
    "auto_restart": True,
    "start_on_scan": True,
    "result_display_ms": 3000,
    "duplicate_policy": "BLOCK",           # BLOCK | WARN | ALLOW  (driven by station processes)
    "job_select_mode": "OPERATOR_SELECT",
    "remember_last_job": True,
    "overtime_warning": True,
    "reset_enabled": True,
    "last_job_id": None,
    "save_pass_evidence": True,
    "evidence_retention_days": 365,
    "idle_logout_min": 15,
    "require_independent_release": True,   # releaser must differ from the last editor
    "max_login_attempts": 5,
    "lockout_minutes": 15,
    "projector_screen": "",
    "projector_rotation": 0,
    "projector_flip_h": False,
    "projector_flip_v": False,
    "projector_show_all": False,
    "pjlink_host": "",
    "pjlink_port": 4352,
    "projector_serial_port": "",
    "projector_serial_commands": {},
    "scanner_mode": "KEYBOARD",            # KEYBOARD | SERIAL
    "scanner_port": "",
    "scanner_baud": 9600,
    "camera_options": {},
    "instruction_area_mm": [0, -120, 700, 90],
    "result_area_mm": [750, -120, 400, 90],
    "color_todo": "#F2B233",
    "color_ok": "#2FB670",
    "color_ng": "#E5484D",
    "color_idle": "#4C8DD6",
    "calib_margin": 0.12,
    "calib_marker_px": 22,
    "calib_settle_ms": 600,
}


class AuthError(Exception):
    pass


def safe_name(text: str, limit: int = 60) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-]+", "_", text or "")[:limit].strip("._") or "item"


class AppContext:
    def __init__(self, cfg: AppConfig, db: Database):
        self.cfg, self.db = cfg, db
        self.station = StationRepo(db).ensure(cfg.station_code, cfg.station_name)
        sid = self.station["id"]
        self.stations = StationRepo(db)
        self.users = UserRepo(db)
        self.jobs = JobRepo(db, sid)
        self.detections = DetectionRepo(db, sid)
        self.calibrations = CalibrationRepo(db, sid)
        self.runs = RunRepo(db, sid)
        self.audit_repo = AuditRepo(db, cfg.station_code)
        self.settings_repo = SettingsRepo(db, sid)
        self.settings = {**SETTINGS_DEFAULTS, **self.settings_repo.all()}
        self.catalog = JobCatalogRepo(db, sid)
        self.processes = ProcessRepo(db, sid)
        self.processes.ensure()
        self.apply_processes()
        self.session: Session | None = None
        self.engine = DetectionEngine()
        self.recorder = ResultRecorder(self.runs, cfg.data_dir / "spool")
        self.worker = None          # CameraWorker, attached by the main window
        self.camera = None
        self.calibration: Calibration | None = None
        row = self.calibrations.active()
        if row:
            try:
                self.calibration = Calibration.from_dict(row["data"])
            except Exception:
                log.exception("Stored calibration is invalid")
        closed = self.runs.close_dangling()
        if closed:
            log.warning("Closed %d run(s) left RUNNING by a previous session", closed)

    # ------------------------------------------------------------------ audit / auth
    def audit(self, action: str, entity: str = "", entity_id="", details: dict | None = None) -> None:
        s = self.session
        try:
            self.audit_repo.log(s.user_id if s else None, s.username if s else None, action, entity, entity_id,
                                details)
        except Exception:
            log.exception("Audit write failed for %s", action)

    def require(self, perm: str) -> Session:
        if self.session is None:
            raise PermissionDenied("Not logged in")
        self.session.require(perm)
        return self.session

    def needs_first_admin(self) -> bool:
        return self.users.count() == 0

    def create_first_admin(self, username: str, full_name: str, password: str) -> None:
        if not self.needs_first_admin():
            raise AuthError("An administrator already exists.")
        errs = password_policy_errors(password, username)
        if errs:
            raise AuthError("Password must " + ", ".join(errs) + ".")
        uid = self.users.create(username, full_name, None, "ADMIN", hash_password(password), True, None,
                                must_change=False)
        self.audit_repo.log(uid, username, "FIRST_ADMIN_CREATED", "user", uid, {})

    def check_credentials(self, login: str, password: str, perm: str | None = None) -> Session:
        """Validates credentials (lockout aware). Does not change the active session."""
        u = self.users.by_login(login.strip())
        generic = "Invalid user name or password."
        if u is None:
            self.audit_repo.log(None, login[:64], "LOGIN_FAILED", "user", "", {"reason": "unknown user"})
            raise AuthError(generic)
        if not u["is_active"]:
            raise AuthError("This account is disabled. Contact the administrator.")
        if u["locked_until"] and u["locked_until"] > datetime.now(timezone.utc):
            raise AuthError("Account locked after repeated failures. Try again later or ask an administrator.")
        if not verify_password(password, u["password_hash"]):
            self.users.register_failure(u["id"], int(self.settings["max_login_attempts"]),
                                        int(self.settings["lockout_minutes"]))
            self.audit_repo.log(u["id"], u["username"], "LOGIN_FAILED", "user", u["id"], {"reason": "password"})
            raise AuthError(generic)
        if not self.users.has_station_access(u["id"], self.station["id"]):
            self.audit_repo.log(u["id"], u["username"], "LOGIN_DENIED", "station", self.station["id"], {})
            raise AuthError(f"You are not authorised for station {self.cfg.station_code}.")
        sess = Session(u["id"], u["username"], u["full_name"], u["role_code"], self.users.permissions(u["role_code"]))
        if perm and not sess.can(perm):
            raise AuthError("This user is not authorised for this action.")
        self.users.register_success(u["id"])
        sess.must_change_password = u["must_change_password"]  # type: ignore[attr-defined]
        return sess

    def login(self, login: str, password: str) -> Session:
        sess = self.check_credentials(login, password)
        self.session = sess
        self.audit("LOGIN", "user", sess.user_id, {})
        return sess

    def logout(self) -> None:
        if self.session:
            self.audit("LOGOUT", "user", self.session.user_id, {})
        self.session = None

    def change_password(self, old: str, new: str) -> None:
        s = self.session
        u = self.users.by_id(s.user_id)
        if not verify_password(old, u["password_hash"]):
            raise AuthError("Current password is incorrect.")
        errs = password_policy_errors(new, s.username)
        if errs:
            raise AuthError("Password must " + ", ".join(errs) + ".")
        if verify_password(new, u["password_hash"]):
            raise AuthError("The new password must differ from the current one.")
        self.users.set_password(s.user_id, hash_password(new), must_change=False)
        self.audit("PASSWORD_CHANGED", "user", s.user_id, {})

    # ------------------------------------------------------------------ settings
    def save_settings(self, values: dict) -> None:
        values = {k: v for k, v in values.items() if k not in PROCESS_KEYS}
        s = self.require("MANAGE_SETTINGS") if any(k not in HARDWARE_KEYS for k in values) else \
            self.require("MANAGE_HARDWARE")
        for k, v in values.items():
            if self.settings.get(k) != v:
                self.settings_repo.set(k, v, s.user_id)
                self.audit("SETTING_CHANGED", "setting", k, {"old": self.settings.get(k), "new": v})
                self.settings[k] = v

    # ------------------------------------------------------------------ processes
    def apply_processes(self) -> None:
        """Station processes drive the runtime switches the executor reads from self.settings."""
        for p in self.processes.list():
            prm, on = p["params"], p["enabled"]
            if p["code"] == "JOB_SELECTION":
                self.settings["job_select_mode"] = prm.get("mode", "OPERATOR_SELECT") if on else "OPERATOR_SELECT"
                self.settings["start_on_scan"] = bool(prm.get("start_on_scan", True)) and on
                self.settings["remember_last_job"] = bool(prm.get("remember_last_job", True))
            elif p["code"] == "INSPECTION_CYCLE":
                self.settings["auto_restart"] = bool(prm.get("auto_restart", True)) and on
                self.settings["result_display_ms"] = int(prm.get("result_display_ms", 3000))
                self.settings["overtime_warning"] = bool(prm.get("overtime_warning", True)) and on
            elif p["code"] == "BARCODE_CHECK":
                self.settings["duplicate_policy"] = prm.get("duplicate_policy", "BLOCK") if on else "ALLOW"
            elif p["code"] == "EVIDENCE":
                self.settings["save_pass_evidence"] = bool(prm.get("save_pass_evidence", True)) and on
                self.settings["evidence_retention_days"] = int(prm.get("evidence_retention_days", 365))
            elif p["code"] == "RESET":
                self.settings["reset_enabled"] = on

    def save_process(self, code: str, enabled: bool, params: dict) -> None:
        s = self.require("MANAGE_PROCESSES")
        old = next((p for p in self.processes.list() if p["code"] == code), None)
        self.processes.save(code, enabled, params, s.user_id)
        self.audit("PROCESS_CHANGED", "process", code, {"enabled": enabled, "params": params,
                                                        "old": old and {"enabled": old["enabled"],
                                                                        "params": old["params"]}})
        self.apply_processes()

    def find_job_for_barcode(self, code: str) -> dict | None:
        """Released job whose variant barcode pattern matches (process JOB_SELECTION in automatic mode)."""
        import re as _re
        hits = []
        for j in self.jobs.released():
            for v in self.jobs.variants(j["id"]):
                rx = v.get("barcode_regex")
                if rx and v.get("is_active", True):
                    try:
                        if _re.fullmatch(rx, code):
                            hits.append(j)
                            break
                    except _re.error:
                        continue
        return hits[0] if len(hits) == 1 else None

    # ------------------------------------------------------------------ detections -> engine
    def engine_entries(self, job_id: int | None) -> list[tuple[dict, dict, list]]:
        entries = []
        for det in self.detections.list_for(job_id):
            arrays, samples = {}, []
            for smp in self.detections.samples(det["id"]):
                if smp["kind"] == "REFS":
                    arrays = unpack_arrays(smp["data"])
                elif smp["kind"] == "QC":
                    samples.append((smp["class_name"], smp["meta"].get("type", "CORRECT"), decode_png(smp["data"])))
            entries.append((det, arrays, samples))
        return entries

    def load_engine(self, job_id: int | None) -> list[str]:
        return self.engine.load(self.engine_entries(job_id))

    def store_teaching(self, det_id: int, model: dict, arrays: dict | None,
                       qc_samples: list | None = None) -> None:
        s = self.require("TEACH_DETECTIONS")
        det = self.detections.get(det_id)
        if det is None:
            raise ValueError("Detection not found")
        cal = self.calibration
        if cal is not None and model.get("zone_px"):
            if det["sensor"] == "VISION":
                if cal.H_vision2bench is not None:
                    pts = cv2.perspectiveTransform(np.array(model["zone_px"], np.float64).reshape(-1, 1, 2),
                                                   cal.H_vision2bench).reshape(-1, 2)
                    model["zone_mm"] = pts.tolist()
            else:
                h = model.get("top_height_mm") or 0.0
                h = float(h) if np.isfinite(h) else 0.0
                model["zone_mm"] = cal.pixel_poly_to_bench(model["zone_px"], h)
        blob = pack_arrays(**arrays) if arrays else None
        qc = None
        if qc_samples is not None:
            qc = [(cls, encode_png(img), {"type": t}) for cls, t, img in qc_samples]
        self.detections.save_model(det_id, model, s.user_id, blob, qc)
        if det.get("job_id"):
            self.jobs.mark_draft(det["job_id"], s.user_id)
        self.audit("DETECTION_TAUGHT", "detection", det_id, {"name": det["name"], "roi": model.get("roi"),
                                                              "algorithm": model.get("algorithm")})

    # ------------------------------------------------------------------ evidence
    def latest_frame(self):
        return self.worker.latest() if self.worker else None

    def save_evidence(self, run_id, barcode: str | None, name: str, source: str = "COLOR",
                      roi_det: int | None = None) -> str | None:
        f = self.latest_frame()
        if f is None:
            return None
        img = {"VISION": f.vision, "IR": f.ir}.get(source, f.color)
        if img is None:
            img = f.color
        if img is None:
            return None
        img = img.copy() if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        if roi_det is not None:
            det = self.engine.meta().get(roi_det)
            if det and det.get("model", {}).get("roi"):
                x, y, w, h = [int(v) for v in det["model"]["roi"]]
                cv2.rectangle(img, (x, y), (x + w, y + h), (51, 178, 242), 2)
        now = datetime.now()
        folder = self.cfg.evidence_dir / f"{now:%Y-%m-%d}" / safe_name(barcode or str(run_id))
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (f"{now:%H%M%S_%f}"[:-3] + f"_{safe_name(name)}.jpg")
        stamp = f"{self.cfg.station_code}  {now:%d-%m-%Y %H:%M:%S}  {barcode or ''}"
        cv2.putText(img, stamp, (8, img.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
                    cv2.LINE_AA)
        if not cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 90]):
            log.error("Could not write evidence %s", path)
            return None
        return str(path)

    def last_pass_for_barcode(self, code: str):
        try:
            return self.runs.last_pass_for_barcode(code)
        except Exception:
            log.exception("Duplicate check failed")
            return None

    def purge_old_evidence(self) -> int:
        days = int(self.settings.get("evidence_retention_days", 365))
        if days <= 0:
            return 0
        cutoff = datetime.now().timestamp() - days * 86400
        removed = 0
        for day_dir in Path(self.cfg.evidence_dir).glob("*"):
            if day_dir.is_dir() and day_dir.stat().st_mtime < cutoff:
                for f in day_dir.rglob("*.jpg"):
                    f.unlink(missing_ok=True)
                    removed += 1
                for sub in sorted(day_dir.rglob("*"), reverse=True):
                    if sub.is_dir():
                        sub.rmdir()
                day_dir.rmdir()
        return removed

    def shutdown(self) -> None:
        self.recorder.stop()


HARDWARE_KEYS = {"projector_screen", "projector_rotation", "projector_flip_h", "projector_flip_v", "pjlink_host",
                 "pjlink_port", "projector_serial_port", "projector_serial_commands", "scanner_mode", "scanner_port",
                 "scanner_baud", "camera_options", "calib_margin", "calib_marker_px", "calib_settle_ms",
                 "projector_show_all", "instruction_area_mm", "result_area_mm"}

PROCESS_KEYS = {"job_select_mode", "start_on_scan", "remember_last_job", "auto_restart", "result_display_ms",
                "overtime_warning", "duplicate_policy", "save_pass_evidence", "evidence_retention_days",
                "reset_enabled"}
