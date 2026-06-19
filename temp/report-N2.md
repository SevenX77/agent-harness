# 完工报告 · N2 · Authoring · 搭图与编辑

> 给独立审计方（codex）交叉验证用。所有「现状/已实现/偏差」均挂亲自核实的真实代码位置（文件 + 函数/对象名，不写行号）。
> 环境：worktree `/Users/sevenx/Documents/coding/agent-harness/.worktrees/studio-mvp1-mainbased`；手册 `http://192.168.0.47:8902/`；数据文件 `temp/tpl-n2-*.json`；生成器 `temp/build_template_slice.py`。
> ⚠️ 节点边界：编译/lint 门控（绿灯解锁 Predict、Compile drawer、三处投影）归 **N3 Compile**，本节点只把「写回后触发 compile」作为指向 N3 的下游指针，不写 compile 原子。
>
> 🔄 **本版已按 codex 审计（`temp/audit-N2.md`）逐条核实真代码后修正**：① 统计表改回程序汇总（原手填的 canvas/iopanel 细分数错）；② 补漏的浏览器 fallback 写端点；③ 子图拓扑端点补 allowed roots + 错误码；④ #14 下钻（已有多级 drill stack/breadcrumb）、#15 L3（组件已存在仅未接线）、#16 mode（主路径已文件派生）、#18 白名单（MVP 最小子集非全集）、#27 io（output 字段编辑已有）措辞纠偏；⑤ 去 mech 页 ③a/③b 代号、去 impl 页 spec 行号。审计 13 条全部属实、全部已改。

## 1. 概览
- 节点：N2 · Authoring · 搭图与编辑
- surface 拆分：**4 张操作设计页** —— 画布搭建 / Properties 节点属性 / GRAPH.md 宏观契约 / i/o 面板
- 拆分依据：
  - 权威 spec 是 N2 的工作流 spec `docs/studio/mvp1/01_workflows/02_authoring.md`（不是 settings-ux-spec；后者是 N0 的）。其 §1 用户旅程把 N2 定义为「宏观全局契约 → 中观拓扑 → 微观节点编辑 → 实时 compile 门控」，§2 atom action 决策表把区域分成 `canvas` / `properties` / `editor`(GRAPH.md) / `input(→i/o panel)`。
  - 对应真实 UI 组件：画布 = `GraphCanvas`（`GraphCanvas.tsx`，React Flow 画布）；节点属性 = `PropertiesPanel`（`PropertiesPanel.tsx`，选中节点编辑 frontmatter 的右侧面板）；GRAPH.md 宏观契约 = 双击开 `LazyMonacoPanel`（`LazyMonacoPanel.tsx`，懒加载源码编辑器）裸编辑 GRAPH.md 头部；i/o 面板 = `InputPanel` + `SchemaInferPanel`（`InputPanel.tsx`，逐节点 io 字段 + artifact）。compile-lint 区域刻意排除（归 N3）。
  - 与 N0「壳层 + 4 tab = 5 页」颗粒度对齐：N2 无独立壳层（authoring 都在 Workspace 外壳里），实际 4 个并列面板 = 4 张设计页。

## 2. 产出文件
**数据 JSON（11 个）：**
- 设计页：`tpl-n2-canvas-design.json`（画布，原子 1–15）/ `tpl-n2-properties-design.json`（Properties，16–21）/ `tpl-n2-graphmd-design.json`（GRAPH.md 宏观，22–24）/ `tpl-n2-iopanel-design.json`（i/o 面板，25–30）
- 机制（契约）：`tpl-n2-mech-graph.json`（mech_graph，挂画布）/ `tpl-n2-mech-io.json`（mech_io，挂 i/o 面板）
- 前端复用模块：`tpl-n2-femods.json`（8 个模块，单文件被 4 surface 复用、去重）
- 实施 + 测试：`tpl-n2-canvas-impl.json` / `tpl-n2-properties-impl.json` / `tpl-n2-graphmd-impl.json` / `tpl-n2-iopanel-impl.json`（每个含 functions + plan + tests）

