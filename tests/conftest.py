"""Project-wide pytest fixtures and session teardown.

DeerFlow subagent pool preventative guard
-----------------------------------------

The vendored DeerFlow ``subagents.executor`` module exposes two
module-level ``ThreadPoolExecutor`` singletons (``_scheduler_pool`` /
``_execution_pool``) with default (``daemon=False``) worker threads.
If any test submits into them, interpreter shutdown will block until
the workers finish their *current* task — and cannot be unblocked by
either the ``wait=False`` flag on ``executor.shutdown`` or by flipping
the worker threads to ``daemon=True``.

Why daemon=True does NOT help for ThreadPoolExecutor workers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``concurrent.futures.thread`` registers an atexit handler
(``_python_exit``) via ``threading._register_atexit``. That handler
walks ``_threads_queues`` and calls ``t.join()`` on every worker
thread it owns, *regardless of the thread's daemon flag*. So even a
daemon-flagged worker still blocks interpreter exit until its current
task completes. Monkey-patching ``threading.Thread`` to force
``daemon=True`` on DeerFlow workers was verified to give 0s of
shutdown improvement under an in-flight task (pool_long_task.py
experiment, 2026-04-24): identical 4.35s + N seconds of sleep with or
without the patch, where ``N`` is the remaining task time.

What this fixture actually does
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
At session end, ``pool.shutdown(wait=False, cancel_futures=True)``
refuses new submits and drops any *pending* (never-started) futures.
Already-running workers still have to finish their current task —
but that is far better than the default behavior (leaving the pool
open so ``_python_exit`` walks it with ``t.join()``).

Real fix directions (tracked in deferred-items.md as engine debt)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. Upstream DeerFlow change: replace the module-level ThreadPoolExecutor
   singletons with an asyncio-backed scheduler, or with an explicitly
   owned pool the harness can ``close()`` at the end of each run.
2. Orchestration-level isolation: per-task OS scope that can SIGKILL
   the whole process group at task end (see
   ``claude-ccb-scope-orchestration-plan.md``). Under that model the
   Python-level hang becomes a non-issue because the kernel reaps
   everything.

As of 2026-04-24 the test suite (197 tests) does not submit into these
pools, so the fixture does nothing observable today. It's a
preventative guard for the moment integration tests start exercising
the subagent subsystem.

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
            # module docstring for why daemon=True doesn't help).
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            # Best-effort teardown; swallowing here doesn't hide a
            # test failure, only keeps shutdown moving forward.
            pass
