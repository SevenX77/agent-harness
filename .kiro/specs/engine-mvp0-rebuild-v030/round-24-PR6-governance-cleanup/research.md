# PR-6: Governance and Cleanup Research

## Empirical Findings and Evidence

### 1. `parse_skill_file` Exposes Dangerous and Unused Surface
- **Evidence:** `parse_skill_file` in `packages/graph-agent/src/graph_agent/core/parser.py` currently immediately calls `_fatal(...)` stating "schema 2.0 parse_skill_file is not supported; use GRAPH.md" (L239).
- **Caller Analysis:** A workspace-wide grep (`grep_search(pattern="parse_skill_file", filter="*.py")`) confirmed exactly **0** real-world callers. The only references are:
    - Its definition and `__all__` export in `core/parser.py` (L237, L248).
    - Docstring mentions in the package root `__init__.py` (L14) and `core/parser.py` (L5, L49). Note: it is NOT exported in `__init__.py`'s `__all__`.
    - The dedicated test file `tests/core/test_parse_skill_file.py` (L9 import, L65-70 test function). The file also contains 4 live tests for `parse_markdown_parts` which must be preserved.

### 2. `skill_validator.py` is Verified Dead Code
- **Evidence:** The file `packages/graph-agent/src/graph_agent/core/skill_validator.py` exists and is 6673 bytes long.
- **Caller Analysis:** A workspace-wide grep (`grep_search(pattern="skill_validator", filter="*.py")` and specifically searching for imports) returned **0** imports. The only mention of this file is in a comment inside `packages/graph-agent/src/graph_agent/middleware/cognitive_flow.py` at L519:
  > `# The compile-time gate in skill_validator.py rejects validator-...`

### 3. `mvp0-alignment.md` Documentation Hallucination
- **Evidence:** In `docs/engine/skill-compilation/mvp0-alignment.md`, around line 317, there is a conceptual definition for a `DehydratedCompiledSkill` Pydantic model which includes a `schema_version` field.
- **Reality Check:** A workspace-wide search for `DehydratedCompiledSkill` confirmed **0** hits in source code. The compilation caching in PR-4 actually relies on a standard dictionary round-trip strategy with `cache key format v2`, not a specialized `DehydratedCompiledSkill` BaseModel. The documentation is an outdated conceptual illustration.