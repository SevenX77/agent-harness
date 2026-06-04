# Deferred Items（延期 / 移交事项追踪）

> 本文件追踪"当前可做但被推迟、或从某 spec 移出尚未指派 owner"的事项。
> 来源规范见 `.claude/rules/autonomous-workflow.md` 的 Deferred Items Tracking 铁律。
> 完成一个任务后,检查 Active Items 中是否有前置条件已满足者,并提醒用户。

## Active Items

> **DEF-001 / DEF-002 已拉回 `studio-feature-trace-inspector` scope**(2026-06-01),不再是 deferred 项 —— 二者本就是该 spec 自己的 feature,不属跨 spec/孤儿,见下方 Promoted 区与 `requirement.md` REQ-3 / REQ-7。

### DEF-003 — 画布亮暗模式联动(Responsive Canvas Theme)— owner 待指派
- **日期**: 2026-06-01
- **事项**: React Flow 画布的网格、背景、自定义边 SVG(`stroke`/`strokeDasharray`)、节点辉光在 light/dark 切换时自动重绘(对应 trace-inspector level-3 `mvp0-alignment.md` target 2)。
- **延期原因**: 与 trace 流无关,被从 `studio-feature-trace-inspector` 收窄移出;原 level-3 文档列了 3 个 target,spec 只保留 target 1。
- **前置条件**: 指派 owner(候选:`studio-feature-canvas-topology` / `canvas-micro-topology-v1`)。`themeStore.ts` 已存在,缺的是画布订阅 `useThemeValue()` 重绘。
- **来源**: 同上评审。

### DEF-004 — 输出路径 / Artifacts 导出配置(Output Artifacts Path)— owner 待指派
- **日期**: 2026-06-01
- **事项**: Settings 中新增"Outputs & Artifacts Manager",可配置自定义导出目录;run 成功后 `run_manager.py` 原子写出 `.workspace/runs` 的产物到目标目录(对应 trace-inspector level-3 `mvp0-alignment.md` target 3)。
- **延期原因**: 属 project lifecycle / workspace 配置域,被 `studio-feature-trace-inspector` 显式排除以免污染 trace 流;但未指派接管 owner。
- **前置条件**: 指派 owner(候选:`workspace-fs` 平台域 / `studio-feature-asset-explorer`)。
- **来源**: 同上评审。

### DEF-005 — 节点级「编辑-续跑」干预(Intervene-mode)— 后端阻塞
- **日期**: 2026-06-01
- **事项**: `05_debugging.md` 场景C:点边原点 → 可编辑 Monaco 篡改 inter-node state → 点下游节点 `[Resume]` 用伪造数据续跑。
- **延期原因**: 后端 resume 端点 `POST /api/skills/{skill_id}/runs/{run_id}/resume` 当前 `501 Not Implemented`(`apps/studio/backend/app/routers/runs.py:64-70`);`ResumeReq.context_overrides` 字段已定义但全代码零引用;无节点级 resume 粒度(仅 thread/run 级 checkpoint)。
- **前置条件**: 后端实现 resume 端点 + 消费 `context_overrides` + 节点级 checkpoint 恢复粒度。
- **来源**: 同上评审;能力散见于 `05_debugging.md` 场景C 与 `trace-and-predict-visibility` 验收末行。

### DEF-006 — （已撤回）侧边栏去过滤 `needs_setup` —— 经核实为误诊
- **日期**: 2026-06-01（同日核实撤回）
- **结论**: 原描述本于 Gemini 痛点 5（"untested 被侧边栏过滤"）。代码核实**不成立**：
  `AvailableModelsSidebar.tsx:385` 已显示 `untested`；`needs_setup` 实为缺密钥/已失败
  （`llm_state_projection.py:49`），隐藏属合理设计（无密钥/失败路由拖进 chain 也测不通，运行期由 Req 2 跳过）。
- **状态**: **撤回，无待办**。如将来需"重测 failed 路由"，另立精确 scope，不整体放开 `needs_setup`。
- **来源**: 2026-06-01 PLAN REVIEW P2 反馈 + 代码核实。

