# Design Document — Engine lint: node missing input/output

> **STATUS: BLOCKED — needs a product-direction decision (see §6).**
> The open A-vs-B decision is resolved by evidence to **(A) connectivity**, but
> (A) then collides with the authoritative engine design: under (A) there is **no
> design-aligned "no output" defect to add**. Implementing the rule as written in
> `requirements.md` would contradict committed design + tests. Per the project
> 铁律 (MVP1 design = source of truth; fix code to match design, never retrofit
> the design to a drifting requirement), I stopped before shipping it.

## 0. The OPEN DECISION: (A) connectivity vs (B) io-schema → (A)

The MVP1 design names this defect family in connectivity terms, never schema:

- `docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md:239`
  > `| [F-v3-graph-phase-island] | 编译期 | phase 与入口不可达 | 增加依赖连接或删除孤岛 | … |`

  "phase 与入口**不可达**" (unreachable from entry); remediation "增加**依赖连接**"
  (add **dependency edges**). Same file's DAG step is fed by "frontmatter phases +
  body depends_on" → "依赖存在、无环、无孤岛".
- Topology syntax is edge-based (`docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`).

(B) — flagging an empty `properties: {}` — has **no** design support; schema is
policed by the orthogonal data-flow family
(`[F-v3-graph-io-schema-invalid]`, `[F-v3-graph-dataflow-source-missing]`). So the
design-aligned reading is **(A)**.

## 1. "No input" is ALREADY a diagnostic — `[F-v3-graph-phase-island]`

Under (A), a node with no input is one unreachable from the INPUT sentinel.
`_validate_no_islands` (`packages/graph-agent/src/graph_agent/core/loader.py:1398-1418`)
already raises FATAL `[F-v3-graph-phase-island]` for exactly that:

```python
for phase_id in adjacency:
    if phase_id not in visited:
        _graph_fatal(graph_path, 1,
            f"[F-v3-graph-phase-island] phase {phase_id!r} is unreachable from input")
```

A phase connects to INPUT via `depends_on="input"` or by declaring no `depends_on`
at all (`loader.py:1337-1343`), so the only "no input" case is an island — already
covered. **Requirement criteria 1.1 / the input half of 1.5 / 3.x are satisfied by
existing code.** The requirement intro's "Today this produces no diagnostic" is
**false for the input side**.

## 2. "No output" under (A) is NOT a defect — the `output` marker is OPTIONAL

The requirement's "no output" = a phase with no outgoing edge (a terminal leaf
not marked `output`). The authoritative design says that is **valid**:

- `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md:132-138` — body `<phase>`
  rules table marks `<phase depends_on="upstream" output>phase_id</phase>` as
  **required: `no`**. The `output` marker is **optional**.
- Two committed tests lock in the "leaf-terminal fallback" — a graph with **no**
  `output` marker compiles, the terminal leaf being the implicit output:
  - `tests/core/test_round14_skill_compilation_cutover.py:378`
    `test_missing_output_phase_uses_leaf_terminal_fallback` — single
    `<phase depends_on="input">main</phase>` compiles (`output: False`).
  - `:389` `test_bare_body_phase_compiles_as_dependency_free_node` — bare
    `<phase>main</phase>` compiles.
- No design text mentions a "no output" / dead-end-sink defect, and there is no
  `[F-v3-graph-phase-no-output]`-style code in the design error tables.

So under (A) **every** non-island phase already "has output" (a downstream
dependent, or it is the implicit leaf output). Implementing "terminal non-output →
error" directly contradicts the optional-`output` design and breaks the two tests
above. I verified this empirically: a prototype rule turned both committed tests
RED, so it was reverted.

**Net:** under the design-aligned definition (A), the requirement has **no genuine
gap** — the input side is already enforced (island) and the output side is a
design-sanctioned non-defect.

## 3. Why I did not just pick (B) or invent a narrower rule

