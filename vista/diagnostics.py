"""Installation check: `RANE_VISTA.exe --check` (or check_install.bat).

Verifies Python and packages, .env, data folder, database, schema, RealSense camera, displays and serial
ports, then writes a report (no secrets) and shows a summary. Send the report when asking for support.
"""
from __future__ import annotations

import importlib
import platform
import sys
import traceback
from datetime import datetime
from pathlib import Path

OK, WARN, FAIL = "OK  ", "WARN", "FAIL"


class Report:
    def __init__(self):
        self.lines: list[tuple[str, str, str]] = []

    def add(self, status: str, item: str, detail: str = "") -> None:
        self.lines.append((status, item, detail))

    @property
    def worst(self) -> str:
        s = [x[0] for x in self.lines]
        return FAIL if FAIL in s else (WARN if WARN in s else OK)

    def text(self) -> str:
        out = [f"RANE VISTA installation check - {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
        out += [f"[{st}] {item}" + (f"  -  {d}" if d else "") for st, item, d in self.lines]
        out += ["", f"Overall: {self.worst.strip()}"]
        return "\n".join(out)


def _packages(r: Report) -> None:
    v = sys.version_info
    r.add(OK if (3, 10) <= v[:2] <= (3, 13) else WARN, "Python",
          f"{platform.python_version()} {platform.architecture()[0]}" + ("" if (3, 10) <= v[:2] <= (3, 13) else
                                                                        " - use Python 3.11 to 3.13 (64-bit)"))
    for mod, name, required in (("PySide6", "PySide6", True), ("numpy", "numpy", True), ("cv2", "OpenCV", True),
                                ("psycopg", "psycopg", True), ("psycopg_pool", "psycopg-pool", True),
                                ("dotenv", "python-dotenv", True), ("openpyxl", "openpyxl", True),
                                ("serial", "pyserial", True), ("pyrealsense2", "pyrealsense2", False)):
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", "") or getattr(m, "version", "")
            r.add(OK, f"Package {name}", str(ver))
        except Exception as exc:
            r.add(FAIL if required else WARN, f"Package {name}",
                  f"not importable ({exc})" + ("" if required else " - needed only for CAMERA_BACKEND=realsense"))
    try:
        from psycopg.pq import version as pqv
        r.add(OK, "libpq", str(pqv()))
    except Exception:
        pass


def _config(r: Report):
    from vista.core.config import ConfigError, app_base_dir, load_config
    env = app_base_dir() / ".env"
    r.add(OK if env.exists() else FAIL, ".env file", str(env) if env.exists() else
          f"missing - copy .env.example to {env} and fill it in")
    try:
        cfg = load_config()
    except ConfigError as exc:
        r.add(FAIL, "Configuration", str(exc))
        return None
    r.add(OK, "Configuration", f"station {cfg.station_code}, camera backend {cfg.camera_backend}, "
                               f"database {cfg.db.safe_repr()}")
    if cfg.db.user == "postgres":
        r.add(WARN, "Database account", "using the postgres superuser - create vista_app for production "
                                        "(sql/admin/least_privilege_role.sql)")
    try:
        probe = cfg.data_dir / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        r.add(OK, "Data folder writable", str(cfg.data_dir))
    except OSError as exc:
        r.add(FAIL, "Data folder writable", f"{cfg.data_dir}: {exc}")
    return cfg


def _database(r: Report, cfg) -> None:
    from vista.db.database import Database
    db = Database(cfg.db)
    try:
        db.open()
    except Exception as exc:
        cause = exc.__cause__ or exc
        r.add(FAIL, "Database connection", f"{exc} ({type(cause).__name__}: {str(cause)[:200]})")
        return
    try:
        v = db.fetchone("SELECT version() AS v, current_user AS u, "
                        "has_database_privilege(current_database(), 'CREATE') AS can_create")
        r.add(OK, "Database connection", f"{v['v'].split(',')[0]} as {v['u']}")
        ex = db.fetchone("SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name=%s) AS e",
                         (cfg.db.schema,))["e"]
        if not ex:
            r.add(WARN if v["can_create"] else FAIL, f"Schema {cfg.db.schema}",
                  "not created yet - the first start creates it" if v["can_create"] else
                  "missing and this account cannot create it - run --migrate as the owner")
            return
        from vista.core.config import resource_dir
        latest = max(int(p.name.split("_", 1)[0]) for p in (resource_dir() / "sql" / "migrations").glob("*.sql"))
        try:
            cur = db.fetchone("SELECT max(version) AS v FROM schema_version")["v"] or 0
        except Exception:
            cur = 0
        r.add(OK if cur >= latest else WARN, "Schema version",
              f"{cur} of {latest}" + ("" if cur >= latest else " - pending migrations are applied at start-up "
                                                                "(or run --migrate as the owner)"))
        try:
            n = db.fetchone("SELECT count(*) AS n FROM app_user")["n"]
            r.add(OK if n else WARN, "Users", f"{n} user(s)" if n else "none - the first start asks for an admin")
        except Exception:
            pass
    finally:
        db.close()


def _camera(r: Report, cfg) -> None:
    if cfg is not None and cfg.camera_backend == "sim":
        r.add(OK, "Camera", "simulator backend (CAMERA_BACKEND=sim)")
        return
    try:
        from vista.hardware.realsense_camera import list_devices
        devs = list_devices()
    except Exception as exc:
        r.add(FAIL, "RealSense camera", str(exc))
        return
    if not devs:
        r.add(FAIL, "RealSense camera", "no device found - check the USB 3 cable; a D457 needs its interface "
                                        "switch set to USB")
    for d in devs:
        usb2 = str(d.get("usb", "")).startswith("2")
        r.add(WARN if usb2 else OK, "RealSense camera",
              f"{d['name']} serial {d['serial']} firmware {d['firmware']} USB {d['usb']}"
              + (" - connected as USB 2, use a USB 3 port/cable" if usb2 else ""))
    if cfg is not None and cfg.realsense_serial and cfg.realsense_serial not in [d["serial"] for d in devs]:
        r.add(FAIL, "REALSENSE_SERIAL", f"{cfg.realsense_serial} is not connected")


def _displays(r: Report) -> None:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    screens = app.screens()
    r.add(OK if len(screens) >= 2 else WARN, "Displays",
          f"{len(screens)} found" + ("" if len(screens) >= 2 else " - connect the projector as an extended display"))
    for s in screens:
        g = s.geometry()
        scale = s.devicePixelRatio()
        r.add(OK if scale == 1.0 else WARN, f"Display {s.name()}",
              f"{g.width()}x{g.height()} at {g.x()},{g.y()}, scaling {scale * 100:.0f}%"
              + ("" if scale == 1.0 else " - the projector display must use 100% scaling"))


def _serial(r: Report) -> None:
    try:
        from serial.tools import list_ports
        ports = [f"{p.device} ({p.description})" for p in list_ports.comports()]
        r.add(OK, "Serial ports", ", ".join(ports) or "none (fine for USB keyboard-wedge scanners)")
    except Exception as exc:
        r.add(WARN, "Serial ports", str(exc))


def run_check() -> int:
    r = Report()
    cfg = None
    for step in (_packages, _config):
        try:
            res = step(r)
            cfg = res if step is _config else cfg
        except Exception:
            r.add(FAIL, step.__name__.strip("_"), traceback.format_exc(limit=2).replace("\n", " | "))
    if cfg is not None:
        try:
            _database(r, cfg)
        except Exception:
            r.add(FAIL, "database", traceback.format_exc(limit=2).replace("\n", " | "))
    for step in (lambda x: _camera(x, cfg), _displays, _serial):
        try:
            step(r)
        except Exception:
            r.add(FAIL, "check", traceback.format_exc(limit=2).replace("\n", " | "))
    text = r.text()
    from vista.core.config import app_base_dir
    target = (cfg.log_dir if cfg is not None else app_base_dir()) / "check_report.txt"
    try:
        target.write_text(text, encoding="utf-8")
    except OSError:
        target = Path.home() / "RANE_VISTA_check_report.txt"
        target.write_text(text, encoding="utf-8")
    if sys.stdout is not None:
        print(text)
        print(f"\nReport written to {target}")
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        box = QMessageBox(QMessageBox.Information if r.worst != FAIL else QMessageBox.Critical,
                          "RANE VISTA - installation check",
                          f"Overall result: {r.worst.strip()}\n\nReport saved to:\n{target}")
        box.setDetailedText(text)
        if sys.stdout is None or not sys.stdout.isatty():
            box.exec()
        _ = app
    except Exception:
        pass
    return 0 if r.worst != FAIL else 1
