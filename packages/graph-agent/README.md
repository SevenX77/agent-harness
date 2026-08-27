# graph_agent

`graph_agent` is the current document-driven Python engine in this monorepo. The workspace distribution is `graph-agent` 0.3.1 and requires Python 3.11 or newer.

This README describes the package that exists today. The proposed standalone `graph-skill-runtime` distribution, `graph_skill_runtime` import, `gskill` CLI, Agent Skills entry, and host-native executor are a [drafted future target](../../docs/engine/graph-skill-runtime/v1-alignment.md), not current package features.

## Current responsibility

The engine compiles a skill directory into a typed graph and executes or predicts it. It owns aggregated compile diagnostics, `LOGIC` / `AGENT` / `SUBGRAPH` execution, typed blackboard and I/O, iterate, checkpoints and resume, typed events and traces, artifacts, golden evaluation, resolution, and structured errors.

The current file-format contract is the FROZEN [`00-FORMAT-GROUND-TRUTH.md`](../../docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md). In that contract, the skill root contains `GRAPH.md`; phase files are `LOGIC.md`, `SUBGRAPH.md`, or `SKILL.md`; nested graphs use the root `subgraph/` layout. Pass the skill root directory to the SDK. Do not infer the current format from the drafted extraction target.

Business rules and domain tools belong to the user-owned skill or the host application. The engine supplies domain-agnostic compilation and orchestration. Persistence, model execution, registry truth, and product UI remain explicit host boundaries.

## Install in this workspace

From the agent-harness repository root:

```bash
uv sync --all-packages --all-extras --group dev
```

`graph-agent` is currently a monorepo workspace package. It is not yet published under the future `graph-skill-runtime` PyPI name.

## Use the current SDK

`workspace_dir` is a required, absolute path for `run_skill`, `predict_skill`, and `resume_skill`. A caller can use the default local resolver for a direct skill path or pass `LocalWorkspaceResolver` when it owns search roots.

```python
from pathlib import Path

from graph_agent import compile_skill, run_skill

skill_root = Path("/absolute/path/to/my-skill").resolve()
workspace_dir = (skill_root / ".workspace").resolve()

# The compile path does not run a model.
compile_result = compile_skill(skill_root)

# This form is sufficient for a graph whose executed path has no AGENT phase.
run_result = run_skill(
    skill_root,
    workspace_dir=workspace_dir,
    user_name="Developer",
)
```

For an executed `AGENT` phase, the host must supply model execution explicitly. Pass either an `llm_provider` adapter or a `model_resolver` through the current SDK:

```python
from pathlib import Path

from graph_agent import RunResult, run_skill


def run_with_host_provider(llm_provider) -> RunResult:
    skill_root = Path("/absolute/path/to/my-skill").resolve()
    workspace_dir = (skill_root / ".workspace").resolve()
    return run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        llm_provider=llm_provider,
        user_name="Developer",
    )
```

The example leaves the provider parameter unannotated because the current provider protocol is not a complete top-level public export. In production, pass the concrete provider adapter owned by the host. The engine does not discover an implicit `config/llm_roles.yaml`, built-in role map, or `.env` model route on behalf of SDK callers.

## Public API

`graph_agent.__all__` currently contains exactly 24 exports:

| Name | Current purpose |
| --- | --- |
| `run_skill` | Compile and execute a skill root |
| `predict_skill` | Compile and predict a skill path with controlled model interception |
| `resume_skill` | Resume a checkpointed run |
| `evaluate_golden_baseline` | Evaluate prediction output against golden cases |
| `RunResult` | Unified run/predict result contract |
| `PathDiff` | Predicted-path comparison diagnostics |
| `PhaseRecord` | Per-phase execution or prediction record |
| `compile_artifact` | Compile a skill into a productization artifact |
| `run_artifact` | Execute a compiled artifact |
| `predict_artifact` | Predict a compiled artifact |
| `compile_skill` | Compile and validate a skill with aggregated diagnostics |
| `CompileResult` | Compile diagnostic container |
| `SkillManifest` | Current manifest schema model |
| `serialize_skill` | Serialize a current manifest |
| `assemble_graph` | Assemble a compiled skill into a runnable graph |
| `CompiledSkill` | Compiled skill model |
| `CompiledStateGraph` | Assembled graph wrapper |
| `BlackboardState` | Typed runtime blackboard state |
| `LocalWorkspaceResolver` | Filesystem resolver for local skill roots |
| `GraphAgentError` | Base graph-agent exception |
| `GraphCompileError` | Compile, validation, reference, or contract error |
| `GraphExecutionError` | Runtime, state, tool, or checkpoint error |
| `ModelProviderError` | Model provider or resolver error |
| `ResourceNotFoundError` | Workspace, skill, or resolver resource error |

Internal modules under `graph_agent.core`, `graph_agent.io`, `graph_agent.models`, and similar packages are not top-level SDK commitments. `CallbackEvent`, the complete error catalog, runtime config, and executor seams exist internally but have not yet been promoted into a complete standalone public contract.

## Current CLI

The package has no `[project.scripts]` entry. Its legacy argparse surface is available only through:

```bash
python -m graph_agent --help
```

This module entry is not the future `gskill` console contract. Scripts that need a stable integration today should prefer the 24 exported Python names and pin the current package revision.

## Source layout

```text
graph_agent/
├── __init__.py          # the 24 top-level exports
├── __main__.py          # legacy python -m graph_agent entry
├── py.typed             # PEP 561 marker
├── core/                # compiler, assembler, runner, resolver, errors, checkpoints
├── callbacks/           # typed events and event sinks
├── runtime/             # runtime state
├── io/                  # run layout, artifacts, and I/O adapters
├── cognitive/           # current embedded agent-loop controls
├── middleware/          # current embedded execution middleware
├── models/              # model-resolution internals
├── tools/               # domain-agnostic orchestration tools
├── tracing/             # trace support
├── skills/              # engine-owned internal skills
└── examples/            # package examples and fixtures
```

There is no `GraphAgentHarness` public export and no `core/harness.py` in the current package.

## Verification and design references

The package ships `py.typed`, and CI runs `mypy --strict` over its source in addition to ruff, tests, manifest validation, and dependency audit.

- [Current engine MVP1 design index](../../docs/engine/mvp1/INDEX.md)
- [Current FROZEN file-format contract](../../docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md)
- [Standalone extraction baseline](../../docs/engine/graph-skill-runtime/baseline.md)
- [Drafted standalone v1 target](../../docs/engine/graph-skill-runtime/v1-alignment.md)

## License

Apache-2.0; see the repository root `LICENSE`.
