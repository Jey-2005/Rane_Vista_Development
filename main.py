"""RANE VISTA - Visual Inspection & Smart Task Assistance.

Usage:
  RANE_VISTA.exe                 start the station application
  RANE_VISTA.exe --check         diagnose the installation (Python packages, .env, database, camera, displays)
  RANE_VISTA.exe --migrate       apply database migrations and exit (run with the schema owner account)
  RANE_VISTA.exe --seed-demo     (simulator only) create a calibrated, taught demo job after sign-in
"""
from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox


def _fatal(msg: str) -> int:
    _app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841 - must exist for the message box
    QMessageBox.critical(None, "RANE VISTA", msg)
    return 1


def _schema_current(db) -> bool:
    from vista.core.config import resource_dir
    latest = max(int(p.name.split("_", 1)[0]) for p in (resource_dir() / "sql" / "migrations").glob("*.sql"))
    try:
        row = db.fetchone("SELECT max(version) AS v FROM schema_version")
        return bool(row and row["v"] is not None and row["v"] >= latest)
    except Exception:
        return False


def _install_excepthook() -> None:
    """Uncaught errors (e.g. inside a button handler) are logged and shown - a windowed .exe has no console."""
    import traceback
    log = logging.getLogger("vista.crash")
    state = {"open": False}

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("Unhandled error:\n%s", text)
        if state["open"] or QApplication.instance() is None:
            return
        state["open"] = True
        try:
            box = QMessageBox(QMessageBox.Critical, "RANE VISTA - unexpected error",
                              f"{exc_type.__name__}: {exc}\n\nThe details were written to the log file "
                              "(DATA_DIR\\logs\\vista.log). Please send it to the developer.")
            box.setDetailedText(text)
            box.exec()
        finally:
            state["open"] = False

    sys.excepthook = hook


def main() -> int:
    from vista import __version__
    from vista.core.config import ConfigError, load_config
    from vista.core.logging_setup import setup_logging

    ap = argparse.ArgumentParser(prog="RANE_VISTA")
    ap.add_argument("--migrate", action="store_true")
    ap.add_argument("--seed-demo", action="store_true")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--check", action="store_true", help="diagnose the installation and write a report")
    args = ap.parse_args()
    if args.version:
        print(__version__)
        return 0
    if args.check:
        from vista.diagnostics import run_check
        return run_check()

    app = QApplication(sys.argv)
    app.setApplicationName("RANE VISTA")
    app.setApplicationVersion(__version__)
    try:
        cfg = load_config()
    except ConfigError as exc:
        return _fatal(f"Configuration error:\n\n{exc}\n\nCopy .env.example to .env and fill it in.")
    setup_logging(cfg.log_dir, cfg.log_level)
    _install_excepthook()
    log = logging.getLogger("vista")
    log.info("RANE VISTA %s starting - station %s, camera %s", __version__, cfg.station_code, cfg.camera_backend)

    lock = QLockFile(str(cfg.data_dir / "vista.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        return _fatal("RANE VISTA is already running on this PC.")

    from PySide6.QtGui import QIcon
    from vista.core.config import resource_dir
    from vista.ui.theme import apply_theme
    apply_theme(app)
    app.setWindowIcon(QIcon(str(resource_dir() / "assets" / "rane_vista.png")))

    from vista.db.database import Database, DatabaseError
    db = Database(cfg.db)
    try:
        db.open()
    except DatabaseError as exc:
        return _fatal(str(exc))
    try:
        applied = db.migrate()
        if applied:
            log.info("Migrations applied: %s", applied)
    except Exception as exc:
        if args.migrate:
            return _fatal(f"Migration failed: {exc}")
        log.warning("Migration step skipped (%s) - assuming the schema is managed by the DBA", exc)
        if not _schema_current(db):
            return _fatal("The database schema is out of date and this account may not change it.\n\n"
                          f"{exc}\n\nRun RANE_VISTA.exe --migrate once with the schema owner account "
                          "(e.g. postgres), then start again.")
    if args.migrate:
        QMessageBox.information(None, "RANE VISTA", "Database schema is up to date.")
        return 0

    from vista.app_context import AppContext
    from vista.ui.dialogs import ChangePasswordDialog, FirstAdminDialog, LoginDialog
    try:
        ctx = AppContext(cfg, db)
    except Exception as exc:
        log.exception("Startup failed")
        return _fatal(f"Startup failed: {exc}\n\nRun RANE_VISTA.exe --check for a full installation report.")

    if ctx.needs_first_admin() and FirstAdminDialog(ctx).exec() != QDialog.Accepted:
        return 0
    while True:
        if LoginDialog(ctx).exec() != QDialog.Accepted:
            ctx.shutdown()
            return 0
        if getattr(ctx.session, "must_change_password", False):
            if ChangePasswordDialog(ctx, forced=True).exec() != QDialog.Accepted:
                ctx.logout()
                continue
        break
    ctx.audit("APP_STARTED", "station", cfg.station_code, {"version": __version__})

    from vista.hardware.camera_base import CameraError
    if cfg.camera_backend == "sim":
        from vista.hardware.simulated_camera import SimulatedCamera
        camera = SimulatedCamera(cfg.depth_width, cfg.depth_height, cfg.fps)
        camera.start()
        if args.seed_demo:
            from vista.core.security import PermissionDenied
            from vista.demo import seed_demo
            try:
                ctx.require("TEACH_DETECTIONS")
                ctx.require("EDIT_JOBS")
                seed_demo(ctx, camera)
            except (PermissionDenied, CameraError) as exc:
                QMessageBox.warning(None, "RANE VISTA", f"Demo not created: {exc}")
    else:
        from vista.hardware.realsense_camera import RealSenseCamera
        camera = RealSenseCamera(cfg.realsense_serial, cfg.depth_width, cfg.depth_height, cfg.fps)
    vision = None
    if cfg.vision_camera_index >= 0:
        from vista.hardware.uvc_camera import UvcCamera
        vision = UvcCamera(cfg.vision_camera_index)

    from vista.ui.main_window import MainWindow
    win = MainWindow(ctx, camera, vision)
    win.show()
    win.maximize()
    rc = app.exec()
    lock.unlock()
    return rc


if __name__ == "__main__":
    sys.exit(main())
