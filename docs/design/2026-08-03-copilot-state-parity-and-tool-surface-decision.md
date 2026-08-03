# 决议：copilot 工具面的能力对等与状态对等（2026-08-03）

状态：已批准（用户 2026-08-03 口头批准原则与工作项，本文件为落盘正本）。
适用范围：Studio 后端 MCP 工具面、Studio 前端闸门状态、engine 编译期声明校验、
CLI 会话启动上下文、agent 知识资产（`.ah/knowledge`）。
不适用：LLM 角色/端点/路由配置（工具面已完备）、golden 基准（工具面已完备）、
skill 发布与派生（工具面已完备）。

## 1. 结论

Studio 的 MCP 工具面按两条原则补齐：

- **能力对等**：Studio 产品界面上存在入口、且能改变 skill 或改变运行结果的操作，
  MCP 工具面必须存在对应工具。
- **状态对等**：同一个操作，无论由人点击界面发起还是由 copilot 调用 MCP 工具发起，
  Studio 前端的最终状态与副作用必须完全一致。

两条原则各自独立可验证：能力对等的判据是"该操作有无对应工具"，状态对等的判据是
"两条发起路径的前端状态迁移序列是否逐条相同"。

## 2. 事实基础

本决议的每一条都来自 2026-08-03 exp-b-round3 北极星轮次的实测，不来自推测。
该轮次的形态是：真人坐在 Studio 前，通过内嵌 CLI 会话（Claude Code，manual 审批模式，
Studio MCP 25 工具已连通）用自然语言把一个 skill 跑通。轮次证据存于
`D:/coding/skills/_copilot-lab/rounds/exp-b-round3/`（会话 transcript、trace、run 产物）。

### 2.1 工具面缺一整类：skill 与 workspace 的数据面

现有 25 个工具的职责分布：LLM 配置 11 个、三关（compile/predict/run/get_run_detail）
4 个、golden 4 个、生命周期（create/publish/fork/resume/get_resume_validity）5 个、
角色连通性测试 1 个。

**没有任何工具回答"这个 skill 长什么样""输入怎么绑定""产物怎么声明"
"这次 run 的每个 phase 发生了什么"。** 会话因此改用 `Bash` 与 `Read` 直接读文件：
本轮它用 `python3` 逐行解析 `trace.jsonl`、用 `strings` 扫 `checkpoints.db-wal`
来推断 phase 内部发生了什么。它靠这条自制路径定位到了一个真实设计缺陷
（`io.outputs.required` 把 validator 派生字段声明成 agent 必交字段，导致 segment
前 8 次提交、review 前 7 次提交被 schema 门驳回，20 轮迭代上限用掉 13 轮）。
诊断结论正确，但取证手段完全绕开了产品的可观测面。

### 2.2 产物声明：既无工具，亦无知识，编译器还不报错

会话被要求让真实 run 把分段结果单独落成一个文件。它依次遭遇三重不可达：

1. **知识库无覆盖**：`.ah/knowledge/` 14 个 KB 中，"artifact" 仅出现一次且指
   Studio publish；"target" 的全部出现都是 `target_skill`（子图指针）与
   `target validity`。产物声明这一能力在 agent 的知识资产里不存在。
2. **编译器不校验**：会话以 `target: __probe_invalid__` 作探针写入 GRAPH.md 根输出，
   `compile_skill` 返回 `status: ok`、0 缺陷，非法值原样透传进 manifest 与 io_schema。
   而 engine 运行期只接受 `target ∈ {file, artifact}`
   （`packages/graph-agent/src/graph_agent/core/runner.py:1952`
   `schema.get("target") in {"file", "artifact"}`），取值不匹配即整段跳过、静默不产出。
   编译器因此不能充当契约 oracle。
3. **predict 不产出产物**：产物写入只挂在真实 run 路径上，predict 目录从不生成
   `artifacts/`，故 predict 也不能充当验证手段。

