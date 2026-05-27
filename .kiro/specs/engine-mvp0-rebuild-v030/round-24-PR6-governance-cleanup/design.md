# PR-6: Governance and Cleanup Design

## Overview
This PR handles the zero-risk governance and cleanup tasks identified during WS3 auditing. These tasks are purely subtractive (removing dead code/APIs) and corrective (fixing outdated documentation), focusing on removing technical debt and outdated information.

## Key Design Decisions

- **D1. Safe Removal of Deprecated Parser APIs:** The `parse_skill_file` function in `core/parser.py` was previously gutted to only raise a `_fatal` error. Since it has no actual callers in the workspace outside of a single dedicated test, its definition (`parser.py:237-239`), its `__all__` export (`parser.py:248`), and its docstring mentions will be removed to reduce API surface.
- **D2. Dead Code Elimination (`skill_validator.py`):** The `skill_validator.py` file is unused. A comprehensive search confirmed 0 imports across the codebase. It will be safely deleted, and its leftover configuration in `pyproject.toml` will be cleaned up.
- **D3. Comment and Documentation Cleanup:** 
    - The misleading comment referring to `skill_validator.py` in `middleware/cognitive_flow.py:519` will be corrected to remove the false dead-file reference without inventing new hallucinated gates.
    - The outdated documentation in `docs/engine/skill-compilation/mvp0-alignment.md:317` regarding `DehydratedCompiledSkill` and its `schema_version` will be corrected to reflect the actual caching implementation (dict round-trip with version switching in the cache key format v2).

## Field Heritage Table

| Entity / API | Current State | Target Design | Tag | Migration Path |
| :--- | :--- | :--- | :--- | :--- |
| `parse_skill_file` | API exists in `core/parser.py`, but only raises `_fatal`. | Removed. | `[NEW]` | Remove its definition and `__all__` entry in `parser.py`, remove docstring mentions in `parser.py` and `__init__.py`. In `test_parse_skill_file.py`, only delete the L65-70 test function and L9 import (keep the file and live tests). |
| `skill_validator.py` | Exists in `core/`, ~6KB size, 0 callers. | Deleted. | `[NEW]` | Delete the file. Update the misleading comment in `middleware/cognitive_flow.py:519`. Remove `"graph_agent.core.skill_validator",` from the mypy quarantine list in `pyproject.toml:104`. |
| `DehydratedCompiledSkill` | Outdated conceptual model in `mvp0-alignment.md`. | Corrected documentation. | `[NEW]` | Direct modification of `docs/engine/skill-compilation/mvp0-alignment.md:317` to accurately reflect the Dict serialization approach. |

## Defect Classification
All issues addressed in this PR are **implementation defects** or **documentation defects**. They represent leftover artifacts from previous architectural shifts rather than fundamental design flaws in the current target architecture.