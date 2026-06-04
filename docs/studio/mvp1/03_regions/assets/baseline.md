# assets Baseline

Status: live file tree; subgraph library is fake/stale and uses registry-like language.

Source workflows: `01_workflows/01_init.md`, `01_workflows/02_authoring.md`.

## Current Component Index

| Component/area | Current behavior | Evidence |
|---|---|---|
| File tree | Assets builds a nested tree from `skillDetail.files`. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:37` |
| File open | File rows call workspace `onFileOpen`. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:69`, `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:88` |
| Subgraph detection | Subgraphs are detected from old `mode`, `target_skill`, or `sub_skill_ref` fields. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:95` |
| Fake cache | Registered subgraphs are seeded from a local hardcoded cache. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:86` |
| Fake fallback rows | If no subgraphs exist, the panel displays hardcoded classifier/translation rows. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:120` |
| Register action | Register picks a directory or browser fallback path, then only updates local cache/toast. | `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:140` |
| Panel routing | Panels routes active `assets` to `AssetsPanel`. | `apps/studio/frontend/src/components/studio/panels/Panels.tsx:31` |

## Current Region Ownership

- Owns: file tree, folder/file rows, subgraph path status/recovery UI.
- Does not own: Properties fields, workspace import root policy, graph topology.

## Known Drift

- MVP1 subgraph references should be local paths; current code still detects registry-era target fields (`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:103`).
- Fallback subgraph rows are demo data and must not ship as actual workspace state (`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:120`).
