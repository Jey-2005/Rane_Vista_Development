"""Calibration wizard: 1 Projector output · 2 Markers · 3 Review · 4 Verify (fully automatic marker detection)."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QProgressBar, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from vista.calibration.calibration import (CalibrationError, find_marker, marker_grid, solve_calibration,
                                           solve_vision_homography)
from vista.core.security import PermissionDenied, Perm
from vista.ui.theme import C
from vista.ui.widgets.common import ImageView, KpiTile, Page, button, error, hrow, label

STEPS = [("Projector output", "projector"), ("Markers", "calibration"), ("Review", "check_circle"),
         ("Verify", "grid")]


class Stepper(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Panel")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        self.dots, self.texts = [], []
        for i, (t, _ico) in enumerate(STEPS):
            d = QLabel(str(i + 1))
            d.setFixedSize(26, 26)
            d.setAlignment(Qt.AlignCenter)
            tl = QLabel(t)
            lay.addWidget(d)
            lay.addWidget(tl)
            self.dots.append(d)
            self.texts.append(tl)
            if i < len(STEPS) - 1:
                line = QFrame()
                line.setFixedHeight(2)
                line.setMinimumWidth(40)
                line.setStyleSheet(f"background: {C['line']};")
                lay.addWidget(line, 1)
        self.set(0)

    def set(self, idx: int) -> None:
        for i, (d, t) in enumerate(zip(self.dots, self.texts)):
            if i < idx:
                d.setText("✓")
                d.setStyleSheet(f"background: {C['ok']}; color: white; border-radius: 13px; font-weight: 600;")
                t.setStyleSheet(f"color: {C['text']};")
            elif i == idx:
                d.setText(str(i + 1))
                d.setStyleSheet(f"background: {C['primary']}; color: white; border-radius: 13px; font-weight: 600;")
                t.setStyleSheet(f"color: {C['primary']}; font-weight: 600;")
            else:
                d.setText(str(i + 1))
                d.setStyleSheet(f"background: #E3E7ED; color: {C['muted']}; border-radius: 13px;")
                t.setStyleSheet(f"color: {C['muted']};")


class CalibrationPage(Page):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        self.result = None
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        self.stepper = Stepper()
        root.addWidget(self.stepper)
        body = QHBoxLayout()
        root.addLayout(body, 1)
        left = QFrame()
        left.setObjectName("Panel")
        left.setFixedWidth(420)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 14, 16, 14)
        self.pages = QStackedWidget()
        ll.addWidget(self.pages, 1)
        self.b_back = button("Back", None, lambda: self.go(self.idx - 1), ico="arrow_left")
        self.b_next = button("Next", "primary", lambda: self.go(self.idx + 1))
        ll.addLayout(hrow(self.b_back, None, self.b_next))
        body.addWidget(left)
        right = QFrame()
        right.setObjectName("Panel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 10, 10, 10)
        rl.addLayout(hrow(label("Camera view", "H2"), None, label("Mouse wheel zooms, right button pans", "Muted")))
        self.view = ImageView()
        rl.addWidget(self.view, 1)
        self.summary = label("", "Muted", wrap=True)
        rl.addWidget(self.summary)
        body.addWidget(right, 1)
        self._build_pages()
        self.idx = 0
        self.go(0)

    # ================================================================== wizard pages
    def _page(self, title: str, text: str):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        t = QLabel(title)
        t.setObjectName("H1")
        lay.addWidget(t)
        lay.addWidget(label(text, "Muted", wrap=True))
        self.pages.addWidget(w)
        return lay

    def _build_pages(self) -> None:
        lay = self._page("Projector output", "Choose the display the Optoma projector is connected to and check "
                         "that the test image is upright on the bench. Windows scaling of that display must be 100 %.")
        f = QFormLayout()
        self.screen = QComboBox()
        self.rotation = QComboBox()
        self.rotation.addItems(["0", "90", "180", "270"])
        self.flip_h, self.flip_v = QCheckBox("Mirror horizontally"), QCheckBox("Mirror vertically")
        f.addRow("Display", self.screen)
        f.addRow("Rotation", self.rotation)
        f.addRow("", self.flip_h)
        f.addRow("", self.flip_v)
        lay.addLayout(f)
        lay.addLayout(hrow(button("Apply output", "primary", self.apply_output, ico="projector"),
                           button("Test pattern", None, lambda: self.main.projector.set_mode("VERIFY"), ico="grid"),
                           None))
        self.out_status = label("", wrap=True)
        lay.addWidget(self.out_status)
        lay.addStretch(1)

        lay = self._page("Markers", "Clear the bench area, keep hands out and dim strong spot lights. Nine markers "
                         "are projected one after another and located automatically in the camera image.")
        f = QFormLayout()
        self.margin = QDoubleSpinBox()
        self.margin.setRange(0.02, 0.4)
        self.margin.setSingleStep(0.02)
        self.marker_px = QSpinBox()
        self.marker_px.setRange(6, 80)
        self.marker_px.setSuffix(" px")
        self.settle = QSpinBox()
        self.settle.setRange(150, 3000)
        self.settle.setSuffix(" ms")
        self.origin_idx, self.xaxis_idx = QComboBox(), QComboBox()
        names = [f"Marker {i + 1} - {['top', 'middle', 'bottom'][i // 3]} {['left', 'centre', 'right'][i % 3]}"
                 for i in range(9)]
        self.origin_idx.addItems(names)
        self.xaxis_idx.addItems(names)
        f.addRow("Grid margin", self.margin)
        f.addRow("Marker radius", self.marker_px)
        f.addRow("Settle time", self.settle)
        f.addRow("Origin (0, 0)", self.origin_idx)
        f.addRow("X-axis direction", self.xaxis_idx)
        lay.addLayout(f)
        self.b_run = button("Run calibration", "primary", self.run, ico="wizard")
        lay.addWidget(self.b_run)
        self.prog = QProgressBar()
        self.prog.setRange(0, 9)
        self.prog.setValue(0)
        lay.addWidget(self.prog)
        self.status = label("", wrap=True)
        lay.addWidget(self.status)
        lay.addStretch(1)

        lay = self._page("Review", "Accept when the reprojection error is below about 2 px and all markers were found.")
        g = QHBoxLayout()
        self.k_found, self.k_rms = KpiTile("Markers found", "-", ico="calibration"), KpiTile("Error (px)", "-", ico="fit")
        g.addWidget(self.k_found)
        g.addWidget(self.k_rms)
        lay.addLayout(g)
        g2 = QHBoxLayout()
        self.k_mm, self.k_plane = KpiTile("mm per pixel", "-", ico="grid"), KpiTile("Bench plane fit", "-", ico="cube")
        g2.addWidget(self.k_mm)
        g2.addWidget(self.k_plane)
        lay.addLayout(g2)
        self.review = label("", wrap=True)
        lay.addWidget(self.review)
        self.b_save = button("Save calibration", "primary", self.save, ico="save")
        self.b_save.setEnabled(False)
        lay.addWidget(self.b_save)
        lay.addStretch(1)

        lay = self._page("Verify", "A 100 mm grid with the origin (red X, green Y) is projected. Measure two grid "
                         "lines with a ruler to confirm the scale. Detections taught before stay valid.")
        lay.addLayout(hrow(button("Project test grid", "primary", lambda: self.main.projector.set_mode("VERIFY"),
                                  ico="grid"),
                           button("Back to guidance", None, lambda: self.main.projector.set_mode("RUN")), None))
        self.b_vision = button("Calibrate vision camera", None, self.run_vision, ico="eye")
        lay.addWidget(self.b_vision)
        self.verify_status = label("", wrap=True)
        lay.addWidget(self.verify_status)
        lay.addStretch(1)

    def go(self, i: int) -> None:
        self.idx = max(0, min(len(STEPS) - 1, i))
        self.pages.setCurrentIndex(self.idx)
        self.stepper.set(self.idx)
        self.b_back.setEnabled(self.idx > 0)
        self.b_next.setText("Finish" if self.idx == len(STEPS) - 1 else "Next")
        self.b_next.setEnabled(self.idx < len(STEPS) - 1)

    def on_show(self) -> None:
        s = self.ctx.settings
        self.screen.clear()
        for scr in QGuiApplication.screens():
            g = scr.geometry()
            self.screen.addItem(f"{scr.name()}  ({g.width()}x{g.height()} at {g.x()},{g.y()})", scr.name())
        self.screen.setCurrentIndex(max(0, self.screen.findData(s.get("projector_screen"))))
        self.rotation.setCurrentText(str(s.get("projector_rotation", 0)))
        self.flip_h.setChecked(bool(s.get("projector_flip_h")))
        self.flip_v.setChecked(bool(s.get("projector_flip_v")))
        self.margin.setValue(float(s.get("calib_margin", 0.12)))
        self.marker_px.setValue(int(s.get("calib_marker_px", 22)))
        self.settle.setValue(int(s.get("calib_settle_ms", 600)))
        self.origin_idx.setCurrentIndex(6)
        self.xaxis_idx.setCurrentIndex(8)
        self.b_vision.setVisible(self.ctx.cfg.vision_camera_index >= 0)
        cal = self.ctx.calibration
        self.summary.setText(f"Active calibration from {datetime.fromtimestamp(cal.created):%d-%m-%Y %H:%M}: "
                             f"{cal.rms_px:.2f} px error, {cal.mm_per_px():.2f} mm per camera pixel."
                             if cal else "This workstation is not calibrated yet.")

    def on_frame(self, frame) -> None:
        if self.isVisible() and self.result is None and frame.color is not None:
            self.view.set_image(frame.color)

    def _guard(self, perm: str) -> bool:
        try:
            self.ctx.require(perm)
            return True
        except PermissionDenied as exc:
            error(self, str(exc))
            return False

    def apply_output(self) -> None:
        if not self._guard(Perm.MANAGE_HARDWARE):
            return
        self.ctx.save_settings({"projector_screen": self.screen.currentData(),
                                "projector_rotation": int(self.rotation.currentText()),
                                "projector_flip_h": self.flip_h.isChecked(), "projector_flip_v": self.flip_v.isChecked()})
        self.out_status.setText(f"Projector window on display {self.main.projector.place()}.")
        self.main.projector.set_mode("VERIFY")

    # ================================================================== marker sequence
    def _present(self, pts) -> None:
        r = self.marker_px.value()
        self.main.projector.show_markers(pts, r)
        if hasattr(self.ctx.camera, "set_markers"):
            self.ctx.camera.set_markers(pts, r)

    def _image(self, vision: bool):
        f = self.ctx.latest_frame()
        return (None, None) if f is None else ((f.vision if vision else f.color), f)

    def _sequence(self, vision: bool, on_done) -> None:
        if self.main.executor.mode == "RUNNING":
            return error(self, "Stop the running inspection before calibrating.")
        if self.ctx.latest_frame() is None:
            return error(self, "No camera image - check the 3D sensor on the Connectivity page.")
        g = self.main.projector.geometry()
        proj = self.ctx.calibration.proj_size if (vision and self.ctx.calibration) else (g.width(), g.height())
        if proj[0] < 200:
            proj = (1920, 1080)
        self.proj_size = proj
        self.grid = marker_grid(proj[0], proj[1], self.margin.value())
        self.found = []
        self.b_run.setEnabled(False)
        self.prog.setValue(0)
        self._present([])
        settle = self.settle.value()

        def ref_step():
            img, _ = self._image(vision)
            if img is None:
                return self._abort("No image from the camera.")
            self.ref = img.copy()
            marker_step(0)

        def marker_step(i):
            if i >= len(self.grid):
                self._present([])
                self.main.projector.set_mode("RUN")
                if hasattr(self.ctx.camera, "set_markers"):
                    self.ctx.camera.set_markers([])
                self.b_run.setEnabled(True)
                return on_done()
            self.status.setText(f"Marker {i + 1} of {len(self.grid)}…")
            self._present([self.grid[i]])
            QTimer.singleShot(settle, lambda: grab(i))

        def grab(i):
            img, _ = self._image(vision)
            self.found.append(find_marker(self.ref, img) if img is not None else None)
            self.prog.setValue(i + 1)
            marker_step(i + 1)

        QTimer.singleShot(settle, ref_step)

    def _abort(self, msg: str) -> None:
        self._present([])
        self.main.projector.set_mode("RUN")
        self.b_run.setEnabled(True)
        self.status.setText(f"<span style='color:{C['ng']}'>{msg}</span>")

    def run(self) -> None:
        if self._guard(Perm.CALIBRATE):
            self.result = None
            self.b_save.setEnabled(False)
            self._sequence(False, self._solve)

    def _solve(self) -> None:
        _, f = self._image(False)
        oi, xi = self.origin_idx.currentIndex(), self.xaxis_idx.currentIndex()
        missing = [i + 1 for i, p in enumerate(self.found) if p is None]
        if self.found[oi] is None or self.found[xi] is None:
            return self._abort(f"Origin or X-axis marker not found (missing: {missing}). Reduce ambient light, "
                               "increase the marker radius or the settle time.")
        idx = [i for i, p in enumerate(self.found) if p is not None]
        pairs = [(c, g) for c, g in zip(self.found, self.grid) if c is not None]
        try:
            cal = solve_calibration(f.intrinsics, f.depth_mm, [p for p, _ in pairs], [g for _, g in pairs],
                                    self.proj_size, idx.index(oi), idx.index(xi))
        except CalibrationError as exc:
            return self._abort(str(exc))
        self.result = cal
        self.status.setText(f"<span style='color:{C['ok']}'>Found {len(pairs)} of 9 markers.</span>")
        self.k_found.set(f"{len(pairs)}/9")
        self.k_rms.set(f"{cal.rms_px:.2f}")
        self.k_mm.set(f"{cal.mm_per_px():.2f}")
        self.k_plane.set(f"{getattr(cal, 'plane_inlier_ratio', 0):.0%}")
        ok = cal.rms_px < 3.0
        self.review.setText(f"<span style='color:{C['ok'] if ok else C['warn']}'>"
                            + ("Good calibration - save it." if ok else "Error is high - check that all markers fall "
                                                                         "on the flat bench, then run again.")
                            + "</span>")
        self.b_save.setEnabled(True)
        self.view.set_image(f.color.copy())
        ovs = []
        for i, p in enumerate(self.found):
            if p is not None:
                u, v = p
                col = C["ng"] if i == oi else (C["ok"] if i == xi else C["primary"])
                ovs.append({"poly": [[u - 9, v - 9], [u + 9, v - 9], [u + 9, v + 9], [u - 9, v + 9]], "color": col,
                            "label": str(i + 1)})
        self.view.set_overlays(ovs)
        self.go(2)

    def save(self) -> None:
        if self.result is None or not self._guard(Perm.CALIBRATE):
            return
        self.ctx.calibrations.save(self.result.to_dict(), self.result.rms_px, self.ctx.session.user_id)
        self.ctx.calibration = self.result
        self.ctx.audit("CALIBRATION_SAVED", "calibration", "", {"rms_px": self.result.rms_px})
        self.b_save.setEnabled(False)
        self.result = None
        self.view.set_overlays([])
        self.main.add_message("Calibration saved", "ok", "Calibration")
        self.main.projector.set_mode("VERIFY")
        self.on_show()
        self.go(3)

    def run_vision(self) -> None:
        if not self._guard(Perm.CALIBRATE):
            return
        if self.ctx.calibration is None:
            return error(self, "Calibrate the 3D sensor and projector first.")
        self._sequence(True, self._solve_vision)

    def _solve_vision(self) -> None:
        pairs = [(c, g) for c, g in zip(self.found, self.grid) if c is not None]
        try:
            H = solve_vision_homography(self.ctx.calibration, [p for p, _ in pairs], [g for _, g in pairs])
        except CalibrationError as exc:
            return self._abort(str(exc))
        cal = self.ctx.calibration
        cal.H_vision2bench = H
        self.ctx.calibrations.save(cal.to_dict(), cal.rms_px, self.ctx.session.user_id)
        self.ctx.audit("VISION_CALIBRATION_SAVED", "calibration", "", {"markers": len(pairs)})
        self.verify_status.setText(f"Vision camera calibrated with {len(pairs)} markers.")