三个可自助验证的出口全部哑火后，会话拒绝以真实 run 盲猜（其原话：手工往
`artifacts` 数组填 JSON "就是在伪造 Studio 私有 schema——填错静默失效，填对也只是碰运气"），
把工作区逐字节还原后请求人类介入。人类在 I/O 面板点击一次
"Configure output artifacts"，产品写入
`{"stem": "segmentation_result", "fields": ["segmentation_result"], "mode": "single", "format": "json"}`，
会话据此 diff 出 schema 并重跑，`artifacts/segmentation_result_latest_20260803_081824.json`
才落盘（run `2026-08-03T08-13-12_b53154de`，产品面 `status: success`）。

**判定**：这一环上"用户只通过对话把 skill 改对"不成立——不是模型能力不足，
而是产品没有给出可达路径。

### 2.3 会话不知道自己的 skill_id

会话启动时不被告知自身绑定的 skill_id 与 workspace 路径，只能从 manifest 名推断。
该缺陷已两次独立复现（exp-B R0 因此对受保护原件执行了修复操作；exp-A round2
因未登记而调用扑空并试图全盘 grep 找 id）。

### 2.4 前端不知道 copilot 做了什么

前端的闸门状态机与其全部副作用内联在点击处理器中。以 compile 为例，
`apps/studio/frontend/src/components/studio/Workspace.tsx:1174-1200` 的
`handleCompile` 在一个函数里完成五件事：推进 stage、写错误列表、开关 Compile 抽屉、
弹 toast、刷新 SWR 缓存。`deriveBuildStage` 只读本地 `compileStages` 状态与
sessionStorage 中的 lint 状态。run 同理：`runId` 仅由前端自身发起的
run/predict/compare 写入（同文件 2240 / 2388 / 2409 / 2426 行），
`useRunStream(runId)` 因此只订阅前端自己发起的 run。

后端侧没有任何 run 领域事件：`run_manager.py` 全文不引用 `STUDIO_EVENTS_TOPIC`
或 `event_bus`。故前端即使想监听"有新 run 开始了"也无信号可听。

**关键澄清（回答"MCP 为什么不能跑一样的代码"）**：MCP 跑的就是同一段后端代码。
HTTP 路由 `apps/studio/backend/app/routers/skills.py:360` 与 MCP 工具
`apps/studio/backend/app/services/copilot_tools.py:79` 调用的是同一个函数
`compile_skill_for_studio(user_id, skill_id, storage, metadata)`。
差异不在"代码是否相同"，而在**点击一次 Compile 实际跑的是分居两个进程的两段代码**：
webview 进程内的 `handleCompile`（React 状态与界面副作用）与 Python sidecar 进程内的
`compile_skill_for_studio`（编译本身）。MCP 完整执行了后者，够不到前者——
因为前者活在另一个进程的内存里。任何后端调用方（HTTP 客户端、CLI 会话、MCP）
都同样够不到。这不是 MCP 的缺陷，是"前端仅在自身发起时才更新状态"这一既有缺陷，
copilot 只是第一次把它暴露出来。

## 3. 关键设计决定

### D1 动作留在后端，前端订阅结果

闸门动作（compile / predict / run）的唯一出口保持在 Studio 后端 service 层。
前端从"自身发起才知道结果"改为"订阅后端领域事件"。

**否决的替代方案**：把动作做成 webview 内的前端工具（copilot 面板直接调用
`handleCompile()`）。否决依据有二：其一，CLI 会话运行在 WSL 的独立进程中，
只能经 HTTP/MCP 到达后端，该方案对 CLI 面完全不可用，而北极星要求 SDK 面板与 CLI
两个面用同一套任务词都能跑通；其二，该方案把"编译是否通过"的真相移到前端，
与"服务端权威 + 底座一"冲突。

### D2 领域事件在 service 层发出，不在 router 层

事件发出点必须位于 HTTP 路由与 MCP 工具的公共下游（service 层），
使两条发起路径天然发出同一条事件。若在 router 层发出，则 MCP 路径不会发出事件，
状态对等在实现层即被破坏。

### D3 事件载荷必须钉住数据集

载荷形状：

```
{ "type": "skill_gate",
  "skill_id": <str>,
  "gate": "compile" | "predict" | "run",
  "outcome": "started" | "pass" | "fail",
  "content_hash": <str>,
  "run_id": <str | null>,
  "defect_count": <int> }
```

