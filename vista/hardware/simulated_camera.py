"""Synthetic top-down bench camera for engineering without hardware (CAMERA_BACKEND=sim).

It renders depth / colour / IR for a bench with toggleable objects, an operator hand and
projected calibration markers, so the complete flow (calibration, teaching, inspection,
reporting) can be exercised and regression-tested on any PC.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

from vista.hardware.camera_base import CameraBase, Frame, Intrinsics


@dataclass
class SimObject:
    name: str
    rect: tuple[int, int, int, int]       # camera px x, y, w, h
    height: float                          # mm above bench
    color: tuple[int, int, int]            # BGR
    present: bool = True
    qc: str | None = None                  # None | good | bad | missing (QC patch drawn on top)


def default_scene() -> list[SimObject]:
    return [
        SimObject("JOB LOADING", (140, 215, 560, 60), 45, (70, 70, 75), present=False),
        SimObject("BARCODE SCANNER", (90, 330, 70, 50), 70, (40, 40, 40), present=True),
        SimObject("P POINT GAUGE", (300, 120, 40, 40), 60, (60, 140, 200), present=True),
        SimObject("THREAD RING GO GAUGE", (380, 110, 50, 50), 35, (90, 160, 90), present=True),
        SimObject("THREAD RING NOGO GAUGE", (450, 110, 50, 50), 35, (60, 60, 190), present=True),
        SimObject("BELLOW CLIP LH", (200, 225, 34, 34), 0, (0, 0, 0), present=True, qc="good"),
        SimObject("BELLOW CLIP RH", (600, 225, 34, 34), 0, (0, 0, 0), present=True, qc="good"),
        SimObject("RESET", (720, 390, 50, 40), 0, (0, 0, 0), present=False),
    ]


class SimulatedCamera(CameraBase):
    def __init__(self, width: int = 848, height: int = 480, fps: int = 30):
        self.width, self.height, self.fps = width, height, fps
        self.name = "Simulated bench camera"
        f = width / 2.0  # ~90 deg horizontal field of view
        self.intr = Intrinsics(width, height, f, f, width / 2.0, height / 2.0)
        self.cam_height = 1000.0
        self.objects = default_scene()
        self.hand: tuple[int, int, int, int] | None = None
        self.hand_height = 140.0
        self.markers_proj: list[tuple[float, float]] = []
        self.marker_radius_proj = 22
        self.proj_size = (1920, 1080)
        # ideal projector -> camera pixel mapping (projector covers most of the camera view)
        sx, sy = (width - 80) / self.proj_size[0], (height - 60) / self.proj_size[1]
        self.H_proj2cam = np.array([[sx, 0.02 * sx, 40], [0.01 * sy, sy, 30], [0, 0, 1]], dtype=np.float64)
        self._lock = threading.Lock()
        self._rng = np.random.default_rng(7)
        self._texture = self._rng.normal(0, 6, (height, width)).astype(np.float32)
        self._last = 0.0
        self._seq = 0
        self._running = False
        vv, uu = np.mgrid[0:height, 0:width]
        self._table_z = (self.cam_height + 0.025 * (vv - height / 2) + 0.01 * (uu - width / 2)).astype(np.float32)

    # ------------------------------------------------------------------ control API (thread-safe)
    def get(self, name: str) -> SimObject | None:
        return next((o for o in self.objects if o.name == name), None)

    def toggle(self, name: str) -> None:
        with self._lock:
            o = self.get(name)
            if o:
                o.present = not o.present

    def set_present(self, name: str, present: bool) -> None:
        with self._lock:
            o = self.get(name)
            if o:
                o.present = present

    def set_qc(self, name: str, state: str) -> None:
        with self._lock:
            o = self.get(name)
            if o:
                o.qc = state

    def set_hand(self, rect: tuple[int, int, int, int] | None) -> None:
        with self._lock:
            self.hand = rect

    def set_markers(self, proj_points: list[tuple[float, float]], radius_proj: int = 22) -> None:
        with self._lock:
            self.markers_proj = list(proj_points)
            self.marker_radius_proj = radius_proj

    # ------------------------------------------------------------------ CameraBase
    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def info(self) -> dict:
        return {"name": self.name, "serial": "SIM-0001", "firmware": "-", "usb": "-",
                "resolution": f"{self.width}x{self.height}@{self.fps}"}

    def read(self, timeout_ms: int = 1000) -> Frame | None:
        period = 1.0 / max(1, self.fps)
        wait = self._last + period - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        with self._lock:
            depth, color, ir = self._render()
        self._seq += 1
        return Frame(ts=time.monotonic(), depth_mm=depth, color=color, ir=ir, intrinsics=self.intr, seq=self._seq)

    # ------------------------------------------------------------------ rendering
    def _render(self):
        h, w = self.height, self.width
        z = self._table_z.copy()
        base = np.clip(110 + self._texture, 0, 255)
        color = np.dstack([base, base, base * 0.97]).astype(np.uint8)
        ir = np.clip(90 + self._texture * 0.8, 0, 255).astype(np.uint8)
        for o in self.objects:
            x, y, ow, oh = o.rect
            if o.qc is not None:
                self._draw_qc(color, ir, o)
                continue
            if not o.present:
                continue
            z[y:y + oh, x:x + ow] -= o.height
            cv2.rectangle(color, (x, y), (x + ow, y + oh), o.color, -1)
            cv2.rectangle(color, (x + 3, y + 3), (x + ow - 3, y + oh - 3), tuple(min(255, c + 40) for c in o.color), 1)
            ir[y:y + oh, x:x + ow] = 160
        if self.hand is not None:
            x, y, hw, hh = self.hand
            cv2.ellipse(color, (x + hw // 2, y + hh // 2), (hw // 2, hh // 2), 0, 0, 360, (120, 150, 190), -1)
            mask = np.zeros((h, w), np.uint8)
            cv2.ellipse(mask, (x + hw // 2, y + hh // 2), (hw // 2, hh // 2), 0, 0, 360, 1, -1)
            z[mask > 0] = self._table_z[mask > 0] - self.hand_height
            ir[mask > 0] = 130
        if self.markers_proj:
            pts = cv2.perspectiveTransform(np.array(self.markers_proj, np.float64).reshape(-1, 1, 2),
                                           self.H_proj2cam).reshape(-1, 2)
            r = max(2, int(round(self.marker_radius_proj * self.H_proj2cam[0, 0])))
            for (u, v) in pts:
                cv2.circle(color, (int(round(u)), int(round(v))), r, (255, 255, 255), -1, lineType=cv2.LINE_AA)
        noise = self._rng.normal(0, 1.2, (h, w)).astype(np.float32)
        depth = z + noise
        drop = self._rng.random((h, w)) < 0.003
        depth[drop] = 0
        return depth.astype(np.float32), color, ir

    @staticmethod
    def _draw_qc(color, ir, o: SimObject) -> None:
        x, y, ow, oh = o.rect
        c = (x + ow // 2, y + oh // 2)
        r = min(ow, oh) // 2 - 3
        if o.qc == "good":
            cv2.circle(color, c, r, (40, 200, 60), 4)
            cv2.circle(color, c, r // 3, (40, 200, 60), -1)
        elif o.qc == "bad":
            cv2.line(color, (x + 4, y + 4), (x + ow - 4, y + oh - 4), (40, 40, 220), 4)
            cv2.line(color, (x + ow - 4, y + 4), (x + 4, y + oh - 4), (40, 40, 220), 4)
        # "missing" -> plain bench texture
