---
related:
  - KB-00-hub
  - KB-02-io-dataflow
  - KB-09-run-trace-checkpoint
  - KB-11-workspace-runtime
  - KB-13-studio-gates-tools
---

> Distilled from: decision `docs/design/2026-08-03-copilot-state-parity-and-tool-surface-decision.md` (D5/D6, PR-I/PR-J) & `app/services/runtime_config.py` & `graph_agent/core/loader.py:1966`

# KB-14: Run Artifacts & Persistence

How a skill's outputs become files on disk, and how to verify them without guessing.

## 1. The Two Declaration Paths (nothing declared ⇒ nothing written)

A run writes artifact files **only for declared outputs**. There are exactly two
declaration paths; both are validated at compile time (unknown values are compile
defects, not runtime surprises):

1. **Schema-level**: an output field in `io.outputs.*` carries `target: "file"` or
   `target: "artifact"` (the full legal enum — anything else is a `[F-v3-*]` compile
   defect).
2. **Workspace-level**: a `runtime_config.artifacts` entry `{stem, fields}` in
   `.workspace/runtime_config.json`, where every `fields` item must exist on the
   blackboard (invalid references are compile defects too). Edit this via
   `set_output_artifacts` — never by hand-editing the JSON.

## 2. Where Files Land & How They Are Named

```text
<skill>/.workspace/runs/<run_id>/artifacts/<stem>_latest_<timestamp>.<ext>
```

One file per declared stem per run; the `_latest_<timestamp>` suffix makes the
newest write self-describing without a separate index.

## 3. Fingerprint Participation

The artifacts declarations live inside `runtime_config.json`, which carries a
content `fingerprint` (`sha256:` over the config). Changing artifact declarations
therefore changes the execution fingerprint — a run's provenance includes what it
was asked to persist, not just its inputs.

## 4. How to Verify (bounded read tools, zero approval)

| Question | Tool |
|---|---|
| What artifacts are declared right now? | `get_workspace_config` (projection includes `artifacts`) |
| What did a run actually write? | `list_run_artifacts(skill_id, run_id?)` — names + sizes per run |
| What is inside one artifact? | `read_run_artifact(skill_id, run_id, name)` — bounded (48 KB cap, truncation flagged) |
| Change the declarations | `set_output_artifacts` (approval-gated write; same service as the I/O panel) |

Trust the causal chain, not the declaration alone: declared ⇒ run ⇒ listed ⇒ read.
A declaration with no file after a sealed run is a defect worth reporting, not
something to silently regenerate.
