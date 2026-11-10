"""Common camera types. All images handed to the rest of the app share ONE pixel grid:
the depth sensor grid (colour is aligned to depth, IR-left is natively in that grid on D4xx)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np


class CameraError(RuntimeError):
    pass


@dataclass(frozen=True)
class Intrinsics:
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float

    def to_dict(self) -> dict:
        return {"width": self.width, "height": self.height, "fx": self.fx, "fy": self.fy, "cx": self.cx, "cy": self.cy}

    @staticmethod
    def from_dict(d: dict) -> "Intrinsics":
        return Intrinsics(int(d["width"]), int(d["height"]), float(d["fx"]), float(d["fy"]), float(d["cx"]),
                          float(d["cy"]))


@dataclass
class Frame:
    ts: float
    depth_mm: np.ndarray | None          # float32, 0 = invalid
    color: np.ndarray | None             # BGR uint8, aligned to depth grid
    ir: np.ndarray | None                # uint8, depth grid
    intrinsics: Intrinsics | None
    height_mm: np.ndarray | None = None  # float32 height above bench plane (NaN = invalid), set by worker
    vision: np.ndarray | None = None     # optional separate 2D vision camera (BGR, own pixel grid)
    seq: int = 0
    meta: dict = field(default_factory=dict)

    @staticmethod
    def now() -> float:
        return time.monotonic()


class CameraBase:
    """Interface implemented by RealSenseCamera and SimulatedCamera."""

    name = "camera"

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def read(self, timeout_ms: int = 1000) -> Frame | None:
        raise NotImplementedError

    def info(self) -> dict:
        return {"name": self.name}

    def set_option(self, key: str, value) -> None:  # pragma: no cover - optional
        pass

    def options(self) -> dict:
        return {}
