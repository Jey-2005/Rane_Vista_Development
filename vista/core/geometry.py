"""Small geometry helpers shared by vision, calibration and UI."""
from __future__ import annotations

import numpy as np
import cv2


def apply_homography(H: np.ndarray, pts) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 1, 2)
    if len(pts) == 0:
        return np.zeros((0, 2))
    return cv2.perspectiveTransform(pts, np.asarray(H, dtype=np.float64)).reshape(-1, 2)


def rect_to_poly(x: float, y: float, w: float, h: float) -> list[list[float]]:
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def clamp_rect(x: int, y: int, w: int, h: int, width: int, height: int) -> tuple[int, int, int, int]:
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(width, int(x + w)), min(height, int(y + h))
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


def mask_to_png(mask: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", (mask.astype(np.uint8) * 255))
    if not ok:
        raise ValueError("mask encoding failed")
    return buf.tobytes()


def png_to_mask(data: bytes) -> np.ndarray:
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    return arr > 127
