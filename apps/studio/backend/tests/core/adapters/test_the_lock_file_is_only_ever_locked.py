"""The runtime-state lock file is locked, never written.

`cross-platform-smoke (windows-latest)` went red at random on
`test_runtime_state_store_multiprocess_first_acquire_allows_only_one_owner`:
one of the eight racing workers came back with a bare
`PermissionError(13, 'Permission denied')` instead of the
`state.lease_conflict` the store's contract promises. Seen on `main` at
2026-08-20 23:17 (run 32428036298) and on 2026-08-19 (run 32227500016), so it
predates any single PR and it blocks a required gate for everyone.

The cause was in `_platform_lock_file`'s Windows branch, which opened with
"make sure there is a byte here to lock":

    file.seek(0, os.SEEK_END)
    if file.tell() == 0:
        file.write(b"\\0")
        file.flush()

That write sits outside the lock **and** outside the `try` that classifies
PermissionError as contention. On a cold start every worker sees a 0-byte file
at once; the one that wins locks byte 0, and a straggler whose `tell()` read 0
before that write lands then writes byte 0 itself. Windows answers a write into
a locked range with ERROR_LOCK_VIOLATION, which Python surfaces as
`PermissionError(13)` — untyped, escaping the `StudioAdapterError` contract
every caller of this module is written against.

Measured on the Windows 11 dev box rather than assumed:

  - locking a **0-byte** file with `msvcrt.locking(LK_NBLCK, 1)` succeeds, so
    the byte was never needed. Windows documents locking a range past EOF as
    legal (`LockFileEx`), and `fcntl.flock` never cared about size at all.
  - writing a byte another handle holds a lock on raises exactly
    `PermissionError(13, 'Permission denied')` — the CI error, reproduced.

So the fix is a deletion, not a wider `except`: with nothing writing to the
file, there is no write to lose the race. These two tests pin the property that
makes it impossible, rather than trying to re-stage an eight-way cold-start race
and hoping it loses.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.core.adapters.runtime_state_store_local import (
    LocalRuntimeStateStore,
    _platform_lock_file,
    _platform_unlock_file,
)


def _lock_file_of(root: Path, run_id: str) -> Path:
    return root / "runs" / run_id / ".runtime_state.lock"


def test_a_full_lease_cycle_leaves_the_lock_file_empty(tmp_path: Path) -> None:
    """Nothing writes into the byte the lock is taken on.

    Size, not content, is the assertion: a single stray byte is all it took, and
    a byte is what a reader would otherwise have to notice is missing.
    """
    store = LocalRuntimeStateStore(root=tmp_path)
    lease = store.acquire_lease(run_id="run-lock-shape", owner_id="owner-a", ttl_ms=30_000)
    store.heartbeat(run_id="run-lock-shape", lease=lease)
    store.snapshot(run_id="run-lock-shape", state={"step": 1}, lease=lease)

    lock_file = _lock_file_of(tmp_path, "run-lock-shape")
    assert lock_file.exists(), "the store should have created its lock file"
    assert lock_file.stat().st_size == 0, (
        "something wrote into the lock file. Whatever writes there races the "
        "process holding the lock on that same byte, and on Windows that write "
        "comes back as a bare PermissionError(13) instead of the store's typed "
        "lease conflict"
    )


def test_an_empty_lock_file_can_be_locked(tmp_path: Path) -> None:
    """The premise the deletion rests on, checked instead of assumed.

    If a platform ever needs a byte present before it will lock, this fails
    here — loudly and in one place — rather than as an intermittent red on a
    required gate.
    """
    lock_file = tmp_path / ".runtime_state.lock"
    lock_file.touch()
    assert lock_file.stat().st_size == 0

    with open(lock_file, "a+b") as handle:
        _platform_lock_file(handle)
        try:
            assert os.path.getsize(lock_file) == 0, (
                "taking the lock grew the file, so the lock path is writing again"
            )
        finally:
            _platform_unlock_file(handle)
