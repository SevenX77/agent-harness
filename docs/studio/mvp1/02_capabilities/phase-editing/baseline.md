# phase-editing Baseline

Status: save path exists, but the Properties schema is stale and writes old phase formats.

Source workflow: `01_workflows/02_authoring.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Properties branch | Properties panel renders selected-node form and selected-edge trace branch. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:195`, `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:293` |
| Phase file parsing | Properties reads the selected phase file, parses frontmatter, and infers mode/kind from old fields. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:121`, `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:359` |
| Save | Properties applies form data to the file and calls `onPhaseFileSave`. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:172`, `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:188` |
| Form fields | Phase form fields are old `mode/pythonCallable/systemPrompt/exitContract/tools/targetSkill`. | `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:8`, `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:380` |
| XML blocks | Phase write helper manages old XML blocks like system prompt and exit contract. | `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:203` |
| Add phase scaffold | New phase draft writes old `mode`, prompt, exit contract, target skill, and python callable body. | `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:143` |
| Node type inference | Build helpers still inspect `mode`, `target_skill`, and old subagent shape. | `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:151`, `apps/studio/frontend/src/components/GraphCanvas/build-nodes.ts:197` |
| Phase save path | Workspace writes the edited phase file and updates open editor/skill detail. | `apps/studio/frontend/src/components/studio/Workspace.tsx:159` |
| Input/schema panel | Input panel shows inferred schema only; no writeback to node i/o/golden settings. | `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:18`, `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:72` |

## Current Coverage

- live: selected-node Properties form, phase file read/save, editor synchronization.
- stale: field set, node kind inference, subgraph target field, XML body blocks.
- missing: current three node-type field whitelist, i/o output artifact settings, L3 step editing, golden output settings.

## Known Drift

- Workflow calls the current Properties form stale and requires a field whitelist rebuild (`docs/studio/mvp1/01_workflows/02_authoring.md:28`, `docs/studio/mvp1/01_workflows/02_authoring.md:29`).
- Current helpers still write old fields that the target authoring flow should not expose (`apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:143`).
