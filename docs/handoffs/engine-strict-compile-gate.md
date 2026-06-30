# Engine Strict Compile Gate Handoff

Use this prompt when continuing or reviewing the engine strict compile gate work.

## Goal

Make `packages/graph-agent` compile act as the first strict source gate for defects that can be proven before assemble/run. The gate should reject invalid skill source instead of allowing later engine runtime failures or silent partial outputs.

## Required Reading

- `AGENTS.md`
- `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`
- `.kiro/specs/engine-strict-compile-gate/requirements.md`
- `packages/graph-agent/src/graph_agent/core/loader.py`
- `packages/graph-agent/tests/core/test_strict_compile_gate.py`

## Scope

- Remove Agent `phase_config` compatibility behavior.
- Enforce root and phase inline IO as strict JSON Schema object contracts.
- Compile-check static dataflow for required phase inputs and required root outputs.
- Compile-check declared Agent tools and declared reference/example files.
- Require LOGIC actions to accept `inputs`, treat `inputs` as read-only, and return declared output keys.
- Prevent action/tool imports from writing `__pycache__` into skill source folders.
- Migrate graph-agent tests, fixtures, and live sample skills to the strict source contract.

## Non-Goals

- Do not make pure engine compile depend on gateway role truth. `llm_role` reachability belongs to Studio strict compile/run preflight when a gateway role resolver is injected.
- Do not validate actual run input values at source compile. Runtime values are checked by run preflight/invoke.
- Do not execute validators/actions during compile.

## TDD Anchors

Start with or preserve RED tests in:

- `packages/graph-agent/tests/core/test_strict_compile_gate.py`

Focused verification:

```powershell
uv run pytest packages/graph-agent/tests/core/test_strict_compile_gate.py -q
uv run pytest packages/graph-agent/tests/core -q
uv run pytest packages/graph-agent/tests/integration/skills packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py packages/graph-agent/tests/tools/test_builtin_resource_tools.py packages/graph-agent/tests/callbacks/test_ws_e4_runtime_edge_events_red.py -q
uv run ruff check packages/graph-agent/src packages/graph-agent/tests
uv run mypy --strict packages/graph-agent/src
```

Live skill compile probe should include:

- `skills/text-segmentation`
- `skills/event-extraction`
- `skills/batch-analysis`
- `skills/global-synthesis`
- `skills/story-deconstruction`

## Known Local Windows Noise

Full `uv run pytest packages/graph-agent/tests -q` may still fail on this Windows workstation for existing environment/baseline issues unrelated to strict compile: POSIX path expectations, shell script executable-bit checks, GBK default decoding of UTF-8 YAML, and audited doc hash drift in files not touched by this work.
