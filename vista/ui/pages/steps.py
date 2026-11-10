"""Steps page (Arkite layout): step tree | Projector / Screen preview | Properties."""
from __future__ import annotations

import re

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QPlainTextEdit, QRadioButton, QSplitter, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from vista.core.security import PermissionDenied, Perm
from vista.engine.steps import CONTAINERS, STEP_SPECS, default_name, default_params, operator_text
from vista.ui.icons import icon
from vista.ui.theme import C, font
from vista.ui.widgets.bench import BenchCanvas
from vista.ui.widgets.common import (Page, ParamForm, PropertiesPanel, SearchBox, button, confirm, error, hrow, label,
                                     tool)

STEP_ICON = {"NUMBERED": "steps", "COMPOSITE": "composite", "PLACE": "place", "TAKE": "take", "ACTIVITY": "hand",
             "PRESS": "button", "QUALITY_CHECK": "eye", "WAIT_BARCODE": "barcode", "SNAPSHOT": "camera",
             "SET_VARIABLE": "variable", "DELAY": "delay", "OPERATOR_DIALOG": "dialog",
             "WORK_INSTRUCTION": "instruction"}
CATEGORIES = [("General", ["NUMBERED", "COMPOSITE", "WORK_INSTRUCTION", "OPERATOR_DIALOG", "DELAY"]),
              ("Detections", ["PLACE", "TAKE", "ACTIVITY", "PRESS", "QUALITY_CHECK"]),
              ("Data", ["WAIT_BARCODE", "SNAPSHOT", "SET_VARIABLE"])]
TRIGGER_TYPES = {"PLACE", "TAKE", "ACTIVITY", "PRESS", "QUALITY_CHECK", "WAIT_BARCODE", "DELAY", "OPERATOR_DIALOG",
                 "WORK_INSTRUCTION"}


class StepTree(QTreeWidget):
    dropped = Signal()

    def __init__(self):
        super().__init__()
        self.setHeaderLabels(["Step Name", "", ""])
        self.setColumnWidth(0, 380)
        self.setColumnWidth(1, 120)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setIconSize(QSize(18, 18))
        self.setIndentation(18)
        self.setUniformRowHeights(True)
        self.header().setStretchLastSection(False)
        self.setColumnWidth(2, 34)

    def dropEvent(self, e):  # noqa: N802
        super().dropEvent(e)
        self.dropped.emit()


