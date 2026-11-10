"""Pop-ups: command palette, export, help, about, shortcuts, message log and a generic popup frame."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QDialog, QFileDialog, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QTableWidget,
                               QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from vista import __version__
from vista.core.config import resource_dir
from vista.reporting.export import export_csv, export_traceability_xlsx
from vista.ui.icons import icon
from vista.ui.theme import C
from vista.ui.widgets.common import button, error, info, label


class Popup(QDialog):
    """Standard pop-up frame: icon + title header, body layout, footer buttons."""

    def __init__(self, parent, title: str, subtitle: str = "", ico: str = "info", width: int = 640):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.setStyleSheet(f"QDialog {{ background: {C['surface']}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        head = QFrame()
        head.setStyleSheet(f"QFrame {{ background: {C['ribbon']}; border-bottom: 1px solid {C['line']}; }}")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(18, 12, 18, 12)
        badge = QLabel()
        badge.setFixedSize(36, 36)
        badge.setAlignment(Qt.AlignCenter)
        badge.setPixmap(icon(ico, C["primary"], 20).pixmap(20, 20))
        badge.setStyleSheet(f"background: {C['primary_soft']}; border-radius: 8px; border: none;")
        hl.addWidget(badge)
        tl = QVBoxLayout()
        tl.setSpacing(0)
        t = QLabel(title)
        t.setObjectName("H2")
        t.setStyleSheet("border: none;")
        tl.addWidget(t)
        if subtitle:
            s = label(subtitle, "Muted")
            s.setStyleSheet("border: none;")
            tl.addWidget(s)
        hl.addLayout(tl, 1)
        root.addWidget(head)
        w = QWidget()
        self.body = QVBoxLayout(w)
        self.body.setContentsMargins(18, 14, 18, 10)
        self.body.setSpacing(10)
        root.addWidget(w, 1)
        self.footer = QHBoxLayout()
        self.footer.setContentsMargins(18, 8, 18, 14)
        self.footer.addStretch(1)
        root.addLayout(self.footer)

    def add_buttons(self, *btns) -> None:
        for b in btns:
            self.footer.addWidget(b)


class CommandPalette(QDialog):
    """VS Code-style quick open: pages, jobs, steps, detections and menu commands."""

    def __init__(self, win):
        super().__init__(win, Qt.Popup | Qt.FramelessWindowHint)
        self.win = win
        self.setFixedWidth(560)
        self.setStyleSheet(f"QDialog {{ background: white; border: 1px solid {C['line']}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Type a job, step, detection, page or command…")
        self.edit.textChanged.connect(self.refresh)
        self.edit.returnPressed.connect(self.activate)
        lay.addWidget(self.edit)
        self.list = QListWidget()
        self.list.setIconSize(QSize(18, 18))
        self.list.setMinimumHeight(360)
        self.list.itemActivated.connect(lambda _: self.activate())
        lay.addWidget(self.list)
        self.items = self._collect()
        self.refresh("")
        self.edit.setFocus()

    def _collect(self):
        w, ctx = self.win, self.win.ctx
        from vista.ui.main_window import RIBBON
        out = []
        for _, items in RIBBON:
            for key, text, ico, _p, sc in items:
                if key in w._allowed:
                    out.append(("page", key, f"Go to {text}", sc or "", ico))
        for j in ctx.jobs.list():
            out.append(("job", j["id"], f"{j['code']}  -  {j['name']}", f"job · {j['status'].lower()}", "job"))
        if w.edit_job_id:
            for s in ctx.jobs.steps(w.edit_job_id):
                out.append(("step", s["id"], s["name"], "step", "steps"))
        for d in ctx.detections.list_for(w.edit_job_id):
            out.append(("detection", d["id"], d["name"], f"detection · {d['det_type'].lower()}", "detection"))
        for a in w._actions:
            if a.isEnabled():
                out.append(("action", a, a.text().replace("…", ""), a.shortcut().toString(), "chevron_right"))
        return out

    def refresh(self, text: str) -> None:
        self.list.clear()
        t = text.lower().strip()
        for kind, ref, title, hint, ico in self.items:
            if t and t not in title.lower() and t not in hint.lower():
                continue
            it = QListWidgetItem(icon(ico, C["ink"], 18), f"{title}      {hint}")
            it.setToolTip(title)
            it.setData(Qt.UserRole, (kind, ref))
            self.list.addItem(it)
            if self.list.count() >= 60:
                break
        if self.list.count():
            self.list.setCurrentRow(0)

    def activate(self) -> None:
        it = self.list.currentItem()
        if it is None:
            return
        kind, ref = it.data(Qt.UserRole)
        self.accept()
        w = self.win
        if kind == "page":
            w.show_page(ref)
        elif kind == "job":
            w.set_edit_job(ref)
            w.show_page("jobs" if "jobs" in w._allowed else "steps")
        elif kind == "step":
            w.show_page("steps")
            w.pages["steps"].select_step(ref)
        elif kind == "detection":
            w.show_page("detections")
            w.pages["detections"].select_detection(ref)
        elif kind == "action":
            ref.trigger()


class ExportDialog(Popup):
    def __init__(self, win):
        super().__init__(win, "Export inspection data", "Traceability workbook with one column per check, "
                         "linked evidence images", "export", 520)
        self.ctx = win.ctx
        f = QFormLayout()
        self.d_from, self.d_to = QDateEdit(QDate.currentDate().addDays(-1)), QDateEdit(QDate.currentDate())
        for d in (self.d_from, self.d_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd-MM-yyyy")
        self.job = QComboBox()
        self.job.addItem("All jobs", None)
        for j in self.ctx.jobs.list(include_archived=True):
            self.job.addItem(j["code"], j["id"])
        self.result = QComboBox()
        self.result.addItems(["All results", "PASS", "FAIL", "ABORTED"])
        self.barcode = QLineEdit()
        self.barcode.setPlaceholderText("optional - part of the barcode")
        self.fmt = QComboBox()
        self.fmt.addItems(["Excel traceability workbook (.xlsx)", "CSV summary (.csv)"])
        for lab_, w in (("From", self.d_from), ("To", self.d_to), ("Job", self.job), ("Result", self.result),
                        ("Barcode", self.barcode), ("Format", self.fmt)):
            f.addRow(lab_, w)
        self.body.addLayout(f)
        self.add_buttons(button("Cancel", None, self.reject), button("Export", "primary", self.run, ico="export"))

    def run(self) -> None:
        a = datetime.combine(self.d_from.date().toPython(), datetime.min.time()).astimezone()
        b = datetime.combine(self.d_to.date().toPython(), datetime.min.time()).astimezone() + timedelta(days=1)
        res = "" if self.result.currentIndex() == 0 else self.result.currentText()
        runs = self.ctx.runs.search(a, b, self.barcode.text().strip(), res, self.job.currentData(), limit=20000)
        if not runs:
            return error(self, "No inspections match the filter.")
        xlsx = self.fmt.currentIndex() == 0
        default = self.ctx.cfg.export_dir / (f"traceability_{self.ctx.cfg.station_code}_{datetime.now():%Y%m%d_%H%M}"
                                             + (".xlsx" if xlsx else ".csv"))
        path, _ = QFileDialog.getSaveFileName(self, "Export", str(default), "Excel (*.xlsx)" if xlsx else "CSV (*.csv)")
        if not path:
            return
        if xlsx:
            export_traceability_xlsx(Path(path), runs, self.ctx.runs.step_results_for_runs([r["id"] for r in runs]),
                                     self.ctx.cfg.station_code)
        else:
            export_csv(Path(path), runs, ["started_at", "finished_at", "barcode", "job_code", "job_revision",
                                          "variant_code", "operator", "result", "cycle_time_ms", "ng_count",
                                          "forced_count", "remarks"])
        self.ctx.audit("REPORT_EXPORTED", "report", "", {"rows": len(runs), "format": "xlsx" if xlsx else "csv"})
        info(self, f"Exported {len(runs)} inspections to\n{path}")
        self.accept()


GUIDE = {
    "Quick start": """
