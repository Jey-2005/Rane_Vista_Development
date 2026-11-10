"""Hardware diagnostics: live streams of every sensor, health figures, projector tests, scanner test, simulator."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QScrollArea,
                               QVBoxLayout, QWidget)

from vista.ui.icons import icon
from vista.ui.theme import C
from vista.ui.widgets.common import STREAM_LABELS, ImageView, KpiTile, Page, button, frame_view, hrow, label


class HardwarePage(Page):
    def __init__(self, ctx, main):
        super().__init__()
        self.ctx, self.main = ctx, main
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        centre = QVBoxLayout()
        tiles = QHBoxLayout()
        self.k_fps = KpiTile("3D sensor frame rate", "-", C["primary"], "camera")
        self.k_valid = KpiTile("Valid depth pixels", "-", C["ok"], "grid")
        self.k_noise = KpiTile("Bench noise (mm, centre)", "-", C["warn"], "calibration")
        self.k_vision = KpiTile("Vision camera", "-", C["ink"], "eye")
        for t in (self.k_fps, self.k_valid, self.k_noise, self.k_vision):
            tiles.addWidget(t)
        centre.addLayout(tiles)
        grid = QGridLayout()
        grid.setSpacing(10)
        self.views = []
        for i, stream in enumerate(("COLOR", "IR", "HEIGHT", "DEPTH")):
            f = QFrame()
            f.setObjectName("Panel")
            fl = QVBoxLayout(f)
            fl.setContentsMargins(8, 6, 8, 8)
            combo = QComboBox()
            for k, v in STREAM_LABELS.items():
                combo.addItem(v, k)
            combo.setCurrentIndex(combo.findData(stream))
            fl.addLayout(hrow(label(f"View {i + 1}", "H3"), None, combo))
            v = ImageView()
            v.setMinimumSize(300, 190)
            fl.addWidget(v, 1)
            grid.addWidget(f, i // 2, i % 2)
            self.views.append((combo, v))
        centre.addLayout(grid, 1)
        root.addLayout(centre, 1)

        side = QScrollArea()
        side.setWidgetResizable(True)
        side.setFixedWidth(330)
        sw = QWidget()
        sw.setObjectName("Page")
        sw.setAttribute(Qt.WA_StyledBackground, True)
        sl = QVBoxLayout(sw)
        sl.setContentsMargins(0, 0, 4, 0)
        sl.setSpacing(10)
        side.setWidget(sw)
        root.addWidget(side)
        p, pl = self._box("Projector test", "projector")
        pj = main.projector
        pl.addLayout(hrow(button("Grid", None, lambda: pj.set_mode("VERIFY"), ico="grid"),
                          button("All zones", None, lambda: pj.set_mode("TEST"), ico="detection")))
        pl.addLayout(hrow(button("Blank", None, lambda: pj.set_mode("BLANK"), ico="moon"),
                          button("Guidance", "primary", lambda: pj.set_mode("RUN"), ico="play")))
        sl.addWidget(p)
        p, pl = self._box("Scanner test", "barcode")
        pl.addWidget(label("Scan any code - it appears here.", "Muted"))
        self.scans = QListWidget()
        self.scans.setFixedHeight(120)
        pl.addWidget(self.scans)
        main.scanned_any.connect(lambda c: self.scans.insertItem(0, c))
        sl.addWidget(p)
        self.sim_box, self.sim_lay = self._box("Simulator controls", "wizard")
        sl.addWidget(self.sim_box)
        sl.addStretch(1)
        self._sim_built = False
        self._t = QTimer(self)
        self._t.timeout.connect(self._stats)

    @staticmethod
    def _box(title: str, ico: str):
        f = QFrame()
        f.setObjectName("Panel")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(12, 10, 12, 12)
        ic = QLabel()
        ic.setPixmap(icon(ico, C["ink"], 18).pixmap(18, 18))
        lay.addLayout(hrow(ic, label(title, "H2"), None))
        return f, lay

    def on_show(self) -> None:
        cam = self.ctx.camera
        sim = hasattr(cam, "set_hand")
        self.sim_box.setVisible(sim)
        if sim and not self._sim_built:
            self._build_sim(cam)
        self._t.start(1000)

    def on_hide(self) -> None:
        self._t.stop()

    def _stats(self) -> None:
        w = self.main.worker
        self.k_fps.set(f"{w.fps:.0f} FPS" if w.connected else "offline")
        f = self.ctx.latest_frame()
        if f is not None and f.depth_mm is not None:
            self.k_valid.set(f"{100 * float(np.mean(f.depth_mm > 0)):.1f}%")
            if f.height_mm is not None:
                h, wd = f.height_mm.shape
                c = f.height_mm[h // 2 - 10:h // 2 + 10, wd // 2 - 10:wd // 2 + 10]
                self.k_noise.set(f"{float(np.nanstd(c)):.1f}" if np.isfinite(c).any() else "-")
        self.k_vision.set("streaming" if f is not None and f.vision is not None else
                          ("not configured" if self.ctx.cfg.vision_camera_index < 0 else "no image"))

    def _build_sim(self, cam) -> None:
        lay = self.sim_lay
        lay.addWidget(label("Exercise teaching and inspection without hardware.", "Muted", wrap=True))
        for o in cam.objects:
            if o.qc is not None:
                cb = QComboBox()
                cb.addItems(["good", "bad", "missing"])
                cb.setCurrentText(o.qc)
                cb.currentTextChanged.connect(lambda v, n=o.name: cam.set_qc(n, v))
                lay.addLayout(hrow(label(o.name), None, cb))
            elif o.name != "RESET":
                lay.addWidget(button(f"Place / take {o.name.title()}", None, lambda _=False, n=o.name: cam.toggle(n)))
        self.hand = QComboBox()
        for o in cam.objects:
            self.hand.addItem(f"Hand over {o.name.title()}", o.rect)
        self.hand.addItem("Hand over gauge assembly zone", (270, 215, 70, 50))
        lay.addWidget(self.hand)
        lay.addLayout(hrow(button("Put hand", "primary", lambda: cam.set_hand(tuple(self.hand.currentData())),
                                  ico="hand"), button("Remove hand", None, lambda: cam.set_hand(None))))
        self._sim_built = True

    def on_frame(self, frame) -> None:
        if self.isVisible():
            for combo, v in self.views:
                v.set_image(frame_view(frame, combo.currentData()))
