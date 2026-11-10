"""Optoma ZH406ST remote control.

Primary: PJLink Class 1 over LAN (TCP 4352) - supported by the ZH406ST per Optoma's manual.
Fallback: RS-232 (9600 8N1). The RS-232 command strings below follow Optoma's common
"~XXnn v" ASCII format; verify them against the ZH406ST RS-232 protocol sheet on site - they
are editable in Hardware > Projector without code changes.

The projected *image* is not sent over this channel: the projector is a normal Windows display
(HDMI) and the app renders a full-screen window on it (see ui/projector_window.py).
"""
from __future__ import annotations

import hashlib
import logging
import socket

log = logging.getLogger(__name__)


class ProjectorError(RuntimeError):
    pass


POWER_STATES = {"0": "Standby", "1": "On", "2": "Cooling down", "3": "Warming up"}
PJLINK_ERRORS = {"ERR1": "undefined command", "ERR2": "out of parameter", "ERR3": "unavailable time",
                 "ERR4": "projector failure", "ERRA": "authentication failed"}


class PJLinkClient:
    def __init__(self, host: str, port: int = 4352, password: str = "", timeout: float = 3.0):
        self.host, self.port, self.password, self.timeout = host, port, password, timeout

    def _send(self, body: str) -> str:
        if not self.host:
            raise ProjectorError("Projector IP address is not configured.")
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as s:
                s.settimeout(self.timeout)
                greeting = self._readline(s)
                if not greeting.startswith("PJLINK"):
                    raise ProjectorError(f"Unexpected greeting from projector: {greeting!r}")
                prefix = ""
                parts = greeting.split()
                if len(parts) >= 3 and parts[1] == "1":
                    if not self.password:
                        raise ProjectorError("Projector requires a PJLink password.")
                    prefix = hashlib.md5((parts[2] + self.password).encode("ascii")).hexdigest()
                s.sendall(f"{prefix}%1{body}\r".encode("ascii"))
                resp = self._readline(s)
        except OSError as exc:
            raise ProjectorError(f"Cannot reach projector at {self.host}:{self.port} ({exc})") from exc
        if "PJLINK ERRA" in resp:
            raise ProjectorError("PJLink authentication failed - check the projector password.")
        value = resp.split("=", 1)[1] if "=" in resp else resp
        if value in PJLINK_ERRORS:
            raise ProjectorError(f"Projector replied {value}: {PJLINK_ERRORS[value]}")
        return value

    @staticmethod
    def _readline(s: socket.socket) -> str:
        buf = b""
        while not buf.endswith(b"\r"):
            chunk = s.recv(1)
            if not chunk:
                break
            buf += chunk
            if len(buf) > 512:
                break
        return buf.decode("ascii", errors="replace").strip()

    def power_on(self) -> None:
        self._send("POWR 1")

    def power_off(self) -> None:
        self._send("POWR 0")

    def power_state(self) -> str:
        return POWER_STATES.get(self._send("POWR ?"), "Unknown")

    def av_mute(self, on: bool) -> None:
        self._send("AVMT 31" if on else "AVMT 30")

    def error_status(self) -> str:
        # 6 digits: fan, lamp, temperature, cover, filter, other (0 ok, 1 warning, 2 error)
        code = self._send("ERST ?")
        names = ["fan", "light source", "temperature", "cover", "filter", "other"]
        issues = [f"{n}: {'warning' if c == '1' else 'error'}" for n, c in zip(names, code) if c in "12"]
        return ", ".join(issues) if issues else "No errors"

    def name(self) -> str:
        return self._send("NAME ?")

    def info(self) -> dict:
        return {"power": self.power_state(), "errors": self.error_status()}


DEFAULT_SERIAL_COMMANDS = {
    "power_on": "~0000 1",
    "power_off": "~0000 0",
    "power_query": "~00124 1",
}


class OptomaSerial:
    def __init__(self, port: str, baudrate: int = 9600, commands: dict | None = None):
        self.port, self.baudrate = port, baudrate
        self.commands = {**DEFAULT_SERIAL_COMMANDS, **(commands or {})}

    def _send(self, key: str) -> str:
        try:
            import serial  # pyserial
        except ImportError as exc:
            raise ProjectorError("pyserial is not installed.") from exc
        if not self.port:
            raise ProjectorError("Projector COM port is not configured.")
        try:
            with serial.Serial(self.port, self.baudrate, timeout=2) as ser:
                ser.write((self.commands[key] + "\r").encode("ascii"))
                return ser.read_until(b"\r").decode("ascii", errors="replace").strip()
        except serial.SerialException as exc:
            raise ProjectorError(f"Serial error on {self.port}: {exc}") from exc

    def power_on(self) -> None:
        self._send("power_on")

    def power_off(self) -> None:
        self._send("power_off")

    def power_state(self) -> str:
        resp = self._send("power_query")
        return {"Ok0": "Standby", "Ok1": "On"}.get(resp, resp or "No reply")