依据 AGENTS.md「Server-authoritative state + event-driven revalidation」：
允许触发重新读取的事件必须精确标识变化的数据集；无法标识精确数据集的事件
应当修正事件契约，而不是让前端做宽泛刷新。

通道复用既有的 `/ws/events`（`STUDIO_EVENTS_TOPIC`），
`roles_changed` 与 `llm_probe_active` 已是该范式
（`apps/studio/backend/app/routers/llm.py:5928`）。

### D4 前端"闸门结果 → UI 状态"只保留一份归约器

从点击处理器中抽出纯函数 `applyGateOutcome(state, event) -> state`，
以及一张"状态迁移 → 副作用"表（fail 开抽屉、pass 关抽屉并提示、run started 切 Trace 面板）。
点击处理器此后只承担两件事：乐观置 `compiling` / `predicting` / `running`，发起请求；
**终态一律由领域事件驱动**。copilot 触发的事件走完全相同的路径。

三条实现约束：

- **幂等**：事件按 `(skill_id, gate, content_hash | run_id)` 去重，
  重复到达不产生第二次副作用。
- **副作用挂在迁移上**：抽屉弹出等副作用只在状态真正发生迁移时触发，重放时不触发。
- **作用域**：事件携带 skill_id，只作用于匹配的 skill；用户正在查看其他 skill 时
  不发生视图跳转。

### D5 未知声明必须在编译期成为缺陷

`io.outputs.*.target` 出现枚举外取值，以及 `runtime_config.artifacts` 条目的
`stem` / `fields` 不合法（`fields` 引用黑板中不存在的字段），均须由
`compile_skill(...)` 单出口报为缺陷（新 `[F-v3-*]` 码），进入同一份聚合诊断。

依据两条既有规则：「让非法状态不可表示」——能在校验期挡住的错误不留给运行期；
「compile/lint 单出口 + 全量聚合」——诊断只有一个权威来源。
此决定同时恢复编译器作为契约 oracle 的能力，使 agent 可以自助探路而不必盲跑真实 run。

### D6 只读工具一律有界，写工具一律走后端 service

只读工具返回有界投影而非全量转储；范式已由 PR #499 确立
（`get_llm_registry` 全量转储 → `search_llm_registry` 有界搜索）。
trace 单次 run 可达 25 万字节，必须按 phase / 事件类型 / 序号切片，并附每 phase 聚合。

写工具调用与 HTTP 路由相同的后端 service，agent 不得手写结构化配置文件
（与 KB-13「结构化配置写入 never by hand-editing config files」一致）。

## 4. 工作项与 PR 拆分

按「一个任务一个 PR」拆分；同一优先级内的 PR 可并行开发，跨优先级按依赖顺序。

### P0（本轮实测直接撞到的墙）

| PR | 内容 | 依赖 |
|---|---|---|
| PR-A | 后端三关领域事件（D2/D3）：compile / predict / run 在 service 层发 `skill_gate` 事件；契约测试覆盖"HTTP 路径与 MCP 路径发出同一条事件" | — |
| PR-B | 前端闸门归约器重构（D4）：抽出 `applyGateOutcome` 与副作用表，订阅 `/ws/events`，幂等与作用域，双路径一致性回归测试 | PR-A 的事件契约 |
| PR-C | run 可观测性：`query_run_trace(skill_id, run_id, phase?, event_types?, since_seq?, limit?)` 返回有界切片 + 每 phase 聚合（迭代数 / llm_call 数 / tool_call 数 / 驳回次数与驳回原因 top-N）；`wait_for_run(run_id, timeout_s)` 挂在 `run_manager` 既有 `subscribers` 队列上，终止或超时才返回，消除轮询 | — |
| PR-D | `set_output_artifacts(skill_id, artifacts[])`：I/O 面板 "Configure output artifacts" 的后端等价工具，调用同一 service | — |
| PR-E | CLI 会话启动注入 `skill_id` 与 `workspace_root`（修 F3/F13） | — |
| PR-F | engine 编译期校验未知声明（D5），新增缺陷码与用例 | — |

### P1（数据面读工具与知识资产）

