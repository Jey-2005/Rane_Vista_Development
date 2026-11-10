"""Barcode scanner input.

* Keyboard-wedge (USB HID) scanners: `KeyboardWedgeFilter` recognises a fast burst of keys
  terminated by Enter (human typing is far slower) and emits it as one scan.
* Serial / virtual-COM scanners: `SerialScanner` reads lines on a background thread.
"""
from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QWindow

log = logging.getLogger(__name__)


class KeyboardWedgeFilter(QObject):
    scanned = Signal(str)

    def __init__(self, max_interval_ms: int = 45, min_length: int = 4):
        super().__init__()
        self.max_interval = max_interval_ms / 1000.0
        self.min_length = min_length
        self.enabled = True
        self._buf: list[str] = []
        self._last = 0.0

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        if not self.enabled or event.type() != QEvent.KeyPress:
            return False
        # A real key press reaches an application-wide filter twice: first for the top-level QWindow, then for
        # the focused widget. Count it only at window level, otherwise every scanned character is doubled.
        if not isinstance(obj, QWindow):
            return False
        now = time.monotonic()
        if now - self._last > self.max_interval:
            self._buf = []
        self._last = now
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
            if len(self._buf) >= self.min_length:
                code = "".join(self._buf)
                self._buf = []
                self.scanned.emit(code)
                return True     # swallow the terminator of a genuine scan
            self._buf = []
            return False
        text = event.text()
        if text and text.isprintable():
            self._buf.append(text)
        return False


class SerialScanner(QObject):
    scanned = Signal(str)
    error = Signal(str)

    def __init__(self, port: str, baudrate: int = 9600):
        super().__init__()
        self.port, self.baudrate = port, baudrate
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="SerialScanner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        try:
            import serial
        except ImportError:
            self.error.emit("pyserial is not installed")
            return
        while not self._stop.is_set():
            try:
                with serial.Serial(self.port, self.baudrate, timeout=0.5) as ser:
                    buf = b""
                    while not self._stop.is_set():
                        chunk = ser.read(64)
                        if not chunk:
                            continue
                        buf += chunk
                        while b"\r" in buf or b"\n" in buf:
                            idx = min(i for i in (buf.find(b"\r"), buf.find(b"\n")) if i >= 0)
                            line, buf = buf[:idx], buf[idx + 1:]
                            code = line.decode("ascii", errors="ignore").strip()
                            if code:
                                self.scanned.emit(code)
            except Exception as exc:  # serial.SerialException or port vanished
                self.error.emit(f"Scanner {self.port}: {exc}")
                log.warning("Serial scanner error: %s", exc)
                self._stop.wait(3.0)