### DEF-007 — WaveSpeed 协议边界诚实失败提示（gateway-redesign Req 6，支持项）
- **日期**: 2026-06-01
- **事项**: `_probe_copilot_sdk_tool_call` 在 WaveSpeed（OpenAI 兼容）被以 Anthropic 协议接入失败时返回清晰降级提示；**不做**协议翻译。
- **延期原因**: 同上，近期范围外。已推翻 Gemini 草案 REQ-6 "100% 格式对齐"表述。
- **前置条件**: 无。
- **来源**: `.kiro/specs/studio-llm-gateway-redesign/requirements.md` Req 6；research.md §2。

### DEF-008 — 第三方模型分类归一（Gemini 痛点 4）
- **日期**: 2026-06-01
- **事项**: `ProviderCard` 让第三方 provider 复用 `groupOfficialRouteInfos` 分类展示（后端 `_third_party_route_capability_values` 已写入 `model_type`/`model_type_label`）。
- **延期原因**: 纯前端展示优化，不在 ①②③ 近期范围。
- **前置条件**: 无。
- **来源**: Gemini implementation_plan.md 痛点 4。

### DEF-009 — LLM 配置/gateway 远端服务化（远期独立 spec）+ 偿还反远端债
- **日期**: 2026-06-01
- **事项**: 按 `architecture-direction.md`，将 gateway/LLM 调用相关（含 roles/credentials/test）真正远端服务化：多用户 + DB 存储 + 密钥 KMS/加密 + 真实认证。同时偿还三项反远端债：credentials 明文（仅 `chmod 0600`）、LLM 模块无 `user_id`/全局单文件、测试状态 SSOT 本地单文件。
- **延期原因**: 本次只做"形状对齐远端、实现先本地"（gateway-redesign Req 4）；真正远端化是大决策，需独立 spec。
- **前置条件**: gateway-redesign Phase 1-3 落地（形状已对齐）；产品确认远端化排期。
- **来源**: `.kiro/specs/studio-llm-gateway-redesign/architecture-direction.md`；2026-06-01 用户战略确认「gateway 和 llm调用相关模块未来都要远端服务化」。

### DEF-010 — Compile 结构化报错(从 trace-inspector 拆出,候选 owner: canvas-authoring-v1)
- **日期**: 2026-06-01
- **事项**: 重做 Compile 报错的呈现。
- **用户原话(原文留底)**:
  > "现在的弹出 compile 报错的方式不好,因为 compile 报错通常应该是很长且很详细的,不是弹个消息告诉你个错误码。可以用 drawer 从底部弹出(不要全局弹,只覆盖画布,不影响边栏),有一键复制按钮,可以复制到 copilot。"
- **设计要点**:
  - **底部 drawer**,**只覆盖画布,不遮挡侧边栏**(非全局 modal / 非 toast);
  - 承载**长而详细**的结构化报错(字段 / 行号 / 多条),非单一错误码;
  - **一键复制 → Copilot**。
- **归属**: 属**编写期(authoring/compile)**,与运行追踪(trace-inspector)正交,已从 trace-inspector 拆出。**UX 协调注意**:trace 控制台也在底部区域,两个底部面板需协调布局,勿互相冲突。
- **前置条件**: 指派 owner(候选 `canvas-authoring-v1`);后端 compile API 返回结构化字段 + 行号(旧 spec US4 已要求,待核实现状)。
- **来源**: `trace-and-predict-visibility`(旧名)US4 + 用户 2026-06-01 意图澄清。

### DEF-011 — 覆盖白名单哈希 403 小修(从 skill-lifecycle 移出,owner 待定)
- **日期**: 2026-06-01
- **事项**: 修复"点 Allow Overwrite 保存撞 403 → 弹窗卡死无法恢复"。本地版最小修法:
  - "加入白名单"提供**后端 read-modify-write**(`addSequentialOverwriteField` 的服务端等价,在 `apps/studio/backend/app/services/skills.py`),该操作不再经客户端 hash → 不会 403;
  - 通用编辑器保存撞 403 时给一个**"重新加载"按钮**。
