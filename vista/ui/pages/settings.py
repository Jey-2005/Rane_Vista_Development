"""Settings (VS Code style): search, category list, one row per setting with description; changes apply
immediately and are audited."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from vista.core.security import PermissionDenied, Perm
from vista.ui.theme import C
from vista.ui.widgets.common import Page, SearchBox, chip, error, hrow, label

# category, key, title, description, kind, options
SETTINGS = [
    ("Station", "@name", "Station name", "Shown in the title bar, reports and evidence stamps.", "str", None),
    ("Station", "@plant", "Plant", "e.g. P4 Varanavasi.", "str", None),
    ("Station", "@line", "Line", "Production line or module of this station.", "str", None),
    ("Security", "idle_logout_min", "Idle sign-out (minutes)",
     "Engineering users are signed out after this idle time (never during an inspection).", "int", (1, 240)),
    ("Security", "max_login_attempts", "Failed sign-ins before lock", "Account is locked after this many failures.",
     "int", (3, 20)),
    ("Security", "lockout_minutes", "Lock duration (minutes)", "How long a locked account stays locked.", "int",
     (1, 1440)),
    ("Security", "require_independent_release", "Independent release",
     "A job must be released by someone other than its last editor (segregation of duties).", "bool", None),
    ("Projection", "projector_show_all", "Show all zones faintly", "Draw every taught zone in outline during "
     "inspection, not only the active step.", "bool", None),
    ("Projection", "color_todo", "Colour - next action", "Colour painted on the bench for the active step.", "color",
     None),
    ("Projection", "color_ok", "Colour - done", "Short flash when a step completes.", "color", None),
    ("Projection", "color_ng", "Colour - bad result", "Shown on a failed quality check.", "color", None),
    ("Bench areas", "instruction_area_mm", "Instruction text area",
     "Bench rectangle X, Y, width, height (mm) where the projector writes the instruction.", "rect", None),
    ("Bench areas", "result_area_mm", "Result banner area", "Bench rectangle X, Y, width, height (mm) for "
     "PASS / FAIL.", "rect", None),
    ("Calibration", "calib_margin", "Marker grid margin", "Distance of the outer markers from the image edge "
     "(fraction).", "float", (0.02, 0.4)),
    ("Calibration", "calib_marker_px", "Marker radius (px)", "Larger markers help in bright workshops.", "int",
     (6, 80)),
    ("Calibration", "calib_settle_ms", "Settle time (ms)", "Wait after each projected marker.", "int", (150, 3000)),
]


class SettingsPage(Page):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        self.search = SearchBox("Search settings")
        self.search.setMinimumHeight(30)
        self.search.textChanged.connect(self._filter)
        self.saved = chip("All changes saved", "ok")
        root.addLayout(hrow(self.search, self.saved))
        body = QHBoxLayout()
        root.addLayout(body, 1)
        self.cats = QListWidget()
        self.cats.setFixedWidth(200)
        self.cats.setStyleSheet("QListWidget { font-size: 10pt; } QListWidget::item { padding: 6px 8px; }")
        cats = []
        for c, *_ in SETTINGS:
            if c not in cats:
                cats.append(c)
        self.cats.addItem("All")
        for c in cats:
            self.cats.addItem(c)
        self.cats.currentRowChanged.connect(lambda _: self._filter(self.search.text()))
        body.addWidget(self.cats)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setStyleSheet("background: white;")
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(24, 16, 24, 16)
        self.lay.setSpacing(4)
        scroll.setWidget(inner)
        frame = QFrame()
        frame.setObjectName("Panel")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.addWidget(scroll)
        body.addWidget(frame, 1)
        self.rows: list[tuple[QWidget, str, str]] = []
        self.ctrls: dict[str, object] = {}
        self._pending: dict = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._flush)
        self._build()
        self.cats.setCurrentRow(0)

    def _build(self) -> None:
        last = None
        for cat, key, title, desc, kind, opts in SETTINGS:
            if cat != last:
                h = QLabel(cat)
                h.setObjectName("H1")
                h.setStyleSheet("font-size: 13pt; padding-top: 10px;")
                self.lay.addWidget(h)
                self.rows.append((h, cat, cat.lower()))
                last = cat
            row = QWidget()
            rl = QVBoxLayout(row)
            rl.setContentsMargins(8, 8, 8, 8)
            rl.setSpacing(3)
            t = QLabel(f"<span style='color:{C['muted']}'>{cat}: </span><b>{title}</b>")
            rl.addWidget(t)
            rl.addWidget(label(desc, "Muted", wrap=True))
            ctrl = self._control(key, kind, opts)
            rl.addLayout(hrow(ctrl, None))
            row.setStyleSheet("QWidget:hover { background: #F6F8FB; }")
            self.lay.addWidget(row)
            self.rows.append((row, cat, f"{title} {desc} {cat}".lower()))
        self.lay.addStretch(1)

    def _control(self, key, kind, opts):
        if kind == "bool":
            w = QCheckBox("Enabled")
            w.toggled.connect(lambda v, k=key: self._changed(k, v))
        elif kind == "int":
            w = QSpinBox()
            w.setRange(*opts)
            w.setFixedWidth(140)
            w.valueChanged.connect(lambda v, k=key: self._changed(k, v))
        elif kind == "float":
            w = QDoubleSpinBox()
            w.setRange(*opts)
            w.setSingleStep(0.02)
            w.setFixedWidth(140)
            w.valueChanged.connect(lambda v, k=key: self._changed(k, v))
        elif kind == "rect":
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            boxes = []
            for cap in ("X", "Y", "W", "H"):
                sb = QSpinBox()
                sb.setRange(-3000, 4000)
                sb.setSuffix(" mm")
                sb.setPrefix(f"{cap} ")
                sb.setFixedWidth(110)
                hl.addWidget(sb)
                boxes.append(sb)
                sb.valueChanged.connect(lambda _v, k=key, bx=boxes: self._changed(k, [b.value() for b in bx]))
            w.boxes = boxes
        elif kind == "color":
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            sw = QLabel()
            sw.setFixedSize(26, 26)
            ed = QLineEdit()
            ed.setFixedWidth(110)
            hl.addWidget(sw)
            hl.addWidget(ed)
            w.edit, w.swatch = ed, sw
            ed.editingFinished.connect(lambda k=key, e=ed, s=sw: self._color(k, e, s))
        else:
            w = QLineEdit()
            w.setFixedWidth(320)
            w.editingFinished.connect(lambda k=key, e=w: self._changed(k, e.text().strip()))
        self.ctrls[key] = (kind, w)
        return w

    def _color(self, key, edit, swatch) -> None:
        if not QColor.isValidColorName(edit.text().strip()):
            edit.setStyleSheet(f"border: 1px solid {C['ng']};")
            return
        edit.setStyleSheet("")
        swatch.setStyleSheet(f"background: {edit.text().strip()}; border-radius: 4px; border: 1px solid {C['line']};")
        self._changed(key, edit.text().strip())

    def on_show(self) -> None:
        s, st = self.ctx.settings, self.ctx.station
        vals = {**s, "@name": st["name"], "@plant": st["plant"] or "", "@line": st["line"] or ""}
        allowed = bool(self.ctx.session and self.ctx.session.can(Perm.MANAGE_SETTINGS))
        self._loading = True
        for key, (kind, w) in self.ctrls.items():
            v = vals.get(key)
            if kind == "bool":
                w.setChecked(bool(v))
            elif kind in ("int", "float"):
                w.setValue(v if v is not None else 0)
            elif kind == "rect":
                for b, x in zip(w.boxes, v or [0, 0, 0, 0]):
                    b.setValue(int(x))
            elif kind == "color":
                w.edit.setText(str(v or ""))
                w.swatch.setStyleSheet(f"background: {v}; border-radius: 4px; border: 1px solid {C['line']};")
            else:
                w.setText(str(v or ""))
            w.setEnabled(allowed)
        self._loading = False

    def _changed(self, key, value) -> None:
        if getattr(self, "_loading", False):
            return
        self._pending[key] = value
        self.saved.setText("Saving…")
        self._timer.start(600)

    def _flush(self) -> None:
        pending, self._pending = self._pending, {}
        try:
            self.ctx.require(Perm.MANAGE_SETTINGS)
            st = self.ctx.station
            station_keys = {k: pending.pop(k) for k in list(pending) if k.startswith("@")}
            if station_keys:
                name = station_keys.get("@name", st["name"]) or st["code"]
                plant = station_keys.get("@plant", st["plant"] or "")
                line = station_keys.get("@line", st["line"] or "")
                self.ctx.stations.update(st["id"], name, plant, line)
                self.ctx.station = {**st, "name": name, "plant": plant, "line": line}
                self.ctx.audit("STATION_UPDATED", "station", st["id"], station_keys)
            if pending:
                self.ctx.save_settings(pending)
        except PermissionDenied as exc:
            self.saved.setText("Not saved")
            return error(self, str(exc))
        self.saved.setText("All changes saved")
        self.main.reset_idle_timer()

    def _filter(self, text: str) -> None:
        t = text.lower().strip()
        cat = self.cats.currentItem().text() if self.cats.currentItem() else "All"
        for w, c, hay in self.rows:
            w.setVisible((cat == "All" or c == cat) and (not t or t in hay))
