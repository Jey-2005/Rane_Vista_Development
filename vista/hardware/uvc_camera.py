"""Optional dedicated 2D vision camera (UVC / DirectShow) for high-resolution quality checks."""
from __future__ import annotations

import logging
import sys
import threading
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)


class UvcCamera:
    def __init__(self, index: int, width: int = 1920, height: int = 1080):
        self.index, self.width, self.height = index, width, height
        self._cap = None
        self._latest: np.ndarray | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.index, backend)
        if not cap.isOpened():
            raise RuntimeError(f"Vision camera index {self.index} could not be opened")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap = cap
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="VisionCam", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            ok, img = self._cap.read()
            if ok:
                with self._lock:
                    self._latest = img
            else:
                time.sleep(0.05)

    def latest(self) -> np.ndarray | None:
        with self._lock:
            return None if self._latest is None else self._latest.copy()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._cap is not None:
            self._cap.release()
            self._cap = None
