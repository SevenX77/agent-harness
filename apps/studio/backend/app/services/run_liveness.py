"""Whether the worker a run claims to have is still there.

A run record that says ``running`` is a CLAIM, and until now nothing could check
it. The claim is written by a sidecar that may be gone: the sidecar keeps its
live runs in memory only, so a fresh one starts with an empty registry while the
record on disk still reads ``running``. Asked "is this run going?", the run list
answered yes (from the record) and ``pause_run`` answered ``RUN_NOT_RUNNING``
(from the registry) — one question, two answers, and the badge spins forever.

So a run that claims to be running names who is running it, in a way any later
process can check: **its worker holds an exclusive OS lock on a file inside the
run's own directory, for exactly as long as it lives**. Anyone can then ask by
trying to take that lock — refused means a live holder, granted means nobody is
there.

*Borrowed*, and from where: PostgreSQL locks its data directory alongside
``postmaster.pid``, and systemd's ``PIDFile`` handling treats the lock, not the
number, as the liveness fact. Both do it for the same reason — the OS releases
the lock however the holder dies, including a kill nobody could run cleanup for.

*Rejected*: probing the pid (``os.kill(pid, 0)``). Pids are reused, so a recycled
pid makes a dead run read as alive — which is the exact lie being removed here,
reintroduced in a new place. Also rejected: a heartbeat timestamp, because it
needs a staleness threshold, and a phase waiting on a slow LLM call is
indistinguishable from a worker that died.

*Where the reference does not hold*: PostgreSQL can assume one well-known data
directory and a supervisor that outlives everything on the machine. This repo has
no daemon — the sidecar dies with the app window — so there is no single place to
keep the lock and no supervisor to consult. The lock therefore lives in each
run's own directory and is found by walking the runs, not by looking somewhere
central.

The pid is written next to the lock anyway. It is not the liveness answer; it is
the handle needed to actually stop an adopted worker whose parent is gone.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO

LIVENESS_FILENAME = "worker.lock"
"""The file a worker holds for its lifetime. Named for what it is, not what it stores."""


@dataclass(frozen=True)
class RunWorkerHandle:
    """Who is executing a run, as recorded next to the lock it holds."""

    pid: int


def _open_for_locking(path: Path) -> IO[bytes]:
    """A read/write handle on the lock file, creating it if this is the first claim.

    Not ``"a+b"``: append mode sends every write to the end regardless of seek,
    and on Windows the locked region is taken at the CURRENT file position — so
    two handles at different positions would lock different bytes and never see
    each other, which is exactly the silent no-conflict this cost an hour to.
    """
    path.touch(exist_ok=True)
    return path.open("r+b")


def _try_lock(handle: IO[bytes]) -> bool:
    """Take an exclusive lock on byte 0 without waiting. False = someone holds it."""
    handle.seek(0)
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(handle: IO[bytes]) -> None:
    if sys.platform == "win32":
        import msvcrt

        with contextlib.suppress(OSError, ValueError):
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    with contextlib.suppress(OSError, ValueError):
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def hold_run_liveness(run_dir: Path) -> Iterator[None]:
    """Claim this run as mine for the duration of the block.

    Called by the worker around its whole life. On the way in it writes its pid
    so a parent that lost its handle can still stop it; on the way out — however
    the block ends — the OS drops the lock, which is the point: a worker killed
    outright cannot run cleanup, and does not need to.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / LIVENESS_FILENAME
    handle = _open_for_locking(path)
    try:
        if not _try_lock(handle):
            # Two workers for one run directory is not a state this system can
            # produce; if it ever does, refusing loudly beats two writers racing
            # over the same trace.
            raise RuntimeError(f"another worker already holds {path}")
        # The pid goes AFTER byte 0, which the lock covers — writing over a byte
        # this handle already locked is allowed, and keeping the two apart means
        # a reader never has to parse and lock the same byte.
        handle.seek(1)
        handle.truncate(1)
        handle.write(json.dumps({"pid": os.getpid()}).encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
        yield
    finally:
        _unlock(handle)
        with contextlib.suppress(OSError):
            handle.close()


def run_worker_is_alive(run_dir: Path) -> bool:
    """Is a worker still holding this run?

    Absent file = nobody ever claimed it, or the claim predates this mechanism;
    either way there is no live worker to find. Taking the lock proves the same
    thing, and it is released again immediately so the answer costs nothing.
    """
    path = run_dir / LIVENESS_FILENAME
    if not path.exists():
        return False
    try:
        handle = _open_for_locking(path)
    except OSError:
        # Windows can refuse to open a file another process has open exclusively.
        # Unreadable-because-held is still held.
        return True
    try:
        if not _try_lock(handle):
            return True
        _unlock(handle)
        return False
    finally:
        with contextlib.suppress(OSError):
            handle.close()


def run_worker_handle(run_dir: Path) -> RunWorkerHandle | None:
    """The pid recorded alongside the lock, when one was recorded.

    Reads from byte 1 on. Windows locks are MANDATORY, not advisory, so a read
    that spans byte 0 fails outright while a worker holds it — which is exactly
    when the pid matters most. Skipping the locked byte is why the pid was put
    after it.
    """
    path = run_dir / LIVENESS_FILENAME
    try:
        with path.open("rb") as reader:
            reader.seek(1)
            raw = reader.read()
    except OSError:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    pid = payload.get("pid") if isinstance(payload, dict) else None
    return RunWorkerHandle(pid=pid) if isinstance(pid, int) else None