- **延期/移出原因**: 它本质是文件并发/版本问题,横跨所有文件写入,**不属于 skill-lifecycle 的「测试输入 + 批量运行」语义**;且本地单用户场景并发极罕见,无需平台级契约。曾被过度设计为"平台 file-versioning 契约 + 三方合并",已撤回。
- **前置条件**: 指派 owner(候选:独立小 bug-fix spec,或并入 canvas/authoring 相关 spec)。
- **来源**: `.kiro/specs/studio-feature-skill-lifecycle/`(`review-2026-06-01.md` 原 S1)+ 2026-06-01 用户「本地!!」前提澄清。

### DEF-012 — 常用文件标准化/格式转换工具(移交引擎内置 tools)
- **日期**: 2026-06-01
- **事项**: 把常用的"文件标准化 / 格式转换"做成引擎内置 tools/actions,供技能图直接调用(配合"假定导入物料干净":脏数据先用这些工具规整)。
- **归属**: `packages/graph-agent/src/graph_agent/tools/builtin/`(已有 `md_to_json` 可作范式),**不属于 skill-lifecycle**。
- **前置条件**: 引擎侧排期;明确要内置哪些转换(待用户列清单)。
- **来源**: 2026-06-01 用户提议「可以写一些常用 tools/actions 放进内置 tools,各种文件标准化格式转换」。