**生成器改动（`build_template_slice.py`，一次性公共泛化）：**
- 把 N0 硬编码泛化成「按节点清单」驱动：引入 `_make_nctx`（建节点上下文：页面 id 映射 + anchor 前缀）/ `_build_full`（加载某 full 节点的 stages + 本节点复用模块登记表）/ `_render_full_node`；`render_design / render_contract / render_fe_modules / render_impl_all / render_tests_all / render_node_overview / render_impl` 全部参数化 `nctx`；`render_handbook_overview` 改成遍历节点注册表（`_full_node_card` / `_legacy_node_card`）；`main()` 改成遍历 `NODES` 装配。
- `NODES` 里 N2 翻 full 的那条：`{"code": "N2", "kind": "full", "name": "Authoring · 搭图与编辑", "pages": PAGES_N2, "intent": ...}`
- `PAGES_N2` 清单：`[("canvas", "画布搭建", ...mech_graph...), ("properties", "Properties 节点属性", []), ("graphmd", "GRAPH.md 宏观契约", []), ("iopanel", "i/o 面板", ...mech_io...)]`
- N0 用 `"bare": True` 保持裸页面 id（`contract`/`fe_modules`/`impl`/`tests`）与裸 anchor，N0 的 5 张设计页输出逐字节不变。
- 注：N1、N3–N6 由并行 agent 各自翻 full（共用同一套泛化基建），现 7 节点全 full。

**页面 id 清单（N2，8 页）：** `n2_overview` / `n2_canvas_design` / `n2_properties_design` / `n2_graphmd_design` / `n2_iopanel_design` / `n2_contract` / `n2_fe_modules` / `n2_impl` / `n2_tests`

## 3. 每个 surface 的原子统计
> 程序从 `tpl-n2-*-design.json` 实时汇总（不手填），命令：`python3` 读各 design.json 的 `fe_status`/`be_status` 计数。

| surface | 操作原子数 | 前端实施：符合/偏差/未实施 | 后端契约：已实现/未实现/契约问题/n/a |
|---|---|---|---|
| 画布搭建 | 15 | 11 符合 / 3 偏差 / 1 未实施 | 11 已实现 / 0 未实现 / 2 契约问题 / 2 n/a |
| Properties 节点属性 | 6 | 3 符合 / 3 偏差 / 0 未实施 | 1 已实现 / 0 未实现 / 1 契约问题 / 4 n/a |
| GRAPH.md 宏观契约 | 3 | 2 符合 / 1 偏差 / 0 未实施 | 3 已实现 / 0 未实现 / 0 契约问题 / 0 n/a |
| i/o 面板 | 6 | 3 符合 / 3 偏差 / 0 未实施 | 4 已实现 / 0 未实现 / 2 契约问题 / 0 n/a |
| **合计** | **30** | **19 符合 / 10 偏差 / 1 未实施** | **19 已实现 / 0 未实现 / 5 契约问题 / 6 n/a** |

> 注：无「桩」状态原子（N2 的桩在 N0/N3 侧，不在本节点路径）。#15 L3 后端轴已改「已实现」（保存复用现成 native-fs / fallback 写路径，不需新增端点，见 §6）。

## 4. 后端接口契约清单（逐条）
> N2 对接的「后端」= Studio FastAPI sidecar（gateway/engine 的承载层）+ graph-agent 引擎内核 + Studio Rust native-fs。authoring 内核是 **graph-agent 引擎**，不是 gateway。

