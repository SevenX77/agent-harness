"""Shared fixtures + import-time invariants for the graph_agent suite.

The middleware-chain topological order regression test lives in
``tests/graph_agent/middleware/test_chain_topology.py`` so pytest
collects it as part of the full suite (``conftest.py`` is treated as
a fixtures file and tests inside it do not run during a full
``pytest tests/graph_agent/`` invocation). The import below acts as
an import-time sanity check — if the middleware package fails to
import (e.g., a missing module after a refactor), every test in the
suite errors out at collection rather than producing a confusing
runtime failure deep in a single test case.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from graph_agent.core import SkillResolutionError

# Import-time sanity: ensure the MVP-3 middleware package is importable
# before any test runs. The actual ordering assertions live in the
# adjacent ``middleware/test_chain_topology.py`` test file.
from graph_agent.middleware import DEFAULT_MIDDLEWARE_ORDER  # noqa: F401

collect_ignore_glob = [
    "core/test_manifest.py",
    "integration/test_mvp2_schema_io.py",
]


class InMemorySkillResolver:
    def __init__(self, roots: dict[str, Path]) -> None:
        self.roots = roots

    def resolve_skill(self, skill_id: str) -> Path:
        try:
            return self.roots[skill_id]
        except KeyError as exc:
            raise SkillResolutionError(skill_id, "not registered") from exc


@pytest.fixture
def in_memory_skill_resolver_factory() -> Callable[[dict[str, Path]], InMemorySkillResolver]:
    return InMemorySkillResolver

_V1_SKILL_AWAITING_CUTOVER = [
    "tests/core/test_t11_phase_token_info.py",
    "tests/integration/test_mvp1_smoke.py",
    "tests/tools/test_dual_run_shadow.py",
]

_V1_SKILL_AWAITING_CUTOVER_TESTS = {
    "tests/core/test_module_sandbox.py::test_loader_pipeline_resolves_skill_forward_ref_segment_class",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    xfail_marker = pytest.mark.xfail(
        reason="by-design: legacy repo skill awaiting V0.3.0 fixture migration",
        strict=False,
    )
    tests_root = config.rootpath
    if not (tests_root / "tests").exists() and (tests_root / "packages/graph-agent/tests").exists():
        tests_root = tests_root / "packages/graph-agent"
    for item in items:
        nodeid = str(item.path.relative_to(tests_root))
        full_nodeid = f"{nodeid}::{item.name}"
        if full_nodeid in _V1_SKILL_AWAITING_CUTOVER_TESTS:
            item.add_marker(xfail_marker)
            continue
        if any(nodeid.startswith(pattern) for pattern in _V1_SKILL_AWAITING_CUTOVER):
            item.add_marker(xfail_marker)
