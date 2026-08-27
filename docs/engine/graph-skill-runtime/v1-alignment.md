---
module: graph-skill-runtime
doc: v1-alignment
role: alignment
status: drafted
binds_baseline: ./baseline.md
aligns_with: ../mvp1/INDEX.md
updated: 2026-08-27
---

# Graph Skill Runtime v1 目标设计

本文定义把当前 engine 提炼为独立 Python runtime、SDK 与 CLI 的 v1 目标。它与 [`baseline.md`](./baseline.md) 双向绑定。本文状态为 `drafted`：文中的“目标决定”约束未来实现，但不表示当前 `graph-agent`、Studio 或任何宿主已经支持这些接口。

## 1. 目标、术语与不可变约束

**Graph Skill Runtime** 是读取、编译并执行 graph skill 的 Python runtime。这里的 **graph skill**（下文简称 gSkill）是用户拥有的一组业务指令、机器图定义和 phase 文件；runtime 是解释并执行这些文件的通用软件。

目标产品同时提供三种接口形态：

- **SDK**：Python 调用者使用的强类型接口；
- **CLI**：人在终端或通用自动化中调用的命令行接口；
- **MCP server**：通过 Model Context Protocol（模型上下文协议，一种让 agent 结构化调用工具的协议）提供的工具接口。

PyPI、`pip` 和 `uv` 是 Python 软件的分发与安装方式；SDK 是调用接口形态。二者不是相互竞争的产品类型。v1 首发渠道是 PyPI，不是 npm。

目标由以下不可变约束导出：

1. 用户业务 gSkill 永远由用户拥有。runtime wheel 不捆绑、不注册、不复制业务 gSkill，只发现并读取调用者给出的路径。
2. 业务声明、单次运行输入、机器配置、宿主 UI 状态和秘密具有不同生命周期，必须分别拥有唯一事实源。
3. 编译、预测、执行、恢复、CLI 与 MCP 必须调用同一 application service。application service 是组织用例的应用层入口；适配器只能转换输入输出，不能复制业务规则。
4. 业务图 checkpoint 与 agent 进程/session 是两个正交状态域。更换 agent supervisor 不能替代图状态的 durable resume。
5. Agent Skills 的说明入口与机器拓扑各有一个职责。一个 `SKILL.md` 不能同时成为人类/agent 指令和机器图 manifest 的双重真相源。
6. v1 每种语义只支持一个当前格式。迁移通过显式转换完成，不在 runtime 核心保留 dual reader、legacy alias 或版本猜测。

## 2. 产品命名与发布身份

### 2.1 目标决定

| 对象 | v1 工作名 |
| --- | --- |
| GitHub repository | `graph-skill-runtime` |
| PyPI distribution | `graph-skill-runtime` |
| Display name | Graph Skill Runtime |
| Python import | `graph_skill_runtime` |
| Console command | `gskill` |
| MCP server/tool namespace | `gskill` |

这些名字是 drafted working decision，不是已经占用的商标、仓库或 registry 名称。

选择完整的 `graph-skill-runtime`，而不是 `g-skill-runtime`，理由是 **Graph Skill** 是清楚的开放复合短语，读者不需要先解码缩写；`GSkill` 则是人为缩合，不是自然英文复合词。完整名字也直接说明包的职责是 graph skill 的 runtime，而不是一个泛化的 “G” 工具。

### 2.2 已核验的命名风险

截至 2026-08-27，精确的 `graph-skill-runtime`、`g-skill-runtime`、`graphskill-runtime` 在 npm 与 PyPI 均返回 404，GitHub exact repository search 未见精确命中。这只是时间点观察，不构成占名或商标许可。