| 端点 | 对应真实 router/service/内核 文件 + 函数名 | 请求要点 | 响应要点 | 实现状态 |
|---|---|---|---|---|
| GET /api/skills/{skill_id} | router `skills.py` `get_skill`（response_model=SkillDetail）→ service `skills.py` `compile_skill_for_studio` / `_detail_from_manifest` / `_graph_topology` | path skill_id | SkillDetail：manifest(name/io/phases) + graph_topology(真实 DAG) + 原始 files 文本 | 已实现 |
| POST /api/skills/{skill_id}/graph/serialize | router `skills.py` `serialize_skill_graph` → service `skills.py` `serialize_skill_graph_markdown` → `graph_roundtrip.py` 透传 → 引擎 `graph_serializer.py` `serialize_graph_topology` / `_preserve_graph_markdown_topology` | SerializeGraphReq{phases[{id,src,depends_on,mode}], expected_hash} | SerializeGraphRes{markdown_content, phase_count, current_hash}；[409] snapshot_conflict；[422] CanvasSerializerFatal(orphan/self-cycle/cycle) | 已实现 |
| native-fs write_workspace_file（Rust command，桌面态主写） | Rust `native_fs.rs` `write_workspace_file` → `write_workspace_file_impl` / `create_workspace_file_if_absent_impl` | {workspaceRoot, relativePath, content, expectedHash?, createIfAbsent?} | WriteOutcome{path,hash}；错误 HashConflict{current_hash,current_content} / WriteFailed{message} | 已实现 |
| **POST /api/skills/{skill_id}/files/{file_path:path}**（浏览器 fallback 写，**审计 F4 补漏**） | router `skills.py` `update_skill_file_endpoint` → service `update_skill_file`；边界 `native_fs_write_boundary.py`；前端 `client.ts` `writeSkillFile`（带 header `X-Studio-Write-Fallback: browser`） | path skill_id + file_path；body `UpdateSkillFileReq{content, expected_hash}`；必须带 fallback header | `UpdateSkillFileRes{hash}`；缺 fallback header → `NATIVE_FS_REQUIRED`；hash 冲突 → `snapshot_conflict` | 已实现（非桌面 fallback；桌面态走 native-fs，浏览器态才走它） |
| GET /api/skills/{skill_id}/subgraph?path=… （子图真实拓扑） | router `skills.py` `get_subgraph_child_topology` → service `get_child_graph_topology` + `_allowed_child_graph_roots`；前端 `client.ts` `getChildGraphTopology` | path skill_id + query path；**后端只放行三类 allowed root：父 skill 树 + workspace skills + bundled skills**（非任意绝对路径，**审计 F5**） | ChildGraphTopology{phases[name], graph_topology[{id,mode,path}]}；非法/越界 path → 422 `SUBGRAPH_PATH_INVALID`；合法但找不到 → 404 `SUBGRAPH_PATH_NOT_FOUND` | 已实现（引擎语法要求的「任意绝对路径 + copilot cwd 覆盖」需后端把 allowed roots 扩成配置化 cwd 边界） |
| POST /api/skills/{skill_id}/compile（写回后触发，门控归 N3） | router `skills.py` `compile_skill_endpoint` → service `compile_skill_for_studio` → 引擎 `compile_skill` | path skill_id | CompileSuccess{phase_count, manifest_name, artifact_ref, source_map_ref, execution_fingerprint}；[422] CompileFailure(errors[]) | 已实现（门控呈现归 N3） |
| 引擎 loader 子图 io outputs 1:1 校验（编译期，⚠️ 待删 G2） | 引擎 `loader.py` `_validate_subgraph_io_contracts`（取 parent_outputs/child_outputs 比对）；子图按绝对 path 解析 `_resolve_subgraph_path_root` + `manifest.py` `SubgraphNodeAST`（字段 `target_skill = Field(alias="path")`，真读 `path` key） | 编译期父/子 io.outputs | parent_outputs ≠ child_outputs → FATAL `[F-v3-subgraph-io-mismatch]` | 契约问题（仍 FATAL，G2 要求删；子图 path 已收口、旧 target_skill 字面 key 被拒为 deprecated） |
| 引擎 io/manager artifact 落盘（运行期，归 N4） | 引擎 `io/manager.py` `artifact_saver`（认 target='artifact'/'artifact_manager'） | 运行期 output 字段带 {target:'artifact', path} | 落 .workspace/runs/<id>/artifacts/<path>（md/json） | 已实现（运行期落盘归 N4） |
| REQ-2 字段供需结构化（#10 黑板字段勾选所需） | 现状仅引擎 compile 回吐 `CompileError`（前端 `Workspace.tsx` compileErrorsByNodeId 叠节点）；引擎 `io/manager.py` 有 io.output 字段 type mismatch 报错 | — | — | 契约问题（⚠️ 待后端把字段供需暴露成结构化可勾选数据；spec 自述 REQ-2/FROZEN-4「待统一出 FROZEN 新版本」） |