<h3>Commissioning a station</h3>
<ol>
<li><b>Connectivity</b> - check that the 3D sensor, projector and scanner show a green tick.</li>
<li><b>Calibration</b> - choose the projector display and run the automatic calibration (clear bench).</li>
<li><b>Jobs</b> - create the job, add variants with barcode patterns (e.g. <code>LH\\d{6}</code>).</li>
<li><b>Detections</b> - create detections, draw the working zone, capture <i>without</i> / <i>with</i>
   snapshots or class samples, press <b>Teach</b>, test the live state.</li>
<li><b>Steps</b> - build the step tree and link each step to its detection.</li>
<li><b>Processes</b> - choose how jobs are selected, duplicate barcode policy and evidence capture.</li>
<li><b>Jobs → Release</b> - a second person releases the revision for production.</li>
</ol>""",
    "Operator": """
<h3>Running inspections</h3>
<ul>
<li>Open <b>Operate</b>, select the job (or scan - automatic job selection can pick it).</li>
<li>Follow the amber highlight on the bench; it turns green when the step is done.</li>
<li>A red highlight means a bad quality result: correct the part, the check repeats automatically.</li>
<li><b>F8 Supervisor override</b> needs a supervisor password and is recorded.</li>
<li>The station RESET button on the bench aborts the running inspection.</li>
</ul>""",
    "Shortcuts": """
