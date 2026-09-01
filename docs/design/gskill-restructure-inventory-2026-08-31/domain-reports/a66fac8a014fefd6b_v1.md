Evidence gathered across both repos. Report follows.

---

# 三辅助域域级对账

**扫描基线**:主仓 `D:\coding\agent-harness` @ `d034e5f1`;engine 仓 `D:\coding\graph-skill-runtime` @ `230fc3bd`。

## 前置:premise 校正(先纠证据,再谈账)

任务书里五处数字/坐标与实际不符,后续结论按实测口径:

| premise | 实测 | 坐标 |
|---|---|---|
| 新仓路径 `integrations/assets/moirai/` | 实为 `src/graph_skill_runtime/integrations/assets/moirai/`(仓根**无** `integrations/`) | `D:\coding\graph-skill-runtime\src\graph_skill_runtime\integrations\assets\moirai\` |
| tauri CLI **23** 命令 | **40** 条注册命令(23 in `lib.rs` + 17 in `native_fs.rs`) | `apps\studio\tauri\src\lib.rs:4392-4433` |
| i18n **8** namespace | **9**(第 9 个 `runtimeGate`) | `apps\studio\frontend\src\i18n\namespaces.ts:56-79` |
| `formatTimestamp` 无日期缺陷 | `formatTimestamp` **有**日期(委托 `dateAndTime`);真缺陷在 `formatLogTime`(纯 `HH:MM:SS`)。另 `dateAndTime` 缺**年** | `GeneralTab.tsx:642-649`;`src\utils\wall-clock.ts:56-80` |
| copilot SDK 探测走 `AsyncAnthropic` | 全仓 **0** 处 `AsyncAnthropic`;探测同样用 `ClaudeSDKClient`。⚠️ 成立但机制不同(见域一③) | `copilot.py:2038-2110`;`copilot.py:815-819` |

---

# 域一:委托域

## ① 应然

**Effect**:用户不必手写 gskill 源文件 —— 在 Studio 面板里说话、或在外部 CLI 里说话,都能让 agent 代写;每一次落盘前用户看得见改了什么并能否决;关掉重开接着聊;三工位分工可编排。

**own 概念词表**(本域独占定义,别处不得再定义):`CopilotSession` / `CopilotEvent`(及 `CopilotEventText`/`CopilotEventError`)/ `SessionCacheKey` / `ToolApprovalResolution` / `_SafeWriteSink` / `CopilotSkillBinding` / `CopilotImageAttachment` / `CheckpointStatus` / `CliTerminalState` / `CodeAssistantId`。

**膜**:三层同心。
- 外膜 = `can_use_tool` 回调(`copilot.py:667-723`):SDK 唯一权限入口。
- 中膜 = `bind_tools_to_open_skill`(`copilot_tools.py:2040`):未绑定 skill 的工具面**在物理上不存在**,`build_copilot_mcp_servers` 的 `binding` 无默认值(`copilot_tools.py:2029-2036` 注释明写"让调用方记得传就是把结构性保证降级成纪律")。
- 内膜 = Rust 唯一写者(`native_fs::write_workspace_file` / `checkpoint_workspace_file`):Accept/Reject 都经 Rust,Reject 从 checkpoint 还原而非反向覆盖(`patch-proposed-bubble.tsx:174-176`)。

**北极星贡献**:主打「比裸写简单」(自然语言→gskill)+「去黑盒」(42 工具全部有名有参、审批卡渲染参数明细)。**不贡献** engine+AST 核心,**弱贡献**本地=服务端。

## ② 实然(file:line)

**42 工具边界表 —— 封闭已验证**:`_DECLARATIVE_ALLOWED_TOOLS`(`copilot.py:118-147`)含 21 条 `mcp__studio__*` + 5 条原生;`_MCP_APPROVAL_WRITE_TOOLS`(`copilot.py:154-178`)含 21 条。**21 + 21 = 42 = `copilot_mcp_tools()` 返回长度**(`copilot_tools.py:1989-2027`)。表封闭,无第三档,无漏项。

| 档 | 21 条 | 语义 |
|---|---|---|
| **零审批**(`_ZERO_APPROVAL_TOOLS`, `copilot.py:148`) | get_llm_roles / search_llm_registry / **compile_skill** / get_skill_overview / read_skill_file / get_workspace_config / list_run_artifacts / read_run_artifact / **run_role_test** / get_skill_output_contract / **predict_skill** / get_run_detail / query_run_trace / wait_for_run / list_golden / get_golden_content / get_resume_validity / **test_llm_endpoint** / **test_llm_endpoint_models** / **probe_llm_route** / **fetch_web_page** | 读 + 探测 |
| **须审批** | create_skill / run_skill / resume_run / pause_run / stop_run / publish_skill / fork_skill / set_output_artifacts / write_skill_file / bind_test_input / set_golden_baseline / write_golden_case / delete_golden_baseline / create_llm_role / update_llm_role / delete_llm_role / apply_model_profile_to_role / upsert_llm_endpoint / delete_llm_endpoint / update_llm_route / delete_llm_route | 写配置真相 + 写 skill 实体 + 真实执行 |

三档权限流有显式注释锚点(`copilot.py:281-295`),且 exp-B 事故(未知工具 fall-through Allow → PowerShell 零审批写越界)已用"名单外一律挂起、无默认放行档"结构性封死。Bash 另有 `PreToolUse "ask"` hook 双保险(`copilot.py:445-461`),理由写在 `:449-451`:沙箱对"安全只读命令"的自动放行会**绕过** `can_use_tool`(实测 `find | wc -l` 直通)。

**功能接线清单**:

| 特性 | 状态 | 坐标 |
|---|---|---|
| patch 气泡 Accept | ✅ 接线 | `patch-proposed-bubble.tsx:138-153` |
| patch 气泡 Reject(经 Rust 从 checkpoint 还原) | ✅ 接线 | `patch-proposed-bubble.tsx:159-182` |
| patch 气泡 Compare | ✅ 接线 | `patch-proposed-bubble.tsx:108,194` → `copilot-compare-overlay.tsx` |
| checkpoint 撤销(seed/clear/restore 三命令) | ✅ 接线 | `native_fs.rs:1201-1233`;`patch-proposed-bubble.tsx:71-88,126-134` |
| @mention | ✅ 接线(4 类候选:filePaths/phases/diagnostics/trace) | `composer/mention-candidates.ts`;`copilot-panel.tsx:540-545,1283`;送出于 `:960` |
| 图片附件(by value) | ✅ 接线,含拒收路径 `RefusedImage` | `composer/attachment-intake.ts`;`copilot-panel.tsx:536-538,85-101` |
| 审批过期 | ✅ 接线,过期卡自述 | `copilot.py:398`(`_TOOL_APPROVAL_TIMEOUT_S` 默认 1800s,env 可覆盖)、`:545-561`;前端回归测试 `an-expired-hold-says-so-on-its-own-card.test.tsx` |
| 会话持久恢复 | ✅ 接线(落盘 + window state 双写) | `copilotStore.ts:236-246,343-369` |
| 三工位编排 | ✅ 接线(4 roles → AgentDefinition) | `app/agents/roles/{moirai,clotho,lachesis,atropos}.md`;`copilot.py:235-240` |
| 外部 CLI(PTY) | ✅ 接线 | `cli_terminal.rs:105-195`(`portable_pty`);5 条 tauri 命令 |
| vendored ah 自动布署 | ✅ 接线,**失败不缓存**(旧 bug 已修) | `lib.rs:44-46`(`AH_READY` 只缓存成功)、`:148-188`、`:279-300` |

## ③ 账实不符

1. **探测路 ≠ 聊天路,不等价点已被代码自己写明**。`build_options` 无 `can_use_tool` 时(= 探测路)走 `permission_mode="acceptEdits"` + `_ALLOWED_TOOLS` 全放行(`copilot.py:106,815-819,841`),且 `mcp_servers` 空(`copilot_tools.py:2029` 明写"probe 路不挂,保持探测确定性")。**后果**:探测绿灯只证明"CLI 子进程 + base_url + model + 一次 tool loop 通",对 42 工具面、审批挂起、写围栏、checkpoint —— 全域生产护栏 —— **零覆盖**。用户在 Settings 看到的绿勾与"面板能不能安全干活"没有推理关系。

2. **3 条写工具在审批卡上裸奔**。`_MCP_APPROVAL_WRITE_TOOLS` 21 条,`_WRITE_TOOL_ACTION_LABELS`(`copilot.py:180-199`)仅 18 条。缺 `set_output_artifacts` / `write_skill_file` / `bind_test_input` → `_build_write_tool_approval_detail`(`:213`)回落成裸工具名 `mcp__studio__write_skill_file`。**恰是三条最像"改你源文件"的工具**,审批卡上最不该没有人话标签。

3. **零审批档里混了 5 条有真实外部副作用的工具**。`run_role_test` / `predict_skill` / `test_llm_endpoint` / `test_llm_endpoint_models` / `probe_llm_route` 都会**发真实付费 LLM 请求**;`compile_skill` 会写编译产物。按「只收语义已知且无文件系统写/命令执行副作用」的自述口径(`copilot.py:110-117`)它们合规,但口径本身把"花钱"排除在副作用之外 —— 这是口径缺一维,不是实现违规。⚠️ 需裁决:副作用轴要不要加"计费"。

4. **审批超时可被环境变量放大到无穷**。`STUDIO_TOOL_APPROVAL_TIMEOUT_S`(`copilot.py:398`)无上界校验。

## ④ 概念多 owner 违章(全列)

| 概念 | owner A | owner B | 判 |
|---|---|---|---|
| **MoirAI 资产**(roles/skills/knowledge) | `apps/studio/backend/app/agents/` + `agent_assets.py:21` | engine 仓 `src/graph_skill_runtime/integrations/assets/moirai/` + `integration.json` | **已批归新仓**。漂移已 100%:4 个同名 role 文件**逐行全异**(`clotho.md` 24 vs 22 行 / 46 行变更;`moirai.md` 22 vs 27 / 49);`KB-00-hub.md` 44 vs 24 行 / 60 变更;`KB-04-agent-nodes.md` **61 vs 18 行**(3.4×)。8 个 skill **命名规则不同**(主仓 `brainstorming`/`compile-error-repair`/`moirai-intro`;新仓 `moirai-brainstorming`/`moirai-compile-repair`/`moirai`)。最恶:**KB 编号槽位撞名不同义** —— KB-11 = `workspace-runtime`(主) vs `runtime-config`(新);KB-12 = `llm-roles` vs `agent-execution`;KB-13 = `studio-gates-tools` vs `runtime-tools`。而 KB-00-hub **按编号路由**,于是"KB-12"在两个 owner 里指两份不同文档。这不是两份副本漂移,是**两部各自独立的作品共用文件名**。 |
| 资产完整性指纹 | `agent_assets.fingerprint_of` / `assets_fingerprint()`(`agent_assets.py:155,169`) | — | **假保证**:只指纹主仓那一份,检测得到单 owner 内漂移,检测不到跨 owner 分叉 —— 恰好给了错误的安心感。 |
| 工具白名单事实源 | `copilot.py:118`(`_DECLARATIVE_ALLOWED_TOOLS`) | `copilot_tools.py:1989`(`copilot_mcp_tools()` 返回列表) | ⚠️ **双向手工同步**。测试锁定"两名单不相交",但**不锁定"并集 == 42"**。加第 43 个工具而忘记登记 → 静默落入"挂审批"档(安全侧失效模式,可接受),删工具而忘删名单 → 名单里留幽灵条目(无检测)。 |
| "ah" 这个名字 | 仓根 `ah.toml:1`(开发期 agent 团队编排 SOP:master + c1/c2 + o1/d1/r2 + r1 + test) | `lib.rs:40-188`(桌面版 "Open in CLI" 的运行时前置依赖,`AH_VERSION_MIN = "1.8.2"`,vendored 快照自动布署) | **同名异物,零关系**。全仓 grep 确认:`apps/studio/backend/app/` 与 `packages/*/src` 中**无任何** `ah` 运行时调用(仅 `.pyc` 二进制误命中)。ah **不参与** gskill 执行。 |

## ⑤ 死码/未接线(逐个已查 git log -S)

| 对象 | 判决 |
|---|---|
| `POST /api/skills/{id}/copilot/dispatch` → 501(`routers/copilot.py:46-55`) | **已挂载**(`main.py:192`)、**前端零消费者**(grep `copilot/dispatch` 全 `src/` 无命中)。`git log -S'dispatch_copilot'` 最早 `3aac2748`(Studio MVP1 Phase 0-3),函数 docstring 自述"Preserve the existing Copilot dispatch scaffold **until T2.6** wires SDK events" —— 而 T2.6 的实际落地是 `662eea53`(T2.2/2.3/2.4)之后走了 **WebSocket** 路(`routers/websockets.py`),脚手架的续接条件**已被另一条路满足**。**未见主动下线裁决**。按 no-backward-compat:**删**。 |
| `GET /api/skills/{id}/runs/{run_id}/audit` → 501(`routers/audit.py:20-21`) | **已挂载**(`main.py:196`)、**前端零消费者**。`git log -S'get_run_audit'` **唯一**命中 `03999d98`(monorepo 物理迁移)—— 即它从未被功能性提交碰过,是搬进来的原生脚手架。`AuditResult` 模型 + `raise_not_implemented` 一并孤立。**未见主动下线裁决**。按 no-backward-compat:**删**(整个 `routers/audit.py` + `models/audit.py` + `main.py:26,196`)。|
| `golden.py` 三处 `responses={501: ...}`(`:33,58,100`) | **非**脚手架 —— 三条路由都真正返回数据(`list_golden_baselines_for_skill` / `set_golden_baseline_for_run` / `plan_golden_baseline_for_run`)。501 是**过时的 OpenAPI 声明** = 文档撒谎。**裁**:删 `responses` 里的 501 项。 |

## ⑥ 对其他域依赖(指名 API)

- **执行域**:`run_manager.start_run_from_artifact`(经 `run_skill_tool`/`resume_run_tool`);`run_liveness`;`resume_downstream`;`run_trace_query`。
- **发布共享域**(域二):`publish_skill_tool`(`copilot_tools.py:1319`)→ `publish_pipeline`;`fork_skill_tool`(`:1366`)。**委托域是发布域唯一的 agent 侧入口**。
- **LLM 配置域**:12 条 `*_llm_*` 工具直接 `from app.routers import llm` 调路由函数(**不经 service 层**,如 `copilot_tools.py:1928` `llm.probe_route`)—— 层级跳跃,routers 被当 service 用。
- **平台域**(域三):`native_fs::{write,read,checkpoint,seed,restore,clear}_workspace_file`;`cli_terminal::*`;`vendored_ah` 布署链;`agent_assets.agents_dir()` 依赖 vendor 快照存在。
- **Web 访问**:`web_access.fetch_page`(动词表对写动作封闭 —— `copilot.py:144-146`)。

## ⑦ Level-3 模块候选

**候选:`copilot-permission`(权限与审批)** —— 从 `copilot.py` 2138 行中 **split-first** 抽出 `:106-199`(三份名单 + 标签 + 脱敏)、`:281-341`(sink/挂起态)、`:347-398`(清理 + 超时)、`:445-513`(两个 hook)、`:667-760`(`can_use_tool` + `resolve_tool_approval`)≈ **480 行**。

**三类合并证据(→ 判定"该拆",不该合并)**:
1. *变更耦合证据*:exp-B 事故、Bash hook 补丁、`AH_READY` 式"只缓存成功"教训,均只改这一簇,不碰会话/流式/翻译。
2. *测试独立证据*:前端已有专门回归 `an-expired-hold-says-so-on-its-own-card.test.tsx` / `a-decision-outlives-its-card.test.tsx`,后端断言"两名单永不相交"—— 这些测试的被测面就是本候选边界。
3. *概念自足证据*:own 词表(`_SafeWriteSink`/`ToolApprovalResolution`/三档名单)与会话词表(`SessionCacheKey`/`CopilotSession`)零交集。

**八项义务缺口**(拆前必须补):(a) 应然一句话 —— 有,`copilot.py:281-295` 现成;(b) own 词表 —— 有;(c) 膜 —— 有;(d) 不变量 —— 部分(不变量 3「密钥明文绝不进审批卡/日志」已写在 `:206-207`),**缺**"并集 == 工具总数"不变量;(e) 证据 —— 前端足,后端**缺**"42 = 21+21"门禁测试;(f) 依赖显式化 —— **欠**,12 条 LLM 工具跳层 import routers;(g) 反例/事故档 —— 足(exp-B、Bash 沙箱绕过、AH 失败缓存);(h) 北极星归属 —— 明确(去黑盒)。

**否决候选**:`copilot_tools.py`(2052 行)**不**够 Level-3 —— 它是 42 个彼此无耦合的薄适配器 + 一个绑定器,无 own 不变量,拆了只是搬文件。

## ⑧ 工单

| # | 工单 | 依据 |
|---|---|---|
| D1-1 | **补 3 条缺失审批标签** `set_output_artifacts`/`write_skill_file`/`bind_test_input` | `copilot.py:180-199` vs `:154-178` |
| D1-2 | **加"42 封闭"门禁**:断言 `len(copilot_mcp_tools()) == len(_ZERO_APPROVAL_TOOLS ∩ mcp) + len(_MCP_APPROVAL_WRITE_TOOLS)`,且并集覆盖全体 | ④ 双向手工同步 |
| D1-3 | **裁掉 `copilot/dispatch` + `runs/{id}/audit` 两条 501 脚手架**(含 `routers/audit.py`、`models/audit.py`、`main.py:26,196`);清 `golden.py:33,58,100` 的过时 501 声明 | ⑤ |
| D1-4 | **裁决:副作用轴是否含"计费"**。若含,5 条真实付费探测工具需迁档或加会话级预算闸 | ③-3 |
| D1-5 | **探测路补齐生产护栏**,或明确降级为"连通性探针"并在 UI 上取消"绿勾=可用"的暗示 | ③-1、`copilot.py:815-819` |
| D1-6 | `STUDIO_TOOL_APPROVAL_TIMEOUT_S` 加上界 | ③-4 |
| D1-7 | **12 条 LLM 工具改走 service 层**,不再 `from app.routers import llm` | ⑥ |
| D1-8 | **【指定】执行域 ah-executor 与本域 ah 集成的边界划分**。**实测事实**:两者**同名异物、零代码关系**。① 仓根 `ah.toml` = 开发期 agent 团队编排 SOP,与产品无关,**不属任何产品域**;② `lib.rs` 的 `vendored_ah`/`deploy` 链 = 桌面 "Open in CLI" 的**运行时前置依赖**,纯属委托域;③ engine 仓**无** `ah_executor`(grep `ah_executor|AhExecutor` 零命中),执行域的 executor 是 `integrations/` 下的 direct agent CLI executors(`37d080b0 feat: add direct agent CLI executors`)。**裁决建议**:边界划在"谁 spawn 进程"—— 委托域 spawn 交互式 PTY 会话给**人**用(`cli_terminal.rs`),执行域 spawn 非交互 executor 给**图**用(engine 仓)。二者不得共用版本门禁常量(`AH_VERSION_MIN` 归委托域独占)。同时**改名消歧**:文档/代码中 `ah`(编排 SOP)与 `ah`(CLI 二进制)必须用不同词。 |
| D1-9 | 立 Level-3 `copilot-permission` 模块,补 (d)(e)(f) 三项义务 | ⑦ |

---

# 域二:发布共享域

## ① 应然

**Effect**:一次 publish 产出**内容寻址、版本锁定、可脱离源文件独立运行**的资产;团队三动作(存/取/评审)走 Gitea;社区目录能上下行 verified 能力事实。

**own 概念词表**:`PublishResult` / `ReleaseArtifactRef` / `HeaderReleaseIdentity` / `PublishPackageWriteRequest`/`Outcome`/`Error` / `CollaborateResult` / `GitHistoryItem` / schema `studio.publish.package.v1`(`native_fs.rs:433`)。

**膜**:两道。① **Rust 唯一写者 + 不覆盖**:`publish_package_writer_impl`(`native_fs.rs:403-431`)三重路径校验(`safe_join` + `ensure_existing_path_components_inside_workspace` + `ensure_final_parent_inside_workspace`)后,`target.exists()` → `Conflict` 硬拒。② **artifact store 内容寻址**:`store.get(artifact_ref["content_hash"])` 在起 run 前先取物(`skills.py:433`)—— 取不到就不跑。

**北极星贡献**:**北极星④「发布物 = 锁定版本的可复用资产」的唯一雏形**,并强贡献"流程可靠可重现"(content_hash 锁定)。

## ② 实然

**Team 菜单确为 5 项**(`Header.tsx:261-286`),且**分两组、有语义隔断**:
- git 组:`Save to Team`(`skillSync.save`)/ `Sync from Team`(`skillSync.sync`)/ `Submit for Review`(`handleSubmitForReview` → devBranch + prTitle)
- 分隔符 + 标签 **"Artifact Registry (not git push)"**(`Header.tsx:274-276`)—— 明确告诉用户下面两项不是 git:`Release`(`publish.publish()`)/ `Package release`(`handlePackageRelease`)

**Release 身份可见**:`releaseIdentity` 悬浮显示 4 元组 —— `artifactId` / `contentHash` / `manifestRef` / `remoteSyncLabel`(`Header.tsx:222-226`)。这是"去黑盒"的正面样本。

**后端 7 条路由**(`routers/skills.py`):`:365` GET releases / `:379` GET release / `:408` POST releases/{v}/runs / `:479` POST sync / `:564` POST publish / `:903` GET history / `:921` POST revert。

**社区目录**:`sync_verified_catalog`(`community_catalog_sync.py:145`)下行,`community_catalog_upload.py` 上行,`_autoshare_after_probe_best_effort`(`llm.py:181-253`)在两处探测后触发(`:1306`、`:1450`),三态可观测(`autoshare_uploaded`/`autoshare_failed`/`sync_verified_catalog_skipped`)。

## ③ 账实不符

1. **`run-from-release` 后端完备、前端不存在** —— 域内最大空洞。`POST /{skill_id}/releases/{release_version}/runs`(`skills.py:408-437`)实现完整(404 处理、artifact 预取、错误分流 `_raise_release_artifact_error`/`_raise_release_store_error`),`run_manager.start_run_from_artifact` 就位。但前端 `api/client.ts` **只有 GET**(`:345`),**无 POST**;grep `releases/` 在 `src/` 的全部命中除 `client.ts:345` 外**都在 `.test.ts(x)` 里**。**后果**:应然的"发布物 = **可复用**资产"里的"用"字**没有用户路径** —— 用户能造出锁定版本的资产,但在 UI 里无法运行它。北极星④ 只兑现了一半(锁定 ✅ / 复用 ❌)。

2. **零真机测试成立(限定于 e2e)**。`tests-e2e/` 共 9 个文件(`test_analysis_bar` / `test_cli_toast` / `test_desktop_lifecycle` / `test_io_panel_test_inputs` / `test_lint_flow` / `test_run_flow` / `test_timeline_history`),**无一触碰** publish/release/sync/catalog。但**单测/路由测不空**:`backend/tests/services/` 11 个 + `backend/tests/routers/` 8 个 = **19 个**发布域测试文件,含 `test_productization_publish_atomicity_red.py`、`test_publish_package_rust_writer_boundary.py`、`test_run_manager_release.py`。**修正口径**:不是"零测试",是**"零端到端真机证据"** —— 恰恰是这个域最需要的那种(涉及 Rust 写者 + 文件系统 + 远端 Gitea 三个真实边界,单测全部 mock 掉了)。

3. **`Release` 与 `Package release` 的时序耦合无解释**。`Package release` 的 `disabled={!releaseIdentity}`(`Header.tsx:282`)—— 只有先点过 `Release` 才能打包。用户视角是"两个按钮里一个莫名灰着",UI 无一句提示。

## ④ 概念多 owner 违章

| 概念 | owner A | owner B | 判 |
|---|---|---|---|
| **"发布"这个动词** | `publish_pipeline.py`(509 行,artifact registry 语义) | `git_collab.py` / `skills.py:479` sync(git push 语义) | ⚠️ 已用 UI 标签"Artifact Registry (not git push)"(`Header.tsx:275`)缓解 —— 但这是**在 UI 上贴纸条**,不是概念分离。两条链在 `Header.tsx` 同一个 `isBusy` 里互斥(`:117`),即代码承认它们抢同一把锁,却不肯给出统一名字。 |
| **package 落盘** | `publish_pipeline.py`(后端,产出 manifest) | `native_fs::publish_package_writer`(`native_fs.rs:403`,前端经 tauri 直调,写 `.workspace/releases/*.package.json`) | ⚠️ **同一次"打包"跨进程双写者**。schema `studio.publish.package.v1` 在 Rust 侧硬编码(`native_fs.rs:433`),后端 manifest 格式在 Python 侧 —— 两侧格式无共享 schema 源。 |
| release 身份 | `HeaderReleaseIdentity`(前端派生,`Header.tsx:45-51,118`) | 后端 `PublishResult` | 派生逻辑 `getReleaseIdentity(publish.lastResult)` 在前端 —— a11yLabel 拼装(`Header.test.tsx:125`)是前端事实,后端不知道。可接受(呈现层),但**归属需登记**。 |

## ⑤ 死码/未接线

| 对象 | 判决 |
|---|---|
| `POST /{skill_id}/releases/{v}/runs` | **不是死码,是未接线** —— 后端活、有 `test_run_manager_release.py`、前端无入口。**裁:补前端**(见 ⑧ D2-1),不删。 |
| `GET /{skill_id}/history` + `POST /{skill_id}/revert` | ✅ **已接线**。`client.ts:1020,1025` → `useRunHistory.ts:10,143`(SWR key `/skills/{id}/history`)→ `panels/HistoryPanel.tsx` → `components/history/HistoryPanel`。`Workspace.tsx:794-806` 有一段注释解释"开 skill 时不冷加载 /history,靠 revalidate"。**活的**。 |
| `_autoshare_after_probe_best_effort` | ✅ 接线且有三态测试(`test_community_catalog_autoshare.py:84,100,133` 覆盖 upload-disabled / shared / choice-unset)。**活的**。 |
| 两条 501 脚手架 | 归域一 ⑤ 处置(`copilot/dispatch`);`runs/{id}/audit` 虽在 runs 路径下但属审计而非发布,同归域一。 |

## ⑥ 对其他域依赖

- **执行域**:`run_manager.start_run_from_artifact(skill_id, request, artifact_ref=...)` —— 发布域向执行域的**唯一** API,且是 release→run 的关键接缝。
- **平台域**:`native_fs::publish_package_writer` tauri 命令;`revealInFileManager`(`Header.tsx:28`);`writePublishPackage`(`lib/tauri`)。
- **LLM 配置域**:`llm.py:1306,1450` 探测完成后调 autoshare —— **反向依赖**(配置域主动调发布域),方向可疑。
- **委托域**:被 `publish_skill_tool` / `fork_skill_tool` 调用。
- **artifact store**:`_product_artifact_store()`(`skills.py:417`)、`ProductStoreLocal` 适配器。

## ⑦ Level-3 模块候选

**候选:`release-artifact`(发布物身份与取用)** —— `publish_pipeline.py`(509)+ `artifact_registry.py` + `skills.py:365-437`(3 条 release 路由)+ `native_fs.rs:403-460`(Rust 写者)。

**三类合并证据**:
1. *变更耦合*:`test_productization_publish_atomicity_red.py` / `test_productization_publish_artifact_red.py` / `test_productization_run_artifact_flow_red.py` —— 三个 `_red` 文件同批产生,证明"发布原子性 + artifact 引用 + run-from-artifact"是**一次设计**的三个面。
2. *不变量自足*:content_hash 寻址 + 不覆盖 + 起 run 前先取物 —— 三条不变量彼此闭合,不需要外部概念。
3. *膜清晰*:Rust 唯一写者已是物理膜(`native_fs.rs:403-431`)。

**⚠️ 但当前不满足 split-first 的义务 (e)「证据」**:19 个测试全在 mock 层,**零真机**。**结论:先补真机证据,再立模块** —— 否则会把"未验证"固化成"已封装"。

**否决候选**:`community_catalog_*`(3 文件 674 行)—— 概念上确实自足(verified 能力事实的上下行),但它的 own 概念(verified capability)真正的 owner 是 **LLM 配置域**,发布域只是搬运工。**不在本域立模块**。

## ⑧ 工单

| # | 工单 | 依据 |
|---|---|---|
| D2-1 | **接线 run-from-release**:`client.ts` 补 `POST /skills/{id}/releases/{v}/runs`,UI 给入口(建议挂在 `releaseIdentity` 悬浮卡上,它已展示 contentHash) | ③-1、`skills.py:408` vs `client.ts:345` |
| D2-2 | **补发布域真机 e2e**:至少一条 `publish → package → run-from-release` 全链,落进 `tests-e2e/`(现 9 文件零覆盖) | ③-2 |
| D2-3 | **统一 package schema 单一源**:`studio.publish.package.v1` 从 `native_fs.rs:433` 硬编码提出,后端 manifest 与 Rust 写者共读一份定义 | ④ |
| D2-4 | **解耦或解释 `Release`/`Package release` 时序**:要么合成一步,要么 disabled 态给出人话原因 | ③-3 |
| D2-5 | **裁 autoshare 依赖方向**:配置域探测完成不应直调发布域;改为发布域订阅事件(`event_bus.py` 已在) | ⑥ |
| D2-6 | **两条 501 脚手架处置** —— 与 D1-3 合并执行(裁决:删,均无消费者、均无主动下线记录) | 域一⑤ |
| D2-7 | 「发布」动词二义性:给 git 链与 artifact 链各自的**代码级**名字,不只 UI 标签 | ④ |

---

# 域三:平台域

## ① 应然

**Effect**:用户装完包看到的行为 = 开发者在 dev 树里验过的行为;三个 OS 都能装;偏好/语言/主题记得住;升级、卸载、换机器各有说得出的行为。

**own 概念词表**:`SidecarConfig`(`sidecar.rs:53-76`)/ `resource_root` / `python_runtime_dir` / `site_packages` / `VendoredAh` / `QuitFlushState` / `STUDIO_CONFIG_DIR` / `STUDIO_RESOURCE_DIR` / `STUDIO_SKILLS_SOURCE_DIR` / `namespaceResources` / `Theme`。

**膜**:`sidecar.rs` 的路径解析函数群 = 唯一"我在哪"的判定处。`python_runtime_dir`(`:646-649`)**刻意不做候选搜索**(`:640-645` 注释:另两个名字 `vendor/python_runtime`、裸 `python_runtime` 曾试过并被下线),且有诱饵测试锁定(`:865-877` 摆两个假目录验证不被选中)。这是本域最硬的一道膜。

**北极星贡献**:**「本地=服务端」的物理承载**;并为其余全部北极星提供"证据环境=发货环境"这一前提 —— 若此域失守,**其他域的一切证据同时失效**。

## ② 实然

- **打包链**:`.github/workflows/package.yml` → `download_runtime.js`(CPython 下载,`python-runtime.lock.json` 锁 sha256,`:163,174`)→ `build_vendor.py`(uv export + uv pip install **for 目标 ABI**)→ `ensure_vendor.js` / `ensure_ah_vendor.js` → `sync_resources.js`(拷 backend/app + skills/resources)→ tauri build。
- **`build_vendor.py` 两条正确性规则写在 docstring**(`:11-17`):① 为**vendored** CPython 安装而非当前解释器(native wheel ABI);② 装全 workspace 闭包含本地 `packages/`。两条都是"曾经的潜在 bug"。
- **`sync_resources.js` 有一条事故档**(`:36-49`,ledger D3):曾把 `&lt;repo&gt;/../skills`(即 `D:\coding\skills`,39 个私有 skill)当第三候选源 → `bundle.resources` 的 `vendor/**` 会**整包发货私有 skill**。已删该候选,现只认 `STUDIO_SKILLS_SOURCE_DIR` 或 repo 自己的 `skills/`,并明写"A path nobody named is not a decision"。
- **`download_runtime.js` 另一条事故档**(`:14-21`):下载缓存曾放 `vendor/downloads/`,被 `vendor/**/*` 捎带 **48.9 MB tar.gz 进安装包**;现刻意移出 `vendor/`。
- **i18n**:9 namespace,**显式注册表、无 glob**(`namespaces.ts:20-53` 长注释解释两种存放约定共存 —— 5 个集中式 `src/locales/` + 4 个就地 co-located),2 语言(en / zh-CN)。
- **主题**:`themeStore.ts` —— `systemTheme()`(`:15-19` matchMedia)+ `readStoredTheme()`(`:26`)+ `subscribeTheme`(`:112`)+ 系统变更监听(`:96`)。**双向成立**。
- **数据分布**:`STUDIO_CONFIG_DIR` 单一 override 点(`app/core/paths.py:23` ← `sidecar.rs:680` 注入 ← `lib.rs:1356-1368` 解析),**多实例隔离有测试**(`native_fs.rs:1750` "running with STUDIO_CONFIG_DIR keeps its own list")。

## ③ 账实不符

1. **多平台:应然全灭**。`package.yml` **只有 `runs-on: windows-latest`**(`:54`),**唯一产物 `bundle/nsis/*-setup.exe`**(`:109`)。而 `sidecar.rs`/`build_vendor.py` 里 darwin-arm64 / darwin-x86_64 / linux-x86_64 / linux-aarch64 四个 triple 全部就位(`build_vendor.py:36-42`;`sidecar.rs:627-631` 处理 `bin/python3.12` 回落)。**账**:代码为 5 平台准备好了;**实**:CI 只造 1 个平台的包。engine 仓有 `5aa5bb8a ci: gate releases on cross-platform artifacts (#9)` —— **跨平台门禁做在了 engine 仓,没做在发货 Studio 的仓**。

2. **updater:结构性缺席,已确证**。`tauri/Cargo.toml` 与 `tauri.conf.json` 中 `updater` 命中数 **0/0**;`tauri.conf.json` **无 `plugins` 块**。升级 = 手动重装。**连带后果(应然"搬家/升级有定义的行为"全空)**:重装是否保留 `%APPDATA%` 数据、`.workspace/`、`vendor/ah` 布署态 —— 代码里**没有任何一处**表达过这件事的意图。无卸载清理逻辑,无数据迁移版本号。

3. **vendor/venv 分叉:根因已定位到具体两行**。
   - `sync_resources.js:62-70` `copyBackend()`:`fs.rmSync(target)` + `copyDir(backend/app → vendor/backend/app)` —— **物理拷贝**,gitignored(`tauri/.gitignore:8`),**无版本戳、无内容 hash、无 mtime 比对**。全仓 grep `stale|VERSION|hash|mtime|freshness` 命中 **仅 1 处**,且是 `build_vendor.py:76` 的 `--no-hashes`(uv export 参数,与新鲜度无关)。
   - **物理证据:同一份 `paths.py` 现存 4 副本** —— `backend/app/core/paths.py`(源)、`tauri/vendor/backend/app/core/paths.py`、`tauri/target/debug/vendor/backend/.../paths.py`、`tauri/target/release/vendor/backend/.../paths.py`。
   - **对比反证**:`vendor/ah` **有** VERSION 戳,且语义严谨 —— `lib.rs:125-127` 明写"VERSION 由 ensure_ah_vendor.js 在校验+解压成功后**最后**写入:它在,旁边的二进制就完整"。**同一个 vendor 树里,ah 有完整性戳而 backend 没有**。这不是能力缺失,是没做。
   - **纪律替代结构的书面证据**:`docs/development/PROBLEM_LEDGER.md` 中"**真机点验前须重建 vendor**"作为人工提醒**反复出现**(E3、E6 等条目);E6 更记录了一次**真机点验推翻了先前的 ✅** —— 即"装着 #895 的 vendor"与源码不同步导致的误判正是这条纪律失效的实例。
   - **判定**:这是**系统性盲区的结构性根因**,而非若干偶发 bug。dev 路(源码树 + repo venv,经 `studio-dev.ps1` → `dev_studio.js`)与 packaged 路(`vendor/python/&lt;triple&gt;/python.exe` + PYTHONPATH=`vendor/site-packages`+`vendor/backend`,`sidecar.rs:670-718`)是**两个互不知情的 Python 世界**。「证据环境=发货环境」这条应然**在结构上不成立**。

4. **日志时间戳缺陷(坐标已校正)**:`formatLogTime`(`GeneralTab.tsx:647-649`)→ `timeOfDay`(`wall-clock.ts:56-59`)→ 纯 `HH:MM:SS`。用于 `:510`(最新日志摘要)与 `:567`(日志列表每行)。三天前的日志行显示 `06:58:12`,与今天的**不可区分**。次级:`dateAndTime`(`wall-clock.ts:71-79`)`Intl` 字段只给 `month/day/hour/minute` —— **缺年**;`formatTimestamp`(`:642`)用它渲染 truth source 的 `updated_at`,跨年即歧义。`wall-clock.ts:82-89` 已存在带年的第三个函数,**GeneralTab 没用它**。

5. **`vendor/` 与 `target/*/vendor/` 双份 + 无 gitignore 覆盖后者**:`tauri/.gitignore:6-12` 只忽略 `/vendor/*`(前导斜杠 = 仅顶层),`target/` 另有忽略。可用但**语义不清**:两处 vendor 谁是权威没有声明。

## ④ 概念多 owner 违章(全列)

| 概念 | owner A | owner B | owner C | 判 |
|---|---|---|---|---|
| **backend 源码** | `apps/studio/backend/app/`(权威) | `tauri/vendor/backend/app/`(`sync_resources.js:66` 拷贝) | `tauri/target/{debug,release}/vendor/backend/app/`(构建产物再拷) | **本域头号违章**。4 副本,无一处 hash/戳/门禁。就是 ③-3 的分叉本体。 |
| **Python 解释器** | repo venv / uv(dev 路) | `vendor/python/&lt;triple&gt;`(packaged 路,`sidecar.rs:646`) | — | 二者**依赖闭包不同**(dev 用 uv.lock 全量;packaged 用 `uv export --no-emit-project --no-editable` 结果)。无一致性断言。 |
| **"vendor" 这个词** | `vendor/python` + `vendor/site-packages`(Python 运行时) | `vendor/backend` + `vendor/resources`(应用源码/资源快照) | `vendor/ah`(第三方二进制) | ⚠️ 三种完全不同的东西共用一个目录名和一个 `bundle.resources` glob `vendor/**/*`。**这个 glob 正是两次发货事故(39 私有 skill、48.9MB tar.gz)的共同放大器** —— 因为"vendor 里的一切都发货"是隐式规则,而"什么该进 vendor"没有 owner。 |
| **完整性戳约定** | `vendor/ah/VERSION`(有,`lib.rs:125-127`) | `vendor/backend`(无) / `vendor/site-packages`(无) / `vendor/resources`(无) | `vendor/python/.python-runtime.json`(有,`download_runtime.js:112`) | **约定存在但只覆盖 2/5** —— 有戳的两个都是"下载来的第三方",没戳的三个都是"我们自己拷的"。恰好反了:自己拷的才是会漂移的那些。 |
| i18n 存放约定 | `src/locales/{en,zh-CN}/*.json`(5 ns) | 模块就地 `*/locales/*.json`(4 ns) | — | ✅ **不算违章**:`namespaces.ts:20-53` 显式声明"两种约定共存 by design",并指定本文件为唯一接缝,新模块走 co-located。**这是本次盘点里最规范的一处 owner 声明,可作模板。** |
| 时间格式化 | `wall-clock.ts`(3 函数,权威) | `GeneralTab.tsx:642-654` 三个本地包装(`formatTimestamp`/`formatLogTime`/`timestampValue`) | — | ⚠️ 薄包装本身无害,但 `formatLogTime` 选了错误的底层函数 → ③-4。 |

## ⑤ 死码/未接线

| 对象 | 判决 |
|---|---|
| `sidecar.rs:627-631` darwin `bin/python3.12` → `bin/python` 回落 | **未接线路径**(CI 从不产 mac 包),但**不是死码** —— 是为多平台预留的正确实现。`:865-877` 有单测。**裁:保留**,由 D3-1 激活。 |
| `build_vendor.py:36-42` 四个非 Windows triple | 同上,**保留**。 |
| `wall-clock.ts:82-89`(带年的第三个格式化函数) | **有实现、GeneralTab 未用**。**裁:接线**(D3-4),不删。 |
| `verify_installed_sidecar.ps1`(`tauri/scripts/`) | 存在但未在 `package.yml` 中调用(grep `runs-on|matrix|target` 未见)。⚠️ **需单独查**:若确未接入 CI,则是"已写好的安装后验证脚本没人跑" —— 恰是 ③-3 最需要的门禁。**列为 D3-2 的现成起点**。 |
| `lib.rs:8645-8652` `invoke_handler_exposes_no_subscriber_driven_teardown_command` | ✅ 活的元测试(用 `include_str!("lib.rs")` 自扫注册块)。**保留** —— 且是"用测试锁定注册表"的好样本,可复用给 D1-2。 |

## ⑥ 对其他域依赖

- **被全域依赖**(本域是地基,依赖是单向入):
  - 委托域:`native_fs::*` 12 命令、`cli_terminal::*` 5 命令、`vendored_ah` 链、`agent_assets.agents_dir()` ← `vendor/resources`。
  - 发布共享域:`native_fs::publish_package_writer`、`revealInFileManager`、`open_path`。
  - 执行域:sidecar 生命周期(`restart_sidecar` / `restart_sidecar_automatic` / `get_sidecar_stderr` / `confirm_quit_ready` + `QuitFlushState`)。
  - 全后端:`app/core/paths.py:23` ← `STUDIO_CONFIG_DIR`。
- **本域向外依赖**(应为零,实际有一处):`sync_resources.js:56-58` 读 repo 根 `skills/` —— 打包链依赖**内容域**的目录约定。

## ⑦ Level-3 模块候选

**候选:`shipping-vendor`(发货环境物化与新鲜度)** —— `tauri/scripts/{download_runtime,ensure_vendor,ensure_ah_vendor,sync_resources}.js` + `backend/scripts/build_vendor.py` + `tauri/src/sidecar.rs` 的路径解析群(`:53-102,540-560,622-649`)+ `verify_installed_sidecar.ps1`。

**三类合并证据**:
1. *事故同源证据(最强)*:三起事故 —— 39 私有 skill 发货(`sync_resources.js:36-49`)、48.9MB tar.gz 发货(`download_runtime.js:14-21`)、`[google]` 类 vendor 陈旧误判(`PROBLEM_LEDGER.md` E6 "真机点验推翻先前 ✅")—— **三起全部是"vendor 边界没有 owner"的不同表现**,且三处修复注释都在互相解释同一件事。
2. *不变量已成文但分散*:「vendor 里的一切都发货」「VERSION 最后写入才算完整」「为目标 ABI 装依赖」「路径解析不做候选搜索」—— 四条不变量分散在 4 个文件的注释里,无一处集中声明。**这正是"该立模块"的教科书信号**。
3. *测试已成簇*:`download_runtime.test.js` / `ensure_vendor.test.js` / `ensure_ah_vendor.test.js` / `sync_resources.test.js` + `sidecar.rs:865-877` 诱饵测试 —— 5 处测试的被测面恰好合成本候选边界。

**八项义务缺口**:(a) 应然 —— **缺**,需新写"证据环境=发货环境"一句话;(b) own 词表 —— 有(见 ①);(c) 膜 —— 有(`sidecar.rs` 路径解析群);(d) **不变量 —— 分散,须集中并补第五条「vendor/backend 与源码内容一致」**;(e) **证据 —— 最大缺口:无跨环境一致性门禁**;(f) 依赖显式化 —— 一处越界(读 repo `skills/`);(g) 反例档 —— **最充实**(3 起事故 + 2 处"曾试过并下线"记录);(h) 北极星 —— 明确(本地=服务端 + 全域证据前提)。

**否决候选**:`i18n`(9 ns)—— `namespaces.ts` 已是自洽的显式注册表,**已达标不必升级**;单独立模块只会增加一层。

## ⑧ 工单

| # | 工单 | 依据 |
|---|---|---|
| D3-1 | **`package.yml` 加跨平台 matrix**,产 mac(dmg/app)+ linux(AppImage/deb)。代码侧四 triple 已就位,只差 CI。可直接借 engine 仓 `5aa5bb8a` 的门禁形状 | ③-1、`package.yml:54,109` vs `build_vendor.py:36-42` |
| D3-2 | **【指定】vendor 分叉的根治方向**。**根因**:`sync_resources.js:62-70` 物理拷贝 backend 源码入 `vendor/backend`,**无任何新鲜度表达**(全仓仅 1 处 hash 相关字符串且无关),而同树的 `vendor/ah`(`lib.rs:125-127`)与 `vendor/python`(`download_runtime.js:112`)**都有**完整性戳 —— 约定存在却只覆盖"下载来的",漏掉"自己拷的"。**三步根治,按优先级**:&lt;br&gt;**(1) 立即 —— 让分叉可被发现(补齐既有约定,零新机制)**:`copyBackend()` 末尾按 `vendor/ah/VERSION` 的同一手法(校验成功后**最后**写)落 `vendor/backend/.content-hash`,内容 = 拷贝源 `backend/app` 的递归内容 hash(复用 `native_fs.rs` 已有的 `workspace_text_hash` 思路);`sidecar.rs` 启动时比对源树(dev 下可比,packaged 下源树不存在则跳过)不一致即在启动日志和 Studio 里**响亮报错**,而不是静默跑旧码。这一步把 `PROBLEM_LEDGER` 里"真机点验前须重建 vendor"这条**人工纪律换成结构**。&lt;br&gt;**(2) 短期 —— 让分叉不可能发生**:dev 路不再有第二个 Python 世界。`dev_studio.js` 改为**也走 `vendor/python` + `vendor/site-packages`**,`vendor/backend` 在 dev 下用**符号链接/junction 指向源树**而非拷贝(Windows 用 `fs.symlinkSync(..., 'junction')`,无需管理员权限)。dev 与 packaged 从此共用同一解释器与同一份 backend 源 —— **「证据环境=发货环境」由结构保证,不由重建纪律保证**。&lt;br&gt;**(3) 中期 —— CI 门禁**:把已存在但(经查)未接入 `package.yml` 的 `tauri/scripts/verify_installed_sidecar.ps1` 接进打包工作流,并扩展为"装完包后跑一遍冒烟 + 断言 `.content-hash` == 本次 commit 的 backend hash"。&lt;br&gt;**(4) 同时 —— 拆掉 `vendor/**/*` 这个放大器**:`vendor` 一词现承载三类物(运行时 / 应用快照 / 第三方二进制),`bundle.resources` 的 wholesale glob 是两起发货事故的共同放大器。改为按类分目录 + **逐类显式列举**,让"什么该发货"成为一个有 owner 的决定 | ③-3、④、`sync_resources.js:62-70`、`lib.rs:125-127`、`download_runtime.js:112`、`PROBLEM_LEDGER.md` E3/E6 |
| D3-3 | **updater 立项或明确不做**。若不做,须**写下**升级/卸载/搬家的行为定义(`%APPDATA%` 保留策略、`.workspace/` 归属、`vendor/ah` 布署态处置、数据格式版本号),现状是**零表达** | ③-2、`Cargo.toml`/`tauri.conf.json` 各 0 命中 |
| D3-4 | **修日志时间戳**:`GeneralTab.tsx:647` 的 `formatLogTime` 改用 `wall-clock.ts:82-89` 的带年函数(或 `dateAndTime`);`dateAndTime`(`wall-clock.ts:71-79`)的 `Intl` 字段补 `year` | ③-4 |
| D3-5 | **声明 `target/*/vendor/` 与 `tauri/vendor/` 的权威关系**,并让 gitignore 语义与之一致 | ③-5 |
| D3-6 | **`sync_resources.js` 对 repo `skills/` 的依赖显式化**(打包链→内容域的唯一越界) | ⑥ |
| D3-7 | 立 Level-3 `shipping-vendor` 模块,**集中四条既有不变量 + 补第五条「vendor/backend 与源码内容一致」**,补义务 (a)(d)(e) | ⑦ |

---

# 跨域收口

**三域共用一条裁决**(建议合并为一张单执行):**两条 501 脚手架(`copilot/dispatch`、`runs/{id}/audit`)按 no-backward-compat 删**。证据齐备:均已挂载(`main.py:192,196`)、均零前端消费者(grep 确认)、`git log -S` 均无主动下线裁决、`copilot/dispatch` 的续接条件(T2.6 SDK events)已由 WebSocket 路另行满足。附带清 `golden.py:33,58,100` 三处过时 501 声明(那是文档撒谎,非脚手架)。

**MoirAI 单一 owner 归新仓的执行风险(必须先解决,否则迁移即回归)**:漂移已达 100%,不是"取新覆盖旧"能收的。**KB 编号槽位撞名不同义**是最硬的障碍 —— KB-11/12/13 在两个 owner 里指三对不同文档(`workspace-runtime`/`llm-roles`/`studio-gates-tools` vs `runtime-config`/`agent-execution`/`runtime-tools`),而 `KB-00-hub.md` **按编号路由**且两份 hub 本身也全异(44 vs 24 行)。主仓那三份 KB 承载的是 **Studio 特有事实**(workspace 运行时、LLM 角色、Studio 闸门与工具),engine 仓不可能有 —— 所以"归新仓"必须先回答:**这三份 Studio 事实迁到哪个编号、由谁 own**。另需注意 `agent_assets.assets_fingerprint()`(`agent_assets.py:169`)只指纹主仓那一份,迁移期间它会持续给出**错误的安心感**。

**风险排序(按"失守后波及面")**:
1. **D3-2 vendor 分叉** —— 唯一会让**其他所有域的证据同时失效**的问题。三起发货事故同源,且 `PROBLEM_LEDGER` E6 已记录一次真机点验推翻先前 ✅ 的实例。**最高优先级**。
2. **D1-5 探测/聊天不等价** —— 让用户对安全边界产生错误信念(绿勾 ≠ 护栏可用)。
3. **D2-1 run-from-release 未接线** —— 北极星④ 只兑现一半,发布物"不可用"。
4. **D3-1 单平台发货** —— 应然全灭,但代码已就位,是 CI 缺口而非设计缺口,修复成本最低。
