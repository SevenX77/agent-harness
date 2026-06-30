# Engine Strict Compile Gate

## Purpose

Make engine compile behave as the first strict gate for source-level defects that
can be proven before a real run. The goal is to stop invalid skills at compile
time instead of allowing them to fail later in assemble or runtime.

## Scope

This spec covers source-only checks owned by `packages/graph-agent`:

- Reject legacy Agent `phase_config` compatibility syntax.
- Validate root and phase inline IO as JSON Schema object contracts.
- Validate static dataflow for required phase inputs and root outputs.
- Validate declared Agent tools and declared reference/example files before run.
- Validate LOGIC actions as pure-return functions that accept `inputs`.

This spec does not require engine compile to know host-owned truths:

- Gateway role reachability remains a host/studio strict preflight input.
- Actual run input values remain a run preflight concern.
- Validator/action execution is not performed during compile.

## Requirements

### R1 Agent compatibility syntax is fatal

When an Agent `SKILL.md` frontmatter contains `phase_config`, compile must fail
with `[F-v3-agent-schema-unknown-field]`. Engine must not merge or normalize
`phase_config` into modern top-level fields.

### R2 IO schema is a strict object contract

Root `GRAPH.md` and phase `io.inputs` / `io.outputs` must be valid JSON Schema
objects whose top-level `type` is `object`, whose `properties` is an object, and
whose `required` entries all exist in `properties`.

Nested JSON Schema remains legal. Arrays, nested objects, and `items` schemas
must not be rejected merely because older runtime code only handled a subset.

### R3 Static dataflow is compile fatal

For every phase, each required input field must be available from root inputs,
an upstream phase output, or a declared `source: file` binding. If a required
input has no static source, compile must fail with
`[F-v3-graph-dataflow-source-missing]`.

Each required root output must be available at the end of at least one
output-marked terminal phase. A field may be produced by an upstream dependency
and carried through the cumulative blackboard; it does not need to be directly
declared by the output phase itself. If no output phase can see the field,
compile must fail with `[F-v3-graph-dataflow-source-missing]`.

### R4 Declared resources are real

If a phase declares a reference or document example path, the path must be
relative to the skill root, stay within the skill root, and point to a readable
file. Missing or unreadable reference paths are compile fatal with
`[F-v3-resource-reference-path-invalid]`; missing or unreadable example paths
are compile fatal with `[F-v3-resource-example-path-invalid]`.

### R5 Declared Agent tools resolve before assemble

Every declared Agent tool must resolve at compile time to a framework tool,
resource tool, phase-local tool, root tool, critic tool, or generated subagent
tool. Unknown tools must fail compile with `[F-v3-agent-tool-unknown]`.

### R6 LOGIC action contract is source-checked

LOGIC actions must accept `inputs` as the first parameter. The `inputs` argument
is read-only; static writes such as item assignment, deletion, or mutating
method calls are compile fatal with `[F-v3-logic-action-purity-violation]`.
