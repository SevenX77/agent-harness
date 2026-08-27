---
module: graph-skill-runtime
doc: baseline
role: baseline
status: drafted
binds_alignment: ./v1-alignment.md
binds_code: ../../../packages/graph-agent; ../../../apps/studio/backend/app/agents; ../../../apps/studio/backend/app/services/runtime_config.py
updated: 2026-08-27
---

# Graph Skill Runtime 独立化基线

本文记录独立 runtime 设计所依赖的当前事实。核验截面是 `origin/main@3564b49e`（2026-08-27）。目标契约见双向绑定的 [`v1-alignment.md`](./v1-alignment.md)；本文不把目标决定写成已实现能力。

## 1. 当前产品与分发形态

当前 engine 位于 [`packages/graph-agent`](../../../packages/graph-agent)，Python distribution 名为 `graph-agent`，版本为 `0.3.1`，要求 Python 3.11 或更高版本。它是 monorepo 的 `uv` workspace 成员，还不是独立仓库。

当前 `pyproject.toml` 没有 `[project.scripts]`，因此安装包不提供稳定 console script。现有 argparse 入口只能通过 `python -m graph_agent` 到达；它不能被视为未来 `gskill` CLI 已经存在。

[`graph_agent.__all__`](../../../packages/graph-agent/src/graph_agent/__init__.py) 当前精确导出 24 个名字：

- 执行与预测：`run_skill`、`predict_skill`、`resume_skill`、`evaluate_golden_baseline`、`RunResult`、`PathDiff`、`PhaseRecord`；
- 产物运行：`compile_artifact`、`run_artifact`、`predict_artifact`；
- 编译与序列化：`compile_skill`、`CompileResult`、`SkillManifest`、`serialize_skill`；
- 装配：`assemble_graph`、`CompiledSkill`、`CompiledStateGraph`；
- 状态与解析：`BlackboardState`、`LocalWorkspaceResolver`；
- 错误：`GraphAgentError`、`GraphCompileError`、`GraphExecutionError`、`ModelProviderError`、`ResourceNotFoundError`。

测试目录约有 271 个 Python 文件和 1,047 个顶层 `test_*` 函数。这个数字只证明当前工程的测试规模，不证明所有公开入口或所有跨宿主组合都已被覆盖。

## 2. 当前 engine 能力

当前实现已经具备独立 runtime 所需的大部分领域能力：

- 唯一 compile/lint 出口与同一轮全量聚合诊断；
- `LOGIC`、`AGENT`、`SUBGRAPH` 三类 phase，typed blackboard、声明式输入输出和 iterate；
- `run`、`predict`、golden evaluation、artifact compile/run/predict；
- checkpoint、resume、人工介入（human-in-the-loop，指运行在需要人工输入时可持久化暂停并继续）；
- typed callback events、trace、error catalog、resolver 与本地 workspace 解析。

这些能力的当前职责分布仍由 [engine MVP1 索引](../mvp1/INDEX.md)及其 baseline/alignment 模块解释。独立化应复用这些经过验证的领域机制，而不是在新 CLI、MCP 或 Studio adapter 中复制编译与运行逻辑。

## 3. 独立发布前的接口缺口

当前包能在本仓运行，但顶层契约还不足以作为独立、强类型的公共 SDK：

| 当前接缝 | 可核验现状 | 独立化缺口 |
| --- | --- | --- |
| runtime 参数 | `model_resolver`、`runtime_config`、`artifact_saver`、`checkpointer` 等公共或近公共参数仍出现 `Any` 或 `dict[str, Any]` | 调用者无法仅依赖稳定类型理解允许状态；非法配置仍可进入核心深处 |
| runtime config | Studio 的 `RuntimeConfigPayload` 是 Studio service 内部 schema | runtime 没有公开、宿主无关的 `RunRequest` 与 `RuntimeProfile` 强类型模型 |
| events | `CallbackEvent` 家族存在并被 trace/subscriber 使用 | 完整事件联合类型和版本规则没有成为顶层公共契约 |
| errors | error registry 与异常层级存在 | 错误码 catalog、结构化 payload 与兼容规则没有形成独立包的单一公开入口 |
| executor | 当前 AGENT phase 由 engine 内部 LangChain/LangGraph `create_agent` 路径装配 | 没有窄 `AgentExecutor` Port，也没有宿主原生执行的 dispatch/result 协议 |
| CLI | 只有 `python -m graph_agent` 的旧 argparse 入口 | 没有稳定命令名、机器可读输出、能力探测或版本化 CLI 契约 |
| 分发 | monorepo workspace package | 尚无独立 repo、PyPI release、wheel 验证和跨平台安装证据 |

旧 [`packages/graph-agent/README.md`](../../../packages/graph-agent/README.md) 还曾把不存在的 `GraphAgentHarness` 写成公共外层、混写 24/21 个导出、把根入口描述成 `SKILL.md`，并遗漏必填的绝对 `workspace_dir`。这些是文档漂移，不是活代码的新契约。

## 4. 当前文件格式契约

[FROZEN format ground truth](../skill-spec/00-FORMAT-GROUND-TRUTH.md) 是当前实现格式的唯一真相源，并仍被代码与 contract maps 消费。当前事实是：

