# properties Baseline

Status: live panel with stale phase form and selected-edge JSON dump; MVP1 target requires a major ownership cleanup.

Source workflows: `01_workflows/02_authoring.md`, `01_workflows/03_compile.md`, `01_workflows/04_run-and-verify.md`.

## Current Component Index

| Component/area | Current behavior | Evidence |
|---|---|---|
| Panel route | Panels routes `activePanel === "properties"` to `PropertiesPanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:43` |
| Local UI wrappers | Properties imports local Button/Badge/Field/Input/Select/Textarea/ScrollArea wrappers. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:1` |
| Phase parse | Panel reads phase file content and parses old frontmatter/body fields. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:121` |
| Save | Save applies form data and calls `onPhaseFileSave`. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:172` |
| Selected edge branch | Selected edge renders a "Connection Trace" JSON block. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:195` |
| Phase form | Phase fields include old Mode, Python callable, System prompt, Exit contract, Tools, Target skill. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:380` |
| Form model | `phase-frontmatter.ts` defines old field names and writes old XML blocks. | `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:8`, `apps/studio/frontend/src/components/studio/panels/phase-frontmatter.ts:203` |
| Compile field markers | No field-level tooltip/diagnostic mapping exists. | `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:293` |

## Current Region Ownership

- Owns: selected node property forms, selected edge summary if kept, field-level compile markers.（**golden 不归 Properties** —— PM 2026-06-04 已决 golden 完全不在 Properties，详细 diff 在 editor、入口在 I/O output + Assets。）
- Should not own: raw trace JSON dumping; trace data interpretation belongs to Timeline/Trace.

## Known Drift

- Workflow says current Properties form is stale and must rebuild by node-type whitelist (`docs/studio/mvp1/01_workflows/02_authoring.md:28`).
- Workflow says selected-edge JSON dump should be cleaned up and dot trace moved to trace-observability (`docs/studio/mvp1/01_workflows/04_run-and-verify.md:99`).