## 5. 前端复用模块清单（N2 自己的登记处，8 个）
- **graph round-trip 客户端**（`Workspace.tsx` `handlePersistConnection` / `doWriteSkillFile`；`client.ts` `serializeSkillGraph`；`sha256Hex` 算 graphHash）：画布动作写回源码的编排——serialize → 落盘 → 重编译，带 hash 乐观锁。
- **canvas-authoring**（`canvas-authoring.ts` `connectPhaseRefs` / `disconnectPhaseRefs` / `createPhaseDraft` / `phaseFilePath` / `defaultPhaseMarkdown`）：连断线改 depends_on、建节点草稿、三类 FROZEN-clean 脚手架，纯函数。
- **节点类型派生**（`PropertiesPanel.tsx` + `build-nodes.ts` `phaseKindLabel` / `phaseKindFile`；`build-nodes.ts` `mode = topology?.mode ?? phase.mode`）：把 phase 算成 LOGIC/AGENT/SUBGRAPH + 反算文件名。⚠️ 读 data.mode，但**主路径下 data.mode 由引擎按物理文件派生**（`_PHASE_FILE_TO_MODE`，作者写 `mode:` 被 `_reject_phase_forbidden_metadata` 拒）；残留 F1 风险只是 `phase.mode` fallback 兜底 + UI『Mode』标签（审计 F12 纠偏）。
- **phase 白名单序列化**（`phase-frontmatter.ts` `parsePhaseFrontmatter` / `applyPhaseFrontmatterForm` / `frontmatterFromForm`）：三类节点 frontmatter 解析 + 白名单写回 + round-trip 保真。
- **子图 path 解析**（`subgraph-path.ts` `resolveSubgraphReference` / `normalizeAbsoluteSubgraphPath` / `legacySubgraphTargetSkill` / `invalidSubgraphPathMessage`）：判子图引用 resolved/missing/migration-required + 迁移提示。
- **io schema 推断**（`schema-infer.ts` `inferJsonSchemaFromText` / `applyInputSchemaToGraph` / `applyOutputArtifactPathToGraph`；`panel-files.ts` `inputContractView`/`IoContractView`）：io 推断/写回 GRAPH.md/配 artifact 目标，纯函数；假文件投影已删。
- **子图 inline 预览**（`SubgraphInline.tsx` `SubgraphInline` / `childPhaseRows`；`client.ts` `getChildGraphTopology`）：画布上拉子图真实子拓扑预览，绝不编造未声明 phase。
- **命名弹框**（`RoleNameDialog.tsx` `RoleNameDialog`，跨节点共享，与 N0 API Keys / LLM Roles 同一组件）：通用命名/改名弹框，N2 用于画布建节点命名。

## 6. 现状核实证据（最重要）
> 逐条列「偏差 / 未实施 / 契约问题 / 关键已实现」claim，每条挂亲自打开核实的真实代码位置。

