"""Background writer for inspection results.

The operator flow never waits for the database: results are queued and written by a worker
thread. If the database is unreachable, records are appended to a local spool file
(data/spool/*.jsonl) and replayed automatically once the connection is back.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from datetime import datetime
from pathlib import Path

from vista.db.repositories import RunRepo

log = logging.getLogger(__name__)


def _enc(o):
    if isinstance(o, datetime):
        return {"__dt__": o.isoformat()}
    if isinstance(o, uuid.UUID):
        return {"__uuid__": str(o)}
    raise TypeError(type(o))


def _dec(d):
    if "__dt__" in d:
        return datetime.fromisoformat(d["__dt__"])
    if "__uuid__" in d:
        return uuid.UUID(d["__uuid__"])
    return d


class ResultRecorder:
    def __init__(self, run_repo: RunRepo, spool_dir: Path):
        self.repo = run_repo
        self.spool_dir = spool_dir
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="ResultRecorder", daemon=True)
        self.failures = 0
        self._thread.start()

    # public API (any thread) ------------------------------------------------------
    def start_run(self, run_id, job_id, revision, operator_id, started_at):
        self._q.put(("start", (run_id, job_id, revision, operator_id, started_at)))

    def identity(self, run_id, barcode, variant):
        self._q.put(("identity", (run_id, barcode, variant)))

    def step_result(self, run_id, row: dict):
        self._q.put(("step", (run_id, row)))

    def finish_run(self, run_id, result, finished_at, cycle_ms, ng, forced, remarks):
        self._q.put(("finish", (run_id, result, finished_at, cycle_ms, ng, forced, remarks)))

    def flush(self, timeout: float = 5.0) -> None:
        done = threading.Event()
        self._q.put(("barrier", done))
        done.wait(timeout)

    def stop(self) -> None:
        self.flush()
        self._stop.set()
        self._q.put(("noop", None))
        self._thread.join(timeout=3)

    @property
    def pending(self) -> int:
        return self._q.qsize() + len(self._spool_files())

    # worker -----------------------------------------------------------------------
    def _apply(self, op, args) -> None:
        if op == "start":
            self.repo.start(*args)
        elif op == "identity":
            self.repo.update_identity(*args)
        elif op == "step":
            self.repo.add_step_result(*args)
        elif op == "finish":
            self.repo.finish(*args)

    def _spool_files(self):
        return sorted(self.spool_dir.glob("*.jsonl"))

    def _spool(self, op, args) -> None:
        f = self.spool_dir / f"{datetime.now():%Y%m%d}.jsonl"
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"op": op, "args": args}, default=_enc) + "\n")

    def _replay(self) -> bool:
        for f in self._spool_files():
            lines = f.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                rec = json.loads(line, object_hook=_dec)
                try:
                    self._apply(rec["op"], rec["args"])
                except Exception as exc:
                    if "duplicate key" in str(exc):
                        continue      # already written before the outage
                    f.write_text("\n".join(lines[i:]) + "\n", encoding="utf-8")
                    return False
            f.unlink()
            log.info("Replayed spooled results from %s", f.name)
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                op, args = self._q.get(timeout=10)
            except queue.Empty:
                if self._spool_files():
                    try:
                        self._replay()
                    except Exception:
                        log.debug("Spool replay deferred")
                continue
            if op == "barrier":
                args.set()
                continue
            if op == "noop":
                continue
            if self._spool_files():           # keep ordering while an outage is being recovered
                try:
                    if not self._replay():
                        self._spool(op, args)
                        continue
                except Exception:
                    self._spool(op, args)
                    continue
            try:
                self._apply(op, args)
                self.failures = 0
            except Exception as exc:
                self.failures += 1
                log.error("Result write failed (%s) - spooled locally: %s", op, exc)
                self._spool(op, args)