相邻名称已经拥挤：npm 有直接竞品 [gwaghmar/graph 的 `graph-skill`](https://github.com/gwaghmar/graph)，GitHub 另有 [`ouyangyipeng/Graph-Skill`](https://github.com/ouyangyipeng/Graph-Skill)；`gskill` 还会让人联想到 G.SKILL 硬件品牌、GEPA 的 `gskill` 和 Go 生态同名工具。因此，发布前必须完成 PyPI/GitHub 占名、包名混淆检查、域名与商标复核。任何一项失败都应在发布前重新裁决名称，而不是为兼容 drafted 名称留下别名。

## 3. 目标架构与公共契约

### 3.1 模块边界

| 层 | 单一职责 | 允许依赖 |
| --- | --- | --- |
| domain | 编译规则、typed dataflow、checkpoint 语义、预测与 golden 判据 | Python 标准库与明确的领域依赖；不依赖 Studio、Gateway 或某个宿主 |
| application | `compile`、`predict`、`run`、`resume`、`submit_agent_result`、`inspect`、`evaluate_golden` 用例 | domain Port 与强类型请求/结果 |
| ports | `AgentExecutor`、checkpoint store、artifact store、event sink、skill source 等稳定协议 | 只包含宿主无关类型 |
| adapters | 本地文件、host-native、vendor CLI、embedded、MCP、console、Python facade | 依赖 ports；可以依赖具体平台或厂商 |
| integrations | MoirAI、Gateway plugin、Studio plugin、宿主安装 renderer | 通过 SDK/CLI/MCP 契约调用 application，不进入 core |

核心包不提供 HTTP API，也不持有 Studio 文件扫描、Gateway credential truth 或某个宿主的全局配置。新仓可以包含多个 optional distribution extra，但每个 extra 都必须通过同一 Port 接入。

### 3.2 强类型 facade

目标顶层 `graph_skill_runtime` 至少公开以下版本化契约：

- `CompileRequest` / `CompileResult` 与完整 diagnostics；
- `PredictRequest` / `PredictResult`；
- `RunInvocation`、`RunRequest` / `RunResult`；`RunInvocation` 表达调用者本次给出的覆盖与可选 preset id，`RunRequest` 是配置合并后的 immutable 执行快照；
- `ResumeRequest`、`AgentTask`、`AgentResult`、`AgentRequired`；
- `RuntimeProfile`、`RunPreset` 与 resolved immutable profile snapshot；
- 完整 `CallbackEvent` 判别联合类型、error code catalog 和结构化 error payload；
- `AgentExecutor`、checkpoint store、artifact store、event sink 和 skill source Port。

所有会跨进程、落盘或进入 MCP 的对象必须带明确 `schema_version` 和判别字段。公共函数不得让调用者传入未约束的 `Any` 字典来表达 executor、runtime config、checkpointer 或 provider。内部实现可以使用 LangGraph，但公开请求、暂停结果与事件不能暴露 LangGraph `interrupt()` 对象或内部 runnable config。

### 3.3 单一用例出口

Python SDK、`gskill` CLI 与 `gskill` MCP server 均是薄 adapter：

1. 解析各自 transport 的输入；
2. 构造同一个强类型 `RunInvocation`；
3. 通过同一个配置 resolver 生成 `RuntimeProfile` snapshot 与 immutable `RunRequest`；
4. 调用同一个 application service；
5. 将同一个 result/event/error contract 投影为 Python、JSON 或终端输出。

因此，`gskill compile`、MCP `compile` 和 `graph_skill_runtime.compile(...)` 必须返回同源诊断；`run`、`resume` 与 `submit_agent_result` 也不得各自实现状态转换。

## 4. Portable gSkill 格式

### 4.1 目录布局

v1 的一个业务 gSkill 目录采用以下唯一布局：

```text
my-skill/
├── SKILL.md
├── graph.yaml
├── phases/
│   └── <phase_id>/
│       └── LOGIC.md | AGENT.md | SUBGRAPH.md
├── graphs/
│   └── <graph_id>/
│       ├── graph.yaml
│       └── phases/
│           └── <phase_id>/
│               └── LOGIC.md | AGENT.md | SUBGRAPH.md
├── references/
├── examples/
└── .gskill/
```

`.gskill/` 是默认的 skill-local runtime state 目录，必须加入 `.gitignore`；profile 或 `--state-dir` 可以覆盖它。runtime 在真正读写前把所有路径解析成绝对路径，并把解析结果写入本次运行的 immutable snapshot。

### 4.2 `SKILL.md` 是 Agent Skills 入口

Agent Skills 是一种让兼容宿主发现并按需加载技能说明的开放目录约定。其[规范](https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx)要求根目录有 `SKILL.md`，最小 frontmatter 使用 `name` 与 `description`，并允许可选 metadata 及 `references/`、`scripts/`、`assets/` 等辅助资源。

目标 `SKILL.md` 只承担两个职责：

1. 让 Claude、Codex、Copilot、Gemini、Cursor、OpenCode 等兼容宿主理解何时使用这个业务 skill；
2. 给当前宿主 agent 一段简洁、跨宿主安全的调用协议，例如优先调用 `gskill` MCP tools，MCP 不可用时调用稳定 `gskill` CLI。

它不保存 node、edge、I/O schema 或 subgraph registry。机器可读拓扑只在 `graph.yaml` 中定义。`SKILL.md` 也不应指令宿主调用 `python -m ...`：宿主当前解释器和虚拟环境不确定，模块命令不能形成稳定、可发现的用户协议。

MCP 是结构化首选，因为 request/result schema 可直接校验；CLI 是任何能启动进程的宿主都能采用的通用 fallback。v1 不是 MCP-only。

### 4.3 `graph.yaml` 与 phase 文件

根 `graph.yaml` 声明 root graph 的 `graph_id`、输入输出 schema、phase registry 和显式 edge。每个 phase 目录必须且只能有一个类型文件：

- `LOGIC.md`：确定性逻辑 phase；
- `AGENT.md`：需要 agent executor 的 phase；
- `SUBGRAPH.md`：调用另一个 graph 的 phase。

当前格式中的 agent phase `SKILL.md` 在目标格式中必须改名为 `AGENT.md`。Cursor 等宿主会递归发现 `SKILL.md`；把 phase 文件继续叫 `SKILL.md` 会使宿主把内部节点误认成可独立调用的 Agent Skill。

portable declaration 包括根 `SKILL.md`、所有 `graph.yaml` 与 phase 文件，可以提交版本控制。runtime state、credentials、宿主 session 和 UI 扫描投影不属于 portable declaration。

## 5. Subgraph registry 与调用图

### 5.1 目标决定

v1 使用 root `graphs/<graph_id>/` 单层 registry。`graph_id` 在一个业务 gSkill 内全局唯一；phase id 只需在所属 graph 内唯一。root `graph.yaml` 也声明一个不与 registry 冲突的 graph id。

`SUBGRAPH.md` 通过显式引用调用 registry 中的 graph：

```yaml
---
graph: fact-check
---
```

trace 和诊断使用稳定地址 `<graph_id>/<phase_id>`。编译器必须在执行前聚合并拒绝：

- 不存在的 graph 引用；
- 重复 graph id；
- 同一 graph 内重复 phase id；
- 调用环；
- registry 目录名、manifest id 与引用不一致。

`gskill inspect --call-graph` 从显式 call edge 生成面向人的调用拓扑。parent 和 callers 必须从 edge 派生，不能另存 `parent` 真相；同一 graph 可以被多个 caller 复用，单一 parent 字段无法表达这一事实。

目录只表达资产所有权，调用图才表达运行拓扑。v1 不按 caller 在 `subgraph/` 下递归嵌套，也不在具体 phase 目录里套娃。v1 不同时支持嵌套布局与 registry 布局；未来若需要真正 inline scope，应另立作用域、可见性和生命周期语义，而不是复活隐式物理嵌套。

### 5.2 成熟方案的取舍

- [LangGraph subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs)把 subgraph 作为可独立编译的 graph，再作为 node 使用。我们借用“独立单元 + 明确嵌入点”，不借其 Python graph object 作为公共文件契约。
- [Camunda call activity](https://docs.camunda.io/docs/components/modeler/bpmn/call-activities/)调用可被多个流程复用的外部 process；[embedded subprocess](https://docs.camunda.io/docs/components/modeler/bpmn/embedded-subprocesses/)则是同一 diagram 内的内嵌作用域。我们 v1 选择 reusable call 的语义，不把两类语义混在一个目录形状里。
- [GitHub Actions reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)将可复用 workflow 平铺在 `.github/workflows`，由显式 `uses` 引用。我们借用平铺 registry 与显式引用，不借其 YAML job/runtime 模型。

共同结论是：可复用单元应独立拥有，调用关系应显式表示。物理嵌套无法正确表达动态、多父或共享调用，所以不作为 v1 拓扑真相。

## 6. Agent phase 与 `AgentExecutor` Port

### 6.1 公共 dispatch/result 协议

核心不再拥有唯一的自制 ReAct agent。ReAct 是让模型在“思考—调用工具—观察结果”循环中完成任务的一种 agent 策略；它可以是一个 adapter 的实现，不能定义整个 runtime。

目标 `AgentExecutor` 是窄 Port。它消费版本化 `AgentTask`，产生 `AgentResult` 或 durable `AgentRequired`：

| 对象 | 必须表达的事实 |
| --- | --- |
| `AgentTask` | schema version、task/run id、`graph_id/phase_id`、已渲染指令、typed input、output schema、允许工具/路径/网络策略、deadline 与 capability requirements |
| `AgentRequired` | task reference、checkpoint reference、允许的提交入口、所需 executor capability；它表示任务已持久化等待宿主，不表示 agent 已启动 |
| `AgentResult` | schema version、task id、terminal status、typed output 或结构化 failure、executor identity 与可复核 provenance |
| lifecycle events | `agent_required`、`agent_dispatched`、`agent_started`、`agent_completed`、`agent_failed`、`agent_result_rejected`；每个事件只能在有相应可观察证据时发出 |

runtime 收到结果后先验证 task identity、状态转换和 output schema，再把结果写入 blackboard 并继续 graph。错误 task、重复提交、过期 checkpoint 或 schema 不匹配必须 fail fast。

### 6.2 Adapter 1：`host-native`，v1 默认

`host-native` 是协作式 adapter：它让当前交互宿主自己的 root agent 创建原生、干净上下文的 subagent，而不是让 runtime 外部进程假装进入当前 session。

一次 AGENT phase 的完整时序是：

1. runtime 在 phase 执行前持久化业务 checkpoint 与 `AgentTask`；
2. runtime 返回结构化 `agent_required`，同时提供 MCP `submit_agent_result` 和 CLI `gskill submit` / `gskill resume` 提交路径；
3. 当前宿主 root agent 按业务 `SKILL.md` 的协议，用宿主原生 tool 或 instruction 创建 clean-context subagent；
4. 宿主把 `AgentTask` 交给该 subagent，并把完成结果提交回 runtime；
5. runtime 校验 `AgentResult` output schema，提交 checkpoint transition，然后继续图。

持久化必须发生在 `agent_required` 对外可见之前，因此宿主崩溃或会话结束后仍能恢复。公开契约是 durable dispatch/result，不是 LangGraph interrupt object。

若当前宿主没有 native subagent 能力，`host-native` 必须在运行边界明确失败；只有 `RuntimeProfile` 显式允许 `cli` 或 `embedded` executor 时才能选择替代路径，不能静默降级。

### 6.3 Adapter 2：`cli`，第二阶段直接执行

`cli` adapter 从 runtime 启动厂商 headless CLI。每次启动是一个新的、vendor-native 顶层 session，虽然上下文干净，但不是当前交互会话里的 child thread。

实现期需要探测的候选命令形状如下。它们是调研示例，不是可硬编码的稳定契约：

| Vendor | 候选 headless 形状 | 官方能力证据 |
| --- | --- | --- |
| Claude | `claude -p --bare --agent <agent> ...` | [headless](https://code.claude.com/docs/en/headless)、[subagents](https://code.claude.com/docs/en/sub-agents) |
| Codex | `codex exec --ephemeral ...` | [non-interactive](https://developers.openai.com/codex/noninteractive)、[subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) |
| GitHub Copilot | `copilot -p ... --agent <agent>` | [CLI reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference)、[fleet](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/fleet) |
| Gemini | `gemini -p ... --output-format json` | [headless](https://geminicli.com/docs/cli/headless/)、[subagents](https://geminicli.com/docs/core/subagents/) |
| Cursor | `cursor-agent -p ... --output-format json` | [headless](https://prod.cursor.com/docs/cli/headless)、[subagents](https://prod.cursor.com/docs/subagents) |
| OpenCode | `opencode run --agent <agent> ...` | [CLI](https://opencode.ai/v2/docs/cli)、[agents](https://opencode.ai/v2/docs/agents) |

二进制名和参数会变化。例如 Cursor 当前文档示例使用 `agent -p`，OpenCode v2 文档使用 `opencode2 run`。所以 adapter 必须先做 executable/version/flag/output/capability probe，再声明可用；不能只凭进程退出码猜测协议兼容。

Claude、Codex、Copilot、Gemini、Cursor 与 OpenCode 都提供原生 subagent 或 clean headless 机制，但不存在一个跨厂商 shell 命令，能从外部进程统一地在已经运行的当前会话里创建 child。当前会话 child 必须由宿主自己的 tool 或 instruction 触发；headless CLI 只能创建新的顶层 session。Codex 交互 `/agent` 用于查看或切换线程，不是可供外部 runtime 调用的 spawn 命令。

### 6.4 Adapter 3：`embedded`，可选 fallback

现有 LangChain `create_agent` 路径可以迁入独立 optional extra，例如 `graph-skill-runtime[embedded]`，并实现同一个 `AgentExecutor` Port。它不再是默认 executor。

保留它有四个实际价值：

- server 与 CI 即使没有任何厂商 CLI，也可以执行 agent phase；
- runtime 可以完整控制工具、schema、middleware、checkpoint 与 trace；
- predict 与 eval 可以注入确定性模型或 fake；
- 对 executor parity 和错误契约提供可重复的离线基准。

它的保留条件是依赖隔离和 Port parity。host-native/CLI 达到同等 contract coverage 后，再根据真实 server 使用证据决定继续保留或删除；在此之前不让 embedded 的模型、middleware 或 LangGraph 类型泄漏进 core public API。

## 7. Checkpoint、interrupt 与 agent supervisor

checkpoint 保存业务图的 durable state：已完成 phase、blackboard、待处理 `AgentTask`、恢复位置和提交幂等信息。ah 或 Prime Agent 这类系统管理 agent session、进程、provider、角色拓扑与 crash recovery。两者解决不同问题，不是二选一。

内部实现可以继续用 LangGraph checkpoint。只有人工介入和 cooperative host adapter 需要 interrupt-like pause；普通 CLI executor 可以在一次 application call 内等待子进程完成。无论内部如何实现，SDK/CLI/MCP 只暴露 versioned pause/dispatch/result，不暴露 `interrupt()`、Command 或内部 checkpoint object。

[ah](https://github.com/SevenX77/ah) 提供 provider CLI、进程监督、tmux workspace、角色编队和 JSON-RPC control plane。v1 借它的 provider adapter、生命周期监督与显式角色拓扑思想；不把它作为核心依赖，因为当前实现依赖 Linux/WSL、systemd/tmux，并以预配置编队为中心，这与 Windows/macOS 原生支持和“装进现有宿主”的目标不一致。

[Prime Agent architecture](https://github.com/PrimeIntellect-ai/prime-agent/blob/main/packages/coding-agent/docs/architecture.md)把 presentation、supervisor、runtime、provider 与 persistence 分层，并用 versioned command/RPC 和 child registry 管理 session tree；其[subagent extension](https://github.com/PrimeIntellect-ai/prime-agent/blob/main/packages/coding-agent/examples/extensions/subagent/README.md)以隔离进程运行 child。v1 借这些边界和 registry 思想；不把 Prime 作为核心依赖，因为它是完整替代型 harness，而本产品要作为兼容现有宿主的 plugin/runtime。

未来可以实现 `AhExecutor` 或 `PrimeExecutor` adapter。v1 先完成直接 CLI adapter 的最小闭环，避免在未证明需要完整 supervisor 前引入第二套控制平面。

## 8. Standalone 配置与状态

### 8.1 四层优先级

同一配置项只能按以下固定优先级解析，高者覆盖低者：

1. `RunInvocation` 中的显式本次覆盖或 CLI flags；
2. 业务项目根 `gskill.toml`，其中 `[runtime]` 是 project `RuntimeProfile` overlay，`[presets.<preset_id>]` 是可选的具名 `RunPreset`；
3. 操作系统标准 config directory 中的 user `RuntimeProfile`；
4. safe defaults，以及 portable declaration 明确声明的业务默认值。

`RuntimeProfile` 只承载 executor、checkpoint store、state directory、capability 与权限/失败策略等运行环境选择。`RunPreset` 承载需要跨多次运行复用的**非秘密业务运行默认值**，例如 input/binding defaults、breakpoints、node overrides、compare candidates 和 artifact requests。二者是 `gskill.toml` 中两个独立的强类型 schema；不能为了少一个文件把业务输入、artifact 定义或 UI 扫描状态塞进 `RuntimeProfile`。

调用者可以选择一个具名 preset，再只覆盖本次变化的值，不需要每次重新配置整套运行。resolver 合并上述四层后必须输出两个 normalized、强类型对象：resolved `RuntimeProfile` snapshot，以及包含实际 inputs/bindings/overrides/artifact requests 的 immutable `RunRequest`。两者都随 run 保存并记录每个值的来源层；后续 resume 读取该快照，而不是重新读取已经变化的 profile 或 preset。

秘密只来自宿主 secret store、环境变量或操作系统 keychain，绝不写入业务 gSkill、`gskill.toml`、run snapshot 或安装 manifest。配置可以保存 secret reference 名称，不能保存 secret value。

### 8.2 Executor 所需配置

- `host-native` 不需要 LLM key 或 model provider 配置；当前宿主负责模型与登录。
- `cli` 由厂商 CLI 持有登录和默认模型；runtime profile 只选择 executor、agent profile、可选 model override 与所需 capabilities。
- 只有 `embedded` extra 需要 provider/model resolver；它的 credential 仍通过环境或 secret provider 注入。

### 8.3 State directory

默认 state directory 是业务 skill 根的 `.gskill/`。`--state-dir` 或 profile 可显式覆盖。runtime 必须在边界解析并验证绝对路径，不允许内部模块各自从 CWD 推导目录。run snapshot、checkpoint、trace 与 artifact manifest 都引用同一 resolved state root，但各自仍有独立 owner 和保留策略。

## 9. 从 `studio.runtime_config.v2` 拆分

旧 `.workspace/runtime_config.json` 不能整体迁入 runtime。目标按 owner 与生命周期拆成四类：

1. **Portable declarations**：`SKILL.md`、`graph.yaml`、phase 文件，以及 `graph.yaml` 中具名 artifact declarations；随业务 skill 提交。
2. **Reusable configuration**：project `gskill.toml` 同时容纳彼此独立的强类型 `RuntimeProfile` overlay 与可选 named `RunPreset`；user config 只提供机器/用户级 `RuntimeProfile` 默认值。`RunPreset` 保存可复用、非秘密的运行默认值，不保存 artifact definition。
3. **RunRequest**：由显式 invocation、选中的 preset、profile 与声明默认值合并出的本次 immutable snapshot；包含实际 inputs/bindings、breakpoints、artifact requests、node overrides 与 compare candidates。
4. **StudioAdapterState**：Studio 文件 mirror、扫描和 UI 编辑投影；只属于 Studio adapter。

Artifact declaration 和 artifact request 是两个不同对象。根 `graph.yaml` 以稳定 `artifact_id` 声明 `stem`、`fields`、`mode`、`format`，回答“这个 skill 能产出什么、怎样物化”；`RunPreset` 或 `RunRequest.artifact_requests` 只引用 `artifact_id`，回答“这次要产出哪些”。v1 默认只允许 request 指定输出 destination；若未来确需覆盖其他属性，必须由 declaration 中的强类型 override schema 明确开放，不能让 request 任意改写 `fields`、`mode` 或 `format`。

逐字段映射如下：

| 当前字段 | 新 owner | 转换规则 |
| --- | --- | --- |
| `schema_version` | converter 输入判别；各新对象各自有版本 | 不复制成统一 runtime config version |
| `inputs.import_root` | `StudioAdapterState.import_root` | 只用于 Studio 导入扫描，不进入 runtime core |
| `inputs.manifest.root` / `.phases` | `StudioAdapterState.input_manifest` | 保留文件 mirror/scan 事实，不作为运行输入 |
| `inputs.active.root` | named `RunPreset.inputs` → resolved `RunRequest.inputs` | 非秘密、可复用值进入 converter 生成的 project preset；本次覆盖合并后进入 immutable request。秘密或机器临时值不得持久化，converter 必须报告并要求运行时显式提供 |
| `inputs.active.phases` | named `RunPreset.bindings` → resolved `RunRequest.bindings` | 按 `<graph_id>/<phase_id>/<field>` 规范化；同样先保留长期默认，再在每次运行形成最终快照 |
| `inputs.removed.root` / `.phases` | `StudioAdapterState.removed` | UI 差异状态，不进入 runtime |
| `inputs.conflicts.root` / `.phases` | `StudioAdapterState.conflicts` | Studio 在提交 RunRequest 前解决；未解决则边界拒绝 |
| `llm.node_params.nodes` | named `RunPreset.node_overrides` → resolved `RunRequest.node_overrides` | 可复用、非秘密覆盖可进 preset；显式本次覆盖优先，最终值只接受公开 schema |
| `llm.compare_candidates.nodes` | named `RunPreset.compare_candidates` → resolved `RunRequest.compare_candidates` | 经常复用的非秘密候选集可进 preset；一次性候选只进 invocation，二者都在本次 snapshot 固化 |
| `llm.custom_params.nodes` | named `RunPreset.node_overrides.custom_params` → resolved `RunRequest` | 按 executor capability/schema 校验；秘密值禁止进入 preset 与 snapshot |
| `breakpoints` | named `RunPreset.breakpoints` → resolved `RunRequest.breakpoints` | 使用稳定 graph/phase address；可复用默认值进 preset，本次增删在最终 snapshot 固化 |
| `artifacts[].{stem,fields,mode,format}` | `graph.yaml.artifacts[]` + named `RunPreset.artifact_requests` | converter 将每个旧条目提升为 portable declaration，并为其生成稳定 `artifact_id`；为保持旧配置“已启用”的语义，生成的 preset 以 ID 选择这些 declaration。RunRequest 只保存最终选择、destination 与声明允许的本次覆盖 |

portable graph 中声明允许的输入输出、可覆盖点和 artifact definitions，不保存某次运行的实际值。`RuntimeProfile` 不接收表格中的业务运行字段；这些字段只在 named `RunPreset` 与最终 `RunRequest` 之间流动。

新仓不实现 dual reader 或 legacy shim。可以提供一次性 `gskill migrate studio-skill <source> <destination>` 转换器：它显式读取旧 Studio skill 与 runtime config，生成新格式目录、project `gskill.toml`、named migration preset 与迁移报告，遇到未知或有冲突字段就失败，且不覆盖源目录。

artifact id 不能使用旧数组位置，因为增删或排序会改变身份。converter 先把 `{stem, fields, mode, format}` 规范化，以合法化后的 `stem` 生成可读候选 ID；若不同定义产生同名候选，则追加规范化定义内容的确定性短 hash。完全相同的重复定义是无法证明意图的重复身份，converter 必须在报告中列出并失败，不能静默合并。迁移报告逐条记录旧数组索引到新 `artifact_id` 的映射。转换完成后，新 runtime 只读新格式，并只按 ID 接受 artifact request。

## 10. MoirAI 随包集成

### 10.1 资产边界与安装模型

MoirAI 是可选 agentic front door：它用 4 个 role、8 个 skill 和知识库帮助用户设计、修复、评估与运行 gSkill。它的 canonical integration assets 以 integration id `moirai` 随 runtime wheel/repo 携带，但只是包内只读资源；只有用户显式执行安装命令后，renderer 才会把它们投影到具体宿主。MoirAI 不是 core runtime 的必需依赖。

安装 `graph-skill-runtime` 不得静默修改 Claude、Codex、Copilot、Gemini、Cursor、OpenCode 或用户项目配置。唯一安装入口是用户显式执行的命令，例如：

```text
gskill integrations install moirai --targets detected --scope user --dry-run
gskill integrations install moirai --targets claude,codex,cursor --scope project
```

installer 必须先输出计划，进行冲突检测，并生成含 integration id、目标、scope、源 asset version、目标路径、内容 hash 和 ownership 的 install manifest。默认不覆盖非本工具拥有的文件；`gskill integrations uninstall moirai ...` 只删除 manifest 证明由本次安装拥有且 hash 未被用户修改的文件。冲突必须报告并要求显式处理。

canonical assets 只维护一份。每个 host renderer 将其投影为相应的 skill、custom-agent、plugin 与 MCP 配置。安装的是 MoirAI runtime integration，包括 4 roles、8 skills、`KB-00` hub 与 `KB-01..14`、host adapters/MCP；安装的不是用户业务 gSkill。

`gskill init` 与 `gskill link` 可以在用户明确请求时 scaffold 或链接一个业务 gSkill。`pip install`、import package、启动 MCP server 和 capability detection 都不得调用这两个有写入副作用的动作。

### 10.2 Tool ownership

| Tool family | 目标 owner | 原因 |
| --- | --- | --- |
| compile、predict、run、resume/submit、trace、artifacts、golden、inspect、portable skill reads | portable runtime MCP | 只依赖业务 skill 与 runtime application service |
| LLM credential、role、route、endpoint registry 与 provider probe | optional Gateway plugin | Gateway 是配置真相 owner；秘密与 route 不属于 portable skill |
| create/fork/publish、Studio UI file writing、workspace mirror | Studio plugin | 需要 Studio native-fs、router 与产品工作流 |
| web fetch/search | 当前宿主能力 | 网络权限、登录和安全策略由宿主拥有，runtime 不重复内置 |

同一用例的 MCP、CLI 与 SDK 入口必须调用同一 application service。MoirAI prompt 或 renderer 不允许直接调用 runtime 内部模块，也不允许复制 compile/run 判断。

## 11. 同类型方案比较

| 方案 | 它解决的核心问题 | v1 借用 | v1 不采用为核心的部分 |
| --- | --- | --- | --- |
| [Agent Skills standard](https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx) | 跨宿主发现、说明与渐进加载 skill | 根 `SKILL.md`、安全 frontmatter、references/examples | 它不定义 typed DAG、checkpoint、predict 或 eval；这些由 runtime 补充 |
| [LangGraph](https://docs.langchain.com/oss/python/langgraph/) | graph execution、state、checkpoint、subgraph | 内部图执行与 durable checkpoint 的成熟机制 | 不把 Python graph object、interrupt 或 provider agent 变成公开 portable contract |
| [gwaghmar/graph](https://github.com/gwaghmar/graph) | 多宿主的本地 DAG 工程，含 cache、retry、quality gate 与 live report | 显式 DAG、thin host adapters、本地可观察执行 | 其公开能力弱于本项目已有 typed blackboard、聚合 compile、predict/golden 与 durable resume；不以复制其格式替代现有领域能力 |
| [ah](https://github.com/SevenX77/ah) | 多 provider CLI 的 daemon、进程监督与固定角色编队 | provider adapter、进程生命周期、角色拓扑 | Linux/WSL、systemd/tmux 与完整 control plane 不适合作为跨平台 plugin runtime 的 v1 硬依赖 |
| [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent/blob/main/packages/coding-agent/docs/architecture.md) | 完整 coding-agent harness、daemon、session tree 与 provider abstraction | presentation/supervisor/runtime/provider/persistence 分层、versioned RPC、child registry | 它会替代宿主，而 v1 需要接入现有宿主；不把完整 harness 作为核心 |

Graph Skill Runtime 的独特组合是：portable Agent Skill entry、compiled typed dataflow、predict/golden、durable resume、host-native agent execution 与可选 MoirAI front door。相应成本也必须正面承担：六宿主 compatibility matrix、`agent_required`/result 的两步交接协议、installer 的冲突与安全责任，以及 CLI 版本漂移的长期探测测试。

## 12. 安全与失败行为

实现必须在边界 fail fast：

- skill root、state dir、file binding 与 artifact target 在解析绝对路径后检查允许范围；
- vendor CLI adapter 使用明确 executable allowlist、固定 argv 结构、最小环境变量和受控 working directory，不通过 shell 拼接 prompt；
- `AgentTask` 只携带该 phase 所需输入、允许工具与路径，不携带宿主全会话或未声明 secrets；
- 外部 agent 返回值必须先做 schema、task id、checkpoint generation 和大小限制校验；
- MCP 与 installer 遵守宿主权限与信任模型；被动 capability detection 不等于安装授权，只有用户显式执行 `integrations install` 才能写入，即使目标值是 `detected`；
- install/uninstall 以 manifest 和 content hash 证明 ownership，冲突时保留用户文件并失败；
- checkpoint 写入、agent result 提交与 resume 必须幂等，重复/过期提交返回结构化错误而不是再次执行 phase。

## 13. 分阶段迁移

每个阶段都必须有独立退出判据和失败出口。未通过退出判据时，当前 `graph-agent`、FROZEN 格式和 Studio 集成继续作为运行事实；不能靠 dual reader 掩盖未完成迁移。

### Phase 0：契约冻结与 characterization

**工作**：冻结当前 24-export 行为、格式 fixtures、聚合 diagnostics、run/predict/golden/checkpoint/resume/events/errors、`runtime_config.artifacts` 的 `{stem, fields, mode, format}` 物化语义与 Studio 调用样本；记录 Windows/macOS/Linux 安装和路径行为。

**退出判据**：characterization suite 能在当前提交重复运行，并明确区分公开承诺、待收紧的 `Any` 接缝和已知漂移。

**失败出口**：不拆代码；补齐证据后重跑。FROZEN format ground truth 保持不变。

### Phase 1：拆出 pure runtime 与 typed facade/config

**工作**：建立独立 repo/package 骨架、domain/application/ports/adapters 边界、版本化 invocation/request/result/event/error，以及将 `RuntimeProfile` 与 named `RunPreset` 分离的四层 config resolver；把 compile/predict/checkpoint 等 pure runtime 能力迁入。现有 embedded executor 只作为显式 optional extra 与 characterization oracle，不成为新包默认 executor。

**退出判据**：clean Python 3.11+ 环境可从 wheel 安装；顶层 contract 不泄露 `Any` 配置；RuntimeProfile 不含业务运行字段，named RunPreset 能提供持久非秘密默认值，RunRequest 是可回放的本次 immutable snapshot；CLI/MCP/SDK 的相同用例通过同一 application service；安装无宿主或项目写入副作用。

**失败出口**：停止发布新包，当前 monorepo package 继续运行；不在旧包旁增加永久兼容 facade。

### Phase 2：切换新 `SKILL.md` / `graph.yaml` / `AGENT.md` / `graphs/` 格式

**工作**：实现新 parser/compiler、扁平 registry、具名 artifact declarations、call graph 校验与一次性 Studio converter；converter 为旧 artifact definitions 生成稳定 ID，并输出 project preset；迁移受控 fixture 和 sample cohort。

**退出判据**：新格式 compile/predict 与 typed dataflow characterization 通过；unknown/duplicate/cycle 被同轮聚合拒绝；artifact declaration ID 在重排后稳定，request 只按 ID 选择声明；递归宿主 discovery 只发现根 `SKILL.md`；新 runtime 代码只存在一个 reader。

**失败出口**：丢弃未发布的新格式 build，修正 converter/compiler 后重新生成测试资产；不把旧 reader 加回新 core。

### Phase 3：完成 `host-native` cooperative adapter

**工作**：实现 durable `agent_required`、MCP/CLI submit、output validation、幂等 resume 和至少一个真实宿主闭环；把 `host-native` 设为 v1 默认。

**退出判据**：checkpoint 先于 dispatch 可见；宿主崩溃后可从另一个会话提交并继续；无 native subagent 时准确 fail fast；结果不依赖 LangGraph interrupt public type。

**失败出口**：该宿主标为 unsupported，不静默切 executor；compile/predict 仍可发布为预览，但不得宣称默认 run 完成。

### Phase 4：直接 vendor CLI adapters

**工作**：为 Claude、Codex、Copilot、Gemini、Cursor、OpenCode 建 capability probe、argv builder、JSON parser、timeout/cancel 与 provenance；每个执行都创建 fresh top-level session。

**退出判据**：声明支持的每个 OS/vendor/version 组合都有真实 smoke evidence；缺失 flag、登录、输出 schema 或 capability 时先于业务执行失败；CLI 与 host-native 通过同一 AgentTask/Result contract tests。

**失败出口**：从支持矩阵移除失败组合并给出结构化诊断；不伪装成当前会话 child，也不回退到未授权 embedded。

### Phase 5：MoirAI canonical assets、installer 与 portable MCP

**工作**：以 integration id `moirai` 整理一份 canonical roles/skills/KB，完成六宿主 renderer、显式 `gskill integrations install moirai`、dry-run、manifest/uninstall 与 portable runtime MCP tool set。

**退出判据**：wheel 内能读取 canonical assets，但未执行显式命令时六宿主目录零变化；重复安装幂等；冲突不覆盖；修改后的用户文件不会被 uninstall 删除；六 renderer snapshot 和真实宿主 discovery smoke 通过。

**失败出口**：MoirAI extra 不发布或缩小已验证 target 列表；core runtime release 不依赖它。

### Phase 6：Gateway/Studio optional plugins 与 cutover

**工作**：将 credential/role/route 管理留在 Gateway plugin，将 authoring/publish/UI file writing 留在 Studio plugin；更新 Studio adapter 使用新 typed SDK，重钉 contract maps、文档、fixtures 与发布流水线。

**退出判据**：Studio 真机旅程、三平台包、Gateway/Studio owner 边界和数据破坏恢复验证通过；所有活动引用已从旧格式重钉；旧 package/reader/phase `SKILL.md` 在同一 cutover 中删除；新的格式文档经审计后成为 current SSOT。

**失败出口**：不切 Studio production path，继续以当前 package/FROZEN 契约运行；修复新 adapter 后重新执行 cutover rehearsal。不得让两个 runtime 同时接受写入或成为并行真相源。

## 14. v1 总体验收

v1 只有同时满足以下条件才可标记完成：

1. PyPI wheel 可在 clean Python 3.11+ 环境以 `pip` 和 `uv` 安装，提供 `graph_skill_runtime` 与 `gskill`，且安装零宿主配置副作用。
2. 一个业务 gSkill 只有根 `SKILL.md` 被宿主发现，机器 topology 和具名 artifact declarations 只有 `graph.yaml` 定义，agent phase 只使用 `AGENT.md`；RunRequest 只按稳定 ID 请求已声明 artifact。
3. 编译聚合报告 graph/phase id、unknown reference、duplicate 和 cycle；`gskill inspect --call-graph` 与实际 call edges 同源。
4. SDK、CLI、MCP 对同一输入返回同源 diagnostics、result、events 与 error code；公开 config/executor/checkpoint 接缝没有未约束 `Any`。
5. `host-native` durable handoff 在真实宿主上完成 crash/reopen/submit/resume；CLI adapter 明确证明是 fresh top-level session。
6. checkpoint、trace、artifact 与 immutable run snapshot 可由因果证据关联到同一 run；重复 result 提交不会重复执行。
7. config 四层优先级、RuntimeProfile/RunPreset 职责分离、持久非秘密默认值、immutable RunRequest、secret exclusion 与 state-dir 绝对路径在三平台通过测试。
8. `gskill integrations install moirai` 的 dry-run、conflict、manifest、idempotency 与 safe uninstall 通过；wheel 携带的 canonical assets 在显式安装前不投影到宿主，安装资产也不包含用户业务 gSkill。
9. runtime、Gateway plugin、Studio plugin 与 host web capability 的工具 owner 无交叉真相；MoirAI 仍是 optional integration。
10. 迁移后只有新 reader；旧 FROZEN 契约只在实现、迁移验证和引用重钉完成的 cutover 中才被新的 audited/FROZEN 文档取代。

## 15. 尚待实证的裁决

以下不是 v1 默认事实：

- `embedded` extra 是否在 host/CLI parity 后长期保留，需要真实 server/CI 使用量、维护成本和隔离风险证据；在此之前保持可选，不进入 core default。
- 每个 vendor adapter 首次发布支持的精确 CLI 版本与 OS 组合，需要 Phase 4 capability probe 和真实 smoke 结果；不能仅凭本文的候选命令宣称支持。
- 工作名能否最终发布，需要 registry 占位和商标复核；若失败，应在首次公开发布前一次性改名，而不是增加永久 alias。