**偏差类（前端与设计不符）：**
- #8 reconnect-drag-disconnect「连线四操作只有新建+断连，重连/拖拽断线缺」→ `GraphCanvas.tsx`：有 `onConnect` + 右键 `onDisconnectConnection`（Disconnect 菜单），**无 `onReconnect` / `onReconnectEnd` / `edgesReconnectable`**（grep 两文件零命中）。
- #10 data-gap-viz「前端无供给断层可视化，只有重复覆盖检测」→ `canvas-authoring.ts` `checkSequentialOverwrites`（检的是同字段被重复写，非上游缺供给）；供需校验靠引擎 compile 回吐 `CompileError`（`Workspace.tsx` compileErrorsByNodeId）。⚠️ REQ-2 字段勾选 UI 是 BLOCKER（spec 待统一 FROZEN）。
- #14 subgraph-drilldown「**多级下钻导航已实现，下钻后编辑写回未闭环**」（审计 F2/F8 纠偏）→ `GraphCanvas.tsx` `drillInto`/`drillNavigate` + `drill-stack.ts` `drillStackReducer`（push/pop/popTo 多级下钻栈）+ `DrillBreadcrumb.tsx`（逐级面包屑）+ 按 path 拉各级 child topology + 双击 subgraph 下钻聚焦——能多级下钻看子拓扑；缺的是 `build-nodes.ts` `buildNodesFromTopology` 给 drilled child 节点的 `filePath` 留空、即「进入子图后编辑写回」未接线。⚠️ 引擎 io 切片契约**已 pin**（`skill-syntax §2.10` io 切片 + §2.4「子图从黑板切片、不要求父子 1:1」），blocker 收窄到 Studio child-edit UX（child root 身份 / 保存走哪棵 GRAPH.md / compile scope），**不是切片契约未定**。
- #16 node-type-derivation「**主路径已文件派生，残留 fallback + 标签**」（审计 F12 纠偏）→ `PropertiesPanel.tsx` `phaseKindLabel` 读 data.mode；data.mode = `build-nodes.ts` `topology.mode ?? phase.mode`，而 `topology.mode` 是引擎 `loader.py` `_PHASE_FILE_TO_MODE`/`_discover_phase_files` 按物理文件派生注入、`_reject_phase_forbidden_metadata` 拒作者写的 `mode:`（禁止字段含 `mode`）。所以主路径类型已据文件、作者改不了；残留 F1 风险只有 `?? phase.mode` fallback（可能 stale）+ UI 把它叫『Mode』。非「主路径可变 mode 派生 bug」。
- #17 readonly-mode-row「底部只读区暴露 Mode 行，误导用户」→ `PropertiesPanel.tsx` `DetailRow` 渲染 `label="Mode"` 的只读行（与「类型=文件名」口径冲突）。
- #20 subgraph-whitelist「path 字段+迁移提示已有，缺找不到导入入口」→ `PropertiesPanel.tsx` subgraph 分支渲 `path` Input + legacy 迁移提示（`subgraph-path.ts` `resolveSubgraphReference`）；**无 OS 选文件夹导入入口**（grep folder picker/dialog 仅命中 ui/alert-dialog，无 F4 导入接线）。
- #22 macro-contract-form「头部靠裸编辑，无结构化表单」→ 头部只能双击开 `LazyMonacoPanel` 裸编辑 GRAPH.md，`PropertiesPanel.tsx` 无 name/schema_version/llm_role/description 受控字段 + phases 列表的头部表单。
- #27 io-panel-perfield「**graph-level io.inputs/outputs 字段编辑已实现，缺的是 per-node**」（审计 F10 纠偏）→ `InputPanel.tsx` `IoSchemaFieldsPanel`（逐字段编辑器、对 inputs/outputs **两侧都生效**）+ `IoFieldRow`/`IoFieldAddRow`（增删改字段）+ `OutputArtifactPathPanel`（output artifact 路径）。**output 字段编辑也有**，非只「偏起点 input + artifact」。真正缺口：整图级 io 编辑还没扩成选中任一节点挂它自己的 i/o 面板。
- #28 any-io-import-file「导入入口主要在 input 节点侧」→ `InputPanel.tsx` `SchemaInferPanel`（拖入导入主要服务起点 input），其它节点 i/o 界面导入未铺开。
- #30 subgraph-io-no-1to1「**引擎 loader 仍有 1:1 FATAL，与 spec 硬冲突（硬阻塞）**」（审计 F9）→ 引擎 `loader.py` `_validate_subgraph_io_contracts`：`parent_outputs != child_outputs` 报 `[F-v3-subgraph-io-mismatch]`（仅比 outputs 集合）。但 `skill-syntax §2.4` 明写「子图从黑板切片、**不要求**父子字段集合一一对应」——spec 与 code 硬冲突。这条 fatal 实际阻塞子图 io 编辑，**保持硬阻塞**直到 loader 实际删/改该校验（按 §2.10 切片规则校验）。前端无此校验、无活；子图已按绝对 path 解析。

**未实施类（前端未接线，非未写）：**
- #15 l3-step-edit「**组件已存在但未接线**」（审计 F3 纠偏）→ `AgentStepsInline.tsx` `AgentStepsInlineView`（画布内联渲染 step 列表的展示组件）+ `agent-steps.ts` `parseAgentSteps`/`addAgentStep`/`removeAgentStep`/`reorderAgentSteps`/`updateAgentStep`（对 body 文本增删改序的纯函数）**都已实现**，但 `AgentStepsInline` 没挂到画布/节点编辑入口（孤儿，仅自身+测试引用）。保存复用现成 `Workspace.tsx` `handlePhaseFileSave` → `doWriteSkillFile` → native-fs `write_workspace_file`（桌面）/ `POST /skills/{id}/files/{path}`（浏览器 fallback）。**真实缺口 = 接线，不需新增后端 mutate 端点**。

