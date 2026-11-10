"""Detection engine - evaluates all loaded detections on every frame (camera thread).

Objects / activities / buttons are cheap and always evaluated (so the projector and editor can
show live state). Quality checks are only evaluated while "watched" (active step or selected in
the editor) and at most every `qc_every` frames.
"""
from __future__ import annotations

import copy
import logging
import threading

from vista.vision.detectors import DetState, build_detector

log = logging.getLogger(__name__)


class DetectionEngine:
    def __init__(self, qc_every: int = 2):
        self._lock = threading.Lock()
        self._detectors: dict[int, object] = {}
        self._states: dict[int, DetState] = {}
        self._watch: set[int] = set()
        self._meta: dict[int, dict] = {}
        self.qc_every = qc_every
        self._n = 0

    def load(self, entries: list[tuple[dict, dict, list]]) -> list[str]:
        """entries: (detection row, arrays, qc samples). Returns load warnings."""
        dets, states, meta, warnings = {}, {}, {}, []
        for det, arrays, samples in entries:
            st = DetState(det["id"], det["name"], det["det_type"])
            meta[det["id"]] = det
            if not det.get("enabled", True):
                st.state = "DISABLED"
            elif not det.get("model") or not det["model"].get("roi"):
                st.state = "UNTAUGHT"
            else:
                try:
                    dets[det["id"]] = build_detector(det, arrays, samples)
                    st.state = "UNKNOWN"
                except Exception as exc:  # corrupt teaching must not stop the station
                    st.state = "UNTAUGHT"
                    warnings.append(f"{det['name']}: {exc}")
                    log.exception("Failed to build detector %s", det["name"])
            # keep counters across reloads so running steps are not re-triggered
            old = self._states.get(det["id"])
            if old is not None and det["id"] in dets and hasattr(dets[det["id"]], "counter"):
                dets[det["id"]].counter = old.counter
                st.counter = old.counter
            states[det["id"]] = st
        with self._lock:
            self._detectors, self._states, self._meta = dets, states, meta
        return warnings

    def set_watch(self, ids) -> None:
        with self._lock:
            self._watch = set(ids)

    def detector(self, det_id: int):
        with self._lock:
            return self._detectors.get(det_id)

    def process(self, frame) -> dict[int, DetState]:
        self._n += 1
        with self._lock:
            dets = dict(self._detectors)
            watch = set(self._watch)
        for det_id, d in dets.items():
            st = self._states.get(det_id)
            if st is None:
                continue
            if d.det_type == "QUALITY":
                if det_id not in watch:
                    st.state = "IDLE"
                    d.history.clear()
                    continue
                if self._n % self.qc_every:
                    continue
            try:
                d.update(frame, st)
                st.ts = frame.ts
            except Exception:
                log.exception("Detection %s failed", st.name)
                st.state = "UNKNOWN"
        with self._lock:
            return {k: copy.copy(v) for k, v in self._states.items()}

    def states(self) -> dict[int, DetState]:
        with self._lock:
            return {k: copy.copy(v) for k, v in self._states.items()}

    def meta(self) -> dict[int, dict]:
        with self._lock:
            return dict(self._meta)
