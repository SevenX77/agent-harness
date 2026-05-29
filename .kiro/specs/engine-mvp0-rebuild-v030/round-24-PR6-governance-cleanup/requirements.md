# PR-6: Governance and Cleanup Requirements

## Requirements

- **Req-1 [NEW]:** The `parse_skill_file` function MUST be completely removed from `packages/graph-agent/src/graph_agent/core/parser.py`.
- **Req-2 [NEW]:** The `parse_skill_file` function MUST be removed from `__all__` in `core/parser.py`. Any docstring mentions in `core/parser.py` and `packages/graph-agent/src/graph_agent/__init__.py` MUST also be removed.
- **Req-3 [NEW]:** In `packages/graph-agent/tests/core/test_parse_skill_file.py`, ONLY the single test function `test_parse_skill_file_is_removed_schema20_api` (lines 65-70) and its import on line 9 MUST be deleted. The file itself and the other 4 live tests for `parse_markdown_parts` MUST be preserved.
- **Req-4 [NEW]:** The file `packages/graph-agent/src/graph_agent/core/skill_validator.py` MUST be deleted. Furthermore, the corresponding entry `"graph_agent.core.skill_validator",` MUST be removed from the mypy legacy quarantine list in `pyproject.toml:104`.
- **Req-5 [NEW]:** The misleading comment at `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py:519` MUST have its invalid reference to the dead file `skill_validator.py` removed. The comment MUST NOT be rewritten to point to a different "live gate" (to avoid hallucinations); it should simply preserve the defensive reasoning that "if finish_task validation misses a schema, it's an upstream wiring error and must fail-loud".
- **Req-6 [NEW]:** The outdated documentation in `docs/engine/skill-compilation/mvp0-alignment.md:317-330` MUST be rewritten. The reference to the non-existent `DehydratedCompiledSkill` Pydantic model MUST be removed and replaced with an accurate description of the current dictionary round-trip caching mechanism and the v2 cache key format.

## Acceptance Criteria

1.  **API Surface Reduced:** A search for `parse_skill_file` yields zero results in the `src/` directory.
2.  **Dead Code Eliminated:** The file `core/skill_validator.py` no longer exists, no comments reference it, and its quarantine entry in `pyproject.toml` is removed.
3.  **Documentation Accurate:** `docs/engine/skill-compilation/mvp0-alignment.md` accurately describes the caching mechanism without referring to `DehydratedCompiledSkill`.
4.  **Zero Regressions:** All existing tests pass. The changes are strictly subtractive and corrective.