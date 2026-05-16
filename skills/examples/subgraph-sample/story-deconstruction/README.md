# Story Deconstruction — subgraph reference

This example shows how to stitch four existing sub-skills
(`text-segmentation`, `event-extraction`, `batch-analysis`,
`global-synthesis`) into one top-level pipeline **without any Python
glue code**.

Compared to the legacy orchestrator under
`skills/story-deconstruction/`, every phase in this V2.1 example is
purely declarative:

* `GRAPH.md` owns the four-phase topology.
* Each `phases/*/SUBGRAPH.md` points at a sibling V2.1 skill root through
  `<sub_skill_ref>`.
* `context_bridge.inputs` documents how the parent's context keys map into the
  child skill's runtime inputs.
* `context_bridge.outputs` documents how the child's outputs map back into the
  parent's context keys so the next phase can pick them up.

No `tools:` are declared on these phases — the framework rejects that
combination since Task 5.1 (`F-subgraph-exclusive-tools`).

## Why keep the legacy skill around?

`skills/story-deconstruction/` still uses the Python-dispatcher pattern
(``tools: [script.orchestrator.*]``) because the host project's existing
run scripts and tests point at that path. Moving it to a
`bad-samples/` folder would break them. The recommended migration path
is:

1. Land this new example (done — see this directory).
2. Migrate the host project's callers to the subgraph form a few at a
   time, verifying end-to-end output parity against the legacy
   orchestrator each step.
3. Once no call sites reference the orchestrator version, move the
   legacy skill under `skills/examples/bad-samples/` (Task 8.1) and
   let the `W-python-glue-orchestrator` compiler warning (Task 5.2,
   deferred) surface any remaining external usage.

## Quick run

```python
from graph_agent import run_skill

result = run_skill(
    "skills/examples/subgraph-sample/story-deconstruction",
    chapters=[...],
    project_id="demo-project",
)
print(result["context"]["story_framework"])
```

The engine loads the four child skills as independent harnesses,
executes them sequentially (because of the `depends_on` chain), and
streams their CallbackEvents through the same tracing layer as the
parent, so Studio's timeline view shows one continuous run.