**关键已实现/符合类（重点核实，纠正旧 stale 结论）：**
- #3 tb-layout「rankdir 已 TB」→ `lib/layout.ts` `getAutoLayoutedElements` 设 `rankdir: 'TB'`（纠正 spec `02_authoring.md` 标的「现 LR」过时）。
- #13 subgraph-inline-preview「已接真子拓扑、非 mock」→ `SubgraphInline.tsx` `childPhaseRows`（注释「Never fabricates a phase that the child graph does not declare」）+ `client.ts` `getChildGraphTopology`（纠正旧审计「渲染假数据」过时）。
- #25 input-field-edit「假文件投影已清」→ `panel-files.ts` `IoContractView`/`inputContractView`（注释明确删除 input/schema.json、input/sample.json 两假文件）（纠正 spec 标的「投影 io 成假文件 stale」过时）。
- #4 create-node-is-file「脚手架 FROZEN-clean」→ `canvas-authoring.ts` `defaultPhaseMarkdown` 三模板（`logicPhaseMarkdown`/`agentPhaseMarkdown`/`subgraphPhaseMarkdown`）：subgraph 用 `path:` 非 target_skill，无 system_prompt/exit_contract/python_callable/可编辑 mode。
- #18/#19/#20 三类白名单「已重建，但 agent 是 **MVP 最小子集** 非全集」（审计 F6 纠偏）→ `phase-frontmatter.ts` `frontmatterFromForm`：agent→llm_role/tools/subagents、logic→actions/validator、subgraph→path/validator。logic/subgraph 对齐 engine §2.3/§2.4；agent 是引擎 `manifest.py` `AgentNodeAST` 的最小子集——引擎 agent 全集还含 `subgraphs[]`（按 path，§2.4）/`references`/`examples`/`max_iterations`，Properties 暂未覆盖。**不应表述成「完整对齐引擎语法」**；若 agent `subgraphs[].path` 要纳入 N2 MVP 需补编辑形态。
- #21 whitelist-roundtrip-save「保留 name/io/未知键/body」→ `phase-frontmatter.ts` `applyPhaseFrontmatterForm`（以原 frontmatter 浅拷贝为起点、只 set/delete 白名单键、body 原样拼回、空值 delete）。
- #9 cycle-detection「环检测在 layout.ts 非 GraphCanvas」→ `lib/layout.ts` `graphlib.alg.isAcyclic` 抛 `CycleDetectedError`（纠正旧线索「环检测在 GraphCanvas.tsx 某段」——那段实为 fit/toggle 工具函数）。
- #30 子图解析口径「引擎按绝对 path 解析、非读旧 target_skill」→ 亲自读引擎 `manifest.py` `SubgraphNodeAST`（`target_skill: str = Field(alias="path")`，真读 `path` key）+ `loader.py`（字面 `target_skill:` 被拒为 deprecated）。**此处解决了深挖稿 C 与审计 subagent 的矛盾：以真代码裁定 loader 读 path，纠正「读 target_skill」措辞。**

## 7. spec 依据
- `docs/studio/mvp1/01_workflows/02_authoring.md`（N2 工作流 spec，最高设计裁判）：§1 用户旅程目标（宏观契约→拓扑→节点编辑→compile 门控；节点类型=文件名、无 type/mode 字段，FROZEN）；§2 atom action 决策表（M1 头部表单 / M2+M3 io inline / M4 起点终点节点 / T1+T2 连断线 / T3 环+数据断层 / T4 建 phase / T5 子图 inline / T6+T7 下钻+context / REQ-1 TB 布局 / REQ-2 黑板字段勾选 / REQ-10 Properties 白名单 / 顺序覆盖冲突 / 失败退路 / R3 input files 导入 / R4 连线四操作 / R5 子图同步）；§3 设计决策（D7 子图按 path / G2 删子图 io 1:1 / G3 artifact 落盘 / D12 写全量 Rust / D-1-4 脚手架）；§5 测试关键点；§6 跨切债。
- engine 字段 SSOT `docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md`：§2.3 Logic 白名单（actions/validator）、§2.4 Subgraph（path/validator）、§2.5 Agent（llm_role/tools/subagents），phase-editing F1（类型据文件）/F2（白名单）/F4（子图 path 导入）。
- 后端实施手册 `temp/studio-mvp1-12d-repair-framework-2026-06-15.html`：引 D8（GRAPH parse/serialize：d8.1 roundtrip / d8.2 Canvas 写回 / d8.3 fingerprint / d8.4 子图 path）、D12（native-fs：d12.1 写 / d12.3 hash 冲突 / d12.4 copilot carve-out）、D2.2（RunArtifactStore artifact 落盘）标后端状态。
- ⚠️ N2 节点对应 spec 是 `02_authoring.md`，**不是** 任务环境里写的 `00_settings-ux-spec.md`（那是 N0 的）。