### DEF-013 — 节点 Properties 面板:role 快捷 Test + 状态投影(跨 region,owner 待指派)
- **日期**: 2026-06-03
- **事项**: 在**节点 Properties 面板**(作者/运行期给节点指定 `llm_role` 的地方)每个 role 旁加 **Test 键** + **展示 role 状态**,让用户在用 role 的地方就能验"能不能用",不必切到 Settings → LLM Roles 再测。复用 settings 已有的 role 测试(`POST /api/llm/roles/{name}/test`)+ role-fit 状态投影。
- **归属**: 跨 region —— 能力属 `studio-settings`(role 测试/状态投影)但 UI 落点在 **`phase-editing` / properties region**(节点配置)。非 settings 页本身。
- **延期/移出原因**: 这轮 00_settings §2 Roles 走查浮出(PM 2026-06-03 #11),但 UI 落点不在 settings 页,属节点 Properties 面板。settings 侧已在 [`00_settings-ux-spec.md` §2.7](studio/mvp1/01_workflows/00_settings-ux-spec.md) 登记交叉引用;待 phase-editing/properties region 设计时接入。
- **前置条件**: phase-editing/properties region 细化排期;role 测试/状态投影端点就绪(settings §2.5 接线)。
- **来源**: 2026-06-03 §2 Roles 走查 PM #11。

### DEF-014 — 多模态生成式模型测试(大需求,独立设计 pass,owner 待指派)
- **日期**: 2026-06-03
- **事项**: 为**生成式多模态模型**(文生图、视频生成、TTS、音乐生成)设计配置 + 测试机制,大量借鉴已定稿的 LLM Roles(§2)/ Copilot(§3)。
- **分类裁定(Claude 答 PM,按输出模态分轴)**:
  - **输出文字/推理的模型 → 归 LLM 范围**(即便多模态**输入**:视频分析、图片识别这类 image/video→text)。理由:走同一 chat-completion 调用范式(多模态内容块进 prompt)、输出文本、契合 role→route→ChatX 兜底机制;"多模态输入"只是一个 capability flag,不另起体系。
  - **输出生成资产的模型 → 归多模态生成范围**(text/image→image/video/audio/music)。理由:API 形态非 chat-completion、输出是二进制资产、测试方法学根本不同 → 需独立机制。
- **可借鉴(复用 LLM/copilot 已有)**: provider/endpoint/credential/route 层;6 态 + draft/证据(缓存哪些能用);"测试=真实调用"(role test 范式);model group(同模型跨 provider)/ 类 role 的"生成角色"+ 兜底。
- **新的难点(本 pass 要设计)**: ① 验证标准——文本可读,资产怎么判"能用"(只验"产出合法资产/格式正确",质量靠人看预览,不自动判质);② 异步 job(视频/音乐生成多是 submit→poll→取结果,比 chat 长);③ 资产落点 + 成本(生成贵,测试要省;预览缩略图? 落 `.workspace/artifacts`?);④ 能力维度更丰富(图:分辨率/比例/n;视频:时长/fps;TTS:音色/语言/语速/格式;音乐:时长/风格)→ 扩展 runtime descriptor;⑤ 协议爆炸(各家生成 API 形态各异,非 chat-completion)→ gateway 库的 ChatX 调用范式不适用,**关键架构问题**:生成式调用是 3b gateway 库职责(领域无关"模型调用")还是另起 Studio 多模态调用层?
- **前置条件**: 设置页 §2/§3 定稿(✅ 已完成,提供借鉴基线);独立设计 pass 排期 + PM 探明意图(先做哪类生成模型、测试要不要人评预览闭环)。
- **来源**: 2026-06-03 PM 第三轮"多模态生成式模型测试该怎么做"大需求。

### DEF-015 — i18n 实现落地(设计已定稿,P1 待排期)
- **日期**: 2026-06-03
- **事项**: 按 [i18n 设计](studio/mvp1/04_platform/i18n.md) 落地多语言。**P1**:前端三件套(`i18next` + `react-i18next` + `i18next-browser-languagedetector`)+ `i18n.ts` 初始化 + `react-i18next.d.ts` 类型声明 + `en`/`zh-CN` 词条骨架(按 namespace 分);收编现有 `llm-error-messages.ts`(42 条错误码→英文映射)进 i18n;Settings/LLM workflow 全量词条;清理 6 处残留中文 message(`skills.py:178/187/261/270/279`、`copilot.py:496`)。**P2+**:按 workflow 逐个铺词条(canvas → copilot → trace → …)。
- **归属**: 横切 `04_platform/i18n`(前端主导,Strategy C 前端单权威;引擎/网关语言无关零改动);代码走独立 `.kiro` spec(设计文档只定架构)。
- **延期原因**: PM 2026-06-03 设计定稿后明确「先不用落地」,设计先锁。
- **前置条件**: PM 给落地排期;落地前实现计划须先过 Codex `[PLAN REVIEW REQUEST]`(CCB 规矩),通过后由 Codex 写代码(Claude 不亲自写)。
- **来源**: 2026-06-03 PM「我们现在要设计 studio 的 i18n 功能…目前我只需要简体中文,其他语言顺便」;设计完成后「先不用落地」。

### DEF-016 — glib 0.18.5 unsoundness 升级（受 tauri/GTK 栈约束阻塞）
- **日期**: 2026-06-04
- **事项**: 修 `apps/studio/tauri/Cargo.lock` 里 `glib 0.18.5` 的 `VariantStrIter` 的 `Iterator`/`DoubleEndedIterator` impl unsoundness（dependabot GHSA-wrw7-89jp-8q8g，medium）。修复版 = **glib 0.20.0**。
- **延期原因**: `cargo update -p glib` 锁在 0.18.5 没动 —— 上层 tauri 2.x / GTK 栈把 glib 约束在 0.18.x，升到 0.20 要连带 bump 整个 GTK/tauri Rust 依赖栈，是破坏性大改、需单独回归测桌面外壳，不在本轮「快速安全修」范围。
- **前置条件**: tauri/wry/GTK 栈整体升级排期（确认 0.20 兼容性 + 桌面端回归测试）。
- **来源**: 2026-06-04 dependabot 27 条漏洞修复批；其余 26 条已修，仅此 1 条受栈约束阻塞。

## Completed / Promoted

- **DEF-002 → Promoted (2026-06-01)**: 连线 Context 真实数据接线。已并入 `studio-feature-trace-inspector` **REQ-3(P1 核心,现在可做)** —— 本就是该 spec 自己的 scope,从 deferred 注册表拉回。
- **DEF-001 → Promoted (2026-06-01)**: 结构化前后态 DIFF。已并入 `studio-feature-trace-inspector` **REQ-7(P2,本 spec 拥有,依赖引擎 emit reducer 级 diff)** —— 不再以 deferred 形式悬挂,作为本 spec 的 P2 路线项追踪。快照机制澄清(每 phase 边界全量快照,非 keyframe+delta;diff 是展示层)随 REQ-7 留存。
