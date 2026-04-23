# Implementation Plan

> 任务清单按 8 个 Step 组织，每个 Step 相对独立，可以单独 commit + 回归测试。总体遵循 `design.md` 的 Migration Strategy 顺序。
>
> **Parallel marker** `(P)`：可与同 Step 其他 task 并行。

## Step 1: 仓库清理（低风险，先做）

- [ ] 1.1 `.gitignore` 加入 `.ccb/`、`*.pyc`、`__pycache__/`、`.studio_state/`、`.deer-flow/checkpoints.db`、`workspaces/` (P)
  - 所有 runtime 文件不再被 commit
  - 现有已 commit 的 runtime 文件一并 `git rm --cached`
  - _Requirements: 18_

- [ ] 1.2 删除 `skills/builtin/script/patch_tools.py`（与 `skills/builtin/md-patch/script/patch_tools.py` 重复） (P)
  - 保留 md-patch/ 下的版本作为唯一实现
  - 更新 import 引用
  - _Requirements: 18_

- [ ] 1.3 清理 legacy bak 文件 (P)
  - 删除 `src/visual_learning/phase1_gt_extraction_v1.py.bak` 等 `.bak`
  - 删除顶层 `2026-04-08-*-ai-narrated-recap.txt`（如果存在）
  - _Requirements: 18_

- [ ] 1.4 合并 docs 目录 (P)
  - 把 `src/core/graph_agent/docs/` 和 `docs/graph_agent_docs/` 合并为一份权威文档
  - 另一份改 symlink 或删除
  - 更新所有交叉引用路径
  - _Requirements: 21_

## Step 2: DeerFlow 上游同步（修 bug + 架构小优化）

- [ ] 2.1 同步 PR #2251 — Memory update cache corruption / data loss / thread-safety
  - 关键修复，影响 working_memory 持久化正确性
  - 文件：`deerflow/agents/memory/updater.py` / `storage.py` / `queue.py`
  - 同步后跑回归测试（模拟 disk full 验证 cache 和磁盘一致）
  - _Requirements: 13_

- [ ] 2.2 同步 PR #2107 — tool duplication + skill parser YAML 不一致 (P)
  - `deerflow/skills/parser.py` 的自定义 line-by-line parser 改为 `yaml.safe_load`
  - Deduplication in `get_available_tools`
  - _Requirements: 13_

- [ ] 2.3 同步 PR #2305 — subagent 继承父 agent 的 tool_groups (P)
  - 影响 parallel_map tool 的 subagent 场景
  - _Requirements: 13_

- [ ] 2.4 同步 PR #2350/#2351 — clarification messages 幂等 (P)
  - 影响人工接入点可靠性
  - _Requirements: 13_

- [ ] 2.5 同步 PR #2321 — 防 LLM 幻觉 HTML tag 渲染为 DOM (P)
  - _Requirements: 13_

- [ ] 2.6 同步 PR #2332 — uploads 显式 opt-in (P)
  - 安全加固
  - _Requirements: 13_

- [ ] 2.7 Subagent 中间件继承改造
  - 修改 `deerflow/agents/lead_agent/agent.py` 的 `make_lead_agent()` 签名，加 `inherit_middlewares: bool = True`
  - 加 `# MODIFIED` 注释（按 NOTICE.md 规范）
  - 更新 `INTEGRATION_GUIDE.md` 让"Subagent Middleware 限制"段失效
  - _Requirements: 14_

- [ ] 2.8 Checkpointer GC 策略
  - 在 `deerflow/agents/checkpointer/provider.py` 封装层加 `max_checkpoints_per_thread`（默认 100）参数
  - 超过上限自动删除最老的 checkpoint
  - 加 `ccb-compact-checkpoints` 命令（可选，手动清理用）
  - _Requirements: 15_

- [ ] 2.9 Plan Mode 和 WorkingMemory 职责梳理
  - 审计 `deerflow/client.py` L111 的 `plan_mode` 参数 和 `cognitive/middlewares.py` 的 WorkingMemory
  - 决策：graph_agent 默认关闭 DeerFlow plan_mode
  - 在 `docs/graph_agent_docs/COGNITIVE_LOOP_GUIDE.md` 明确说明两者关系
  - _Requirements: 16_

## Step 3: StorageManager + CallbackEvent 类型化（新组件）

