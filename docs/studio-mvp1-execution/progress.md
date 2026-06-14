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

### ⚠️ 6 态收敛(Tier 2D)与 api/llm.ts 硬约束冲突 —— 待 PM 一句确认

- **冲突**:charter §2 把 D6 6 态收敛列为范围内("两套全部实现不挑不减");但 §5.3/goal 命令把 `api/llm.ts` 列为**KEEP-MAIN 不碰**文件。
- **为何必须碰**:6 态收敛是**前后端原子**改动——后端 adapter 收敛到 gateway canonical(去 needs_setup→failed+missing_config、加 historical_ready)后,前端 `api/llm.ts` 的 `ProviderUiState`/`ModelGroupStatusSummary` 枚举**必须同步翻**,否则前端收到 `historical_ready`/`failed` 而类型不含→运行时分叉(正是 Phase-1 plan 警告的)。只动后端不动前端 = 故意制造分叉。
- **判断**:KEEP-MAIN 约束本是 **Phase-1 前端嫁接**的卫生规则(别拿 wave3 覆盖 #139);Phase-1 plan 自己把"翻 api/llm.ts 到 6 态"显式设计成"**后端 adapter 先收敛后**的下一步",即本阶段。按决策层级(核心决策>配套条件)+ "冲突处 three-module 赢",6 态收敛应做、含翻 api/llm.ts。
- **本轮处理**:因 PM 显式点名该文件、且是大耦合改动,**本轮不擅自翻 api/llm.ts**;先做其余不碰 KEEP-MAIN 的隔离缺口。6 态收敛待 PM 一句"可翻 api/llm.ts 做 6 态"即开工(全程可回滚、非 main)。

### 硬约束提醒(详见 goal-charter.md §5)
仅新分支、永不碰 main;密钥永不打印/提交;Studio 只渲染 gateway 事实;e2e 凭证用 `STUDIO_LLM_CREDENTIALS_PATH` 隔离不碰用户真库;LLM 主用第三方+DeepSeek+ARK、其他官方 fallback。
