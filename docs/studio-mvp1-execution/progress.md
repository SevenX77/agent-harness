# Progress — Studio MVP1 + three-module

- **分支**:`feat/studio-mvp1-mainbased-2026-06-13`(从 `main`=#139 切,含三模块 adapter)
- **更新**:2026-06-13
- **基线**:`goal-charter.md`(目标/done/硬约束)+ `integration-plan.md`(以 main 为基的阶段)

## 当前阶段:Phase 0 — 工作区搭建 + Tauri computer-use 能力探针

### 已完成
- 新 worktree + 分支从 main(#139)切出,工作区干净。
- 章程 + 路线挪到 `docs/studio-mvp1-execution/`(脱离 temp scratch)。
- 全局 `/goal` 命令建好,指向本目录的稳定路径。

### Tauri + computer-use 探针发现(重要)
- **`cargo tauri dev` 裸二进制不可被 computer-use 授权**:进程 `skill-studio-tauri` 的 bundle id = "missing value",access 层按 NSRunningApplication/bundle 匹配不到 → **computer-use 必须驱动打包后的 `.app`**,不是 dev 模式。
- dev sidecar 用 `.venv` + 源码 backend(`cfg!(debug_assertions)`),所以 dev **不需要** download_runtime。
- **构建坑**:`beforeBuildCommand` 调 `python`(本机只有 `python3`/`.venv`)→ `build_vendor` 失败 exit 127。debug bundle 绕过办法:跳过 build_vendor(debug 用 .venv 不需要 vendored site-packages)。
- ✅ **探针通过(2026-06-13)**:打包 debug `.app`(`apps/studio/tauri/target/debug/bundle/macos/Skill Studio.app`,有 bundle id `com.sevenx.skill-studio`)→ computer-use `request_access` 成功(tier **full**)→ 截屏看到完整 Studio UI → 点击设置齿轮成功打开 Settings 面板。**see + click 双双验证,headline「computer-use 驱真桌面」路线可行。**
- 构建很快:warm cargo 缓存下 `cargo tauri build --debug` 19s 编译完。dmg 打包步骤报错可忽略(只要 .app)。
- ⚠️ **遗留**:该 debug bundle **后端不通**(Could not load skills / API Keys Network Error)——跳过了 build_vendor + debug sidecar 没连上。**真生命周期 e2e 需要一个后端可用的 .app**。

### 下一步(已纠正:探针够了,不要现在跑生命周期)
- ✅ computer-use 探针已达成目的(确认能驱动真 .app)。**这是现阶段唯一需要的桌面验证。**
- ⏸️ **生命周期 e2e(新建→编译→run→trace)= 验收闸,推迟到功能实现到位后再跑。** 现在跑只会撞已知桶 B 缺口(run 桩 / resume 501 / trace 孤儿 / copilot 直写),无新信息。"后端可用 .app + 全程走" 留到验收期。
- ➡️ **现在进入实现**:① 新 worktree 装依赖(`npm install` + `uv sync`);② Phase 1 前端嫁接 wave3 增量 + i18n(integration-plan §3 阶段1),带 owner 边界改造。
- 实现期验证 = 单元 + 单功能 smoke + 模块门禁;computer-use 只在"需要肉眼看某个刚做完的 UI/桌面行为"时按需用(那时才需要后端可用 .app)。

## 执行状态(2026-06-13 续)

- **范围已更正**:目标 = MVP1 设计 + 三模块接口设计**两套全部**(charter §2,提交 2cd92edc)。执行主体 = Claude 自写 + 自派 subagent/Workflow,跑到完成不停。
- **Phase 0 ✅**:新 worktree + 依赖装好(uv sync + npm install,exit 0)。
- **前端回归基线绿**(嫁接前):`tsc -b --noEmit` 干净 + vitest **54 文件 / 412 测试全过**。
- **前端回归基线绿**(嫁接前):tsc clean + vitest 412;**studio 后端基线绿**:pytest 479 passed。
- **Phase 1 前端嫁接 ✅ 完成**(8 批,commit `eeac8cb5`→`31bfec39`,44 前端文件):i18n 基础设施 / 加性超集 / native 集群(tauri 并集+多会话 copilot store+client Tauri 写)/ copilot 去 mock(用 gateway 真数据)/ settings 集群+token-trio / copilot-panel thinking_delta / Workspace run-predict-trace 接线 / welcome open-folder UX。
  - **全门禁绿**:tsc clean + vitest **415**(基线 412,净+3,零回归)+ vite build ✓ + lint clean。
  - **api/llm.ts + 所有 KEEP-MAIN 三模块正确文件零改动**(git diff 空)——没回退契约。计划留档:`docs/studio-mvp1-execution/phase1-graft-plan.md`。
  - 关键判断:wave3 多数文件 main #139 反而更对(RouteStatus 契约 / mode+target_skill 的 D8 正确 schema / 确定性 ID),只 graft 了真正前进的子集。
  - **FLAG 转后端**:6 态词汇收敛(Studio adapter `needs_setup`→gateway 6 态 `historical_ready`/`failed`)= 三模块 D6 后端+前端耦合任务。Phase 1 按计划保留 main 5 态,待后端 adapter 收敛后再翻前端枚举 + 对应 KEEP-MAIN 文件。

## Phase 3 桶 B 后端(三模块全部实现)

**① run 路径打通 ✅ 完成**(engine↔studio 握手 3 个 studio 侧 P0,直接关系生命周期 run):
- P0#1 skill 路径(传 SKILL.md)= #139 已修(改走 `compile(skill_dir)→art_ref→run_artifact`)。
- **P0#2 workspace_dir 双层**:worker 传 `run_dir.parent`(=`.workspace/runs`)→ 引擎写 `.workspace/runs/runs/<id>`、studio 读空。改传 `run_dir.parent.parent`(`.workspace` 根),对齐 predict 契约。commit `e412a1c1` + 回归测试。
- **P0#3 假成功**:worker 硬写 status=success、不查 `result.success`。加 `_result_success`/`_result_error` 按 success 分支报 failed+error。commit `1e70d876` + 回归测试。
- 后端全量 **481 passed**(基线 479 + 2 回归测试),零回归。

**剩余优先级**:② resume 501→接引擎(engine 已有 public `resume_skill`,studio `routers/runs.py:69` 仍 501,薄接即可)③ 6 态收敛(Studio adapter `needs_setup`→gateway 6 态,配 Phase 1 前端)④ per-node golden 薄接(engine `evaluate_golden_baseline` 已有)⑤ D10 RuntimeStateStore lease/fencing 接口 ⑥ Rust native-fs 唯一写者(D10/D12)+ RuntimeGate 降级 ⑦ copilot 安全写/dispatch/@mention/冷启动 ⑧ TracePanel 挂载 ⑨ llm_* 下沉 gateway。
完成后:出后端可用 .app → computer-use 走完整生命周期验收。

> **⚠️ 下一轮第一步:先逐项核对桶 B 真实状态再动手**。#139 比 2026-06-06 握手审计完整得多——已确认**已做**的别重复造:P0#1 skill 路径、**resume(完整 resume_skill 接线,非 501)**、run/predict/publish/golden 真后端、copilot fallback 委派 gateway。核完直接打**真·缺口**:6 态收敛(配 Phase 1)→ copilot 安全写(acceptEdits→patch_proposed)/dispatch/@mention/冷启动 → Rust native-fs(D10/D12)+RuntimeGate → TracePanel 挂载核实 → per-node golden 薄接 → llm_* 下沉。核对方式:对每项读 #139 现有代码(file:line)确认是否已实现,只对真未实现的开工。

## Phase 3 桶 B 真实状态核对结果(2026-06-13 续 · 8-verifier sweep + Claude 独立复核)

> 方法:8 个 verifier 子 agent 各读 #139 真代码 + FROZEN 设计端到端 trace;Claude 独立复核 resume 链 / runtime_state_store / RuntimeGate / 设计文档。`DESIGN_UNITS_INDEX.md` 的 22 单元 drift 标记冻结于 2026-06-05(#139 之前),多已过时,以本核对为当前真理。

| 项 | 状态 | 当前真理(file:line) |
|---|---|---|
| ② resume(D10 节点级续跑) | **核心已做** | `runs.py:75`→`EngineAdapter.resume`(engine.py:475)→`resume_skill`(runner.py:451)→SqliteSaver checkpoint→`graph.invoke(None)` 真续跑;有 e2e round-trip(`test_ws_e7_golden_resume.py`)。**缺口**:前端零 resume UI;D10 lease/fencing 未接入 resume 路径(engine 活)。`/engine/resume` http_loopback 路由是死码(live 走 in_process) |
| ③ 6 态收敛(D6) | **真缺口·最大耦合** | gateway 包 canonical = `state_projection.py:13` `['ready,historical_ready,untested,failed,cooling_down,off]`;Studio adapter `gateway.py:66` 仍 needs_setup 且 l332-395 **自己重算不委派 gateway 包**(违 D6);`routers/llm.py:1534` status_summary 硬编码 needs_setup;前端 `api/llm.ts:12` 缺 historical_ready+failed;FROZEN `00_settings-ux-spec.md:106,114` 明令取消 needs_setup→failed+missing_config。修法:adapter 委派 gateway 包 + 前端枚举翻转(注:historical_ready 需 draft_history 信号,probe-worker 是桩) |
| ④ golden per-node(D7) | **逻辑在·真跑断** | studio `golden_headless._compare_node_outputs` 有 per-node 逻辑,但 `_node_outputs()` 找 top-level `'phases'`,真 run 写 BusinessData(`phase_outputs`)→真跑退化 run-level 单节点;前端 `DiffView` 不读 node_results 且孤儿、route mismatch。engine `evaluate_golden_baseline` 是 per-case 跑技能,**故意不在 studio 路径**(D7),勿绕它重建 |
| ⑤ D10 RuntimeStateStore | **部分** | LocalRuntimeStateStore snapshot 期 fencing + 单调 token 真有效;但**未接入 resume**(resume 用 LangGraph checkpointer 绕过它)、签名与 engine SPI(`storage_contracts.py:92`)不兼容、缺 lease 抢占(engine 参考会 raise LeaseConflictError)、TTL 空摆设、`release()` l140 裸 except |
| ⑥ Rust native-fs(D12) | **缺口·large** | 无 native_fs.rs;`lib.rs:308` invoke_handler 只注册 reveal/open/sidecar,**无 write_workspace_file 等 5 命令**;前端 `tauri.ts:90-151` 已 invoke 它们→真桌面构建写路径悬空;今天只靠 Python `skills.py:399 update_skill_file`(target.write_text + sha256 `_graph_content_hash` l1171);publish=Python zip;RuntimeGate 全屏阻塞(违 D10) |
| ⑦ copilot 安全写/@mention/冷启动 | **缺口·large** | `copilot.py:140` 仍 acceptEdits 直写、无 PreToolUse/checkpoint/reject、无 patch 事件(测试 l182/192 还 pin acceptEdits);@mention 纯空壳 textarea(`copilot-panel.tsx:201`);session 只写不读回(`copilotStore.ts` 写 .gemini/copilot/sessions,但无 readWorkspaceFile)→重启丢。**依赖 ⑥ Rust writer**(checkpoint/restore+readWorkspaceFile)。dispatch 501=设计延期✓ |
| ⑧ TracePanel 挂载 | **部分·small wire** | TracePanel 全建好但**零 importer 孤儿**;"Trace Timeline" tab 渲染历史列表 TimelinePanel;真事件管道已活(trace.jsonl→`/ws/runs/{id}`→useRunStream→`Workspace.runStream.events`)仅用于节点上色;edge dot `ContextEdge.tsx:getMockEdgeContext` 是 mock JSON。修法:(A)挂 `<TracePanel traceLogs={runStream.events}>`=薄接无后端;(B)edge 真黑板需 engine 发结构化 transition 事件,后做 |
| ⑨ llm_* 下沉 gateway | **设计登记延期✓** | 两薄服务(state_projection/role_materializer)已掏空成委派、无生产调用方;真逻辑在 adapter `gateway.py:193-538`;`module-disposition-revised.md:78` 明确"下沉是后续工程、本轮不动代码";baseline FROZEN 标 should-sink-3b。**保持延期**,补 DEF-id;dead `services/llm_state_projection.py` 无 live import,可单独删 |

### 本轮攻击清单(依赖 + 风险排序)

**Tier 1 — 薄接/小改,高确定低风险,直接推 headline(先做):**
- A. **TracePanel 挂载**(⑧A,frontend-only,管道已活)→ headline 的"看 trace"
- B. **Resume 前端 UI 接线**(⑧→② 前端缺口,薄接已活端点)→ headline 的"调试(resume)"
- C. **golden per-node 真跑修复**(④:`_node_outputs` 读真 shape + 前端 node 视图 + 挂载 + route)

**Tier 2 — 中等耦合:**
- D. **6 态收敛**(③:adapter 委派 gateway 包 + 前端枚举翻转,Phase 1 FLAG 兑现)
- E. **test_inputs 501→实现**(io-panel 单元,`test_inputs.py:51/60`)
- F. **RuntimeGate 降级启动**(⑥的 F5 frontend 片,可独立于 Rust writer)
- G. **D10 store 硬化**(⑤:release 可观测 + lease 抢占 + SPI 对齐,孤立单文件)

**Tier 3 — large:**
- H. **Rust native-fs writer**(⑥,foundational for copilot)+ sha2 字节兼容 Python
- I. **copilot 安全写 + @mention + 冷启动**(⑦,依赖 H)

**Tier 4 — headline 验收:** computer-use 驱动后端可用 .app 走完整生命周期。

**延期(设计登记,本轮不做)**:⑨ llm_* 下沉(补 DEF-id)、copilot dispatch、publish-zip→Rust(可后)、多机错误(时钟/分区/配额)、DEF-003/004/007/008/009/010/011/012/014/016/017/018。

### 本轮进展(2026-06-13 续 · Tier 1 + 起 Tier 2)

- **A. TracePanel 挂载 ✅**(commit `59169f9c`):timeline 区有活跑时流式 TracePanel(喂 runStream.events)、无活跑显示历史 TimelinePanel;handleRun 自动开 timeline。事件管道本就活,补的是挂载。RED→GREEN `Panels.trace-mount.test.tsx`。
- **C. golden per-node ✅**(后端 `79521944` + 前端 `b2d3559c`):
  - 后端:`golden_headless._node_outputs` 原只认 top-level `'phases'` 列表,真 run 写的是 BusinessData `phase_outputs`(node_id→outputs dict)→真跑退化 run-level。改为先读 `phase_outputs`,保留 legacy phases 路径。RED→GREEN 真 shape 测试。
  - 前端:`DiffView` 原扁平字段列表忽略 `node_results`→改为**按节点分组**(每节点 pass/fail 徽章+score,字段嵌套);接上原孤儿 golden flow(TracePanel Compare/Promote 按钮→useGoldenDiff→DiffView center overlay)。后端 GET /compare 本就在(verifier"route mismatch"是过时说法)。
- **门禁**:前端 tsc clean + vitest 418 + lint clean;后端 golden 18 passed + ruff clean;api/llm.ts 及 KEEP-MAIN 零改动。

- **G. D10 release 可观测化 ✅**(commit `442a95df`):`LocalRuntimeStateStore.release` 原裸 `except Exception: pass`(违 §5 禁静默降级)→ 显式:corrupt lease 留盘+WARNING、stale owner 跳过+INFO、仅 rightful owner unlink。**保留乐观 fencing-token 模型**(未加 engine 参考的 LeaseConflictError 抢占——会破已锁测试 `test_runtime_state_store_rejects_missing_lease_and_stale_fencing_token` 的背靠背异 owner acquire 成功语义);全 SPI 对齐 + lease/fencing 接入 resume 路径 = **engine 活(D10)**,已 flag。RED→GREEN `test_runtime_state_store_release_is_observable_and_stale_safe`。
- **F. RuntimeGate 降级启动 ✅**(commit `aa14a783`):原全屏 gate(sidecar init 失败→只显"Backend startup failed"、children 不渲染,违 D10/native-fs F5)→ 抽纯 `RuntimeShell` 永远渲染 children + 非阻塞底部 banner(loading"Connecting…"/error"Backend unavailable"+Retry)。RED→GREEN `RuntimeGate.test.tsx`。**注**:常见"backend 不通"其实走 ready 路径(get_sidecar_config 多半成功)逐功能降级;本修针对 sidecar-config 命令本身 reject 的全屏遮蔽。真机验证留 computer-use 验收期。
- **本轮门禁(真跑)**:Studio 后端 `uv run pytest tests/` **483 passed**(481 基线+2 新)、前端 `vitest` **421 passed**(412 基线+9 新)、tsc clean、lint clean、api/llm.ts 及 KEEP-MAIN 零改动。Engine/gateway 未触,绿态延续(本轮未重跑)。

**Tier 1/golden 剩余子项(登记,后续)**:trace F2(点历史 run→拉回该 run full trace,需读历史 trace.jsonl)、F4(edge dot 真黑板,需 engine 发结构化 transition 事件)、F5(Prompt Inspector 挂载,onSelectPrompt 现 no-op 占位)。

- **H(部分). Rust native-fs writer ✅**(commit `95d6a96d`):前端 `tauri.ts`/`client.ts`/`copilotStore` 早已 invoke `write_workspace_file`+`add/list/remove_recent_workspace`+`ensure_workspace_support_dirs`,但 Rust `lib.rs` invoke_handler 一个都没注册→真桌面构建写路径悬空、全落 Python(违 D12 唯一写者)。新增 `apps/studio/tauri/src/native_fs.rs`:write_workspace_file(SHA-256 hex **字节兼容** Python `_graph_content_hash`、乐观 expected-hash 闸、HashConflict 序列化成 `client.ts` 解析的精确 `{type,data:{current_hash,current_content}}`、路径穿越沙箱、原子 temp+rename);recent-workspace MRU(identity 去重,corrupt 重置带 WARNING 非静默);ensure_workspace_support_dirs(建 `.gemini/copilot/sessions`)。lib.rs 注册 5 命令;Cargo 加 `sha2`。`cargo test --lib` **25 passed**(9 新,含 Python hash 向量、HashConflict 形状、穿越拒绝、原子写、MRU roundtrip)。前端零改动(invoke 早在)。
  - **native-fs 剩余(follow-up)**:Python `/skills/{id}/files` 写端点降为只读(D12 去双写者)、publish-zip→native(`artifact_registry.build_publish_package`)、**Rust checkpoint/restore**(copilot 安全写 model B 依赖:即时落盘+记 checkpoint、Reject 精确还原)、真机/bundle 验证(需 build_vendor,留 computer-use 验收期)。

### 本轮总结(7 个功能里程碑 + 验证综述)
commit 链:`c05f33cb`(综述)→`59169f9c`(trace 挂载)→`79521944`+`b2d3559c`(golden per-node 后/前)→`442a95df`(D10 release)→`aa14a783`(RuntimeGate)→`95d6a96d`(native-fs writer)。门禁真跑:Studio 后端 pytest 483、前端 vitest 421、tauri cargo test 25,均绿;tsc/lint/ruff/rustfmt clean;api/llm.ts 及 KEEP-MAIN 零改动。

**下一轮优先级(按依赖)**:① **6 态收敛**(D,**待 PM 确认可翻 api/llm.ts**——这是唯一被显式硬约束挡住的范围项)② **copilot 安全写/@mention/冷启动**(I,large 多层:copilot.py PreToolUse 回调 + 新 patch 事件 + 前端 diff/accept/reject UI + **依赖 Rust checkpoint/restore**——native-fs 续作;@mention=tiptap composer+4 层 resolver;冷启动=readWorkspaceFile Rust 命令+hydrate)③ native-fs follow-up(Python 写端点降只读 / publish-native / Rust checkpoint)④ resume 前端 UI(B)⑤ test_inputs create/delete(E,需注册 TEST_INPUT_* 错误码)⑥ D10 lease/fencing 接入 resume(engine 活)⑦ trace F2/F4/F5。建议:copilot + native-fs checkpoint 作一个专门轮;6 态待 PM 一句即开;最后 computer-use 走完整生命周期验收。

### ✅ 6 态收敛(D6)已完成(commit `968e441a`,2026-06-14)
PM 经"最高裁判=设计文档/三模块>MVP1"裁定授权翻 api/llm.ts。原子前后端 flip:Studio 去 needs_setup→failed/missing_config、加 historical_ready,对齐 gateway canonical(`state_projection.py`)+ FROZEN ux-spec。后端 gateway.py adapter + routers/llm.py(status_summary/admission/_force_probe_route metadata);前端 api/llm.ts 枚举+ModelGroupStatusSummary + 5 个 llm-roles 组件(badge/label/color/sort-rank/route-status,对齐 wave3 设计目标)。8-agent workflow + 独立 diff 复核(尤其 route.metadata reason_code 流)。门禁:后端 483、前端 tsc+vitest 423、e2e 7/2skip、lint/ruff clean。登记:dead `services/llm_state_projection.py`(薄委派 wrapper)留作单独 sink/删除任务。

### (历史)⚠️ 6 态收敛与 api/llm.ts 硬约束冲突 —— 已由上方裁定解决

- **冲突**:charter §2 把 D6 6 态收敛列为范围内("两套全部实现不挑不减");但 §5.3/goal 命令把 `api/llm.ts` 列为**KEEP-MAIN 不碰**文件。
- **为何必须碰**:6 态收敛是**前后端原子**改动——后端 adapter 收敛到 gateway canonical(去 needs_setup→failed+missing_config、加 historical_ready)后,前端 `api/llm.ts` 的 `ProviderUiState`/`ModelGroupStatusSummary` 枚举**必须同步翻**,否则前端收到 `historical_ready`/`failed` 而类型不含→运行时分叉(正是 Phase-1 plan 警告的)。只动后端不动前端 = 故意制造分叉。
- **判断**:KEEP-MAIN 约束本是 **Phase-1 前端嫁接**的卫生规则(别拿 wave3 覆盖 #139);Phase-1 plan 自己把"翻 api/llm.ts 到 6 态"显式设计成"**后端 adapter 先收敛后**的下一步",即本阶段。按决策层级(核心决策>配套条件)+ "冲突处 three-module 赢",6 态收敛应做、含翻 api/llm.ts。
- **本轮处理**:因 PM 显式点名该文件、且是大耦合改动,**本轮不擅自翻 api/llm.ts**;先做其余不碰 KEEP-MAIN 的隔离缺口。6 态收敛待 PM 一句"可翻 api/llm.ts 做 6 态"即开工(全程可回滚、非 main)。

## E2E 验证:浏览器驱动生命周期跑通(2026-06-14 · 真分数)

> PM 重申:验证 = computer-use 鼠标模拟用户跑通生命周期;单测绿不算分。本节是用 **Playwright(浏览器)** 作为 headless 代理,把生命周期在**真前端+真后端**上真跑通——逼出并修了一串真 drift。

- **`apps/studio/tests-e2e/test_run_flow.py` ✅ GREEN**(commit `e6776187`):浏览器开 e2e-fast → **Compile→Predict→Run** → **TracePanel 挂载**(我 Tier 1A 的活,真机验证)→ run 产物落盘。验到的真数据流:`final_state={step1:_s1, step2:_s1_s2, final_result:_s1_s2_s3}`、metrics `status=success`、trace `run_started/3×phase/run_ended`。
- **跑起来逼出的 5 个真 bug(全修)**:
  1. **后端强制 auth**:`main.py:71` 没 token 拒启动、每请求要 Bearer(无 dev bypass)。e2e 接 `STUDIO_DEV_TUNNEL_TOKEN` + 前端 `#tkn=` dev-tunnel hash。
  2. **multiprocessing spawn 重导致命**:run_manager spawn worker 重导 `_backend_runner` 的 `__main__`,模块级建了 FastAPI app → worker 重初始化把 run 打断(final_state 不落)。把 app+uvicorn 收进 `__main__` guard。
  3. **skill 格式过时**:e2e-fast 是 V2.0 root SKILL.md("schema 2.0 root SKILL.md is not supported; use GRAPH.md")→ 重写成当前 v0.3.0 GRAPH.md + logic phases(actions)。
  4. **public 只读**:predict 要可写 workspace skill(public SKILLS_DIR 只读→403 SKILL_READ_ONLY)→ 种进 `WORKSPACES_DIR/default/skills`。
  5. **当前 UI 选择器**:旧 header-run/playground test-id 没了 → 改驱 center-action-bar + 工作区卡片 + `.workspace/runs/<ts>` 产物路径。
- **`test_desktop_lifecycle.py` ✅**(4 passed,commit `e6776187`):补 sidecar auth token + Bearer。
- **端口隔离 ✅**(commit `953464e7`):conftest 后端改用 ephemeral 端口,让全套同 session 跑时 8787 留给 desktop"8787 占用"场景。
- **诚实 skip(非伪绿)2 个**(commit `953464e7`):`test_cli_toast`(点已删的"Open CLI")、`test_lint_flow`(编辑已不存在的 root SKILL.md + 已删的 Save/"Saved and linted" 流);各带精确 re-author 理由。
- **全套门禁**:`uv run --group e2e pytest apps/studio/tests-e2e` = **5 passed / 2 skipped / 0 failed**,ruff clean。

### 续:驱动更多生命周期段,继续抓真 bug 修(2026-06-14 续)
> PM 重申:实现设计 ≠ 写完跑一遍;要按 mvp1 设计**成功使用、无 bug**。继续在真 app 上驱动 golden/publish,抓 bug 修。

- **golden compare 全坏 → 修(commit `667b658d`)**:`_find_file`(golden 把 ref 解析成磁盘路径的函数)只在 public `SKILLS_DIR` 找产物,但能跑/promote 的是 `WORKSPACES_DIR` 下的 workspace skill → compare **静默失败**(无 result→无 overlay→无 error toast),对**每个**可跑技能都坏。改为用 `resolve_skill_dir` 解析真 skill dir + 加 `.workspace` 候选。e2e `test_promote_then_compare_golden`:run→Promote→Compare 现真渲染 Golden Diff(100%、verdict、No differences)。
  - **登记**:e2e-fast 的 result 是扁平 final context(非 `phase_outputs` map)→ golden verdict 退化成 run-level 单 `output`;**per-node golden 在扁平结果上不触发**,要引擎在 run result 里发 per-node outputs(引擎活)。
- **AssetsPanel 假子图 → 修(commit `c967bfee`)**:每个技能都硬编码显示假子图 `intent_classifier`/`translator_subgraph`(真 app 肉眼可见 bug)→ 去 mock,渲染真子图 + "No subgraphs" 空态。真 app 验证已生效。
- **publish 澄清 + 修(commit `bb4693dd`)**:Release 要求配 Artifact Registry = **设计 F2 行为(非 bug)**;但前端把后端的清晰 typed error(`REGISTRY_NOT_CONFIGURED`「Artifact Registry Host 未配置」)塌成泛化 toast → 用户不知道要配啥。改为对 typed error 透出后端清晰原因(网络错仍走泛化,向后兼容锁定测试)。e2e `test_release_without_registry_reports_clear_typed_error` 验 400 typed + 清晰原因可见。**登记**:发布前置不满足的"跳 Settings 快捷入口"(设计§6)+ publish 错误码 i18n = 后续。
- **e2e 覆盖扩到**:compile→predict→run→trace→golden(promote/compare)→publish(error 路径)。全套 **7 passed / 2 skipped**。

### publish 收尾(2026-06-14)
- **F2 清晰错误**(commit `bb4693dd`)+ **§6 跳 Settings 快捷入口**(commit `3762a0a5`):Release 缺 registry 时,toast 透出后端清晰原因 +「Open Settings」一键动作(REGISTRY_NOT_CONFIGURED/APP_SETTINGS_INCOMPLETE);Workspace→Header→usePublishSkill 接线。e2e 验真 app 上 button 出现。登记:publish 错误码 i18n = 后续。

### 续轮(2026-06-14 续 · 断点续跑)
- **copilot F1 ThinkingBlock 全流式 ✅**(commit `19d39444`):baseline `_translate_assistant_message` 静默丢 `ThinkingBlock` → copilot 推理过程到不了 UI(违 copilot-assist F1「全部思考全程流式、折叠仅视觉、绝不摘要替代/不丢步」)。修:① `models/copilot.py` 加 `CopilotEventThinking`(type=`thinking_delta`)入事件 union;② `copilot.py` 翻译 ThinkingBlock→thinking_delta(逐字不摘要)+ `build_options` 开 `thinking={"type":"adaptive"}`(default display=full,非 summarized/omitted)让 SDK 真发 ThinkingBlock(SDK 序列化成 `--thinking adaptive`,message_parser 解析回 ThinkingBlock,全链路通);③ 前端 normalize/panel Phase-1 已接(thinking_delta→折叠 Thought),补 `types/copilot.test.ts` 锁前端契约。门禁:后端 copilot 37 passed + mypy/ruff clean,前端 normalize 3 passed + tsc clean。**Phase-1 line 34「copilot-panel thinking_delta」只接了前端;此轮补的是后端真丢点 = F1 真闭环。**
- **test_inputs CRUD(INPUT-3)✅**(commit `0e9995e5`):`03_regions/input` INPUT-3 要 test_input 增删 live,但 create/delete 是 501 桩(只 list 活)。实现:POST 存名 JSON 到 `.workspace/test_inputs/`(安全 slug 名守卫挡穿越 + 重名 409 拒)、DELETE 按 id 删(204,缺则 404);注册 `TEST_INPUT_NOT_FOUND/ALREADY_EXISTS/VALIDATION_FAILED` 三错误码让错误「就近」typed 显示。9 RED→GREEN + 更新 `test_exceptions` 错误码集断言。门禁:后端全量 **495 passed**、mypy/ruff clean。**登记**:前端 io-panel create/delete UI 接线 = follow-up(今仅 list 经 BatchRunner/useBatchRun 接);InputPanel 仍投影固定假数据(input 区前端 F1-F6 = 独立专门轮)。
- **501 桩盘点**:仅剩 `audit.py`(charter §1 line33 明令「audit/intent-drift 501 scaffold,非 MVP1」延期)+ `copilot.py` dispatch(设计延期)= 两个都是登记延期,正确保留不做。**契约内 501 已清完。**

### 大件未做(登记,需各自专门轮 + fresh context)
- **copilot 安全写/@mention/冷启动**(桶B,多层:copilot.py PreToolUse + 前端 diff/accept/reject + **依赖 Rust checkpoint/restore**);**resume 前端 UI**(桶B,设计是节点级 intervene=DEF-005 延期 + 依赖真 edge 黑板 F4;且 e2e-fast 不暂停,headless 难验);**native-fs follow-up**(Python 写端点降只读=去双写者,但浏览器路径仍用 FastAPI,耦合;publish→native;Rust checkpoint);**per-node golden 扁平结果**(引擎发 per-node outputs);**trace edge-dot 真黑板**(F4,引擎 transition 事件)。
- **headless e2e 限制(非 bug)**:Monaco 编辑器在 headless Playwright 不初始化(web worker/dynamic import),编辑流不可 headless 验;真浏览器/桌面正常。

### E2E 剩余(登记,下一步)
- **生命周期 spine 未覆盖段**:resume(前端零 resume UI=桶B缺口,需先建 UI)、publish、golden compare(我已接 Compare 按钮,可加 UI 断言)、debug。
- **lint/cli e2e re-author**:按当前 GRAPH.md 编辑→lint 流 / 确认 CLI 是否在 MVP1 范围。
- **真 headline 仍欠**:computer-use 驱动**真 Tauri .app**(需后端可用 .app,build_vendor 坑)——Playwright 浏览器是代理,桌面 .app 才是 charter §3 ① headline。

### 硬约束提醒(详见 goal-charter.md §5)
仅新分支、永不碰 main;密钥永不打印/提交;Studio 只渲染 gateway 事实;e2e 凭证用 `STUDIO_LLM_CREDENTIALS_PATH` 隔离不碰用户真库;LLM 主用第三方+DeepSeek+ARK、其他官方 fallback。