## 8. 自检结果（审计修正后重跑）
- `python3 temp/build_template_slice.py` 能 build：**是**（输出 `OK -> temp/index.html`，无 Traceback）。
- 本节点（n2_* / n2- 锚点）断链数：**0**（全部解析）。
- 本节点重复 id：**0**。
- 全局自检（含并发节点）：全局重复 id 0、全局断链 0、div 平衡 16472=16472。
- 浏览器 fallback 写端点已渲进 html（grep `NATIVE_FS_REQUIRED` 命中）；渲染后 html 无 `③a/③b` 代号、N2 数据文件无 `xx.md:NN` spec 行号（审计 F11 已修）。
- 与 N0 模板一致：**是** —— 页型（节点主页 + 设计×4 + 契约 + 复用模块 + 实施 + 测试）/ 卡片系统 / 两轴状态 / 一色一义 / 不写行号 / 后端分层统一写「Studio FastAPI sidecar / graph-agent 引擎内核 / Rust native-fs」（已去 ③a/③b 裸代号）/ 左导航子页标签与正文标题逐字一致。

## 9. 已知缺口 / 延期 / 等后端 / ⚠️待定
- **⚠️ BLOCKER #10 data-gap-viz（REQ-2 黑板字段勾选 UI）**：交互模型 + 后端字段供需结构 spec 自述「待统一出 FROZEN 新版本」（`02_authoring.md`），尚未 pin。手册已显式标「落地前不实现、等 FROZEN」。等后端把字段供需暴露成结构化可勾选数据。
- **#14 subgraph-drilldown 下钻编辑写回（blocker 已收窄，审计 F8）**：引擎 io 切片契约**已 pin**（`skill-syntax §2.10` + §2.4「不要求父子 1:1」），不再是「切片契约未定」。多级下钻导航（drill stack/breadcrumb/child topology）已实现；剩的是 **Studio child-edit UX**——子图根目录如何成为写入 root、保存走子图自己的 GRAPH.md、compile scope（父图还是子图）、错误回滚。属 Studio 侧设计，不是引擎契约缺口。
- **硬阻塞 #30 子图 io 1:1（G2）**：引擎 `loader.py` `_validate_subgraph_io_contracts` 仍 FATAL，与 `skill-syntax §2.4`「不要求 1:1」**硬冲突**；后端删/改前子图 io 编辑被硬阻塞（前端无活）。
- **等后端 #28 任一节点导入字段的运行期注入时机**：归引擎 `io/manager.py`，需后端定「跑到该节点才注入」契约。
- **前端独立可做（不等后端）**：#8 重连/拖拽断（接 React Flow onReconnect）、#15 L3 内联骨架、#16/#17 类型派生改文件优先+删 Mode 行、#20 子图 path 标红+Tauri 选文件夹导入入口、#22 头部结构化表单、#27 逐节点 i/o 面板。
- **无桩**：N2 路径上无后端桩（桩在 N0 的 draft probe、不在本节点）。
- **R5 另一半**：「assets 文件树 ↔ 子图文件同步」归 asset-explorer（file-editing 能力），已在画布设计页 intro 声明不在 N2 范围。

## 10. 偏离 N0 模板之处 + 原因
- **N2 无独立壳层设计页**（N0 是「壳层 + 4 tab = 5 页」，N2 是 4 个并列面板 = 4 页）。原因：authoring 没有独立壳层 surface，搭图操作都在 Workspace 外壳内的画布/面板上发生；按真实 UI 面板划分而非机械凑 5 页（符合方法论「按它实际的页面/面板划分」）。
- **契约页拆成 2 块机制**（mech_graph + mech_io），N0 apikeys 是 1 块（mech_cred）。原因：N2 的两块后端机制本质不同 owner——round-trip/native-fs/冲突归「同一棵可执行树」（d8+d12），io/artifact/子图引用归引擎 io/manager+loader；按本质分（方法论 §1.0），不是按体积。
- **生成器做了一次性公共泛化**（N0 当时硬编码）。原因：handoff §4.2 要求第一个深化节点的 agent 先把生成器泛化成「按节点清单」；做了并保持 N0 输出字节内容不变（5 张设计页逐字节一致，聚合页仅中性化措辞如「5 个页面汇总」→「N0 汇总」，为所有节点共享）。
- 除上述外：**无**其它偏离（页型、卡片、两轴、配色、引用规范均照搬 N0）。
