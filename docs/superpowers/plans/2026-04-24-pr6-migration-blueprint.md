# PR #6 Blueprint — Schema 1.x → 2.0 Big-Bang Migration

Date: 2026-04-24
Authors: Claude (engineering), Gemini (architecture), SevenX (product)
Supersedes: the migration sketch in `2026-04-22-graph-agent-studio.md` Task 0.3 Step 2–4.

## Why this document exists

PR #5 (branch `feat/studio-phase0-manifest`) lands the schema 2.0 foundation in four commits:

- `ce44037` — three-axis manifest (agent/graph/persona × llm/logic/delegate)
- `df32e83` — `serialize_skill()` reverse-serialisation
- `c697021` — `parse_skill_file()` forward entry
- `640f4e5` — `user_prompt_template` + agent `tier`/`model_override`

PR #6 is the **big-bang migration** that carries the production runtime across the 1.x→2.0 boundary:

- Rewrite `loader.py` (705 lines) to be manifest-driven, zero XML body parsing.
- Rewrite `compiler.py` (1137 lines) to consume `SkillManifest` instead of raw `frontmatter` + tag dicts.
- Delete or shrink `deerflow/skills/parser.py` (80 lines) — duplicated validation site.
- Migrate **all production SKILL.md files** in `skills/` to schema 2.0 (pure YAML frontmatter, no XML body).
- Delete the schema-1.x scaffolding inside `parser.py` (`_extract_tags`, `_split_by_phase_headers`, `_normalise_phase_tags`, `_resolve_refs`, `_validate_frontmatter`) once no caller needs it.

Explicit user directive (2026-04-24): "不需要兼容,一次性改造一步到位。"
Therefore: **no backwards-compat shim, no `schema_version` branching inside the loader.** A single code path, a single vocabulary, enforced by the new manifest.

## Field map — runtime `Phase` ↔ schema 2.0

Source: `src/core/graph_agent/core/types.py:27`.

| Runtime `Phase` field         | Schema-2.0 source                            | Notes                                                                    |
| ----------------------------- | -------------------------------------------- | ------------------------------------------------------------------------ |
| `name: str`                   | `LLMPhase.name` / `LogicPhase.name` / `DelegatePhase.name` | Identical.                                                  |
| `system_prompt: str \| None`  | `LLMPhase.prompt`                            | Rename at the boundary.                                                  |
| `user_prompt_template: str \| None` | `LLMPhase.user_prompt_template`        | Added in commit `640f4e5`.                                               |
| `tools: list[Callable]`       | `LLMPhase.agent_tools` → resolver; `LogicPhase.execute_steps` → resolver | The import-path strings are resolved to callables by `_resolve_tool_reference`. |
| `max_iterations: int = 20`    | `LLMPhase.max_iterations`                    | Default stays in `Phase`, not in the manifest.                           |
| `max_tool_calls: int = 0`     | (no direct schema field)                     | **Gap** — no production skill sets this today; leave as dataclass default. |
| `tier: str = "balanced"`      | `LLMPhase.tier` / `AgentSkillDef.tier`       | Agent skills promote the phase-level tier to the artifact level.         |
| `model_override: str \| None` | `LLMPhase.model_override` / `AgentSkillDef.model_override` | Added at agent level in commit `640f4e5`.                    |
| `validator: Callable \| None` | `LLMPhase.validator` / `LogicPhase.validator` | Import path → callable.                                                  |
| `retry_target: str \| None`   | `LLMPhase.retry_target`                      | Identical.                                                               |
| `max_retries: int = 3`        | `LLMPhase.max_retries`                       | Default stays in dataclass.                                              |
| `max_nudges: int = 1`         | `LLMPhase.max_nudges`                        | Default stays in dataclass.                                              |
| `dead_end_threshold: int = 3` | (no direct schema field)                     | **Gap** — only `test-segmentation` uses it; consider adding if a second skill needs it. |
| `data_architecture: str \| None` | *(migrate into `LLMPhase.prompt`)*        | Not a schema field. Migration concatenates the old `<data_architecture>` content onto the system prompt with a `## Output Format` heading. |
| `subagent_enabled: bool`      | `LLMPhase.subagent_enabled` / `AgentSkillDef.subagent_enabled` | Identical.                                                      |
| `subgraph: GraphAgentHarness \| None` | `DelegatePhase.subgraph` (resolved via loader recursion) | The manifest holds a path string; loader turns it into a harness. |
| `context_bridge: ContextBridge \| None` | `DelegatePhase.context_bridge`     | Identical shape.                                                         |
| `output_schema: type[BaseModel] \| None` | `LLMPhase.output_schema` (resolver)  | Import path → class.                                                     |
| `output_schema_path: str \| None` | *(drop)*                                 | Runtime detail, not part of the skill contract.                          |
| `md_type_dict: str \| None`   | *(drop)*                                     | Runtime detail.                                                          |
| `requires_llm: bool = True`   | *(derived from `mode`)*                      | `mode=="logic"` → `False`; else `True`.                                  |
| `adopted_persona: str \| None` | `LLMPhase.adopted_persona` / `AgentSkillDef.adopted_persona` | New in 2.0. Loader injects persona's `role_profile` prefix into `system_prompt`. |

