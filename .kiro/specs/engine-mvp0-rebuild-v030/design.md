# Design: Engine MVP0 Rebuild V0.3.0 Cutover

## 1. Architecture overview

V0.3.0 engine is organized around five contracts:

1. `SkillResolverProtocol` resolves child graph skill ids.
2. Compilation builds field-level AST from `GRAPH.md`, `SKILL.md`, `LOGIC.md`, and `SUBGRAPH.md`.
3. `StateMapper` builds phase-local state and validates phase output.
4. Execution runtime invokes Agent / LOGIC / SUBGRAPH / builtin reference reader through wrappers.
5. Tracing records wrapper/tool/model events with structured `[F-v3-*]` error payloads.

## 2. Core data models

### `PhaseIOSchema`

```python
class PhaseIOSchema(BaseModel):
    inputs: dict[str, Any]
    outputs: dict[str, Any]
```

Field requirements:

- `inputs`
  - JSON Schema object
  - required for every phase
  - must have `type: object`
  - `required` entries must be keys in `properties`
- `outputs`
  - JSON Schema object
  - required for every phase
  - must have `type: object`
  - properties define allowed phase output fields

### `GraphRootIOSchema`

```python
class GraphRootIOSchema(BaseModel):
    inputs: dict[str, Any]
    outputs: dict[str, Any]
```

Root IO is stored inline in `GRAPH.md` frontmatter. Physical `io/inputs.json` and `io/outputs.json` are deprecated and must fail compile.

### `AgentNodeAST`

Required fields:

- `id: str`
- `mode: Literal["agent"]`
- `role: str`
- `goal: str`
- `steps: list[AgentStep]`
- `protocols: list[AgentProtocol]`
- `exit_contract: str`
- `io: PhaseIOSchema`

Optional fields:

- `tools: list[str]`
- `subagents: list[AgentRegistryItem]`
- `subgraphs: list[AgentRegistryItem]`
- `references: list[ReferenceSpec]`
- `examples: list[ExampleSpec]`
- `max_iterations: int`
- `llm_role: str`

### `LogicNodeAST`

Required fields:

- `id: str`
- `mode: Literal["logic"]`
- `actions: list[str]`
- `io: PhaseIOSchema`

Action names are one-level names resolved under `<skill_root>/actions/<name>.py`.

### `SubgraphNodeAST`

Required fields:

- `id: str`
- `mode: Literal["subgraph"]`
- `target_skill: str`
- `io: PhaseIOSchema`

Compiler resolves `target_skill`, compiles child root, and checks parent phase IO against child root IO.

## 3. Normalized state shape

```python
class BlackboardData(TypedDict, total=False):
    inputs: dict[str, Any]
    phase_outputs: dict[str, dict[str, Any]]
    scratch: dict[str, Any]
```

Field semantics:

- `inputs`
  - written only by runtime input funnel
  - read-only after run starts
  - source for phase input slicing
- `phase_outputs`
  - written only by StateMapper output wrapper
  - key is `phase_id`
  - value satisfies that phase `io.outputs`
- `scratch`
  - optional temporary area
  - not part of final public result unless explicitly mapped
  - should not be used for cross-phase durable output

## 4. Smart reducer

```python
def smart_dict_reducer(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
    *,
    merge_context: MergeContext | None = None,
) -> dict[str, Any]:
    ...
```

Required semantics:

- merge `data.inputs` only at run initialization
- merge `data.phase_outputs[phase_id]` by phase id
- reject same super-step writes to the same effective path
- permit sequential update only when source phase and stage make it explicit
- include conflict payload with `effective_path`, `left_source`, `right_source`, `super_step_id`

This is the T3 + T5 settlement: T5 defines `data.inputs` / `data.phase_outputs` / `data.scratch`; T3 defines how reducers merge those nested regions.

## 5. StateMapper

```python
class StateMapper:
    def build_phase_input(
        self,
        state: BlackboardState,
        phase_id: str,
        phase_io: PhaseIOSchema,
    ) -> PhaseInput: ...

    def wrap_phase_output(
        self,
        phase_id: str,
        output: dict[str, Any],
        phase_io: PhaseIOSchema,
    ) -> BlackboardPatch: ...

    def build_child_input(
        self,
        target_root_io: GraphRootIOSchema,
        explicit_input: dict[str, Any],
    ) -> dict[str, Any]: ...
```

`build_phase_input`:

- reads `data.inputs`
- reads upstream `data.phase_outputs`
- filters to `phase_io.inputs.properties`
- validates required fields
- deep copies JSON-like values

`wrap_phase_output`:

- extracts phase output from node return
- validates against `phase_io.outputs`
- returns patch under `data.phase_outputs[phase_id]`

`build_child_input`:

- takes explicit tool / SUBGRAPH input only
- validates against child root `io.inputs`
- never copies parent `data`

## 6. Runtime wrapper topology

All runtime node classes use the same wrapper order:

```text
trace NODE_START
  -> StateMapper.build_phase_input
  -> invoke phase implementation
  -> StateMapper.wrap_phase_output
  -> trace NODE_END
  -> return BlackboardPatch
```

Applicable node kinds:

- Agent phase
- LOGIC phase
- SUBGRAPH phase
- builtin reference reader sandbox

## 7. Child graph invocation

Child graph input:

- `data = canonical explicit input`
- `flow = deepcopy(parent.flow)` plus incremented depth
- `messages = []`
- `run_id = child run id`

Child graph output:

- subagent: returned as tool result to parent Agent
- SUBGRAPH phase: mapped through parent phase `io.outputs`

No child graph may read parent `data` unless the parent explicitly passes fields in the child input object.

## 8. Reference reader sandbox

```python
class ReaderSandboxState(TypedDict):
    data: ReaderData
    flow: ReaderFlow
    messages: list[Any]
    run_id: str | None
```

`ReaderData` fields:

- `skill_id: str`
- `phase_id: str`
- `references: list[ReferenceSpec]`

`ReaderFlow` fields:

- `timeout_s: int = 60`

Reader output:

- `markdown: str`
- `warnings: list[str]`
- fallback reason when degraded

Reader failure is WARN `[F-v3-reference-reader-failed]` and falls back to raw excerpts.

## 9. Error payload

```python
class GraphAgentErrorPayload(TypedDict, total=False):
    code: str
    level: Literal["fatal", "warn"]
    stage: str
    message: str
    doc_link: str
    skill_id: str
    phase_id: str
    field_path: str
    source_path: str
```

All user-visible engine errors should carry a `[F-v3-*]` code. Exception string remains human-readable, but structured payload is the stable contract.

## 10. Trace payload

Trace events carry only sanitized data:

- phase inputs after StateMapper filtering
- phase outputs after output validation
- child graph canonical input
- reference reader fallback metadata
- tool args after validation

Trace must not dump full parent `BlackboardState`.

## 11. Cleanup design

T11 cleanup removes dead legacy/schema 2.0 surfaces after cutover:

- `ContextResolver`
- context_mapping docs
- legacy harness entry points
- schema 2.0 parser dependencies

It does not remove graph skill main path or codemod migration helpers.