| PR | 内容 |
|---|---|
| PR-G | `get_skill_overview`：manifest 摘要 + phase 列表 + 每 phase 的 io 字段名与类型 + validator 有无 + llm_role（只给结构不给正文） |
| PR-H | `read_skill_file(skill_id, path, range?)`：经 skill 索引解析、限定 skill 目录内 |
| PR-I | `get_workspace_config(skill_id)`：runtime_config 的结构化投影（输入绑定 / test inputs / artifacts 声明 / llm 覆盖）；`list_run_artifacts` 与 `read_run_artifact` |
| PR-J | 知识资产：新增 KB「产物与落盘」（两条声明路径、`<stem>_latest_<ts>.json` 命名、参与 execution_fingerprint、如何验证）；KB-09 补 `query_run_trace` 诊断套路；KB-13 随工具面更新；修复 KB-08 已知矛盾（第 22 行 "users cannot override this behavior manually" 与第 27 行 P1 档 "manual mock overrides are supplied ... in the test panel or copilot callbacks" 互斥） |

### P2（写工具收口）

| PR | 内容 |
|---|---|
| PR-K | `write_skill_file` 与 `bind_test_input`：经 Studio 校验后写盘。现状是 CLI 会话直接 Write 到磁盘，绕过了「Rust native-fs 层是 skill 文件唯一写者」的约定 |

## 5. 验收判据

全部满足才算本决议交付完成。

1. **双路径一致性**：同一操作分别由人点击与由 copilot 调用 MCP 发起，
   录制前端状态迁移序列并逐条比对，结果相同。此项为自动化回归测试，不以肉眼观察为准。
2. copilot 执行 compile 失败后，Compile 错误抽屉自动弹出，且其列表与
   canvas 节点徽章、字段 tooltip、编辑器 marker 投影同一份完整诊断。
3. copilot 执行 compile 通过后，工具栏推进到 Predict 可用态；predict 通过后 Run 可用。
4. copilot 发起 run 后，面板切换到 Trace 并开始流式呈现；run 结束后进入历史记录。
5. 会话能仅通过 MCP 工具完成 run 诊断，不需要以 `python3` 解析 `trace.jsonl`
   或以 `strings` 扫 checkpoint WAL。回放判据：用 exp-b-round3 的
   `io.outputs.required` 缺陷作为回放样例，会话应能仅凭 `query_run_trace`
   的聚合输出复现该诊断。
6. `target` 取枚举外值时，`compile_skill` 报缺陷（现状为 0 缺陷静默通过）。
7. 会话能不请求人类介入即完成产物声明并验证落盘。
8. **北极星复跑**：同一母本、同一固定任务词重跑 exp-B 轮次，全程不需要人类代为点击
   Studio 界面；人类只做审批应答。

## 6. 边界（本决议不做什么）

- 不改变闸门动作的权威位置：动作出口仍在后端 service 层，前端不持有闸门真相。
- 不引入 MCP resources 或 prompts capability。服务端当前只声明 tools capability
  （实测 `initialize` 返回 `capabilities: {"experimental":{}, "tools":{"listChanged":false}}`），
  工具形态在客户端支持上更一致；如将来确有分页资源需求，另行决议。
- 不为 copilot 新增独立的数据通道。工具面与 HTTP API 同进程，
  MCP 工具直接调用同一批 service（`run_skill` 调 `run_manager.start_run` 即为范式），
  本决议新增的只是投影层，不是数据通道。
- 不调整 LLM 角色 / 端点 / 路由、golden、发布与派生这三类已完备的工具族。

## 7. 术语

- **能力对等**：产品界面上存在入口且能改变 skill 或运行结果的操作，
  MCP 工具面必须存在对应工具。
- **状态对等**：同一操作由人点击发起与由 copilot 调用工具发起，
  前端最终状态与副作用完全一致。
- **领域事件**：后端在事实已落定之后广播的一条"某个明确数据集发生了变化"的通知。
- **归约器**：一个纯函数，接收当前状态与一条事件，返回新状态，自身不产生副作用。
- **有界投影**：对大对象按条件切片并附聚合摘要的只读返回形态，与全量转储相对。
