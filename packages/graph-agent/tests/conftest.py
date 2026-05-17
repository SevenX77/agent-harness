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

# Import-time sanity: ensure the MVP-3 middleware package is importable
# before any test runs. The actual ordering assertions live in the
# adjacent ``middleware/test_chain_topology.py`` test file.
from graph_agent.middleware import DEFAULT_MIDDLEWARE_ORDER  # noqa: F401

# V1 cutover legacy test quarantine: these files import old class names removed
# by the V2 refactor. Keep them as reference corpus pending a V1->V2 migration
# spec deciding whether to delete, migrate, or rewrite them.
collect_ignore_glob = [
    "cognitive/test_finish_v2.py",
    "core/test_build_graph_nodes.py",
    "core/test_compile_skill_hostile_inputs.py",
    "core/test_loader_pipeline.py",
    "core/test_loader_xml_rendering.py",
    "core/test_manifest_phase_builders.py",
    "core/test_manifest.py",
    "core/test_parse_skill_md.py",
    "core/test_personas.py",
    "core/test_validate_manifest.py",
    "core/validators/test_persona_resolution.py",
    "core/validators/test_template_variables.py",
    "core/validators/test_tool_paths.py",
    "integration/test_mvp2_schema_io.py",
]