## Per-skill migration plan

All five production skills plus `producer` (new, persona) and `event-extraction`/`global-synthesis` (existing, inspection needed).

### 1. `text-segmentation` → `type: graph`

Three phases:

- **`setup`** → `mode: logic`, `execute_steps: [script.segmenter.prepare_chapter]`.
- **`segment`** → `mode: llm`, full `prompt` = old `<system_prompt>`, full `user_prompt_template` = old `<user_prompt>`, `agent_tools: [script.segmenter.parse_segmentation_output, script.segmenter.store_segments]`, `validator`, `max_iterations: 10`, `max_nudges: 2`, `tier: balanced`.
- **`review`** → `mode: llm`, same pattern as `segment` with its own prompts, `max_retries: 2`, `retry_target: segment`.

Frontmatter `io:` keeps its current shape (already schema-2.0 compatible).
Delete `phases/*.md` after migration (embed content inline in YAML).

### 2. `story-deconstruction` → `type: graph`

Inspect each phase under `skills/story-deconstruction/phases/`. Based on the 48-line SKILL.md frontmatter, the orchestrator delegates to `text-segmentation`, `event-extraction`, `batch-analysis`, and `global-synthesis` — most phases are **`mode: delegate`** with `subgraph:` pointing at those children. Migration converts each `<ref path="phases/XX.md" />` into a full YAML `phases:` entry.

### 3. `batch-analysis` → `type: graph`

74-line SKILL.md. "Star topology: entity+character analysis runs first, other paths consume entity list." Suggests several `mode: llm` phases with `depends_on` ordering. Under schema 2.0, ordering is implicit in the `phases:` list order; if genuine parallelism is needed (not yet modelled in 2.0), file a follow-up issue.

### 4. `adaptation_v1/SKILL.md` → `type: agent` (name: `plan-scenes`)

Single phase, single system prompt, four tools. Migration is straightforward:

```yaml
schema_version: "2.0"
name: plan-scenes
description: ...
type: agent
tier: balanced
agent_profile:
  role: 统筹制片大管家
  goal: 从物理场拆解一直到编剧分镜,全权调度整个流水线。
  steps:
    - 调用 build_objective_scenes 生成客观物理场
    - 调用 extract_beats_concurrently 并发提取 beats
    - 调用 dispatch_producer_strategy 运行制片人策略
    - 调用 dispatch_writer_drafting 派发剧本起草
    - 全部成功后调用 finish_task 结束
  constraints: []
subagent_enabled: false
agent_tools:
  - tools.scene_builder.build_objective_scenes
  - tools.beat_dispatcher.extract_beats_concurrently
  - tools.producer_dispatcher.dispatch_producer_strategy
  - tools.writer_dispatcher.dispatch_writer_drafting
```

### 5. `adaptation_v1/subskills/beat_extractor/SKILL.md` → `type: agent` (name: `beat-extractor`)

```yaml
schema_version: "2.0"
name: beat-extractor
description: ...
type: agent
tier: balanced
agent_profile:
  role: 专业的影视剧本拆解员
  goal: 客观地将小说长文本切分为具有影视画面感的动作节拍。
context_mapping:
  chapter_text: "{input.chapter_text}"
user_prompt_template: |
  ... (migrated from <user_prompt> if any, else omit)
```

The old `<data_architecture>` block (output format prose) is appended to `agent_profile.constraints` or inlined at the end of the composed system prompt (decide at compile time inside the loader, not at the manifest layer).

### 6. `skills/producer/` — **new persona skill**

