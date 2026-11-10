"""Rotating file + console logging with secret redaction."""
from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET_RE = re.compile(r"(password|passwd|pwd|secret|token)\s*[=:]\s*\S+", re.IGNORECASE)


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # malformed args - let logging report it
            return True
        if _SECRET_RE.search(msg):
            record.msg = _SECRET_RE.sub(r"\1=***", msg)
            record.args = ()
        return True


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))
    for h in list(root.handlers):
        root.removeHandler(h)
    fh = RotatingFileHandler(log_dir / "vista.log", maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(RedactFilter())
    root.addHandler(fh)
    if sys.stderr is not None:          # a windowed (console=False) exe has no stderr
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        ch.addFilter(RedactFilter())
        root.addHandler(ch)
    logging.getLogger("psycopg.pool").setLevel(logging.WARNING)
