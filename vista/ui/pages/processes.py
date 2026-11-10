"""Processes page (Arkite layout): process list + process flow | Properties."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QLabel, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from vista.core.security import PermissionDenied, Perm
from vista.ui.icons import icon
from vista.ui.theme import C, font
from vista.ui.widgets.common import Page, ParamForm, PropertiesPanel, button, chip, error, hrow, label

TRIGGERS = {"STATION_START": "Station started", "JOB_LOADED": "Job loaded", "BARCODE_SCANNED": "Barcode scanned",
            "STEP_COMPLETED": "Step completed", "RESET_BUTTON": "Reset button pressed"}
SPECS = {
    "JOB_SELECTION": [("mode", "Selection mode", "choice", "OPERATOR_SELECT", ["OPERATOR_SELECT", "BARCODE_AUTO"]),
                      ("start_on_scan", "A scan starts the inspection", "bool", True, None),
                      ("remember_last_job", "Reload the last job at start-up", "bool", True, None)],
    "INSPECTION_CYCLE": [("auto_restart", "Start the next part automatically", "bool", True, None),
                         ("result_display_ms", "Show PASS / FAIL for (ms)", "int", 3000, (0, 60000)),
                         ("overtime_warning", "Warn above the job's expected cycle time", "bool", True, None)],
    "BARCODE_CHECK": [("duplicate_policy", "Barcode that already passed", "choice", "BLOCK",
                       ["BLOCK", "WARN", "ALLOW"])],
    "EVIDENCE": [("save_pass_evidence", "Also store images of passed checks", "bool", True, None),
                 ("evidence_retention_days", "Keep images for (days, 0 = forever)", "int", 365, (0, 3650))],
    "RESET": [],
}
MODE_HELP = {"OPERATOR_SELECT": "The operator chooses the job on the Operate page.",
             "BARCODE_AUTO": "The scanned barcode selects the released job whose variant pattern matches."}


class FlowView(QWidget):
    """Vertical chain of process steps (read-only illustration of what the process does)."""

    def __init__(self):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(4, 4, 4, 4)
        self.lay.setSpacing(0)

    def set_steps(self, steps: list[str], enabled: bool) -> None:
        while self.lay.count():
            it = self.lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for i, s in enumerate(steps):
            card = QFrame()
            card.setObjectName("FlowCard")
            card.setStyleSheet(f"QFrame#FlowCard {{ background: {'white' if enabled else '#F4F5F7'}; border: 1px solid "
                               f"{C['line']}; border-left: 3px solid {C['primary'] if enabled else C['faint']}; "
                               "border-radius: 4px; }")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(10, 7, 10, 7)
            n = QLabel(str(i + 1))
            n.setFixedSize(22, 22)
            n.setAlignment(Qt.AlignCenter)
            n.setStyleSheet(f"background: {C['primary_soft']}; color: {C['primary']}; border-radius: 11px; "
                            "border: none; font-weight: 600;")
            cl.addWidget(n)
            t = QLabel(s)
            t.setStyleSheet("border: none;")
            cl.addWidget(t, 1)
            self.lay.addWidget(card)
            if i < len(steps) - 1:
                arrow = QLabel()
                arrow.setPixmap(icon("arrow_down", C["faint"], 16).pixmap(16, 16))
                arrow.setAlignment(Qt.AlignCenter)
                arrow.setFixedHeight(20)
                self.lay.addWidget(arrow)
        self.lay.addStretch(1)


class ProcessesPage(Page):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        self.rows: list[dict] = []
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        left = QFrame()
        left.setObjectName("Panel")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.addLayout(hrow(label("Station processes", "H2"), None,
                          label("Automation that wraps every job on this station", "Muted")))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Process Name", "Start by", "Status"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 200)
        self.table.setFixedHeight(200)
        self.table.currentCellChanged.connect(lambda r, *_: self._select(r))
        ll.addWidget(self.table)
        ll.addWidget(label("Process steps", "H2"))
        self.flow = FlowView()
        self.flow.setMaximumWidth(620)
        ll.addWidget(self.flow, 1)
        root.addWidget(left, 1)
        self.props = PropertiesPanel()
        root.addWidget(self.props)

    def can_edit(self) -> bool:
        return bool(self.ctx.session and self.ctx.session.can(Perm.MANAGE_PROCESSES))

    def on_show(self) -> None:
        self.rows = self.ctx.processes.list()
        cur = max(0, self.table.currentRow())
        self.table.setRowCount(len(self.rows))
        for i, p in enumerate(self.rows):
            name = QTableWidgetItem(icon("process", C["ink"], 16), p["name"])
            self.table.setItem(i, 0, name)
            self.table.setItem(i, 1, QTableWidgetItem(TRIGGERS.get(p["start_trigger"], p["start_trigger"])))
            st = QTableWidgetItem("Active" if p["enabled"] else "Disabled")
            st.setForeground(QColor(C["ok"] if p["enabled"] else C["faint"]))
            self.table.setItem(i, 2, st)
        self.table.setCurrentCell(min(cur, len(self.rows) - 1), 0)
        self._select(self.table.currentRow())

    def _select(self, row: int) -> None:
        p = self.rows[row] if 0 <= row < len(self.rows) else None
        pp = self.props
        pp.clear()
        if p is None:
            pp.end()
            return
        self.flow.set_steps(p["flow"], p["enabled"])
        self.cur = p
        edit = self.can_edit()
        pp.heading("Process", p["code"])
        name = QLabel(p["name"])
        name.setFont(font(12, True))
        pp.body.addWidget(name)
        pp.body.addWidget(label(p["description"] or "", "Muted", wrap=True))
        pp.body.addWidget(chip(f"Start by: {TRIGGERS.get(p['start_trigger'], '')}", "info"))
        self.p_enabled = QCheckBox("Process enabled")
        self.p_enabled.setChecked(p["enabled"])
        self.p_enabled.setEnabled(edit and p["code"] != "INSPECTION_CYCLE")
        pp.body.addWidget(self.p_enabled)
        self.form = ParamForm(SPECS.get(p["code"], []), p["params"], stacked=True)
        self.form.set_enabled(edit)
        if SPECS.get(p["code"]):
            pp.heading("Settings")
            pp.body.addWidget(self.form)
        if p["code"] == "JOB_SELECTION":
            self.mode_help = label(MODE_HELP.get(p["params"].get("mode"), ""), "Muted", wrap=True)
            pp.body.addWidget(self.mode_help)
            self.form.changed.connect(lambda: self.mode_help.setText(MODE_HELP.get(self.form.values()["mode"], "")))
        if p["code"] == "RESET":
            pp.body.addWidget(label("Teach a station-wide virtual button with Station function = RESET on the "
                                    "Detections page.", "Muted", wrap=True))
        if p.get("updated_at"):
            pp.body.addWidget(label(f"Last changed {p['updated_at'].astimezone():%d-%m-%Y %H:%M}", "Faint"))
        pp.end()
        b = button("Save", "primary", self.save, ico="save")
        b.setEnabled(edit)
        pp.footer.addStretch(1)
        pp.footer.addWidget(b)

    def save(self) -> None:
        try:
            self.ctx.save_process(self.cur["code"], self.p_enabled.isChecked(), self.form.values())
        except PermissionDenied as exc:
            return error(self, str(exc))
        self.main.add_message(f"Process '{self.cur['name']}' saved", "ok", "Processes")
        self.on_show()