Not a SKILL.md yet (user indicated it exists as a directory). Create `skills/producer/SKILL.md`:

```yaml
schema_version: "2.0"
name: producer
description: 短剧制片人 persona,提供制片视角的反馈与评审。
type: persona
role_profile: |
  你是一位资深短剧制片人,专注节奏、人物弧、商业吸引力。
  你直率但建设性,不恭维。
evaluation_rubrics: |
  - 首 15 秒钩子强度
  - 人物弧清晰度
  - 商业可行性
```

Agent / LLM phases that need producer judgement reference it via `adopted_persona: producer`.

### 7. Other subdirectories

- `skills/event-extraction/`
- `skills/global-synthesis/`
- `skills/shared/`
- `skills/examples/`

Inspect each `SKILL.md`; migrate per the same pattern. Skills whose sole purpose is to host phases referenced by `story-deconstruction` will collapse into its `phases:` list under `DelegatePhase`s.

## Loader rewrite — core algorithm

```python
def load_workflow_from_md(md_path, callbacks=None, _loading_stack=None):
    parsed = parse_skill_file(md_path)
    manifest = TypeAdapter(SkillManifest).validate_python(parsed["frontmatter"])

    compile_result = compile_skill(manifest, md_path=md_path)   # compiler takes manifest
    if not compile_result.passed:
        raise SkillCompilationError(...)
    for w in compile_result.warnings:
        logger.warning(...)

    if isinstance(manifest, AgentSkillDef):
        phases = [_phase_from_agent_skill(manifest, base_dir, callbacks, loading_stack)]
    elif isinstance(manifest, GraphSkillDef):
        phases = [_phase_from_graph_phase(p, base_dir, callbacks, loading_stack)
                  for p in manifest.phases]
    elif isinstance(manifest, PersonaSkillDef):
        raise SkillLoadError(
            "Persona skills are not runnable on their own — they are "
            "injected into other skills via adopted_persona."
        )

    return GraphAgentHarness(
        phases=phases,
        callbacks=callbacks,
        io_config=manifest.io.model_dump() if isinstance(manifest, GraphSkillDef) else None,
        context_mapping=manifest.context_mapping if hasattr(manifest, "context_mapping") else None,
        skill_dir=base_dir,
    )
```

Where `_phase_from_graph_phase` is a single function that dispatches on `p.mode`:

- `"llm"` → assembles a `Phase(requires_llm=True, system_prompt=p.prompt, ...)` with persona injection if `p.adopted_persona` set.
- `"logic"` → `Phase(requires_llm=False, tools=[resolve(s) for s in p.execute_steps], ...)`.
- `"delegate"` → recursively loads `p.subgraph`, wraps as `Phase(subgraph=child_harness, context_bridge=p.context_bridge, requires_llm=False, ...)`.

Persona injection:
```python
if p.adopted_persona:
    persona_manifest = load_persona(p.adopted_persona, base_dir)  # resolves ./... or global registry
    system_prompt = f"{persona_manifest.role_profile}\n\n---\n\n{system_prompt or ''}"
```

## Compiler `_check_*` function audit (2026-04-24 inspection)

`compile_skill` currently runs six check buckets on the raw file content +
frontmatter dict (`src/core/graph_agent/core/compiler.py:1124-1129`).
Classification for PR #6 Commit 2:

| Check bucket              | Keep / drop | Rationale                                                                      |
| ------------------------- | ----------- | ------------------------------------------------------------------------------ |
| `_check_frontmatter`      | **Drop**    | Pydantic `extra="forbid"` + discriminator + `Field` constraints cover this.    |
| `_check_anthropic_compat` | **Keep (rewrite)** | Still relevant for agent skills — ensure `agent_profile.role/goal` are Anthropic-compatible shape. Rewrite against `AgentSkillDef`. |
| `_check_phases`           | **Drop**    | Pydantic `PhaseDef` discriminator + per-mode field surfaces already enforce mutual exclusion and required-field presence. |
| `_check_structure`        | **Drop**    | 1.x body structure check; schema 2.0 has no XML body.                           |
| `_check_tools`            | **Keep (rewrite)** | Tool-path resolvability is still real work — walk `agent_tools` / `execute_steps` / `validator` and attempt import. Any failure is a fatal. |
| `_check_subgraph_cycle`   | **Keep (rewrite)** | Cross-file topology check — recursively resolve `DelegatePhase.subgraph` paths and detect cycles. Survives schema change. |