class StepsPage(Page):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        self.job: dict | None = None
        self.steps: dict[int, dict] = {}
        self.items: dict[int, QTreeWidgetItem] = {}
        self.dets: list[dict] = []
        self.variants: list[dict] = []
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
        ll.setSpacing(6)
        self.b_new = button("New Step", "primary", ico="plus")
        menu = QMenu(self)
        for cat, types in CATEGORIES:
            menu.addSection(cat)
            for t in types:
                menu.addAction(icon(STEP_ICON[t], C["ink"], 16), STEP_SPECS[t]["label"],
                               lambda k=t: self.add_step(k))
        self.b_new.setMenu(menu)
        self.add_menu = menu
        self.t_out = tool("outdent", "Move out of the parent step", self.outdent)
        self.t_in = tool("indent", "Nest into the step above (numbered / composite)", self.indent)
        self.t_up = tool("arrow_up", "Move up", lambda: self.move(-1))
        self.t_down = tool("arrow_down", "Move down", lambda: self.move(1))
        self.t_del = tool("trash", "Delete step", self.delete_step, color=C["ng"])
        self.search = SearchBox("Search for steps")
        self.search.setFixedWidth(200)
        self.search.textChanged.connect(self.filter)
        ll.addLayout(hrow(self.b_new, self.t_out, self.t_in, self.t_up, self.t_down, self.t_del, None, self.search,
                          tool("expand", "Expand all", lambda: self.tree.expandAll()),
                          tool("collapse", "Collapse all", lambda: self.tree.collapseAll())))
        cols = QHBoxLayout()
        cols.addWidget(label("Columns:", "Muted"))
        self.col_group = QButtonGroup(self)
        for i, t in enumerate(("Variants", "Instructions", "None")):
            rb = QRadioButton(t)
            self.col_group.addButton(rb, i)
            cols.addWidget(rb)
        self.col_group.button(0).setChecked(True)
        self.col_group.idToggled.connect(lambda *_: self.load_steps(self._sel_id()))
        cols.addStretch(1)
        self.job_lbl = label("", "Muted")
        cols.addWidget(self.job_lbl)
        ll.addLayout(cols)
        self.tree = StepTree()
        self.tree.currentItemChanged.connect(self._step_changed)
        self.tree.dropped.connect(self._persist_order)
        ll.addWidget(self.tree, 1)
        legend = label("○ waits for the operator or a detection   ▽ completes instantly   ⚠ needs a detection", "Faint")
        ll.addWidget(legend)
        split.addWidget(left)

        # ---------------------------------------------------------------- preview
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.bench = BenchCanvas(ctx)
        pw = QWidget()
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(6, 6, 6, 6)
        self.t_bench_reset = tool("fit", "Reset view", self.bench.reset_view)
        pl.addLayout(hrow(label("Bench layout as projected - selected step highlighted in blue", "Muted"), None,
                          self.t_bench_reset))
        pl.addWidget(self.bench, 1)
        self.tabs.addTab(pw, "Projector")
        sw = QWidget()
        sl = QVBoxLayout(sw)
        sl.setContentsMargins(16, 16, 16, 16)
        self.screen_step = label("", "Muted")
        self.screen_text = QLabel("Select a step")
        self.screen_text.setWordWrap(True)
        self.screen_text.setFont(font(20, display=True))
        self.screen_text.setMinimumHeight(110)
        self.screen_text.setStyleSheet(f"background: {C['accent']}; color: #1B2129; border-radius: 6px; "
                                       f"padding: 16px 20px;")
        sl.addWidget(label("Operator screen preview", "H3"))
        sl.addWidget(self.screen_step)
        sl.addWidget(self.screen_text)
        self.screen_help = label("", "Muted", wrap=True)
        sl.addWidget(self.screen_help)
        sl.addStretch(1)
        self.tabs.addTab(sw, "Screen")
        ml.addWidget(self.tabs)
        split.addWidget(mid)
        split.setSizes([620, 520])

        self.props = PropertiesPanel()
        root.addWidget(self.props)
        main.job_context_changed.connect(lambda _: self.on_show() if self.isVisible() else None)

    # ================================================================== loading
    def can_edit(self) -> bool:
        return bool(self.ctx.session and self.ctx.session.can(Perm.EDIT_JOBS))

    def on_show(self) -> None:
        jid = self.main.edit_job_id
        self.job = self.ctx.jobs.get(jid) if jid else None
        if self.job is None:
            self.tree.clear()
            self.job_lbl.setText("No job selected - choose one on the Jobs page or with Ctrl+P")
            self._properties(None)
            self.bench.set_scene([])
            return
        self.job_lbl.setText(f"{self.job['code']} · rev {self.job['revision']} · {self.job['status'].lower()}")
        self.variants = self.ctx.jobs.variants(jid)
        self.dets = self.ctx.detections.list_for(jid)
        for w in (self.b_new, self.t_out, self.t_in, self.t_up, self.t_down, self.t_del):
            w.setEnabled(self.can_edit())
        self.load_steps(self._sel_id())

    def _sel_id(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.UserRole) if it else None

    def load_steps(self, select_id=None) -> None:
        if self.job is None:
            return
        self.tree.blockSignals(True)
        self.tree.clear()
        rows = self.ctx.jobs.steps(self.job["id"])
        self.steps = {r["id"]: r for r in rows}
        self.items = {}
        mode = self.col_group.checkedId()
        self.tree.setHeaderLabels(["Step Name", ["Variants", "Instruction", ""][mode], ""])
        children: dict = {}
        for r in rows:
            children.setdefault(r["parent_id"], []).append(r)

        def add(parent_id, parent_item, prefix):
            n = 0
            for r in sorted(children.get(parent_id, []), key=lambda x: (x["sort_order"], x["id"])):
                t = r["step_type"]
                number = ""
                if t == "NUMBERED":
                    n += 1
                    number = f"{prefix}{n}."
                it = QTreeWidgetItem([f"{number} {r['name']}".strip(), "", ""])
                it.setIcon(0, icon(STEP_ICON.get(t, "info"), C["ink"] if r["enabled"] else C["faint"], 18))
                it.setData(0, Qt.UserRole, r["id"])
                flags = it.flags() | Qt.ItemIsDragEnabled
                it.setFlags(flags | Qt.ItemIsDropEnabled if t in CONTAINERS else flags & ~Qt.ItemIsDropEnabled)
                if t == "NUMBERED":
                    it.setFont(0, font(9, True))
                if not r["enabled"]:
                    it.setForeground(0, QColor(C["faint"]))
                if mode == 0 and r["variant_codes"]:
                    it.setText(1, ", ".join(r["variant_codes"]))
                elif mode == 1:
                    it.setText(1, (r["instruction"] or "")[:40])
                if STEP_SPECS.get(t, {}).get("detection") and not r.get("detection_id"):
                    it.setText(2, "⚠")
                    it.setForeground(2, QColor(C["ng"]))
                    it.setToolTip(2, "No detection linked")
                elif t not in CONTAINERS:
                    it.setText(2, "○" if t in TRIGGER_TYPES else "▽")
                    it.setForeground(2, QColor(C["muted"]))
                (parent_item.addChild(it) if parent_item else self.tree.addTopLevelItem(it))
                self.items[r["id"]] = it
                add(r["id"], it, number if number else prefix)
        add(None, None, "")
        self.tree.expandAll()
        self.tree.blockSignals(False)
        if select_id in self.items:
            self.tree.setCurrentItem(self.items[select_id])
        else:
            self._step_changed(None, None)
        self.filter(self.search.text())

    def filter(self, text: str) -> None:
        t = text.lower().strip()
        for sid, it in self.items.items():
            it.setHidden(bool(t) and t not in self.steps[sid]["name"].lower()
                         and not any(t in self.steps[c]["name"].lower() for c in self._descendants(sid)))

    def _descendants(self, sid):
        out = []
        for c in [k for k, v in self.steps.items() if v["parent_id"] == sid]:
            out += [c] + self._descendants(c)
        return out

    def select_step(self, step_id: int) -> None:
        if step_id in self.items:
            self.tree.setCurrentItem(self.items[step_id])

    # ================================================================== preview + properties
    def _step_changed(self, cur, _prev) -> None:
        s = self.steps.get(cur.data(0, Qt.UserRole)) if cur else None
        self._properties(s)
        self._preview(s)

    def _preview(self, s) -> None:
        items, sel = [], None
        for d in self.dets:
            zone = d["model"].get("zone_mm")
            if not zone:
                continue
            off = (d["params"].get("proj_offset_mm") or [0, 0])
            items.append({"id": d["id"], "poly": zone, "label": d["name"], "offset": tuple(off),
                          "color": "#F2E600", "fill": 0.9})
        if s and s.get("detection_id"):
            sel = s["detection_id"]
        st = self.ctx.settings
        ia, ra = st["instruction_area_mm"], st["result_area_mm"]
        self.bench.set_scene(items, [{"rect": ia, "label": "Instruction text"}, {"rect": ra, "label": "Result"}],
                             selected=sel)
        if s:
            self.screen_step.setText(f"{STEP_SPECS[s['step_type']]['label']} · {s['name']}")
            self.screen_text.setText(operator_text(s))
            self.screen_help.setText(STEP_SPECS[s["step_type"]]["help"])
        else:
            self.screen_text.setText("Select a step")
            self.screen_step.setText("")

    def _properties(self, s) -> None:
        p = self.props
        p.clear()
        if s is None:
            p.heading("Step", "Select a step, or add one with New Step.")
            p.end()
            return
        spec = STEP_SPECS[s["step_type"]]
        edit = self.can_edit()
        p.heading(spec["label"], f"ID {s['id']}")
        self.s_name = p.field("Name", QLineEdit(s["name"]))
        self.s_det = QComboBox()
        self.s_det.addItem("-", None)
        if spec["detection"]:
            for d in self.dets:
                if d["det_type"] in spec["detection"]:
                    self.s_det.addItem(f"{d['name']}  ({'station' if d['job_id'] is None else 'job'})", d["id"])
            self.s_det.setCurrentIndex(max(0, self.s_det.findData(s["detection_id"])))
            p.field("Detection", self.s_det)
        self.var_checks = []
        if self.variants:
            vw = QWidget()
            vl = QHBoxLayout(vw)
            vl.setContentsMargins(0, 0, 0, 0)
            for v in self.variants:
                cb = QCheckBox(v["code"])
                cb.setChecked(not s["variant_codes"] or v["code"] in s["variant_codes"])
                cb.setEnabled(edit)
                vl.addWidget(cb)
                self.var_checks.append(cb)
            vl.addStretch(1)
            p.field("Run for variants", vw)
        self.s_enabled = QCheckBox("Enabled")
        self.s_enabled.setChecked(s["enabled"])
        p.body.addWidget(self.s_enabled)
        p.heading("Step instructions")
        self.s_instr = QPlainTextEdit(s["instruction"] or "")
        self.s_instr.setPlaceholderText(operator_text({**s, "instruction": None}))
        self.s_instr.setFixedHeight(60)
        p.field("Text instruction (operator screen and bench)", self.s_instr)
        if spec["params"]:
            p.heading("Settings")
            self.params = ParamForm(spec["params"], s["params"], stacked=True)
            p.body.addWidget(self.params)
        else:
            self.params = None
        hint = QFrame()
        hint.setObjectName("Hint")
        hl = QHBoxLayout(hint)
        hl.setContentsMargins(8, 6, 8, 6)
        hl.addWidget(label(spec["help"], "Muted", wrap=True))
        p.body.addWidget(hint)
        for w in (self.s_name, self.s_det, self.s_enabled, self.s_instr):
            w.setEnabled(edit)
        if self.params:
            self.params.set_enabled(edit)
        p.end()
        b = button("Save step", "primary", self.save_step, ico="save")
        b.setEnabled(edit)
        p.footer.addStretch(1)
        p.footer.addWidget(b)

    # ================================================================== actions
    def _guard(self):
        try:
            return self.ctx.require(Perm.EDIT_JOBS)
        except PermissionDenied as exc:
            error(self, str(exc))
            return None

    def _touch(self) -> None:
        self.ctx.jobs.mark_draft(self.job["id"], self.ctx.session.user_id)
        self.job = self.ctx.jobs.get(self.job["id"])
        self.job_lbl.setText(f"{self.job['code']} · rev {self.job['revision']} · {self.job['status'].lower()}")
        self.main._refresh_command()

    def add_step_menu(self) -> None:
        self.add_menu.exec(self.b_new.mapToGlobal(self.b_new.rect().bottomLeft()))

    def add_step(self, step_type: str) -> None:
        if self.job is None:
            return error(self, "Select a job first.")
        s = self._guard()
        if not s:
            return
        cur = self._sel_id()
        parent_id = None
        if cur is not None:
            st = self.steps[cur]
            parent_id = cur if st["step_type"] in CONTAINERS else st["parent_id"]
        det_id, det_name = None, None
        kinds = STEP_SPECS[step_type]["detection"]
        if kinds:
            opts = [d for d in self.dets if d["det_type"] in kinds]
            if opts:
                from PySide6.QtWidgets import QInputDialog
                names = [d["name"] for d in opts]
                name, ok = QInputDialog.getItem(self, "Detection", "Detection for this step:", names, 0, False)
                if not ok:
                    return
                det_id, det_name = opts[names.index(name)]["id"], name
        siblings = [x for x in self.steps.values() if x["parent_id"] == parent_id]
        order = max([x["sort_order"] for x in siblings], default=0) + 1
        sid = self.ctx.jobs.create_step(self.job["id"], parent_id, step_type, default_name(step_type, det_name), order,
                                        default_params(step_type), det_id)
        self.ctx.audit("STEP_ADDED", "step", sid, {"job": self.job["code"], "type": step_type})
        self._touch()
        self.load_steps(sid)

    def delete_step(self) -> None:
        cur = self.tree.currentItem()
        if cur is None or not self._guard():
            return
        sid = cur.data(0, Qt.UserRole)
        msg = f"Delete step '{self.steps[sid]['name']}'"
        if cur.childCount():
            msg += f" and its {len(self._descendants(sid))} child step(s)"
        if confirm(self, msg + "?"):
            self.ctx.jobs.delete_step(sid)
            self.ctx.audit("STEP_DELETED", "step", sid, {"job": self.job["code"], "name": self.steps[sid]["name"]})
            self._touch()
            self.load_steps()

    def _container(self, item):
        return item.parent() if item.parent() else self.tree.invisibleRootItem()

    def move(self, delta: int) -> None:
        cur = self.tree.currentItem()
        if cur is None or not self._guard():
            return
        cont = self._container(cur)
        i = cont.indexOfChild(cur)
        j = i + delta
        if 0 <= j < cont.childCount():
            self.tree.blockSignals(True)
            cont.takeChild(i)
            cont.insertChild(j, cur)
            self.tree.blockSignals(False)
            self.tree.setCurrentItem(cur)
            self._persist_order()

    def indent(self) -> None:
        cur = self.tree.currentItem()
        if cur is None or not self._guard():
            return
        cont = self._container(cur)
        i = cont.indexOfChild(cur)
        if i == 0:
            return
        target = cont.child(i - 1)
        if self.steps[target.data(0, Qt.UserRole)]["step_type"] not in CONTAINERS:
            return error(self, "The step above must be a numbered or composite step.")
        self.tree.blockSignals(True)
        cont.takeChild(i)
        target.addChild(cur)
        self.tree.blockSignals(False)
        self.tree.setCurrentItem(cur)
        self._persist_order()

    def outdent(self) -> None:
        cur = self.tree.currentItem()
        if cur is None or cur.parent() is None or not self._guard():
            return
        parent = cur.parent()
        grand = self._container(parent)
        self.tree.blockSignals(True)
        parent.removeChild(cur)
        grand.insertChild(grand.indexOfChild(parent) + 1, cur)
        self.tree.blockSignals(False)
        self.tree.setCurrentItem(cur)
        self._persist_order()

    def _persist_order(self) -> None:
        ordering = []

        def walk(item, parent_id):
            for k in range(item.childCount()):
                ch = item.child(k)
                sid = ch.data(0, Qt.UserRole)
                ordering.append((sid, parent_id, k + 1))
                walk(ch, sid)
        walk(self.tree.invisibleRootItem(), None)
        for sid, pid, _ in ordering:
            if pid is not None and self.steps[pid]["step_type"] not in CONTAINERS:
                error(self, "Steps can only be nested inside numbered or composite steps.")
                self.load_steps(sid)
                return
        cur = self._sel_id()
        self.ctx.jobs.reorder(ordering)
        self._touch()
        self.load_steps(cur)

    def save_step(self) -> None:
        cur = self._sel_id()
        if cur is None or not self._guard():
            return
        s = self.steps[cur]
        name = self.s_name.text().strip()
        if not name:
            return error(self, "Step name is required.")
        checked = [cb.text() for cb in self.var_checks if cb.isChecked()]
        if self.variants and not checked:
            return error(self, "Select at least one variant.")
        variants = [] if len(checked) == len(self.variants) else checked
        params = self.params.values() if self.params else {}
        if s["step_type"] == "WAIT_BARCODE" and params.get("regex"):
            try:
                re.compile(params["regex"])
            except re.error as exc:
                return error(self, f"Barcode pattern is not a valid regular expression: {exc}")
        self.ctx.jobs.update_step(cur, name, self.s_det.currentData(), variants, self.s_enabled.isChecked(),
                                  self.s_instr.toPlainText().strip() or None, params)
        self.ctx.audit("STEP_UPDATED", "step", cur, {"job": self.job["code"], "name": name, "params": params})
        self._touch()
        self.load_steps(cur)