- [ ] 3.1 新增 StorageManager 实现
  - 新建 `src/core/graph_agent/io/storage.py`
  - 实现 `StorageManager(workspace_root, skill_id, run_id, *, history_retention=10)` + `get_output_dir(pipeline_prefix=None)` + `save_artifact(name, content, phase=None)` + `load_latest(phase, name)` + `_cleanup_history()`
  - **签名不含 user_id**（设计不变量）
  - `.golden` 后缀目录永不删除
  - 单测覆盖：默认路径、pipeline_prefix 注入、.golden 锁定、超限清理
  - _Requirements: 5, 6_

- [ ] 3.2 IOManager 对接 StorageManager 作为 default saver
  - 修改 `src/core/graph_agent/io/manager.py`
  - 当 SKILL.md 声明 `target: artifact_manager` 且 caller 未注入 `artifact_saver` 时，fallback 到 StorageManager
  - caller 的 artifact_saver 优先级更高（保留 Kitchen-Pass 红线）
  - _Requirements: 5_

- [ ] 3.3 保留 legacy DataManager / ArtifactManager (P)
  - 现有 `src/core/data_manager.py` 和 `src/core/artifact_manager.py` 加 `DeprecationWarning` 日志
  - 文档里引导新代码用 StorageManager
  - **不删除**（避免破坏现有 host project）
  - _Requirements: 5_

- [ ] 3.4 CallbackEvent Pydantic union (P)
  - 新建 `src/core/graph_agent/callbacks/events.py`
  - 定义 14 种事件：12 个现有（phase_start / phase_end / llm_call / tool_call / validation_fail / retry / finish_task / nudge / working_memory_update / dead_end_pruned / compaction / ambiguity_report）+ 2 新增（prompt_captured / llm_fallback）
  - 每种事件一个 payload 子类；全部组成 `CallbackEvent` discriminated union on `event_type`
  - 所有事件含 `schema_version: Literal["1.0"]`
  - _Requirements: 8_

- [ ] 3.5 callbacks/base.py 迁移到 Pydantic 事件
  - 修改 14 个现有钩子（`on_phase_start` 等）emit Pydantic 事件而不是 dict
  - 提供兼容 shim：同时 emit 旧 dict + 新 Pydantic 事件（3 个月后移除 dict）
  - _Requirements: 8_

- [ ] 3.6 TracingCallback 落盘 `tracing.jsonl`
  - 每行一个 `event.model_dump_json()`
  - 按 timestamp 单调
  - _Requirements: 8_

## Step 4: TracingClientProxy + parallel_map（新工具）

- [ ] 4.1 TracingClientProxy 实现
  - 新建 `src/core/graph_agent/core/tracing_proxy.py`
  - 实现 `TracingClientProxy(wrapped_client, callbacks, llm_role, resolved_model)` + `chat(messages, template_source=None, variables=None, **kwargs)`
  - chat 前 emit `prompt_captured` 事件；透明转发其他方法给 wrapped_client
  - _Requirements: 7_

- [ ] 4.2 Harness 集成 TracingClientProxy
  - 修改 `src/core/graph_agent/core/harness.py` 在 resolve model 之后、传给 DeerFlow `create_agent()` 之前包装 Proxy
  - 单测：跑一个 2 轮 agent loop 的 echo skill，验证 `tracing.jsonl` 里有 2 条 prompt_captured
  - _Requirements: 7_

- [ ] 4.3 builtin parallel_map 工具
  - 新建 `src/core/graph_agent/tools/builtin/parallel_map.py`
  - 实现 `parallel_map(skill_path, item_list, item_as, *, max_concurrent=3)`
  - 内部用 `ThreadPoolExecutor(max_workers=max_concurrent)` 并发调用 `run_skill(...)`
  - 每个子 skill 走完整框架路径（不绕过认知循环）
  - 父 callbacks 通过 runtime_inputs propagate 到子 skill
  - 单测：10 item 并发，验证 max_concurrent=3 限流 + callback 事件完整
  - _Requirements: 4_

- [ ] 4.4 parallel_map 注册为 builtin tool
  - 让 SKILL.md 里写 `tools: [builtin.parallel_map]` 能被正确解析
  - 文档里给 skill 作者展示如何使用
  - _Requirements: 4_

## Step 5: Compiler 规则 + Phase 术语统一

- [ ] 5.1 Compiler 新增 FATAL 规则 (P)
  - 在 `skills/compiler/data/rules.yaml` 加三条 F 级规则：
    - `F-subgraph-exclusive-tools`
    - `F-subgraph-exclusive-prompt`
    - `F-subgraph-exclusive-sub-skills`
  - 在 `skills/compiler/script/compile.py` 实现对应检查
  - 在 `skills/compiler/references/rules_spec.md` 补充规则详细说明
  - _Requirements: 2_

