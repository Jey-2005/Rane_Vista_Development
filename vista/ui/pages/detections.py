"""Detections page (Arkite layout): tree | Teaching · Fine tune · Projector | Properties."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMenu,
                               QProgressBar, QScrollArea, QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from vista.core.security import PermissionDenied, Perm
from vista.ui.icons import icon
from vista.ui.theme import C, font
from vista.ui.widgets.bench import BenchCanvas
from vista.ui.widgets.common import (ImageView, Page, ParamForm, PropertiesPanel, SearchBox, button, chip, confirm,
                                     error, frame_view, height_to_color, hrow, info, label, to_qimage, tool)
from vista.vision.detectors import (ACTIVITY_DEFAULTS, BUTTON_DEFAULTS, OBJECT_DEFAULTS, QC_ALGOS, QC_TYPES,
                                   QUALITY_DEFAULTS, TOLERANCE, TeachError, decode_png, teach_object, teach_quality,
                                   teach_zone_baseline)

TYPE_LABEL = {"OBJECT": "Object", "ACTIVITY": "Activity", "BUTTON": "Virtual button", "QUALITY": "Quality check"}
TYPE_ICON = {"OBJECT": "cube", "ACTIVITY": "hand", "BUTTON": "button", "QUALITY": "eye"}
SENSORS = {"OBJECT": ["DEPTH", "IR"], "ACTIVITY": ["DEPTH"], "BUTTON": ["DEPTH"], "QUALITY": ["COLOR", "VISION"]}
SENSOR_LABEL = {"DEPTH": "3D sensor - depth", "IR": "3D sensor - infrared", "COLOR": "3D sensor - colour (RGB)",
                "VISION": "Vision camera"}
STREAM_FOR = {"DEPTH": "HEIGHT", "IR": "IR", "COLOR": "COLOR", "VISION": "VISION"}
TOL_LABEL = {"EXACT": "Exact (0% variation)", "ACCURATE": "Accurate (20% variation)",
             "NARROW": "Narrow (50% variation)", "WIDE": "Wide (100% variation)"}
DEFAULT_CLASSES = [{"name": "Expected result", "type": "CORRECT"}, {"name": "Bad result", "type": "WRONG"},
                   {"name": "Missing", "type": "MISSING"}]
STATE_GLYPH = {"PRESENT": ("●", C["primary"]), "OK": ("●", C["ok"]), "ACTIVE": ("●", C["ok"]),
               "PRESSED": ("●", C["ok"]), "ABSENT": ("○", C["primary"]), "IDLE": ("○", C["faint"]),
               "NG": ("●", C["ng"]), "MISSING": ("●", C["ng"]), "UNTAUGHT": ("⚠", C["warn"]),
               "DISABLED": ("⊘", C["faint"]), "OCC_PRESENT": ("◐", C["primary"]), "OCC_ABSENT": ("◑", C["primary"]),
               "OCCLUDED": ("◐", C["primary"]), "UNKNOWN": ("❚❚", C["primary"])}

PARAM_SPECS = {
    "OBJECT": [("present_score", "Present at score ≥", "float", OBJECT_DEFAULTS["present_score"], (0, 1)),
               ("absent_score", "Absent at score ≤", "float", OBJECT_DEFAULTS["absent_score"], (0, 1)),
               ("min_diff", "Minimum change (mm / IR)", "float", OBJECT_DEFAULTS["min_diff"], (1, 200)),
               ("occlusion_mm", "Occlusion above object (mm)", "float", OBJECT_DEFAULTS["occlusion_mm"], (5, 1000)),
               ("occlusion_max", "Maximum occluded fraction", "float", OBJECT_DEFAULTS["occlusion_max"], (0, 1)),
               ("debounce_ms", "Debounce (ms)", "int", OBJECT_DEFAULTS["debounce_ms"], (0, 5000))],
    "ACTIVITY": [("min_rise_mm", "Hand above bench from (mm)", "float", ACTIVITY_DEFAULTS["min_rise_mm"], (1, 500)),
                 ("max_rise_mm", "… up to (mm)", "float", ACTIVITY_DEFAULTS["max_rise_mm"], (10, 1500)),
                 ("enter_ratio", "Zone fill to count as inside", "float", ACTIVITY_DEFAULTS["enter_ratio"], (0, 1)),
                 ("min_dwell_ms", "Minimum dwell (ms)", "int", ACTIVITY_DEFAULTS["min_dwell_ms"], (0, 60000)),
                 ("exit_ms", "Leave confirmation (ms)", "int", ACTIVITY_DEFAULTS["exit_ms"], (0, 5000)),
                 ("complete_on", "Complete on", "choice", ACTIVITY_DEFAULTS["complete_on"], ["LEAVE", "ENTER"])],
    "BUTTON": [("press_min_mm", "Press height from (mm)", "float", BUTTON_DEFAULTS["press_min_mm"], (1, 500)),
               ("press_max_mm", "… up to (mm)", "float", BUTTON_DEFAULTS["press_max_mm"], (10, 800)),
               ("press_ratio", "Zone fill to press", "float", BUTTON_DEFAULTS["press_ratio"], (0, 1)),
               ("hold_ms", "Hold time (ms)", "int", BUTTON_DEFAULTS["hold_ms"], (0, 5000))],
    "QUALITY": [("min_score", "Minimum similarity", "float", QUALITY_DEFAULTS["min_score"], (0, 1)),
                ("min_margin", "Minimum margin to bad classes", "float", QUALITY_DEFAULTS["min_margin"], (0, 1)),
                ("stable_frames", "Stable evaluations", "int", QUALITY_DEFAULTS["stable_frames"], (1, 30)),
                ("search_px", "Position search (px)", "int", QUALITY_DEFAULTS["search_px"], (0, 80)),
                ("occlusion_mm", "Occlusion height (mm)", "float", QUALITY_DEFAULTS["occlusion_mm"], (5, 1000)),
                ("occlusion_max", "Maximum occluded fraction", "float", QUALITY_DEFAULTS["occlusion_max"], (0, 1))],
}


def _pix(img: np.ndarray | None, w: int, h: int) -> QPixmap | None:
    if img is None:
        return None
    return QPixmap.fromImage(to_qimage(img)).scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class SnapBox(QFrame):
    """Arkite 'Without … / With …' snapshot tile."""

    def __init__(self, title: str):
        super().__init__()
        self.setStyleSheet(f"QFrame {{ background: white; border: 1px solid {C['line']}; border-radius: 4px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        self.title = QLabel(title)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet("border: none; font-size: 8.5pt;")
        lay.addWidget(self.title)
        self.img = QLabel("not captured")
        self.img.setAlignment(Qt.AlignCenter)
        self.img.setMinimumHeight(118)
        self.img.setStyleSheet(f"border: none; background: #F3F5F8; color: {C['faint']};")
        lay.addWidget(self.img, 1)

    def set(self, pm: QPixmap | None, text: str = "not captured") -> None:
        if pm is None:
            self.img.setPixmap(QPixmap())
            self.img.setText(text)
        else:
            self.img.setPixmap(pm)


class DetectionsPage(Page):
    def __init__(self, ctx, executor, main):
        super().__init__()
        self.ctx, self.ex, self.main = ctx, executor, main
        self.det: dict | None = None
        self.rows: list[dict] = []
        self.items: dict[int, QTreeWidgetItem] = {}
        self.caps: dict = {}
        self.qc_samples: list[tuple[str, str, np.ndarray]] = []
        self.roi = None
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)

        # ---------------------------------------------------------------- tree
        left = QFrame()
        left.setObjectName("Panel")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        self.b_new = button("New", "primary", ico="plus")
        m = QMenu(self)
        m.addSection("Job-specific")
        for t in TYPE_LABEL:
            m.addAction(icon(TYPE_ICON[t], C["ink"], 16), TYPE_LABEL[t], lambda t=t: self.new(t, False))
        m.addSection("Station-wide (all jobs)")
        for t in TYPE_LABEL:
            m.addAction(icon(TYPE_ICON[t], C["ink"], 16), TYPE_LABEL[t], lambda t=t: self.new(t, True))
        self.b_new.setMenu(m)
        self.new_menu_obj = m
        ll.addLayout(hrow(self.b_new, None, tool("expand", "Expand all", lambda: self.tree.expandAll()),
                          tool("collapse", "Collapse all", lambda: self.tree.collapseAll())))
        self.search = SearchBox("Search for detections")
        self.search.textChanged.connect(self._filter)
        ll.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setIconSize(QSize(17, 17))
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 30)
        self.tree.currentItemChanged.connect(self._selected)
        ll.addWidget(self.tree, 1)
        left.setMinimumWidth(270)
        split.addWidget(left)

        # ---------------------------------------------------------------- centre tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._teaching_tab(), "Teaching")
        self.tabs.addTab(self._finetune_tab(), "Fine tune")
        self.tabs.addTab(self._projector_tab(), "Projector")
        split.addWidget(self.tabs)
        split.setSizes([290, 900])
        self.props = PropertiesPanel(width=300)
        root.addWidget(self.props)
        self._t = QTimer(self)
        self._t.timeout.connect(self._live)
        self._t.start(200)
        main.job_context_changed.connect(lambda _: self.on_show() if self.isVisible() else None)

    # ================================================================== tab builders
    def _teaching_tab(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        col = QVBoxLayout()
        self.sensor_lbl = label("", "H3")
        self.stream = QComboBox()
        self.stream.addItems(["COLOR", "IR", "HEIGHT", "DEPTH", "VISION"])
        col.addLayout(hrow(icon_lbl := QLabel(), self.sensor_lbl, None, label("Stream", "Muted"), self.stream,
                           tool("zoom_in", "Zoom in", lambda: self.view.zoom_by(1.25)),
                           tool("zoom_out", "Zoom out", lambda: self.view.zoom_by(0.8)),
                           tool("fit", "Fit", lambda: self.view.fit())))
        icon_lbl.setPixmap(icon("camera", C["ink"], 18).pixmap(18, 18))
        self.view = ImageView(placeholder="Waiting for camera")
        self.view.rect_changed.connect(self._roi_changed)
        self.view.hovered.connect(self._hover)
        col.addWidget(self.view, 1)
        self.readout = label("Mouse wheel: zoom   Right button: move   Left drag: working zone", "Muted")
        col.addWidget(self.readout)
        lay.addLayout(col, 1)

        side = QWidget()
        side.setFixedWidth(270)
        self.side = QVBoxLayout(side)
        self.side.setContentsMargins(0, 0, 0, 0)
        self.side.setSpacing(6)
        self.snap_a, self.snap_b = SnapBox("Without"), SnapBox("With")
        self.btn_a = button("Capture", None, lambda: self.capture("without"), ico="camera")
        self.btn_b = button("Capture", None, lambda: self.capture("with"), ico="camera")
        self.side.addWidget(self.snap_a)
        self.side.addWidget(self.btn_a)
        self.side.addWidget(self.snap_b)
        self.side.addWidget(self.btn_b)
        # quality check classes
        self.qc_box = QWidget()
        ql = QVBoxLayout(self.qc_box)
        ql.setContentsMargins(0, 0, 0, 0)
        self.qc_scroll = QScrollArea()
        self.qc_scroll.setWidgetResizable(True)
        self.qc_inner = QWidget()
        self.qc_inner.setStyleSheet("background: white;")
        self.qc_lay = QVBoxLayout(self.qc_inner)
        self.qc_lay.setContentsMargins(4, 4, 4, 4)
        self.qc_scroll.setWidget(self.qc_inner)
        ql.addWidget(self.qc_scroll, 1)
        ql.addLayout(hrow(button("Add class", None, self.add_class, ico="plus"), None))
        self.side.addWidget(self.qc_box, 1)
        hint = QFrame()
        hint.setObjectName("Hint")
        hl = QHBoxLayout(hint)
        hl.setContentsMargins(6, 4, 6, 4)
        self.hint_lbl = label("", "Muted", wrap=True)
        hl.addWidget(self.hint_lbl)
        self.side.addWidget(hint)
        g = QGridLayout()
        self.tolerance = QComboBox()
        for k in TOLERANCE:
            self.tolerance.addItem(TOL_LABEL[k], k)
        self.tolerance.setCurrentIndex(2)
        self.algo = QComboBox()
        self.algo.addItems(list(QC_ALGOS))
        self.mode_lbl = QComboBox()
        self.l_tol, self.l_algo = label("Position tolerance"), label("Algorithm")
        g.addWidget(label("Sensor"), 0, 0)
        g.addWidget(self.mode_lbl, 0, 1)
        g.addWidget(self.l_tol, 1, 0)
        g.addWidget(self.tolerance, 1, 1)
        g.addWidget(self.l_algo, 2, 0)
        g.addWidget(self.algo, 2, 1)
        self.side.addLayout(g)
        self.mode_lbl.currentIndexChanged.connect(self._sensor_changed)
        self.b_cancel = button("Cancel", None, self._show_det)
        self.b_teach = button("Teach", "primary", self.teach, ico="teach")
        self.side.addLayout(hrow(self.b_cancel, self.b_teach))
        lay.addWidget(side)
        return w

    def _finetune_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 12, 14, 12)
        top = QHBoxLayout()
        self.ft_state = QLabel("-")
        self.ft_state.setFont(font(20, display=True))
        top.addWidget(self.ft_state)
        top.addStretch(1)
        self.ft_detail = label("", "Muted")
        top.addWidget(self.ft_detail)
        lay.addLayout(top)
        self.ft_bar = QProgressBar()
        self.ft_bar.setRange(0, 100)
        self.ft_bar.setFixedHeight(14)
        lay.addWidget(self.ft_bar)
        lay.addWidget(label("Live score of the selected detection. Adjust thresholds while placing / removing the "
                            "object or performing the activity, then save.", "Muted", wrap=True))
        self.ft_form = ParamForm()
        lay.addWidget(self.ft_form)
        self.b_ft_save = button("Save fine-tune", "primary", self.save_finetune, ico="save")
        lay.addLayout(hrow(None, self.b_ft_save))
        lay.addStretch(1)
        return w

    def _projector_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        self.bench = BenchCanvas(self.ctx)
        self.bench.zone_clicked.connect(lambda did: self.select_detection(did))
        self.bench.zone_moved.connect(self._zone_moved)
        lay.addLayout(hrow(label("Drag the selected zone to shift its projection on the bench.", "Muted"), None,
                           button("Reset shift", None, self._reset_shift, ico="reset"),
                           button("Show all zones on bench", None, lambda: self.main.projector.set_mode("TEST"),
                                  ico="projector"),
                           button("Normal guidance", None, lambda: self.main.projector.set_mode("RUN")),
                           tool("fit", "Reset view", lambda: self.bench.reset_view())))
        lay.addWidget(self.bench, 1)
        return w

    # ================================================================== loading
    def on_show(self) -> None:
        self.reload()

    def on_hide(self) -> None:
        self.ctx.load_engine(self.ex.job["id"] if self.ex.job else None)
        self.ctx.engine.set_watch(set())
        self.main.projector.highlight = None

    def editable(self) -> bool:
        return bool(self.ctx.session and self.ctx.session.can(Perm.TEACH_DETECTIONS)) and self.ex.mode != "RUNNING"

    def reload(self) -> None:
        job_id = self.main.edit_job_id
        if self.ex.mode != "RUNNING":
            for w in self.ctx.load_engine(job_id):
                self.main.add_message(w, "error", "Detections")
        self.rows = self.ctx.detections.list_for(job_id)
        job = self.ctx.jobs.get(job_id) if job_id else None
        sel = self.det["id"] if self.det else None
        self.tree.blockSignals(True)
        self.tree.clear()
        self.items = {}
        station = [d for d in self.rows if d["job_id"] is None]
        jobspec = [d for d in self.rows if d["job_id"] is not None]
        roots = []
        for title, rows in ((f"Station-wide ({len(station)})", station),
                            (f"Job-specific ({job['code'] if job else 'no job'}) ({len(jobspec)})", jobspec)):
            top = QTreeWidgetItem([title, ""])
            top.setForeground(0, QColor(C["primary"]))
            top.setFont(0, font(9, True))
            self.tree.addTopLevelItem(top)
            roots.append(top)
            groups: dict[str, QTreeWidgetItem] = {}
            for d in rows:
                parent = top
                if d["group_name"]:
                    if d["group_name"] not in groups:
                        g = QTreeWidgetItem([f"{d['group_name']}", ""])
                        top.addChild(g)
                        groups[d["group_name"]] = g
                    parent = groups[d["group_name"]]
                it = QTreeWidgetItem([d["name"], ""])
                it.setIcon(0, icon(TYPE_ICON[d["det_type"]], C["ink"], 17))
                it.setData(0, Qt.UserRole, d["id"])
                it.setToolTip(0, f"{TYPE_LABEL[d['det_type']]} · {SENSOR_LABEL[d['sensor']]}")
                parent.addChild(it)
                self.items[d["id"]] = it
            for name, g in groups.items():
                g.setText(0, f"{name} ({g.childCount()})")
        self.tree.expandAll()
        self.tree.blockSignals(False)
        self._filter(self.search.text())
        if sel in self.items:
            self.tree.setCurrentItem(self.items[sel])
        else:
            self.det = None
            self._show_det()
        self.b_new.setEnabled(self.editable())
        self._bench_scene()

    def _filter(self, text: str) -> None:
        t = text.lower().strip()
        for did, it in self.items.items():
            it.setHidden(bool(t) and t not in it.text(0).lower())

    def select_detection(self, det_id: int) -> None:
        if det_id in self.items:
            self.tree.setCurrentItem(self.items[det_id])

    def new_menu(self) -> None:
        self.new_menu_obj.exec(self.b_new.mapToGlobal(self.b_new.rect().bottomLeft()))

    def _selected(self, cur, _prev) -> None:
        det_id = cur.data(0, Qt.UserRole) if cur else None
        self.det = next((d for d in self.rows if d["id"] == det_id), None)
        self._show_det()

    # ================================================================== show detection
    def _show_det(self) -> None:
        d = self.det
        self.caps = {}
        edit = self.editable()
        self.main.projector.highlight = d["id"] if d else None
        if d is None:
            self.sensor_lbl.setText("Select a detection")
            self.view.set_edit_rect(None, False)
            self.ctx.engine.set_watch(set())
            self._properties()
            for w in (self.btn_a, self.btn_b, self.b_teach, self.b_cancel):
                w.setEnabled(False)
            self.ft_form.build([], {})
            self._bench_scene()
            return
        t = d["det_type"]
        self.mode_lbl.blockSignals(True)
        self.mode_lbl.clear()
        for s in SENSORS[t]:
            self.mode_lbl.addItem(SENSOR_LABEL[s], s)
        self.mode_lbl.setCurrentIndex(max(0, self.mode_lbl.findData(d["sensor"])))
        self.mode_lbl.blockSignals(False)
        self.stream.setCurrentText(STREAM_FOR[d["sensor"]])
        self.sensor_lbl.setText(SENSOR_LABEL[d["sensor"]])
        self.roi = d["model"].get("roi")
        self.view.set_edit_rect(self.roi, edit)
        quality = t == "QUALITY"
        zone = t in ("ACTIVITY", "BUTTON")
        self.qc_box.setVisible(quality)
        for w in (self.snap_a, self.btn_a):
            w.setVisible(not quality)
        for w in (self.snap_b, self.btn_b):
            w.setVisible(t == "OBJECT")
        self.l_tol.setVisible(t == "OBJECT")
        self.tolerance.setVisible(t == "OBJECT")
        self.l_algo.setVisible(quality)
        self.algo.setVisible(quality)
        if t == "OBJECT":
            self.snap_a.title.setText(f"Without {d['name']}")
            self.snap_b.title.setText(f"With {d['name']}")
            self.hint_lbl.setText("Set the working zone around the object, excluding the operator and other moving "
                                  "content. Teaching compares the without and with snapshots.")
        elif zone:
            self.snap_a.title.setText("Empty zone")
            self.hint_lbl.setText("Draw the zone where the hand works, keep it empty and capture. Then perform the "
                                  "activity - the counter on Fine tune must increase.")
        else:
            self.hint_lbl.setText("Draw the region to check. Add several samples per class under realistic "
                                  "variation; AUTO picks the best algorithm.")
            self._load_qc(d)
        self.snap_a.set(None)
        self.snap_b.set(None)
        self._thumbs_from_model(d)
        for w in (self.btn_a, self.btn_b, self.b_teach, self.b_cancel):
            w.setEnabled(edit)
        p = {**{"OBJECT": OBJECT_DEFAULTS, "ACTIVITY": ACTIVITY_DEFAULTS, "BUTTON": BUTTON_DEFAULTS,
                "QUALITY": QUALITY_DEFAULTS}[t], **d["params"]}
        self.ft_form.build(PARAM_SPECS[t], p)
        self.ft_form.set_enabled(edit)
        self.b_ft_save.setEnabled(edit)
        self.ctx.engine.set_watch({d["id"]})
        self._properties()
        self._bench_scene()

    def _thumbs_from_model(self, d: dict) -> None:
        if not d["taught_at"] or d["det_type"] == "QUALITY":
            return
        for s in self.ctx.detections.samples(d["id"]):
            if s["kind"] != "REFS":
                continue
            from vista.vision.detectors import unpack_arrays
            arr = unpack_arrays(s["data"])
            if "ref_without" in arr:
                self.snap_a.set(_pix(height_to_color(arr["ref_without"], 120), 250, 118))
                self.snap_b.set(_pix(height_to_color(arr["ref_with"], 120), 250, 118))
            elif "baseline" in arr:
                self.snap_a.set(_pix(height_to_color(arr["baseline"], 120), 250, 118))

    def _properties(self) -> None:
        p = self.props
        p.clear()
        d = self.det
        if d is None:
            p.heading("Detection", "Select a detection or create one with New.")
            p.end()
            return
        edit = self.editable()
        p.heading("Detection", f"ID {d['id']} · " + ("station-wide" if d["job_id"] is None else "job-specific"))
        self.p_name = p.field("Name", QLineEdit(d["name"]))
        self.p_enabled = QComboBox()
        self.p_enabled.addItems(["On", "Off"])
        self.p_enabled.setCurrentIndex(0 if d["enabled"] else 1)
        p.field("Enabled", self.p_enabled)
        tbox = QComboBox()
        tbox.addItem(icon(TYPE_ICON[d["det_type"]], C["ink"], 16), TYPE_LABEL[d["det_type"]])
        tbox.setEnabled(False)
        p.field("Type", tbox)
        self.p_group = p.field("Group", QLineEdit(d["group_name"]))
        self.p_function = None
        if d["det_type"] == "BUTTON":
            self.p_function = QComboBox()
            self.p_function.addItems(["NONE", "RESET"])
            self.p_function.setCurrentText(d["params"].get("function", "NONE"))
            p.field("Station function", self.p_function)
        state = "Taught " + d["taught_at"].astimezone().strftime("%d-%m-%Y %H:%M") if d["taught_at"] else "Not taught"
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 4, 0, 0)
        rl.addWidget(chip(state, "ok" if d["taught_at"] else "warn"))
        if d["det_type"] == "QUALITY" and d["model"].get("algorithm"):
            rl.addWidget(chip(d["model"]["algorithm"].title(), "info"))
        rl.addStretch(1)
        p.body.addWidget(row)
        used = self.ctx.detections.usage(d["id"])
        p.heading("Used by")
        p.body.addWidget(label("\n".join(f"{u['job_code']} · {u['step_name']}" for u in used[:8]) or "No steps yet",
                               "Muted", wrap=True))
        for w in (self.p_name, self.p_enabled, self.p_group) + ((self.p_function,) if self.p_function else ()):
            w.setEnabled(edit)
        p.end()
        sv = button("Save", "primary", self.save_props, ico="save")
        cl = button("Clear teaching", None, self.clear_teaching)
        dl = button("", "danger", self.delete, "Delete detection", ico="trash")
        for b in (sv, cl, dl):
            b.setEnabled(edit)
        p.footer.addWidget(dl)
        p.footer.addWidget(cl)
        p.footer.addStretch(1)
        p.footer.addWidget(sv)

    # ================================================================== quality classes
    def _load_qc(self, d: dict) -> None:
        self.classes = list(d["params"].get("classes") or DEFAULT_CLASSES)
        self.qc_samples = [(s["class_name"], s["meta"].get("type", "CORRECT"), decode_png(s["data"]))
                           for s in self.ctx.detections.samples(d["id"]) if s["kind"] == "QC"]
        self.algo.setCurrentText(d["params"].get("algorithm", "AUTO"))
        self._render_classes()

    def _render_classes(self) -> None:
        while self.qc_lay.count():
            it = self.qc_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        edit = self.editable()
        for ci, c in enumerate(self.classes):
            head = QHBoxLayout()
            lvl = {"CORRECT": "ok", "WRONG": "ng", "MISSING": "warn"}[c["type"]]
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 2, 0, 6)
            bl.setSpacing(3)
            typ = QComboBox()
            typ.addItems(list(QC_TYPES))
            typ.setCurrentText(c["type"])
            typ.setFixedWidth(96)
            typ.setEnabled(edit)
            typ.currentTextChanged.connect(lambda v, i=ci: self._set_class_type(i, v))
            head.addWidget(chip(c["name"], lvl))
            head.addStretch(1)
            head.addWidget(typ)
            bl.addLayout(head)
            thumbs = QHBoxLayout()
            thumbs.setSpacing(3)
            for si, (cls, _t, img) in enumerate(self.qc_samples):
                if cls != c["name"]:
                    continue
                th = QLabel()
                th.setPixmap(_pix(img, 54, 54))
                th.setFixedSize(56, 56)
                th.setStyleSheet(f"border: 2px solid {C['ok'] if c['type'] == 'CORRECT' else C['ng']}; "
                                 "border-radius: 3px;")
                th.setToolTip("Double-click to remove")
                th.mouseDoubleClickEvent = (lambda _e, k=si: self._remove_sample(k)) if edit else (lambda _e: None)
                thumbs.addWidget(th)
            thumbs.addStretch(1)
            bl.addLayout(thumbs)
            add = button(f"Add {c['name'].lower()}", None, lambda _=False, n=c["name"]: self.add_sample(n), ico="camera")
            add.setEnabled(edit)
            bl.addWidget(add)
            self.qc_lay.addWidget(box)
        self.qc_lay.addStretch(1)

    def _set_class_type(self, i: int, v: str) -> None:
        self.classes[i]["type"] = v
        self.qc_samples = [(c, v if c == self.classes[i]["name"] else t, img) for c, t, img in self.qc_samples]
        self._render_classes()

    def add_class(self) -> None:
        if self.det is None or self.det["det_type"] != "QUALITY":
            return
        name, ok = QInputDialog.getText(self, "New class", "Class name (e.g. 'Clip not fully seated'):")
        if ok and name.strip() and name.strip() not in [c["name"] for c in self.classes]:
            self.classes.append({"name": name.strip(), "type": "WRONG"})
            self._render_classes()

    def add_sample(self, cls: str) -> None:
        if not self._can_teach():
            return
        if not self.roi:
            return error(self, "Draw the region to check on the image first.")
        x, y, w, h = [int(v) for v in self.roi]
        if self.qc_samples and self.qc_samples[0][2].shape[:2] != (h, w):
            if not confirm(self, "The region size changed - existing samples must be removed. Continue?"):
                return
            self.qc_samples = []
        f = self.ctx.latest_frame()
        img = None if f is None else (f.vision if self.mode_lbl.currentData() == "VISION" else f.color)
        if img is None:
            return error(self, "No image from the selected sensor.")
        ctype = next(c["type"] for c in self.classes if c["name"] == cls)
        self.qc_samples.append((cls, ctype, img[y:y + h, x:x + w].copy()))
        self._render_classes()

    def _remove_sample(self, k: int) -> None:
        if 0 <= k < len(self.qc_samples):
            del self.qc_samples[k]
            self._render_classes()

    # ================================================================== actions
    def _can_teach(self) -> bool:
        if self.det is None:
            return False
        try:
            self.ctx.require(Perm.TEACH_DETECTIONS)
        except PermissionDenied as exc:
            error(self, str(exc))
            return False
        if self.ex.mode == "RUNNING":
            error(self, "Teaching is not possible while an inspection is running.")
            return False
        return True

    def new(self, det_type: str, station_wide: bool) -> None:
        try:
            self.ctx.require(Perm.TEACH_DETECTIONS)
        except PermissionDenied as exc:
            return error(self, str(exc))
        job_id = None if station_wide else self.main.edit_job_id
        if not station_wide and job_id is None:
            return error(self, "Select a job first (Jobs page or Ctrl+P) for a job-specific detection.")
        name, ok = QInputDialog.getText(self, f"New {TYPE_LABEL[det_type].lower()}", "Name (used in instructions):")
        if not ok or not name.strip():
            return
        group, _ = QInputDialog.getText(self, "Group", "Group (optional, e.g. GAUGE, QUALITY CHECK):")
        params = {"classes": DEFAULT_CLASSES} if det_type == "QUALITY" else {}
        try:
            det_id = self.ctx.detections.create(job_id, name.strip(), group.strip(), det_type,
                                                SENSORS[det_type][0], params)
        except Exception as exc:
            return error(self, f"Could not create detection (name already used?): {exc}")
        self.ctx.audit("DETECTION_CREATED", "detection", det_id, {"name": name, "type": det_type})
        self.det = {"id": det_id}
        self.reload()

    def _sensor_changed(self) -> None:
        if self.det is not None:
            s = self.mode_lbl.currentData()
            self.stream.setCurrentText(STREAM_FOR.get(s, "COLOR"))
            self.sensor_lbl.setText(SENSOR_LABEL.get(s, ""))

    def save_props(self) -> None:
        if not self._can_teach():
            return
        d = self.det
        params = dict(d["params"])
        if self.p_function is not None:
            params["function"] = self.p_function.currentText()
        if d["det_type"] == "QUALITY":
            params["classes"] = self.classes
            params["algorithm"] = self.algo.currentText()
        try:
            self.ctx.detections.update_props(d["id"], self.p_name.text().strip() or d["name"],
                                             self.p_group.text().strip(), self.mode_lbl.currentData() or d["sensor"],
                                             self.p_enabled.currentIndex() == 0, params)
        except Exception as exc:
            return error(self, f"Save failed: {exc}")
        if d["job_id"]:
            self.ctx.jobs.mark_draft(d["job_id"], self.ctx.session.user_id)
        self.ctx.audit("DETECTION_UPDATED", "detection", d["id"], {"params": params})
        self.reload()

    def save_finetune(self) -> None:
        if not self._can_teach():
            return
        d = self.det
        params = {**d["params"], **self.ft_form.values()}
        self.ctx.detections.update_props(d["id"], d["name"], d["group_name"], d["sensor"], d["enabled"], params)
        if d["job_id"]:
            self.ctx.jobs.mark_draft(d["job_id"], self.ctx.session.user_id)
        self.ctx.audit("DETECTION_FINETUNED", "detection", d["id"], {"params": params})
        self.reload()

    def _roi_changed(self, rect) -> None:
        if self.det is not None and self.editable():
            self.roi = rect
            self.readout.setText(f"Working zone {rect} - capture and press Teach to apply")

    def _hover(self, x: float, y: float) -> None:
        f = self.ctx.latest_frame()
        cal = self.ctx.calibration
        if f is None or f.depth_mm is None:
            return
        H, W = f.depth_mm.shape
        if not (0 <= x < W and 0 <= y < H):
            return
        txt = f"Sensor stream {SENSOR_LABEL.get(self.mode_lbl.currentData(), '')}   Pixel {int(x)}, {int(y)}"
        if cal is not None and f.height_mm is not None:
            h = f.height_mm[int(y), int(x)]
            if np.isfinite(h):
                bx, by = cal.pixel_to_bench(x, y, float(h))
                txt += f"   Location {bx:.1f}, {by:.1f}, {h:.1f} mm"
        if f.ir is not None:
            txt += f"   IR {int(f.ir[int(y), int(x)])}"
        self.readout.setText(txt)

    def _signals(self, n: int = 8):
        frames = self.ctx.worker.recent(n) if self.ctx.worker else []
        if not frames:
            raise TeachError("No camera frames available.")
        if self.mode_lbl.currentData() == "IR":
            sig = [f.ir.astype(np.float32) for f in frames if f.ir is not None]
        else:
            sig = [f.height_mm for f in frames if f.height_mm is not None]
        if not sig:
            raise TeachError("No height data - calibrate the workstation first.")
        return sig, [f.height_mm for f in frames if f.height_mm is not None]

    def capture(self, kind: str) -> None:
        if not self._can_teach():
            return
        if not self.roi:
            return error(self, "Draw the working zone on the image first.")
        kind = "baseline" if self.det["det_type"] in ("ACTIVITY", "BUTTON") else kind
        try:
            sig, heights = self._signals()
        except TeachError as exc:
            return error(self, str(exc))
        self.caps[kind] = (sig, heights)
        x, y, w, h = [int(v) for v in self.roi]
        crop = np.nanmedian(np.stack(sig), axis=0)[y:y + h, x:x + w]
        img = height_to_color(crop, 120) if self.mode_lbl.currentData() != "IR" else crop.astype(np.uint8)
        (self.snap_b if kind == "with" else self.snap_a).set(_pix(img, 250, 118))

    def teach(self) -> None:
        if not self._can_teach():
            return
        d = self.det
        if not self.roi:
            return error(self, "Draw the working zone on the image first.")
        sensor = self.mode_lbl.currentData() or d["sensor"]
        try:
            if sensor != d["sensor"]:
                self.ctx.detections.update_props(d["id"], d["name"], d["group_name"], sensor, d["enabled"],
                                                 d["params"])
            if d["det_type"] == "OBJECT":
                if "without" not in self.caps or "with" not in self.caps:
                    raise TeachError("Capture both the 'without' and 'with' snapshots first.")
                p = {**OBJECT_DEFAULTS, **d["params"]}
                model, arrays = teach_object(self.roi, self.caps["without"][0], self.caps["with"][0], sensor,
                                             self.tolerance.currentData(), self.caps["with"][1], p["min_diff"])
                self.ctx.store_teaching(d["id"], model, arrays)
            elif d["det_type"] in ("ACTIVITY", "BUTTON"):
                if "baseline" not in self.caps:
                    raise TeachError("Capture the empty zone first.")
                model, arrays = teach_zone_baseline(self.roi, self.caps["baseline"][0])
                self.ctx.store_teaching(d["id"], model, arrays)
            else:
                types = {c["name"]: c["type"] for c in self.classes}
                self.qc_samples = [(c, types.get(c, t), img) for c, t, img in self.qc_samples if c in types]
                params = {**d["params"], "classes": self.classes, "algorithm": self.algo.currentText()}
                self.ctx.detections.update_props(d["id"], d["name"], d["group_name"], sensor, d["enabled"], params)
                heights = None
                if sensor == "COLOR":
                    try:
                        heights = self._signals(5)[1] or None
                    except TeachError:
                        heights = None
                model, arrays = teach_quality(self.roi, self.qc_samples, self.algo.currentText(), heights)
                self.ctx.store_teaching(d["id"], model, arrays, self.qc_samples)
        except (TeachError, PermissionDenied) as exc:
            return error(self, str(exc))
        info(self, f"'{d['name']}' taught. Test it now on Fine tune: the live state must follow reality.")
        self.reload()

    def clear_teaching(self) -> None:
        if self._can_teach() and confirm(self, f"Remove all teaching data of '{self.det['name']}'?"):
            self.ctx.detections.clear_teaching(self.det["id"])
            self.ctx.audit("DETECTION_CLEARED", "detection", self.det["id"], {})
            self.reload()

    def delete(self) -> None:
        if not self._can_teach():
            return
        used = self.ctx.detections.usage(self.det["id"])
        msg = f"Delete detection '{self.det['name']}'?"
        if used:
            msg += "\n\nUsed by:\n" + "\n".join(f"{u['job_code']}: {u['step_name']}" for u in used[:10]) + \
                   "\nThese steps lose their detection and the job cannot be released until fixed."
        if confirm(self, msg):
            self.ctx.detections.delete(self.det["id"])
            self.ctx.audit("DETECTION_DELETED", "detection", self.det["id"], {"name": self.det["name"]})
            self.det = None
            self.reload()

    # ================================================================== projector tab
    def _bench_scene(self) -> None:
        items = []
        for d in self.rows:
            zone = d["model"].get("zone_mm")
            if zone:
                items.append({"id": d["id"], "poly": zone, "label": d["name"], "color": "#F2E600", "fill": 0.9,
                              "offset": tuple(d["params"].get("proj_offset_mm") or (0, 0))})
        self.bench.set_scene(items, selected=self.det["id"] if self.det else None, editable=self.editable())

    def _zone_moved(self, det_id: int, dx: float, dy: float) -> None:
        d = next((r for r in self.rows if r["id"] == det_id), None)
        if d is None or not self.editable():
            return
        params = {**d["params"], "proj_offset_mm": [dx, dy]}
        self.ctx.detections.update_props(det_id, d["name"], d["group_name"], d["sensor"], d["enabled"], params)
        d["params"] = params
        self.ctx.audit("PROJECTION_SHIFTED", "detection", det_id, {"offset_mm": [dx, dy]})
        self.ctx.load_engine(self.main.edit_job_id)

    def _reset_shift(self) -> None:
        if self.det is not None and self.editable():
            self._zone_moved(self.det["id"], 0.0, 0.0)
            self._bench_scene()

    # ================================================================== live
    def on_frame(self, frame) -> None:
        if not self.isVisible() or self.tabs.currentIndex() != 0:
            return
        self.view.set_image(frame_view(frame, self.stream.currentText()))
        vision = self.stream.currentText() == "VISION"
        ovs = []
        for d in self.rows:
            zone = d["model"].get("zone_px")
            if not zone or (d["sensor"] == "VISION") != vision:
                continue
            sel = self.det is not None and d["id"] == self.det["id"]
            if sel:
                continue
            ovs.append({"poly": zone, "color": "#E6D200", "fill": 0.25, "width": 1})
        if self.det is not None and self.det["model"].get("zone_px") and not self.view.edit_rect:
            ovs.append({"poly": self.det["model"]["zone_px"], "color": C["primary"], "label": self.det["name"]})
        self.view.set_overlays(ovs)

    def _live(self) -> None:
        if not self.isVisible():
            return
        states = self.main.last_states
        for det_id, it in self.items.items():
            st = states.get(det_id)
            if st is not None:
                g, col = STATE_GLYPH.get(st.state, ("○", C["faint"]))
                it.setText(1, g)
                it.setForeground(1, QColor(col))
                it.setToolTip(1, st.state.replace("_", " ").lower())
        if self.det:
            st = states.get(self.det["id"])
            if st:
                col = STATE_GLYPH.get(st.state, ("", C["muted"]))[1]
                self.ft_state.setText(st.state.replace("_", " ").title())
                self.ft_state.setStyleSheet(f"color: {col};")
                self.ft_bar.setValue(int(min(1.0, st.score) * 100))
                extra = f"score {st.score:.2f}"
                if st.det_type in ("ACTIVITY", "BUTTON"):
                    extra += f" · count {st.counter}"
                if st.qc_class:
                    extra += f" · {st.qc_class}"
                if st.detail.get("occlusion") is not None:
                    extra += f" · occlusion {st.detail['occlusion']:.0%}"
                self.ft_detail.setText(extra)
