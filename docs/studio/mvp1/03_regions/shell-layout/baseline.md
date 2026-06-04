# shell-layout Baseline

Status: live. Shell layout exists with header, toolbar, resizable panels, settings overlay, canvas/editor center, and copilot side panel.

Source workflows: `01_workflows/01_init.md`, `01_workflows/02_authoring.md`, `01_workflows/00_settings-ux-spec.md`.

## Current Component Index

| Component/area | Current behavior | Evidence |
|---|---|---|
| Workspace state | Workspace owns current panels, copilot open state, selected node/edge, compile state, and open editor files. | `apps/studio/frontend/src/components/studio/Workspace.tsx:39`, `apps/studio/frontend/src/components/studio/Workspace.tsx:55` |
| Enter/clear skill | Skill id changes reset panels/nav/copilot and default a skill to Assets + Copilot open. | `apps/studio/frontend/src/components/studio/Workspace.tsx:44` |
| Header | Header renders Back Home, breadcrumb stack, Team menu, and Copilot toggle. | `apps/studio/frontend/src/components/studio/Header.tsx:56`, `apps/studio/frontend/src/components/studio/Header.tsx:98` |
| Toolbar | Toolbar owns left panel mode buttons and Settings entry. | `apps/studio/frontend/src/components/studio/Toolbar.tsx:7`, `apps/studio/frontend/src/components/studio/Toolbar.tsx:80` |
| Panel slot | Workspace mounts `Panels` in a resizable left panel when activePanel exists. | `apps/studio/frontend/src/components/studio/Workspace.tsx:474`, `apps/studio/frontend/src/components/studio/panels/Panels.tsx:20` |
| Center slot | Center switches between Settings, SplitEditor, Welcome, and GraphCanvas. | `apps/studio/frontend/src/components/studio/Workspace.tsx:494`, `apps/studio/frontend/src/components/studio/Workspace.tsx:512` |
| Copilot slot | Copilot panel opens as a right resizable panel. | `apps/studio/frontend/src/components/studio/Workspace.tsx:545` |
| Copilot prop issue | Copilot receives outer `skillId` prop instead of `currentSkillId`. | `apps/studio/frontend/src/components/studio/Workspace.tsx:554` |
| Runtime gate | RuntimeGate initializes app config and shows loading/error/children. | `apps/studio/frontend/src/components/RuntimeGate.tsx:8`, `apps/studio/frontend/src/components/RuntimeGate.tsx:31` |

## Current Region Ownership

- Owns: shell grid, resizable panel placement, header, toolbar, settings overlay placement, copilot panel slot.
- Does not own: content inside each panel, graph canvas internals, settings form internals.

## Known Drift

- The shell should remain usable when sidecar-dependent features fail; RuntimeGate still has full-screen loading/error semantics (`apps/studio/frontend/src/components/RuntimeGate.tsx:31`).
- Copilot panel may use stale skill context because Workspace passes `skillId` rather than `currentSkillId` (`apps/studio/frontend/src/components/studio/Workspace.tsx:554`).