<h3>Most used shortcuts</h3>
<table cellpadding="4">
<tr><td><b>Ctrl+P</b></td><td>Search jobs, steps, detections, commands</td></tr>
<tr><td><b>Ctrl+1 … Ctrl+9</b></td><td>Switch page</td></tr>
<tr><td><b>F5 / Shift+F5</b></td><td>Start / abort inspection</td></tr>
<tr><td><b>Ctrl+S / Ctrl+O</b></td><td>Save / open job package</td></tr>
<tr><td><b>Ctrl+E</b></td><td>Export inspection data</td></tr>
<tr><td><b>Mouse wheel / right drag</b></td><td>Zoom / pan camera images and the bench view</td></tr>
</table>""",
}


class HelpDialog(Popup):
    def __init__(self, win):
        super().__init__(win, "RANE VISTA help", "Commissioning, operation and shortcuts", "help", 720)
        tabs = QTabWidget()
        for name, html in GUIDE.items():
            tb = QTextBrowser()
            tb.setHtml(f"<div style='font-size:10pt'>{html}</div>")
            tb.setStyleSheet("border: none;")
            tabs.addTab(tb, name)
        tabs.setMinimumHeight(360)
        self.body.addWidget(tabs)
        readme = resource_dir() / "README.md"
        b = button("Open full manual", None, lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(readme))),
                   ico="instruction")
        b.setEnabled(readme.exists())
        self.add_buttons(b, button("Close", "primary", self.accept))


class AboutDialog(Popup):
    def __init__(self, win):
        super().__init__(win, "About RANE VISTA", "Visual Inspection & Smart Task Assistance", "info", 560)
        ctx = win.ctx
        cam = ctx.camera.info() if ctx.camera else {}
        rows = [("Version", __version__), ("Station", f"{ctx.cfg.station_code} - {ctx.station['name']}"),
                ("Database", ctx.cfg.db.safe_repr()), ("Camera", cam.get("name", "-")),
                ("Calibration", f"{ctx.calibration.rms_px:.2f} px reprojection error" if ctx.calibration
                 else "not calibrated"), ("Data folder", str(ctx.cfg.data_dir))]
        f = QFormLayout()
        for k, v in rows:
            f.addRow(label(k, "Muted"), label(v, wrap=True))
        self.body.addLayout(f)
        self.body.addWidget(label("Developed in-house by Rane (Madras) Limited, Steering Linkage Division. Built on "
                                  "Qt for Python (LGPL), OpenCV (Apache 2.0), Intel RealSense SDK (Apache 2.0), "
                                  "psycopg (LGPL) and PostgreSQL.", "Muted", wrap=True))
        self.add_buttons(button("Close", "primary", self.accept))


class ShortcutsDialog(Popup):
    def __init__(self, win, actions):
        super().__init__(win, "Keyboard shortcuts", "", "key", 520)
        t = QTableWidget(0, 2)
        t.setHorizontalHeaderLabels(["Command", "Shortcut"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.horizontalHeader().setStretchLastSection(True)
        for a in actions:
            if a.shortcut().isEmpty():
                continue
            r = t.rowCount()
            t.insertRow(r)
            t.setItem(r, 0, QTableWidgetItem(a.text().replace("…", "")))
            t.setItem(r, 1, QTableWidgetItem(a.shortcut().toString()))
        t.resizeColumnsToContents()
        t.setMinimumHeight(380)
        self.body.addWidget(t)
        self.add_buttons(button("Close", "primary", self.accept))


class MessageLogDialog(Popup):
    def __init__(self, win):
        super().__init__(win, "Messages", "Errors, warnings and events of this session", "log", 760)
        self.win = win
        t = QTableWidget(0, 4)
        t.setHorizontalHeaderLabels(["Time", "Level", "Source", "Message"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.horizontalHeader().setStretchLastSection(True)
        col = {"error": C["ng"], "warn": C["warn"], "ok": C["ok"]}
        for m in win.messages:
            r = t.rowCount()
            t.insertRow(r)
            t.setItem(r, 0, QTableWidgetItem(m["ts"].strftime("%H:%M:%S")))
            it = QTableWidgetItem(m["level"])
            it.setForeground(QColor(col.get(m["level"], C["muted"])))
            t.setItem(r, 1, it)
            t.setItem(r, 2, QTableWidgetItem(m["source"]))
            t.setItem(r, 3, QTableWidgetItem(m["text"]))
        t.resizeColumnsToContents()
        t.setMinimumHeight(380)
        self.body.addWidget(t)
        self.add_buttons(button("Clear", None, self.clear), button("Close", "primary", self.accept))

    def clear(self) -> None:
        self.win.messages.clear()
        self.win.status.set_messages(0, 0)
        self.accept()
