# phase-editing MVP1 Alignment

## 定义

`phase-editing` owns editing the selected phase node's allowed fields and body details in Properties/input/editor surfaces, then saving back to the node file and triggering compile feedback.

Source workflow basis: `01_workflows/02_authoring.md:18`, `01_workflows/02_authoring.md:28`, `01_workflows/02_authoring.md:37`.

## 接口契约

- Node type is inferred from the phase file kind: agent, logic, or subgraph file.
- Properties renders a whitelist form per node type; unsupported old fields are not exposed.
- I/O panel owns node input/output files, output schema, artifacts, and golden-adjacent settings.
- Saves go through file-editing/native-fs and then compile-lint.
- Region links: `properties`, `input`, `editor`, `canvas`.
- Platform links: `native-fs`, `engine`.

## F1. Node Type From File Kind

- 机制: determine phase kind from the file the phase points to, not a mutable `mode` field.
- 决策: node type should be structural and stable.
- 原话/来源: `01_workflows/02_authoring.md:29` calls current mode/subagent shape stale and requires a three-type field rebuild.
- 测试: changing old `mode` frontmatter does not change rendered node type; file kind does.
- Status: target-design.
- 归属: capability `phase-editing`; region `properties`; platform `engine`.

## F2. Properties Field Whitelist

- 机制: render only the fields allowed for agent, logic, or subgraph nodes; save only those fields.
- 决策: Properties must stop being a generic old-frontmatter editor.
- 原话/来源: `01_workflows/02_authoring.md:28` marks current Properties save live but stale; `01_workflows/02_authoring.md:29` requires the whitelist rebuild.
- 测试: old fields are absent; required target fields are visible; save round-trips without deleting body content.
- Status: target-design.
- 归属: region `properties`; platform `engine`; capability `file-editing`.

## F3. I/O And Artifact Outputs

- 机制: node input/output config includes imported file injection and output artifact paths, with defaults under workspace artifacts.
- 决策: output artifacts are per-node configuration and belong with i/o, not a separate predict concern.
- 原话/来源: `01_workflows/02_authoring.md:20` assigns i/o panel rename and artifact setup; `01_workflows/02_authoring.md:40` records artifact output decision.
- 测试: output artifact path persists; imported input file is injected when that node runs.
- Status: target-design.
- 归属: capability `phase-editing`; region `input`; platform `native-fs`, `engine`.

## F4. Subgraph Path Field

- 机制: subgraph nodes store an **绝对 path**(engine skill-syntax §2.1:绝对路径、无 registry), and missing path recovery is handled by workspace/assets.
- 决策: no registry id for child graph resolution in MVP1.
- 原话/来源: `01_workflows/02_authoring.md:37` records subgraph path; `01_workflows/02_authoring.md:38` records relaxed child IO.
- 测试: Properties exposes `path`; missing path marks Assets and offers folder add; no strict child IO one-to-one check blocks compile.
- Status: target-design; current code stale.
- 归属: capability `phase-editing`; capability `skill-workspace`; region `properties`, `assets`.

## F5. L3 Step Editing

- 机制: agent body 的 steps/actions(正文 XML 结构)以**画布内联子节点**呈现,**在画布上直接拖拽增/删/改/重排**(保留源文本);**不在 Properties 做**——Properties 只管 frontmatter 属性。这些内联子节点正是运行期 debug bar「对话续跑」作用的对象(agent phase 子节点)。
- 决策: L3 步骤编辑 = **画布内联**(canvas-inline),非 Properties-first;职责切分:Properties=frontmatter,canvas=XML 正文结构(PM 2026-06-04)。
- 原话/来源: `01_workflows/02_authoring.md:30` defines the L3 add/edit/reorder target.
- 测试: add step creates body block; reorder preserves content; compile sees the updated body.
- Status: target-design.
- 归属: capability `phase-editing`; regions `canvas`, `properties`, `editor`.

## F6. Save Then Compile Feedback

- 机制: saving a phase file updates editor state, skill detail, and compile/lint context markers.
- 决策: authoring stays tight: edit field, save, see compile feedback at the place to fix.
- 原话/来源: `01_workflows/02_authoring.md:31` ties lint/compile and error panel to authoring; `01_workflows/03_compile.md:37` defines context-marker tests.
- 测试: save updates file hash; compile markers point to changed field/line; conflict recovery works.
- Status: save live, feedback target-design.
- 归属: capabilities `phase-editing`, `file-editing`, `compile-lint`.

## 已决(PM 2026-06-04)

- L3 步骤重排 = **画布内联拖拽**(canvas-inline),非 Properties。Properties 只设 frontmatter 属性;正文 XML 结构(L3 步骤)= 画布内联子节点。
