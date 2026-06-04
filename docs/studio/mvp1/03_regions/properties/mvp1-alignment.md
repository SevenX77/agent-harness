# properties MVP1 Alignment

## 定义

`properties` owns the right/left panel view for the selected object's editable fields and contextual metadata: phase node whitelist forms, field-level diagnostics, and any selected-object summary that is not a full trace timeline.

Source workflow basis: `01_workflows/02_authoring.md:28`, `01_workflows/03_compile.md:16`, `01_workflows/04_run-and-verify.md:99`.

## 接口契约

- Inputs: selected node/edge, skill detail, diagnostics, optional golden diff summary.
- Outputs: phase file save, file open requests, panel focus changes.
- Capability links: `phase-editing`, `compile-lint`, `trace-observability`, `golden-eval`.

## F1. Node Field Whitelist Form

- 机制: render editable fields per agent/logic/subgraph node type and save to the phase file.
- 决策: rebuild away from stale generic mode/frontmatter fields.
- 原话/来源: `01_workflows/02_authoring.md:28` marks current save stale; `01_workflows/02_authoring.md:29` requires the whitelist rebuild.
- 测试: selected agent/logic/subgraph each show only allowed fields; save preserves non-edited body blocks.
- Status: target-design.
- 归属: region `properties`; capability `phase-editing`.

## F2. Field-level Compile Marker

- 机制: compile diagnostics map to the exact field with tooltip and severity.
- 决策: properties is one of the three contextual error locations.
- 原话/来源: `01_workflows/03_compile.md:16` defines property/io field tooltip.
- 测试: invalid field shows tooltip next to the field; drawer links or focuses that field.
- Status: target-design.
- 归属: region `properties`; capability `compile-lint`.

## F3. Remove Raw Edge Trace Dump

- 机制: selected-edge raw JSON is replaced by trace-owned dot/context views.
- 决策: trace interpretation belongs to trace-observability, while Properties should not duplicate timeline.
- 原话/来源: `01_workflows/04_run-and-verify.md:99` calls for cleaning Properties selectedEdge JSON dump.
- 测试: edge click opens trace/dot context in the trace flow; Properties no longer displays mock JSON.
- Status: target-design cleanup.
- 归属: region `timeline`/`canvas`; capability `trace-observability`.

## F4. Golden Diff Summary

- 机制: after run, Properties may show selected node actual-vs-golden field summary while detailed diff can live in Timeline.
- 决策: golden diff is field-level acceptance after Run.
- 原话/来源: `01_workflows/04_run-and-verify.md:128` lists field-level diff; `01_workflows/04_run-and-verify.md:136` records run-after diff.
- 测试: selecting an agent node after run shows that node's diff; no-golden state shows a design-golden CTA.
- Status: target-design.
- 归属: region `properties`; capability `golden-eval`.

## 待 PM 补 gap

- Whether full golden diff lives primarily in Properties, Timeline, or a dedicated drawer.
