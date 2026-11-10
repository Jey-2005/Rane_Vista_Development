"""Application configuration.

Secrets (database password) are read ONLY from environment variables / the local `.env`
file next to the executable. Nothing sensitive is hard-coded or stored in the database.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when mandatory configuration is missing or invalid."""


_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_CODE_RE = re.compile(r"^[A-Za-z0-9_\-]{2,32}$")


def app_base_dir() -> Path:
    """Folder that contains the executable (frozen) or the project root (source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_dir() -> Path:
    """Folder that contains bundled read-only resources (sql/, assets/)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", app_base_dir()))
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    name: str
    user: str
    password: str
    schema: str
    sslmode: str
    connect_timeout: int

    def conninfo_kwargs(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.name,
            "user": self.user,
            "password": self.password,
            "sslmode": self.sslmode,
            "connect_timeout": self.connect_timeout,
            "application_name": "rane_vista",
            "options": f"-c search_path={self.schema}",
        }

    def safe_repr(self) -> str:
        return f"{self.user}@{self.host}:{self.port}/{self.name} (schema={self.schema})"


@dataclass(frozen=True)
class AppConfig:
    db: DbConfig
    station_code: str
    station_name: str
    camera_backend: str          # realsense | sim
    realsense_serial: str        # empty = first device found
    depth_width: int
    depth_height: int
    fps: int
    vision_camera_index: int     # -1 = disabled (optional UVC / industrial 2D camera)
    data_dir: Path
    log_level: str

    @property
    def evidence_dir(self) -> Path:
        return self.data_dir / "evidence"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"


def _env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and (val is None or str(val).strip() == ""):
        raise ConfigError(f"Missing required setting {name}. Add it to the .env file next to the application.")
    return "" if val is None else str(val).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Setting {name} must be an integer, got '{raw}'.") from exc


def load_config(env_file: Path | None = None) -> AppConfig:
    env_path = env_file or (app_base_dir() / ".env")
    if env_path.exists():
        # Real environment variables take precedence over the file.
        load_dotenv(env_path, override=False)

    schema = _env("DB_SCHEMA", "pdi_inspection")
    if not _IDENT_RE.match(schema):
        raise ConfigError("DB_SCHEMA must be a lowercase SQL identifier (letters, digits, underscore).")

    station_code = _env("STATION_CODE", required=True)
    if not _CODE_RE.match(station_code):
        raise ConfigError("STATION_CODE must be 2-32 characters: letters, digits, '-' or '_'.")

    backend = _env("CAMERA_BACKEND", "realsense").lower()
    if backend not in ("realsense", "sim"):
        raise ConfigError("CAMERA_BACKEND must be 'realsense' or 'sim'.")

    data_dir_raw = _env("DATA_DIR", "")
    if data_dir_raw:
        data_dir = Path(os.path.expandvars(data_dir_raw))
    elif sys.platform.startswith("win"):
        # never default to the program folder - C:\Program Files is not writable for station users
        data_dir = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "RANE_VISTA"
    else:
        data_dir = app_base_dir() / "data"

    db = DbConfig(
        host=_env("DB_HOST", "localhost"),
        port=_env_int("DB_PORT", 5432),
        name=_env("DB_NAME", required=True),
        user=_env("DB_USER", required=True),
        password=_env("DB_PASSWORD", required=True),
        schema=schema,
        sslmode=_env("DB_SSLMODE", "prefer"),
        connect_timeout=_env_int("DB_CONNECT_TIMEOUT", 5),
    )
    cfg = AppConfig(
        db=db,
        station_code=station_code.upper(),
        station_name=_env("STATION_NAME", station_code),
        camera_backend=backend,
        realsense_serial=_env("REALSENSE_SERIAL", ""),
        depth_width=_env_int("DEPTH_WIDTH", 848),
        depth_height=_env_int("DEPTH_HEIGHT", 480),
        fps=_env_int("CAMERA_FPS", 30),
        vision_camera_index=_env_int("VISION_CAMERA_INDEX", -1),
        data_dir=data_dir,
        log_level=_env("LOG_LEVEL", "INFO").upper(),
    )
    for d in (cfg.data_dir, cfg.evidence_dir, cfg.log_dir, cfg.export_dir):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigError(f"Cannot create the data folder {d} ({exc.strerror}). Set DATA_DIR in .env to a folder "
                              "the station user can write to, e.g. C:\\ProgramData\\RANE_VISTA.") from exc
    return cfg