- **(B) io-schema emptiness** would give a real, uniform check (empty
  `io.inputs`/`io.outputs`), but it has zero design support and contradicts the
  design's connectivity framing of this defect family. Choosing it is a
  product/design decision, not an engineering detail.
- **(A-mixed)** — "flag a terminal non-output leaf only when some *other* phase is
  explicitly marked `output`" — preserves both committed tests and is design-silent
  (the leaf-fallback tests only cover the no-output-declared case). It is a
  plausible salvage of criterion 2, but it is narrower than the requirement states
  and is still my invention, not a design mandate.
- **Tighten the design** — make `output` mandatory / deprecate the leaf-terminal
  fallback — is a contract change to `00-FORMAT-GROUND-TRUTH.md` + the two tests.
  Per AGENTS.md ("需求+方向归 PM"; write decisions back to the MVP1 design source)
  I cannot unilaterally flip a documented "optional" to "required".

All three change *what the feature is*, so they belong to the requester, not to a
guess.

## 4. If/when a direction is chosen — the mechanics are scoped

Whichever rule is chosen, the engine wiring + new-code cascade is already mapped:

- **Engine:** a new validator in `_validate_graph_topology`
  (`loader.py:1241-1273`), emitting via `_graph_fatal(..., field_path="<phase>.…")`.
- **New `[F-v3-*]` code cascade** (round28 bijection):
  1. `core/error_registry.py`: `ERROR_REGISTRY` entry **and** an aligned
     `_CATALOG_METADATA_ROWS` row (zipped `strict=True`).
  2. `spec/features.yaml`: add to `F-graph-skill-loading.error_codes_primary`.
  3. `tests/test_round28_invariant_guards.py`: bump `len(ERROR_REGISTRY) == 97`.
  4. Sync `11-error-code-spec.md` / round28 fixtures + contract hash-lock iff the
     full suite flags them.
- **Display (no frontend logic invented):** with `source_path=GRAPH.md` + `line`,
  the GRAPH.md inline marker works via `applyLintMarkers`/`lintErrorsForFile`; a
  `field_path="<phase>.…"` lets the manual-Compile node channel
  (`node-compile-errors.ts:34-50` field-prefix fallback) badge the node — the same
  channel the golden-field gate uses. (Realtime-lint badging of GRAPH.md-scoped
  topology errors is a pre-existing whole-class limitation shared by island/cycle/
  output-invalid; out of scope.)

## 5. Subgraph behavior (whatever rule is chosen)

A `SUBGRAPH` phase is an ordinary node in the parent DAG; the child graph compiles
recursively via `_validate_subgraph_io_contracts` (`loader.py:720-749`), so the
same topology pass applies to child phases. INPUT/OUTPUT sentinels are not real
phases and stay exempt by construction.

## 6. Decision required from the requester

The requirement as written cannot ship without contradicting the authoritative
design. Pick one (recommendation first):

1. **(Recommended) Accept the design as-is — close the "output" half.** Under (A),
   "no input" is already `[F-v3-graph-phase-island]`; "no output" is not a defect
   (optional `output` + leaf-terminal fallback). Deliverable: this design.md +
   tests/docs noting island already covers the input side; **no new code**. This is
   the most 铁律-pure outcome.
2. **Adopt (B) — empty-io-schema lint.** A new code for a phase whose
   `io.inputs`/`io.outputs` declares no properties. Real and uniform, but needs the
   design source updated first (it currently frames the defect as connectivity).
3. **Adopt (A-mixed) — dead-end leaf only when explicit outputs exist.** Narrower
   than criterion 2; design-silent but test-compatible. Add a new connectivity code.
4. **Tighten the contract — make `output` mandatory.** Implement the literal rule,
   but update `00-FORMAT-GROUND-TRUTH.md` (output required) and the two
   leaf-fallback tests as a deliberate design change (PM sign-off per AGENTS.md).

Options 2–4 reuse the mechanics in §4. The TDD test + rule prototype are reverted
and re-applicable in minutes once a direction is set.
