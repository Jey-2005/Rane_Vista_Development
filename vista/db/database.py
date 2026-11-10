"""PostgreSQL access: connection pool, transactions, migrations.

All queries are parameterised (psycopg placeholders). Identifiers that cannot be
parameterised (the schema name) are validated in config and composed with psycopg.sql.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from vista.core.config import DbConfig, resource_dir

log = logging.getLogger(__name__)


class DatabaseError(RuntimeError):
    pass


class Database:
    def __init__(self, cfg: DbConfig):
        self.cfg = cfg
        self._pool: ConnectionPool | None = None

    # ------------------------------------------------------------------ lifecycle
    def open(self) -> None:
        kwargs = self.cfg.conninfo_kwargs()
        kwargs["row_factory"] = dict_row
        self._pool = ConnectionPool(
            conninfo="", kwargs=kwargs, min_size=1, max_size=6, open=False,
            timeout=max(5, self.cfg.connect_timeout * 2), name="vista",
        )
        try:
            self._pool.open(wait=True, timeout=max(5, self.cfg.connect_timeout * 2))
        except Exception as exc:  # pool timeout wraps the real cause
            self._pool = None
            raise DatabaseError(
                f"Cannot connect to PostgreSQL at {self.cfg.safe_repr()}. "
                "Check that the server is running and the .env credentials are correct."
            ) from exc
        log.info("Database connected: %s", self.cfg.safe_repr())

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    @property
    def is_open(self) -> bool:
        return self._pool is not None

    # ------------------------------------------------------------------ helpers
    @contextmanager
    def tx(self) -> Iterator[psycopg.Connection]:
        if self._pool is None:
            raise DatabaseError("Database is not connected.")
        with self._pool.connection() as conn:
            with conn.transaction():
                yield conn

    def fetchall(self, query: str, params: Any = None) -> list[dict]:
        with self.tx() as conn:
            return conn.execute(query, params).fetchall()

    def fetchone(self, query: str, params: Any = None) -> dict | None:
        with self.tx() as conn:
            return conn.execute(query, params).fetchone()

    def execute(self, query: str, params: Any = None) -> int:
        with self.tx() as conn:
            cur = conn.execute(query, params)
            return cur.rowcount

    def ping(self) -> bool:
        try:
            self.fetchone("SELECT 1 AS ok")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ migrations
    def migrate(self) -> list[str]:
        """Apply pending SQL migrations from sql/migrations in filename order."""
        mig_dir = resource_dir() / "sql" / "migrations"
        files = sorted(p for p in mig_dir.glob("*.sql"))
        if not files:
            raise DatabaseError(f"No migration files found in {mig_dir}")
        applied: list[str] = []
        schema = sql.Identifier(self.cfg.schema)
        with self.tx() as conn:
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(schema))
            conn.execute(sql.SQL("SET search_path TO {}").format(schema))
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version ("
                " version INT PRIMARY KEY, name TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            done = {r["version"] for r in conn.execute("SELECT version FROM schema_version").fetchall()}
        for f in files:
            version = int(f.name.split("_", 1)[0])
            if version in done:
                continue
            script = f.read_text(encoding="utf-8")
            with self.tx() as conn:
                conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(schema))
                conn.execute(script)
                conn.execute("INSERT INTO schema_version (version, name) VALUES (%s, %s)", (version, f.name))
            applied.append(f.name)
            log.info("Applied migration %s", f.name)
        return applied