Plus two **new** semantic checks introduced by the 2.0 vocabulary:

- **Persona resolution** — every `adopted_persona` must resolve to an existing
  `PersonaSkillDef` (either `./subskills/<name>/SKILL.md` or global
  `skills/<name>/SKILL.md`). Ship with PR #6 Commit 4.
- **`context_bridge` static type check** — the `inputs` / `outputs` dicts in
  a `DelegatePhase.context_bridge` must resolve against the child skill's
  `io.inputs` / `io.outputs` declarations. Lives in a dedicated
  `validators/context_bridge.py` because it needs both parent and child
  manifests loaded.

## Compiler rewrite — core algorithm

Input: validated `SkillManifest` (not raw dict). Output: `CompileResult{status, errors, warnings}`.

Drop every rule that duplicates Pydantic validation (the manifest's `extra="forbid"` already catches typos). Keep only semantic rules that need cross-field inspection:

- Rule 5: `context_bridge` static type check across parent/child `io:` — requires loading the child manifest to compare schemas. **Implement in a dedicated `validators/context_bridge.py` module** called from the compiler.
- Tool-path resolvability: all `agent_tools` / `execute_steps` strings must resolve via `_resolve_tool_reference`.
- Persona resolution: every `adopted_persona` must resolve to an existing `PersonaSkillDef`.
- Subgraph resolution: every `DelegatePhase.subgraph` must resolve to an existing `AgentSkillDef` or `GraphSkillDef` (not a persona).
- Custom business rules that currently live in the 1137-line `compiler.py` — **audit each one, drop obsolete, keep still-relevant ones and rewrite against the manifest**.

`rules.yaml` stays as the authoring surface for custom rules. Each rule has `id`, `location`, `severity` (`fatal` | `warning`), `applies_to` (`artifact_type` / `phase_mode`), and a Python callable path.

## Test strategy

1. **Unit tests for the new loader paths** — round-trip a manifest through `load_workflow_from_md` and confirm the resulting harness has the expected phases / tools / tiers.
2. **Integration tests against migrated SKILL.md files** — each migrated skill has at least one end-to-end `run()` test that confirms the harness executes.
3. **Delete tests that assert 1.x XML behaviour** — any test inspecting `_extract_tags` / `_parse_simple_mode` / `_parse_graph_mode` output goes away with those functions.

## Commit plan for PR #6

1. **Commit 1 — new loader scaffolding**: `_phase_from_agent_skill` + `_phase_from_graph_phase` as dead code (not called yet). Plus the compiler manifest-taking signature, also dead. No SKILL.md changes. Tests unaffected.
2. **Commit 2 — big-bang switch**: `load_workflow_from_md` calls `parse_skill_file` + `model_validate` + the new phase builders. All five production SKILL.md files migrated to 2.0 in the same commit. Old `_parse_simple_mode`/`_parse_graph_mode` deleted. Tests green on all migrated skills.
3. **Commit 3 — cleanup**: delete `_validate_frontmatter`, `_extract_tags`, `_split_by_phase_headers`, `_normalise_phase_tags`, `_resolve_refs` from `parser.py`. Delete or shrink `deerflow/skills/parser.py`. Update `__all__` lists.
4. **Commit 4 — persona registry**: add `skills/producer/SKILL.md` (if not already created) + loader support for `adopted_persona` resolution.

Each commit leaves the tree buildable and testable; commit 2 is the only large one (~1000-line diff across ~10 files) because it's the point where old and new machinery swap over.

## Known risks / open questions

- **`test-segmentation.dead_end_threshold`** — unclear if any other skill relies on this. Either add to `LLMPhase` schema or fold into the dataclass default (3).
- **Parallel fan-out in `batch-analysis`** — the "star topology" is not expressible in ordered `phases:`. If parallelism matters at runtime (it does for batch perf), schema 2.0 needs a `parallel_group: str` tag on phases or a top-level `dag:` block. File as follow-up, do not block PR #6.
- **`adaptation_v1` frontmatter `name: plan-scenes`** — conflicting with the directory name `adaptation_v1`. Decide whether to rename the directory to `plan-scenes` or accept the inconsistency; the manifest itself is self-consistent either way.
- **`data_architecture` placement** — the blueprint folds it into the system prompt. If it turns out compilers need to reason about output-format structure separately, revisit; but no current skill does.
