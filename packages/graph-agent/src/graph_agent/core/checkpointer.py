"""GraphAgent-owned sync checkpointer factory."""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from langgraph.types import Checkpointer

logger = logging.getLogger(__name__)

SQLITE_INSTALL = (
    "langgraph-checkpoint-sqlite is required for the SQLite checkpointer. "
    "Install it with: uv add langgraph-checkpoint-sqlite"
)
POSTGRES_INSTALL = (
    "langgraph-checkpoint-postgres is required for the PostgreSQL checkpointer. "
    "Install it with: uv add langgraph-checkpoint-postgres psycopg[binary] psycopg-pool"
)
POSTGRES_CONN_REQUIRED = "connection_string is required for the postgres checkpointer"

_checkpointer: Checkpointer | None = None
_checkpointer_ctx: contextlib.AbstractContextManager[Checkpointer] | None = None
_checkpointers_by_spec: dict[tuple[str, str], Checkpointer] = {}
_checkpointer_contexts_by_spec: dict[tuple[str, str], contextlib.AbstractContextManager[Checkpointer]] = {}


def _resolve_sqlite_conn_str(db_path: Path | str) -> str:
    """Return a SQLite connection string suitable for ``SqliteSaver``."""
    raw = str(db_path)
    if raw == ":memory:" or raw.startswith("file:"):
        return raw
    return str(Path(raw).expanduser().resolve())


@contextlib.contextmanager
def checkpointer_context(
    db_path: Path | str | None = None,
    *,
    backend: str = "memory",
    connection_string: str | None = None,
) -> Iterator[Checkpointer]:
    """Yield a fresh checkpointer and close backend resources on exit."""
    if backend == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        logger.info("Checkpointer: using InMemorySaver (in-process, not persistent)")
        yield InMemorySaver()
        return

    if backend == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:
            raise ImportError(SQLITE_INSTALL) from exc

        conn_str = _resolve_sqlite_conn_str(db_path or "store.db")
        if not (conn_str == ":memory:" or conn_str.startswith("file:")):
            os.makedirs(os.path.dirname(conn_str), exist_ok=True)
        with SqliteSaver.from_conn_string(conn_str) as saver:
            saver.setup()
            logger.info("Checkpointer: using SqliteSaver (%s)", conn_str)
            yield saver
        return

    if backend == "postgres":
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError as exc:
            raise ImportError(POSTGRES_INSTALL) from exc

        if not connection_string:
            raise ValueError(POSTGRES_CONN_REQUIRED)
        with PostgresSaver.from_conn_string(connection_string) as saver:
            saver.setup()
            logger.info("Checkpointer: using PostgresSaver")
            yield saver
        return

    raise ValueError(f"Unknown checkpointer backend: {backend!r}")


def get_checkpointer(
    db_path: Path | str | None = None,
    *,
    backend: str | None = None,
    connection_string: str | None = None,
) -> Checkpointer:
    """Return a process-wide sync checkpointer cached by normalized backend spec.

    ``db_path`` is intentionally supplied by the caller; this module does not
    read graph_agent application config.
    """
    effective_backend = backend or ("sqlite" if db_path is not None else "memory")

    if effective_backend == "memory":
        if db_path is not None or connection_string:
            raise ValueError("memory checkpointer does not accept db_path or connection_string")
        return _cached_checkpointer_for_spec(("memory", "memory"), backend="memory")

    if effective_backend == "sqlite":
        if connection_string:
            raise ValueError("sqlite checkpointer does not accept connection_string")
        effective_db_path = db_path or "store.db"
        conn_str = _resolve_sqlite_conn_str(effective_db_path)
        return _cached_checkpointer_for_spec(
            ("sqlite", conn_str),
            db_path=effective_db_path,
            backend="sqlite",
        )

    if effective_backend == "postgres":
        if db_path is not None:
            raise ValueError("postgres checkpointer does not accept db_path")
        if not connection_string:
            raise ValueError(POSTGRES_CONN_REQUIRED)
        return _cached_checkpointer_for_spec(
            ("postgres", connection_string),
            backend="postgres",
            connection_string=connection_string,
        )

    return _cached_checkpointer_for_spec(
        (effective_backend, str(db_path or connection_string or "")),
        db_path=db_path,
        backend=effective_backend,
        connection_string=connection_string,
    )


