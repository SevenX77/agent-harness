# assets MVP1 Alignment

## 定义

`assets` owns the left panel file browser and subgraph workspace membership surface: opening files, showing real skill files, marking missing subgraph paths, and adding subgraph folders to the workspace.

Source workflow basis: `01_workflows/01_init.md:16`, `01_workflows/02_authoring.md:37`.

## 接口契约

- Inputs: `skillDetail.files`, selected node, workspace path/subgraph resolution status.
- Outputs: file open requests and add-folder-to-workspace requests.
- Capability links: `file-editing`, `skill-workspace`, `graph-authoring`, `phase-editing`.
- Platform link: `native-fs`.

## F1. Skill File Tree

- 机制: render actual files/folders from skill detail and open files into the editor.
- 决策: Assets is inspection/navigation, not a second source of file metadata.
- 原话/来源: `01_workflows/02_authoring.md:48` links `.workspace`/file tree to file-editing.
- 测试: all files in detail appear once; clicking file opens editor; file tree updates after save/create.
- Status: live.
- 归属: region `assets`; capability `file-editing`.

## F2. Missing Subgraph Path Status

- 机制: detect local subgraph path references and mark unresolved paths with a recovery action.
- 决策: subgraph references are paths and missing child graph should be fixable from Assets.
- 原话/来源: `01_workflows/02_authoring.md:37` locks path references.
- 测试: unresolved path appears red/actionable; resolved path shows ready; no fake fallback rows.
- Status: target-design.
- 归属: region `assets`; capabilities `skill-workspace`, `graph-authoring`.

## F3. Add Subgraph Folder To Workspace

- 机制: user picks a child folder and Studio adds it to workspace membership/resolution state.
- 决策: recovery should not require registry registration.
- 原话/来源: `01_workflows/01_init.md:35` locks local workspace model; `01_workflows/02_authoring.md:37` removes registry-based child lookup.
- 测试: picker result resolves the missing subgraph; reload keeps resolution.
- Status: placeholder/fake today.
- 归属: region `assets`; platform `native-fs`.

## F4. Selected Node Context

- 机制: Assets may highlight the file/subgraph connected to the selected canvas node.
- 决策: cross-region focus should help orientation without duplicating Properties.
- 原话/来源: `01_workflows/02_authoring.md:18` keeps canvas/properties/file editing in one authoring loop.
- 测试: selecting a phase highlights its file; clearing selection clears highlight.
- Status: target-design.
- 归属: region `assets`; region `canvas`.

## 待 PM 补 gap

- Whether subgraph membership belongs in Assets only or also appears in Welcome workspace settings.
