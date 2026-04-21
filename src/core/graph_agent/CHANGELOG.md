# Changelog

## [1.0.0] - 2026-04-05

### Fixed
- **compiler.py**: P012 code-only phase validation was outside the per-node loop, only checking the last node
- **resolver.py**: `AllProvidersFailedError` imported from non-existent `models/exceptions.py` — fixed to `core/exceptions.py`
- **resolver.py**: `_fallback_to_deerflow_native` used unsafe global hook swap — replaced with thread-safe `_bypass_hook` parameter
- **generate_image.py**: Added `openai_compatible_image` provider type handler (used by OC_GEMINI)
- **harness.py**: `_clone_state` now uses `copy.deepcopy` for context to prevent cross-phase mutation
- **finish.py**: Narrowed bare `except Exception` to `(json.JSONDecodeError, ValueError, TypeError)`
- **middlewares.py**: Silent `except Exception: pass` in callback loop now logs at WARNING level
- **ambiguity.py**: `ctx is None` path now logs a warning instead of silent return
- Removed 2 stale test files referencing deleted modules (`test_tool_executor_parallel.py`, `test_llm_gateway.py`)
- Fixed 5 fragile integration tests that hardcoded model names
- Replaced 21 `print()` calls across deerflow/ with proper `logging` calls
- Fixed silent `except Exception: pass` in `deerflow/sandbox/tools.py` and `deerflow/skills/loader.py`

### Added
- `__init__.py`: Exported `Callback`, `LoggingCallback`, `MetricsCallback`, `TracingCallback`, `clear_cache`
- `__main__.py`: Support for `python -m graph_agent`
- `pyproject.toml`: Package metadata for standalone installation
- `config/__init__.py`: Exported `reset_multimodal_role_config`
- This CHANGELOG

### Changed
- `requirements.txt`: Documented DeerFlow-patched langchain requirement (>=1.2)
- Documentation: All import examples now use `from graph_agent import` (standalone-friendly)
- `runner.py`: Replaced parent-project-specific paths with generic examples
- `runner.py`: State directory renamed from `pipeline_state` to `graph_agent_state`
- `reasoning_patch.py`: Removed duplicate `_deerflow_hook_lock` definition
- `resolver.py`: Updated deprecated `langchain.chat_models` import path
- `middlewares.py`: `CognitivePAORMiddleware` marked as deprecated in docstring

### Known Technical Debt
- `harness.py` is 886 lines (exceeds 300-line guideline) — planned for future split
- `deerflow/` and `core/parser.py` have parallel SKILL.md frontmatter validation with different allowed key sets (by design: discovery-layer vs orchestration-layer)
- Multimodal tool tests (`generate_video`, `synthesize_speech`, `understand_video`) have no unit tests