def _cached_checkpointer_for_spec(
    key: tuple[str, str],
    *,
    db_path: Path | str | None = None,
    backend: str,
    connection_string: str | None = None,
) -> Checkpointer:
    cached = _checkpointers_by_spec.get(key)
    if cached is not None:
        return cached

    ctx = checkpointer_context(
        db_path,
        backend=backend,
        connection_string=connection_string,
    )
    checkpointer = ctx.__enter__()
    _checkpointer_contexts_by_spec[key] = ctx
    _checkpointers_by_spec[key] = checkpointer
    return checkpointer


def _parse_and_get_checkpointer(val: str) -> Checkpointer:
    """Helper to parse memory/sqlite/postgres specifications."""
    if val == "memory":
        return _cached_checkpointer_for_spec(("memory", "memory"), backend="memory")
    if val.startswith("sqlite:"):
        raw_path = val[len("sqlite:") :] or "store.db"
        conn_str = _resolve_sqlite_conn_str(raw_path)
        return _cached_checkpointer_for_spec(("sqlite", conn_str), db_path=raw_path, backend="sqlite")
    if val.startswith(("postgres://", "postgresql://")):
        return _cached_checkpointer_for_spec(("postgres", val), backend="postgres", connection_string=val)
    raise ValueError(f"unrecognised checkpointer value: {val!r}")


def resolve_checkpointer(checkpointer_arg: Any = "auto") -> Checkpointer | None:
    """Resolve checkpointer argument or environment variables to a Checkpointer.

    If checkpointer_arg is "auto", it checks for STUDIO_CHECKPOINTER env var first:
      - "memory" -> InMemorySaver
      - "sqlite:<path>" -> SqliteSaver at <path>
      - "postgres://..." or "postgresql://..." -> PostgresSaver

    If STUDIO_CHECKPOINTER is not set, it falls back to GRAPH_AGENT_CHECKPOINTER_DB
    using get_checkpointer.
    """
    if checkpointer_arg is None:
        return None

    if checkpointer_arg == "auto":
        override = os.environ.get("STUDIO_CHECKPOINTER")
        if override:
            try:
                return _parse_and_get_checkpointer(override.strip())
            except ValueError as exc:
                raise ValueError(f"unrecognised STUDIO_CHECKPOINTER value: {override!r}") from exc

        # Fallback to GRAPH_AGENT_CHECKPOINTER_DB
        db_path = os.environ.get("GRAPH_AGENT_CHECKPOINTER_DB")
        return get_checkpointer(db_path=db_path)

    if isinstance(checkpointer_arg, str):
        try:
            return _parse_and_get_checkpointer(checkpointer_arg)
        except ValueError:
            pass

    return cast(Checkpointer | None, checkpointer_arg)  # Returns explicit Checkpointer instance or None


def reset_checkpointer() -> None:
    """Close the singleton checkpointer and clear cached state."""
    global _checkpointer, _checkpointer_ctx
    for ctx in list(_checkpointer_contexts_by_spec.values()):
        try:
            ctx.__exit__(None, None, None)
        except Exception:
            logger.warning("Error during checkpointer cleanup", exc_info=True)
    _checkpointer_contexts_by_spec.clear()
    _checkpointers_by_spec.clear()

    if _checkpointer_ctx is not None:
        try:
            _checkpointer_ctx.__exit__(None, None, None)
        except Exception:
            logger.warning("Error during checkpointer cleanup", exc_info=True)
        _checkpointer_ctx = None
    _checkpointer = None
