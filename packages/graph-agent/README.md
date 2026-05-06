# graph_agent

Self-contained multi-phase Agent orchestration engine, located at `src/core/graph_agent/`.

Its sole responsibility: execute SKILL.md-described workflows reliably. The underlying agent loop reuses DeerFlow, while the outer layer is handled by `GraphAgentHarness` for phase orchestration, cognitive constraints, validation/retry, tracing, and I/O boundaries.

---

## Core Principles

1. **DeerFlow source code is not lightly modified**
   `graph_agent`'s core agent loop comes from the embedded DeerFlow. Unless it's an upstream bug or required compatibility fix, we solve problems through outer harness, callbacks, configuration, and skill design.

2. **Framework layer contains no business logic**
   `graph_agent` only provides general orchestration: Phase, tool wrappers, model resolution, tracing, context compression, validation/retry. Business-specific tools, field semantics, and domain rules should be written in the skill directory.

3. **Kitchen-pass pattern**
   Phase results are written to `WorkflowState.context` first. Actual persistence is done by `IOManager` through `file` output or `artifact_saver` injected by the caller. The framework only prepares the "food", without directly depending on the host project's file management implementation.

4. **Dual-layer control architecture**
   - Inner layer: DeerFlow middleware handles real-time intervention within each `agent.invoke()` (working memory, dead-end pruning, clarification)
   - Outer layer: `GraphAgentHarness` while-loop handles planning nudges, selfcheck nudges, checkpoint compaction, and finish gates between invokes

5. **Concurrency via subagent**
   Phase-level concurrency uses DeerFlow subagents, currently following DeerFlow's `SubagentExecutor(max_workers=3)`. `graph_agent` no longer maintains an independent `max_concurrent` parameter chain.

6. **Multimodal tools are general capabilities**
   Tools under `tools/` for images, video, and voice remain in the framework layer as they are cross-project reusable capabilities, not business-specific logic.

---

## Quick Start

### 1. Install Dependencies

Use `src/core/graph_agent/requirements.txt` to install minimal runtime dependencies.

**Python Version Requirement**: Minimum **Python 3.12**.
This is not due to `graph_agent` syntax itself, but because the embedded DeerFlow depends on `typing.Self`, `typing.override`, and newer typing behaviors. Below 3.12, the most common symptom is `checkpointer="auto"` automatically downgrading to no checkpoint.

### 2. Provide Configuration

Minimum required files:
- `config/llm_roles.yaml`
- `.env`

Optional:
- `config/deerflow_config.yaml`
- `config/multimodal_roles.yaml`

`llm_roles.yaml` lookup order:
1. Environment variable `GRAPH_AGENT_ROLES_PATH`
2. Upward search for `config/llm_roles.yaml`
3. Built-in minimal default config

### 3. Verify Installation

Run the hello_world example:

```bash
export PYTHONPATH="${PYTHONPATH}:./src"
python3 -c "
from src.core.graph_agent import run_skill
result = run_skill(
    'src/core/graph_agent/examples/hello_world/SKILL.md',
    initial_context={'user_name': 'Developer'}
)
print('Success:', result.get('greeting', 'No greeting'))
"
```

### 4. Choose Entry Point

- `run_skill()`: Most common entry point for direct SKILL.md execution
- `load_workflow_from_md()`: When you need to compile a skill first and reuse the harness
- `GraphAgentHarness`: When you want to hand-write Phase lists

---

## Public API

- `run_skill` — generic Skill runner
- `clear_cache` — clear harness cache
- `GraphAgentHarness` — main orchestrator
- `Phase` — phase definition dataclass
- `WorkflowState` — typed state
- `load_workflow_from_md` — compile SKILL.md into a harness
- `ModelResolver` — role-based model selection
- `get_model_resolver` — singleton accessor
- `get_skill_type` — detect skill type from SKILL.md
- `ContextResolver` — context mapping resolver
- `IOManager` — input/output management
- `Callback` — base callback class
- `LoggingCallback` — structured log output
- `TracingCallback` — JSONL trace output
- `MetricsCallback` — execution metrics
- `GraphAgentError` — base exception
- `SkillLoadError`, `SkillCompilationError`, `TemplateRenderError`, `AllProvidersFailedError`, `MaxRetriesExceededError`