- [ ] 5.2 Compiler 新增 WARNING 规则 (P)
  - `W-node-to-phase-migration` — 检测 `<node id=...>` 建议改 `<phase id=...>`
  - `W-python-glue-orchestrator` — 检测 orchestrator 用 Python dispatcher 而非 subgraph/sub_skills
  - _Requirements: 1, 12_

- [ ] 5.3 Parser 支持 `<phase>` 标签
  - 修改 `src/core/graph_agent/core/parser.py` L162-165 的 `_NODE_PATTERN`
  - 改为同时匹配 `<phase id="...">` 和 `<node id="...">`
  - _Requirements: 1_

- [ ] 5.4 `<step>` 标签支持
  - 让 parser 允许在 `<system_prompt>` / `<user_prompt>` 内嵌 `<step name="..." goal="...">`
  - **不做表达式求值**（只作为 prompt 结构化片段）
  - compiler 加基础格式校验（name + goal 必填）
  - 禁止 `when` / `skip_if` / `if` / `else` 等表达式字段
  - _Requirements: 3_

- [ ] 5.5 业务 skill 术语迁移 (P)
  - 把 6 个业务 skill（包括 compiler skill 自己）的 `nodes/` 目录重命名为 `phases/`
  - 把所有 `<node id="...">` 标签改成 `<phase id="...">`
  - 更新 `<ref path="nodes/...">` 引用
  - _Requirements: 1_

- [ ] 5.6 bad-samples 目录建立
  - 新建 `skills/examples/bad-samples/` 目录
  - 放入 3 个触发 F-subgraph-exclusive-* 的反模式 skill 样本
  - 放入 story-deconstruction 的 Python 胶水版本（从 Step 8 迁移过来）
  - 加入 compiler 测试套件
  - _Requirements: 2, 12_

## Step 6: Model Override + Nudge 降权

- [ ] 6.1 PhaseConfig 加 model_override 字段
  - 修改 `src/core/graph_agent/core/types.py` 的 `Phase` dataclass
  - 加 `model_override: str | None = None`
  - loader 里优先级：`model_override` > `tier`
  - _Requirements: 9_

- [ ] 6.2 llm_roles.yaml 扩展单模型 role + peer groups
  - 在 `config/llm_roles.yaml` 加 `single_model_roles` 段
  - 加 `peer_model_groups` 段（定义同级可 fallback 的代码模型对）
  - 加 `circuit_breaker` 段（熔断阈值可配置）
  - _Requirements: 9_

- [ ] 6.3 ModelResolver fallback 扩展
  - 修改 `src/core/graph_agent/models/resolver.py`
  - 主 provider 失败后读 `peer_model_groups` 自动切同级
  - emit `llm_fallback` 事件（R8.2 新增的事件类型）
  - 全部失败时抛 `FallbackExhaustedError`
  - _Requirements: 9, 8_

- [ ] 6.4 熔断阈值参数化 (P)
  - 现有写死的 30min / 30 errors 改从 `llm_roles.yaml.circuit_breaker` 读
  - 支持 per-provider 覆盖
  - _Requirements: 9_

- [ ] 6.5 Nudge 默认值降权
  - `Phase` dataclass 的 `max_nudges` 默认值从 `3` 改到 `1`
  - 文档更新说明
  - 回归：现有业务 skill 如依赖 `max_nudges=3` 显式声明
  - _Requirements: 10_

## Step 7: Harness 拆分 + 仓库结构整理

- [ ] 7.1 Harness.py 拆分 — GraphBuilder
  - 把 `core/harness.py` 的 `_build_graph()` 相关逻辑抽到新的 `core/graph_builder.py`
  - `GraphAgentHarness` 委派给 `GraphBuilder`
  - _Requirements: 20_

- [ ] 7.2 Harness.py 拆分 — PhaseExecutor (P)
  - `_build_phase_node` / `_build_code_only_node` / `_build_subgraph_node` 抽到 `core/phase_executor.py`
  - _Requirements: 20_

- [ ] 7.3 Harness.py 拆分 — RetryRouter (P)
  - `_should_retry` + 相关 routing 逻辑抽到 `core/retry_router.py`
  - _Requirements: 20_

