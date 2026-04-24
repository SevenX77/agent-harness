"""Project-wide pytest fixtures and session teardown.

Currently handles partial thread-pool cleanup for the vendored DeerFlow
``subagents.executor`` module. That module exposes two module-level
``ThreadPoolExecutor`` singletons (``_scheduler_pool`` /
``_execution_pool``) whose worker threads are ``daemon=False``. If
any test submits into them, the interpreter's shutdown will block
for up to a few seconds at exit waiting for the workers to drain.

Limitations of the fixture:
- ``ThreadPoolExecutor.shutdown(wait=False)`` only refuses new tasks;
  already-running workers still have to finish. Non-daemon workers
  therefore still delay interpreter exit by whatever the longest
  in-flight submission needs. We can't flip them to daemon=True after
  start (Python disallows mutating a live thread's ``daemon`` flag).
- Truly fixing this needs an upstream DeerFlow change (construct
  pools with a daemon-thread-factory) or a monkey-patch at import
  time; tracked under engine debt, not fixed here.
- Current test suite (as of the P0/P1 wave) does *not* submit into
  these pools, so the shutdown cost is 0. The fixture is a
  preventative guard for the moment future integration tests start
  using the subagent subsystem.

We do not patch the vendored file (see
``src/core/graph_agent/deerflow/NOTICE.md`` — all MODIFIED areas are
listed there so upstream sync stays auditable).
"""
from __future__ import annotations

import sys

import pytest


@pytest.fixture(scope="session", autouse=True)
def _shutdown_deerflow_subagent_pools():
    """Cancel pending futures in DeerFlow subagent pools at session end."""
    yield
    module = sys.modules.get("graph_agent.deerflow.subagents.executor")
    if module is None:
        return
    for attr in ("_scheduler_pool", "_execution_pool"):
        pool = getattr(module, attr, None)
        if pool is None:
            continue
        try:
            # wait=False + cancel_futures=True drops pending work;
            # running workers still have to finish naturally (see
            # module docstring for why we can't do better here).
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            # Best-effort teardown; swallowing here doesn't hide a
            # test failure, only keeps shutdown moving forward.
            pass