---

## Directory Structure

```text
graph_agent/
├── __init__.py              # Public API re-export
├── py.typed                  # mypy type marker
├── requirements.txt
├── README.md
│
├── core/                     # Core orchestration engine
│   ├── harness.py           # GraphAgentHarness
│   ├── runner.py            # run_skill
│   ├── loader.py            # load_workflow_from_md
│   ├── compiler.py          # compile_skill
│   ├── state.py             # WorkflowState
│   ├── types.py             # Phase, ContextBridge
│   ├── exceptions.py        # GraphAgentError hierarchy
│   ├── parser.py            # SKILL.md parser
│   ├── template.py          # Template rendering
│   ├── callback_bridge.py   # LangChain → GraphAgent bridge
│   ├── subgraph.py          # Subgraph node builder
│   └── tool_wrapper.py      # Tool → LangChain wrapper
│
├── callbacks/                # Observability callbacks
│   ├── base.py              # Callback base class
│   ├── logging_cb.py        # LoggingCallback
│   ├── metrics.py           # MetricsCallback
│   └── tracing.py           # TracingCallback
│
├── cognitive/                # Cognitive control
│   ├── finish.py            # finish_task + nudges
│   ├── memory.py            # update_working_memory
│   ├── ambiguity.py         # log_ambiguity
│   ├── prompt.py            # apply_cognitive_template
│   └── middlewares.py       # PAOR/WorkingMemory/DeadEnd
│
├── config/                   # Configuration loading
│   ├── llm_config.py        # LLM role config
│   └── multimodal_config.py # Multimodal config
│
├── models/                   # Model resolution
│   ├── resolver.py          # ModelResolver
│   └── reasoning_patch.py   # DeepSeek/ARK monkey-patch
│
├── io/                       # Declarative I/O
│   ├── manager.py           # IOManager
│   ├── context_resolver.py  # ContextResolver
│   └── skill_analyzer.py  # get_skill_type
│
├── tools/                    # Multimodal tools
│   ├── providers.py         # Shared provider helpers
│   ├── generate_image.py
│   ├── generate_video.py
│   ├── understand_video.py
│   └── synthesize_speech.py
│
├── skills/                   # Built-in skills
│   └── compiler/
│
├── deerflow/                 # Embedded DeerFlow (unchanged)
├── docs/                     # Documentation
└── examples/                 # Runnable examples
    └── hello_world/
```

---

## Internal Naming Conventions

To prevent module bloat, internal helpers use consistent naming:
- `_build_*`: Construct nodes, configurations, or composite structures
- `_ctx_*`: Defensive read/normalization of context fields
- `_phase_*`: Type narrowing when parsing `phase_config`
- `_extract_*`: Extract structured fragments from messages, responses, or documents
- `_normalize_*`: Unify external return values to internal framework format

Exposed objects use nouns or clear verbs:
- `GraphAgentHarness`
- `Phase`
- `run_skill`
- `load_workflow_from_md`

Skill-local tools should use `verb_object` style:
- `collect_scene_context`
- `render_html_report`
- `summarize_alignment`

---

## Migrating to a New Project

Minimal migration steps:
1. Copy `src/core/graph_agent/`
2. Install `requirements.txt`
3. Provide `config/llm_roles.yaml` and `.env`
4. Place business tools in skill directory, not in the framework layer
5. If you need to connect to the host project's artifact system, inject via `artifact_saver`

---

## Extended Documentation

- `docs/SKILL_AUTHORING_GUIDE.md` — How to write SKILL.md
- `docs/TOOL_DEVELOPMENT_GUIDE.md` — How to develop tools
- `docs/INTEGRATION_GUIDE.md` — Integration guide
- `docs/CONFIG_REFERENCE.md` — Configuration reference (llm_roles.yaml, multimodal_roles.yaml)
- `docs/COGNITIVE_LOOP_GUIDE.md` — Cognitive control architecture

---

## Type Safety

`graph_agent` includes `py.typed` for PEP 561 compliance. Use with mypy:

```bash
mypy src/core/graph_agent/ --exclude deerflow
```

---

## License

See DeerFlow LICENSE in `deerflow/LICENSE`.
