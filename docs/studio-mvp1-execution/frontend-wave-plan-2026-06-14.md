# Frontend-adaptation wave plan (2026-06-14)

> 接 engine wave(A 已做已提交,B/C/D 核实非 engine)。PM 指令 ③:engine/后端先行已完成 → 现做**前端适配**,沿用现有 UI 组件和风格,**能用 shadcn 就用 shadcn,不自己乱写**。两任务**文件不冲突**,可并行 subagent 实施,我 gatekeep 审计 + 跑门禁。

## 两个非冲突前端任务(均经核实 = 前端-only)

### 任务 1 — F3 输出产物路径编辑器(input 区,原 DEF-029,reclassify 为前端)
**核实结论**:引擎已 honor `io.outputs.<field>.path`+`target:artifact`(`runner.py:1292` `_save_v030_declared_file_outputs`,真跑验证落 `runs/<id>/artifacts/<path>`);F3 设计(FROZEN-2/G3 `02_authoring.md:40`)就是这套。**零 engine 改动**。

**实施(镜像已有 F2 `io.inputs` 写回)**:
- `apps/studio/frontend/src/lib/schema-infer.ts`:加纯函数 `applyOutputArtifactPathToGraph(graphMd, fieldName, path)`(解析 GRAPH.md frontmatter → 在 `io.outputs.properties.<field>` 上 set `target:"artifact"`+`path` → re-dump;**只动 io.outputs,保 io.inputs + phase DAG body 不变**,与 `applyInputSchemaToGraph`(schema-infer.ts:53)同构)。空 path 或裸文件名按设计(裸名→默认 artifacts 目录)。
- `apps/studio/frontend/src/components/studio/panels/InputPanel.tsx`(I/O 面板):在 Output/Golden 区列出 `io.outputs` 字段,每字段一个"Artifact path"编辑入口(shadcn `Input` + `Button`,沿用 InputPanel 现有 Test Inputs / schema-save 风格),保存经既有 `writeSkillFile`(D12 唯一写者,desktop 走 native / browser 走 HTTP)。typed 错误就近显示(复用现有 errorMessage)。
- **纯单测**:`applyOutputArtifactPathToGraph`(写回 + 无 frontmatter 报错 + 保 io.inputs 不变)。
- **不碰** api/llm.ts / KEEP-MAIN;不加新依赖。

### 任务 2 — edge-blackboard(trace/properties 区 F4,消费引擎已发的 transition 事件)
**核实结论**:引擎已发 `InputDispatchEvent`/`BlackboardReduceEvent`/`InputFileInjectedEvent`(`callbacks/events.py:256-283`,带 `from_phase`/`to_phase`/`blackboard_snapshot`);`_TraceJsonlSink.emit`(emit.py:23)**无过滤全写** trace.jsonl;backend `_read_events` 全读全 stream → **事件已到前端 runStream.events**。当前 `ContextEdge.getMockEdgeContext` 是**硬编码 mock**,`buildEdges.ts:26` `hasTraceData` 是**启发式**(`!isGlobal`)非真事件。**零 engine 改动、零 backend 架构改动**(事件已流到前端)。

**实施(消费已流到前端的真事件)**:
- 前端 trace 事件类型补 `input_dispatch`(+ 可选 blackboard_reduce):`apps/studio/frontend/src/types/*`(trace/run 事件 union),保证 normalize 不丢弃。
- 纯选择器(新建小工具或就近):`edgeContextFromEvents(events, fromPhase, toPhase)` → 取最近一条匹配 `from_phase→to_phase` 的 InputDispatchEvent,返回其 `blackboard_snapshot`+changed_keys 结构(= properties 面板期望的 contextJson 形状)。
- `apps/studio/frontend/src/components/nodes/buildEdges.ts` / `ContextEdge.tsx`:`hasTraceData` 改为"该边有匹配的真 transition 事件"而非启发式;`getMockEdgeContext` 替换为从 runStream.events 经选择器取真 contextJson(无事件 = 空态,非假数据)。
- 接线:`Workspace.tsx`(已把 `selectedEdge.contextJson` 喂 properties 面板 `context_json`,:164)把 runStream.events 下钻给 buildEdges/edge 选择。
- **纯单测**:`edgeContextFromEvents`(匹配/取最近/无匹配空)+ ContextEdge 静态渲染(真 contextJson vs 空态)。
- **shadcn/现有组件**:edge dot + properties 面板复用现有渲染,不新写组件。

## 工作流(PM 四步)
1. 本计划落盘 ✅。
2. **pre-audit subagent**:核两任务计划是否符合 MVP1 三模块(input F3 / trace-edge 设计单元)+ 确认前端-only + reuse-shadcn 无自造组件。
3. **并行实施**:两 subagent 各做一任务(文件不重叠);**只写代码不跑全量 build**,我统一跑门禁 gatekeep(tsc/eslint/vitest + git diff 核 KEEP-MAIN/api-llm 零改动)。
4. **post-audit subagent**:核两实现 vs 设计 + 真跑门禁。

## Pre-audit 调整(subagent 审计后纳入,2026-06-14)
- **Task1 = CONFORMS**;新 F3 控件用 **shadcn `Button`/`Input`**(不用裸 `<button>`)。
- **Task2 = CONFORMS-WITH-CONCERNS,本轮只做 REQ-3 数据修(真 blackboard 替 mock),不做 REQ-6/D14 结构清理**(dot→trace console 改道 + 结构化 inspector + 删 Properties raw-JSON dump 分支)= **独立延期项**(记 deferred,别把"Properties 里显真 JSON"当 edge-blackboard 完成态)。设计依据:`properties/mvp1-alignment.md:38-45` F3 / `04_run-and-verify.md:99` D14。
- **Task2 C2 形状映射(关键)**:`InputDispatchEvent.blackboard_snapshot` 是**扁平 dict**(dispatch 给 to_phase 的输入键),但 properties 面板 `EdgeContextJson`(`WorkspaceContext.tsx:6-10`)/`PropertiesPanel.tsx:222,235` 按 `.inputs`/`.phase_outputs` 取。`edgeContextFromEvents` **必须显式映射**:扁平 snapshot → `{inputs: snapshot, from_phase, to_phase, changed_keys, ...}`(dispatch 事件无 phase_outputs,它是下游输入)+ 原始全帧。单测**断言渲染形状**(非只断言事件匹配),防 field-name drift 渲染空白。
- **type 说明纠正**:`input_dispatch` 前端**不会被丢弃**(`CallbackEvent` 是开放 `Record` + `useRunStream` 无条件 push);加 TS 类型是 ergonomic(命名取值/收窄),非"防丢弃"。仍是前端改动。
- **C3 housekeeping**:edge-blackboard reclassify frontend-only(本计划 + progress 续5 已记;旧 progress:215/227"edge 黑板=engine scope"被本核实超越——引擎已发事件、已到 runStream.events)。

## 门禁
tsc clean + eslint clean + vitest 全绿(现 467)+ 新单测;api/llm.ts + KEEP-MAIN 零改动;never main;不新增 npm 依赖。

## 并行实施纪律(避免 tsc/vitest 全局并发竞争)
两 subagent 同树、**文件不重叠**(Task1:`schema-infer.ts`+`InputPanel.tsx`+test;Task2:`buildEdges.ts`+`ContextEdge.tsx`+新 selector+test+`Workspace.tsx` edge 接线),**只写代码+写测、不跑全量 build/gate**;我统一跑一次门禁 gatekeep + 修。