- skill 根入口是 `GRAPH.md`；
- phase 文件名按类型使用 `LOGIC.md`、`SUBGRAPH.md`、`SKILL.md`；
- 子图位于根 `subgraph/` 并按调用结构递归嵌套；
- Studio runtime 配置位于 `.workspace/runtime_config.json`。

未来改用 Agent Skills 入口、`graph.yaml`、`AGENT.md` 和扁平 graph registry 的决定只是 drafted。切换前不能修改或 supersede 现有 FROZEN 文档；切换时也不能让 runtime 长期双读两套布局。

## 5. 当前 Studio runtime config

[`runtime_config.py`](../../../apps/studio/backend/app/services/runtime_config.py) 当前生成 `studio.runtime_config.v2`，默认形状如下：

```yaml
schema_version: studio.runtime_config.v2
inputs:
  import_root: import_files
  manifest: {root: [], phases: {}}
  active: {root: {}, phases: {}}
  removed: {root: [], phases: {}}
  conflicts: {root: [], phases: {}}
llm:
  node_params: {nodes: {}}
  compare_candidates: {nodes: {}}
  custom_params: {nodes: {}}
breakpoints: []
artifacts: []
```

这个对象同时承载四种生命周期不同的数据：Studio 文件扫描投影、某次运行的实际输入、执行覆盖和产物定义。当前 `artifacts` 的每个条目以 `{stem, fields, mode, format}` 定义怎样从 blackboard 字段物化一个产物，并不只是选择一个已经声明的产物。当前 service 会为运行写出 snapshot，但核心 API 仍接收松散字典。独立 runtime 不能把整个 Studio schema 原样搬走，也不能在迁移时把 artifact definition 降格成一个 selection。

## 6. 当前 MoirAI 能力与资产

MoirAI 的当前能力链不是 [命名与人格叙事](../../strategy/moirai-copilot-persona-narrative.md)。当前产品需求、设计、完成状态与追加裁决分别位于：

- [`requirements.md`](../../../.kiro/specs/studio-moirai-agent-system/requirements.md)
- [`design.md`](../../../.kiro/specs/studio-moirai-agent-system/design.md)
- [`tasks.md`](../../../.kiro/specs/studio-moirai-agent-system/tasks.md)
- [`decision-2026-08-07-golden-case-authoring.md`](../../../.kiro/specs/studio-moirai-agent-system/decision-2026-08-07-golden-case-authoring.md)
- [`decision-2026-08-07-run-terminal-output-contract-and-cli-read-tier.md`](../../../.kiro/specs/studio-moirai-agent-system/decision-2026-08-07-run-terminal-output-contract-and-cli-read-tier.md)
- [`decision-2026-08-15-per-runtime-dispatch-operating-rules.md`](../../../.kiro/specs/studio-moirai-agent-system/decision-2026-08-15-per-runtime-dispatch-operating-rules.md)

活资产位于 [`apps/studio/backend/app/agents`](../../../apps/studio/backend/app/agents)：

- 4 个 role：MoirAI、Clotho、Lachesis、Atropos；
- 8 个 skill：`moirai-intro`、`brainstorming`、`domain-analysis`、`graph-design`、`agent-prompt-design`、`compile-error-repair`、`eval-judgement`、`web-research`；
- 14 篇主题知识文档 `KB-01` 至 `KB-14`，另有 `KB-00` hub；
- `agent-skill-map.json` 维护 role 与 skill 的分配关系。

Studio copilot 面板注册 42 个 MCP tools；去掉两个删除类 LLM 管理工具后，CLI MCP surface 暴露约 40 个。它们覆盖 runtime compile/predict/run/resume/pause/stop/trace/artifacts/golden/workspace/skill reads、authoring/publish、Gateway LLM 配置与探测，以及 web fetch。

这组工具并非整体可移植：许多实现直接调用 Studio routers、services、文件写入与 Gateway 配置真相。独立化前必须按事实 owner 拆分；把现有注册表复制到新包只会把 Studio 依赖藏进 runtime。

## 7. 当前边界与必须保留的事实

用户业务 gSkill 当前是项目内容，不是 engine 内置资产。独立 wheel 也不能把业务 skill 捆绑、注册或复制到宿主。MoirAI 的 runtime integration 资产与用户业务 gSkill 是两类不同对象：前者可以成为可选分发资产，后者永远由用户拥有并通过显式路径交给 runtime。

checkpoint 当前保存的是业务图执行事实；Studio/copilot 进程与 agent session 则是宿主运行事实。这两个状态域可以协作，但不能互相替代。未来引入宿主原生 subagent、厂商 CLI、ah 或 Prime Agent 时，仍需保留业务图的 durable checkpoint 与恢复语义。

## 8. 基线结论

从当前证据可得出的结论是：独立化主要不是重新发明图执行器，而是收紧公共契约、拆开配置生命周期、建立可替换 executor、定义 portable skill 入口，并把 Studio/MoirAI 集成按 owner 重组。目标完成之前，`graph-agent` 0.3.1、FROZEN 当前格式与 Studio adapter 仍是运行事实；任何未来名称或命令都不能写成已发布能力。