- [ ] 7.4 Harness.py 拆分 — NudgeInjector (P)
  - Planning nudge + Selfcheck nudge + Standard nudge 抽到 `core/nudge_injector.py`
  - _Requirements: 20_

- [ ] 7.5 拆分后跑全量回归
  - 所有业务 skill 跑一遍验证行为不变
  - _Requirements: 20_

- [ ] 7.6 仓库结构物理整理
  - 把 `src/core/graph_agent/` 目录整体移到 `packages/graph-agent/src/graph_agent/`
  - 新建 `packages/graph-agent/pyproject.toml`（定义 package 名 `graph-agent`、版本、依赖）
  - 更新所有 `from src.core.graph_agent` import 到 `from graph_agent`
  - 在 `src/core/graph_agent/__init__.py` 留兼容 shim（re-export）
  - **不引入 uv workspace**（留给 Studio 项目）
  - _Requirements: 11_

- [ ] 7.7 Studio checkpointer 配置增强 (P)
  - `harness.py` 的 `checkpointer="auto"` 解析加 `STUDIO_CHECKPOINTER` 环境变量检测
  - 支持 `sqlite:.studio/checkpoints.db`、`memory`、`postgres://...`
  - _Requirements: 17_

## Step 8: Story-deconstruction 样板改造

- [ ] 8.1 保留原版作为反模式样本
  - 把 `skills/story-deconstruction/` 整体移到 `skills/examples/bad-samples/story-deconstruction-python-glue/`
  - 加入 compiler 测试套件（验证 `W-python-glue-orchestrator` 能正确识别）
  - _Requirements: 12_

- [ ] 8.2 新建 subgraph 版样板
  - 新建 `skills/story-deconstruction/SKILL.md`
  - 4 个 phase 分别用 `subgraph:` 嵌入 `text-segmentation` / `event-extraction` / `batch-analysis` / `global-synthesis`
  - 每个 phase 提供 `context_bridge` 映射
  - _Requirements: 12_

- [ ] 8.3 端到端测试 subgraph 样板
  - 跑新版 story-deconstruction 完整流程
  - 验证 4 个子 skill 正确执行 + context 正确传递
  - 验证 trace 里每个子 skill 的 CallbackEvent 完整
  - 验证 StorageManager 把产出落到正确的 `/runs/<run_id>/` 目录
  - _Requirements: 12_

## Step 9: 多模态工具单测 + 文档完善

- [ ] 9.1 多模态工具单测 (P)
  - 为 `tools/generate_video.py` / `synthesize_speech.py` / `understand_video.py` 各加一个 happy-path 单测
  - mock 外部 API（不真调）
  - 加入 CI
  - _Requirements: 19_

- [ ] 9.2 更新框架文档
  - `docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md` 更新新增的 StorageManager、parallel_map、TracingClientProxy 章节
  - `docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md` 补 `<step>` 标签 + `model_override` 用法
  - `docs/graph_agent_docs/COGNITIVE_LOOP_GUIDE.md` 补 Plan Mode / WorkingMemory 职责说明
  - _Requirements: 16, 21_

## Verification & Acceptance

完成所有 Step 后：

1. `uv run pytest tests/ -x` 全绿（包括新增单测）
2. `uv run pytest tests/integration/ -x` 全绿（断点续跑、人工接入、parallel_map 等端到端测试）
3. 跑新版 story-deconstruction 完整流程，验证 subgraph 组合正确工作
4. 跑 `ccb-compact-checkpoints` 清理大量 checkpoint 无报错
5. 新建一个带 `<phase>` 标签的 skill，用 compiler Lint 通过
6. 故意写一个 subgraph + tools 冲突的 skill，compiler 报 `F-subgraph-exclusive-tools` FATAL
7. Studio 开发团队的 Kiro spec（基于 `docs/studio/README.md`）可以基于本 spec 交付的引擎能力开始写

## Requirements Traceability

| Step | Tasks | Requirements |
|------|-------|--------------|
| 1 | 1.1-1.4 | 18, 21 |
| 2 | 2.1-2.9 | 13, 14, 15, 16 |
| 3 | 3.1-3.6 | 5, 6, 8 |
| 4 | 4.1-4.4 | 4, 7 |
| 5 | 5.1-5.6 | 1, 2, 3, 12 |
| 6 | 6.1-6.5 | 9, 10 |
| 7 | 7.1-7.7 | 11, 17, 20 |
| 8 | 8.1-8.3 | 12 |
| 9 | 9.1-9.2 | 19, 21 |
