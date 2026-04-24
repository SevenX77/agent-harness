# Graph-Agent-Optimizations — 遗留项追踪

> 持久化的 deferred work 清单。每个 item 标注**来源（原 spec Task 号）/ 为什么延后 / 下一步具体动作 / 估时**。
>
> **更新原则**：每次解决一项就 `[x]` 勾掉、填实际交付的 commit；每次发现新的遗留就 append 到底部；不要直接删条目（保留完整历史方便审计）。

---

## 已完成 (归档参考)

| 原 Task | 交付 commit |
|---------|-------------|
| Step 1 全部 | `1f750ed` / `7b2229a` / `8a3b1d8` / `09f0f6d` |
| Step 2: PR #2251 同步 | `89d2713` + `ab92759` |
| Step 2: PR #2351 同步 | `bd94de0` + `198760c` |
| Step 2: PR #2107 同步 | `dc18068` |
| Step 2: PR #2305 同步 | `e42ec15` |
| Step 2: Task 2.7 Subagent middleware 继承 | `5b674e6` |
| Step 2: Task 2.9 plan_mode 审计 | `4d61cba` |
| Step 2: NOTICE.md 更新 | `18db679` |
| Step 3: 全部（3.1-3.6）| `b4512b9` / `4462391` / `d5a5455` / `fcb415e` / `aa28b3c` |
| Step 4: 全部（4.1-4.4）| `9733beb` / `1f1832e` |
| Step 5: 5.1 / 部分 5.2 / 5.3 / 5.5 | `1565cfd` / `dd085b4` / `b687bd4` |
| Step 6: 6.1 + 6.5 | `df7b1db` |
| Step 7: 7.0 / 7.7 | `966dca0` / `9b6672b` |
| Step 8: 8.2 subgraph 样板 | `46e7f43` |
| Step 9: 9.2 文档更新 | `6b3258a` |
| Tier-1 骨架（T-B1/B5/B12/B14）| `0e40c5c` |
| Tier-1 数据（T-A1/A2/A3/A4 + T-B2/B10）| `e1a4171` |
| Tier-1 并发/子图（T-B8/B9）| `b2ab2bb` |
| Tier-1 D-2.8 cleanup_on_finish | `a296f3f` |
| Tier-1 I-2 snapshot_diff | `3cb48df` |
| Tier-1 T-B13 Heartbeat（threading）| `4a25d61` |
| Tier-1 I-3 golden baseline（text-segmentation only）| `76ab95b` |
| Tier-2 I-1 get_thread_status | `0d5fc19` |
| Tier-2 T-B11 Interrupted/Resumed | `42c8329` |
| Tier-2 D-6.2/6.3/6.4 peer_model_groups | `9a6564e` |
| Tier-2 T-B4 AgentLoopIteration | `837ae72` |
| Tier-3 D-9.1 多模态单测 | `45597a9` |
| Tier-3 D-5.4 `<step>` 校验 | `7a5658d` |
| Tier-3 D-5.6 bad-samples 回归 | `ba07e71` |
| Tier-3 D-5.2 W-python-glue-orchestrator | `dd04f05` |
| I-4 pyproject.toml 版本锁 | `ba50b18` |
| I-5 recap 归档 | `b18bdcf` |

---

## 一、原 spec 遗留 Task（按 Step 分组）

### Step 2 — DeerFlow 同步（1 项）

#### D-2.8 Checkpointer 清理策略（简化版）

- [ ] **原 Task**：2.8 Checkpointer GC
- **简化决定**：经 Gemini + 用户确认，不做"单 checkpoint 删除"wrapper；改为 `cleanup_checkpoints_on_finish: bool = True` 默认，跑完调 `delete_thread(thread_id)` 一次清光。
- **延后原因**：原方案 LangGraph 接口限制需 backend-specific SQL，过度工程；简化版待实施。
- **下一步**：
  1. `runner.run_skill` 成功 return 前加 `if cleanup_checkpoints_on_finish: checkpointer.delete_thread(thread_id)`
  2. 发 `ThreadCleanedUpEvent`（见二-3 B7）
  3. 不要放 `harness.run()` finally，那会把异常中断时的 checkpoint 也删掉（Gemini 强调）
- **估时**：30 分钟

---

### Step 5 — Compiler & Terminology（3 项）

#### D-5.2 W-python-glue-orchestrator 规则

- [ ] **原 Task**：5.2 第三条 warning
- **延后原因**：启发式检测"Python tool 里读子 skill SKILL.md + 绕过框架直接调 LLM + ThreadPoolExecutor"需要对真实业务 skill 扫一遍验证误伤率
- **下一步**：
  1. 明确启发式规则：`script/*.py` 里有 `ThreadPoolExecutor|asyncio.gather` + 读任一 SKILL.md + 调 langchain/openai 直接 import → Warning
  2. 跟 Gemini 先过一轮规则细节再落实
  3. 加 `tests/compiler/test_w_python_glue.py` 覆盖 true positive + false positive
- **估时**：3-4 小时（含 Gemini 设计轮）

#### D-5.4 `<step>` 标签 parser 支持

- [ ] **原 Task**：5.4
- **延后原因**：Step 5 批量做时没展开；是 B 档新事件 `StepTagEnteredEvent`（见二-3 C3）的前置
- **下一步**：
  1. parser.py 允许 `<system_prompt>` / `<user_prompt>` 里嵌 `<step name="..." goal="...">...</step>`
  2. compiler 加基础校验：`name` + `goal` 必填；出现 `when/skip_if/if/else` 等表达式字段直接 FATAL
  3. 不做表达式求值——跟 F006 "framework 不执行业务代码"红线对齐
- **估时**：1 小时

#### D-5.6 bad-samples/ compiler 测试套件

- [ ] **原 Task**：5.6
- **延后原因**：D-5.4 和 D-5.2 的 output 依赖品；需要全部 F-subgraph-exclusive-* 都能通过反模式样本验证
- **下一步**：
  1. 在 `skills/examples/bad-samples/` 下建 3 个样本：一个 subgraph+tools、一个 subgraph+system_prompt、一个 subgraph+sub_skills
  2. 如果 D-5.4 也做完，再加一个含非法 `<step when=...>` 的样本
  3. 新建 `tests/compiler/test_bad_samples.py` 断言每个样本产出预期的 FATAL rule_id
- **估时**：1-2 小时

---

### Step 6 — Model Override 扩展（3 项）

#### D-6.2 llm_roles.yaml schema 扩展

- [ ] **原 Task**：6.2
- **下一步**：加三段：
  ```yaml
  peer_model_groups:
    coding: [DeepSeek_Coder, DeepSeek_Chat]
  circuit_breaker:
    error_threshold: 30
    window_seconds: 1800
    per_provider: {}
  single_model_roles: []
  ```
  对应扩 `RoleConfigData` dataclass + YAML parser
- **估时**：30 分钟

#### D-6.3 ModelResolver peer fallback + LLMFallbackEvent

- [ ] **原 Task**：6.3
- **依赖**：D-6.2 必须先做
- **下一步**：
  1. `resolve()` 里，主 role chain 全炸之后查 `peer_model_groups`，切同级 peer 代号再试
  2. 每次跨模型 fallback 成功/失败都 emit `LLMFallbackEvent`（事件类已在 `events.py`）
  3. 全部失败时抛 `FallbackExhaustedError`
- **估时**：1-2 小时

#### D-6.4 熔断阈值参数化

- [ ] **原 Task**：6.4
- **依赖**：D-6.2 必须先做
- **下一步**：`_is_provider_down` / `_mark_provider_down` 里硬编的 `30min/30` 改读 `get_role_config().circuit_breaker`，支持 per-provider 覆盖
- **估时**：30 分钟

---

### Step 7 — Harness 拆分 + 包化（7 项，整体一个专项）

#### D-7.0 RunContext dataclass（渗透式引入）

- [ ] **原 Task**：7.0
- **Gemini 设计**（上一轮已审）：
  ```python
  @dataclass(frozen=True)
  class RunContext:
      thread_id: str
      trace_dir: Path | None
      runtime_inputs: dict[str, Any]
      storage_manager: Any | None
      artifact_saver: Callable | None
      callbacks: list[Any]
  ```
- **策略**：不等 D-7.1 起的拆分，**在 D-6.3 / D-10 / D-Trace 的实施里就用上这个 dataclass**，让它"渗透式"替换当前 `self._runtime_local.options` 字典
- **估时**：1 小时（加完结构后，后续使用它的 PR 再慢慢替换）

#### D-7.1 - D-7.4 Harness 拆 4 合作者

- [ ] **原 Task**：7.1/7.2/7.3/7.4
- **依赖**：D-7.0 必须先进；最好在 D-Golden-Baseline（见四）录好快照之后再拆
- **下一步**：
  - 7.1 GraphBuilder 抽 `_build_graph()`
  - 7.2 PhaseExecutor 抽 `_build_phase_node` / `_build_code_only_node` / `_build_subgraph_node`
  - 7.3 RetryRouter 抽 `_should_retry` + routing
  - 7.4 NudgeInjector 抽 planning/selfcheck/standard nudge
- **估时**：1-2 天，独立分支 `refactor/harness-split`

#### D-7.5 全量回归

- [ ] **原 Task**：7.5
- **依赖**：D-Golden-Baseline（见四）必须先录好；D-7.1-7.4 完成后
- **下一步**：用 `scripts/snapshot_diff.py` 对比拆分前后的 `tracing.jsonl` 字节级一致性（timestamp + UUID 归一化后）
- **估时**：半天（含修回归问题）

#### D-7.6 packages/graph-agent/ 物理重组

- [ ] **原 Task**：7.6
- **依赖**：D-7.5 全绿后
- **下一步**：
  1. `git mv src/core/graph_agent/ packages/graph-agent/src/graph_agent/`
  2. 新建 `packages/graph-agent/pyproject.toml`（version、依赖、hatchling build）
  3. 所有 `from src.core.graph_agent` → `from graph_agent` 替换
  4. `src/core/graph_agent/__init__.py` 留 re-export shim 两版本
- **估时**：2-3 小时

---

### Step 8 — Story-deconstruction 样板（2 项）

#### D-8.1 老版 story-deconstruction 移到 bad-samples/

- [ ] **原 Task**：8.1
- **阻塞**：宿主项目 story_forge 还依赖 `skills/story-deconstruction/` 路径
- **下一步**：**先跟 host 项目沟通**是否已切到 `skills/examples/subgraph-sample/story-deconstruction/`；确认后 `git mv skills/story-deconstruction skills/examples/bad-samples/story-deconstruction-python-glue`
- **估时**：迁移本身 10 分钟，取决于 host 项目进度

#### D-8.3 subgraph 样板端到端跑

- [ ] **原 Task**：8.3
- **解锁状态**：✅ 测试数据已就位（`skills/story-deconstruction/data/e2e_test_input.json` 含 25 章）+ 本地 langchain/langgraph 装好
- **下一步**：
  1. 装真 API key：`source /home/sevenx/.env`
  2. 跑 `run_skill("skills/examples/subgraph-sample/story-deconstruction/SKILL.md", **test_input)`
  3. 验证 4 个子 skill 按序执行 + `tracing.jsonl` 里每个子 skill 的事件完整 + 每个事件带 `sub_run_id`/`group_key` + StorageManager 把 `story_framework` 落到 `runs/<run_id>/` 下
- **估时**：2-3 小时（含可能遇到的 bug 修复）

---

### Step 9 — 多模态 + 文档（1 项）

#### D-9.1 多模态工具 happy-path 单测

- [ ] **原 Task**：9.1
- **下一步**：`tests/graph_agent/tools/test_multimodal.py` — 三个函数各一个 test：mock HTTP client + 验证参数拼装 + 验证响应解析
- **估时**：30 分钟

---

## 二、本次会话新发现的 Trace 埋点缺口

原 spec 没覆盖 trace 完整性的细节审计。本次按"trace 是事后分析单一真源"原则做了一次全扫，分三档：

### 二-1 A 档 — 现有事件 payload 不完整（**P0，必须补**）

#### T-A1 WorkingMemoryUpdateEvent 缺内容

- [ ] 当前只存 `content_length`（字符数），应存完整的 working memory 文本
- **改动点**：`events.py` 加字段 `content: str`；`tracing.py` 和 harness.py:728/731/816/820 所有 emit 点补全参数
- **估时**：30 分钟

#### T-A2 CompactionEvent 缺被压缩内容（Gemini 给了方案）

- [ ] 当前只存 `removed_pairs`；Gemini 反对"一行塞 250KB"，提出**外链模式**
- **Gemini 实现细节**（Q3 决议）：
  - 事件字段：`removed_summary`（摘要）+ `content_ref`（相对路径）
  - 外链文件路径：**通过 StorageManager 管理**（自动享受 retention 策略）
  - 文件命名：`compaction_<idx>.json`，**idx 是全局递增**（而非 per-phase）——实现最简单，引用时无需感知 phase
  - run 目录：用 **`run_id` (harness uuid4.hex[:12])** 做隔离
- **估时**：1 小时（事件字段扩展 + 外链存储逻辑）

#### T-A3 PhaseEndEvent.context 非 JSON 对象序列化

- [ ] 当前直接 `model_dump_json` 可能把 BaseMessage / Pydantic 实例 / Path 序列化成 `str(obj)` 丢结构
- **Gemini 最终类型表**（Q4 决议）：
  - `BaseMessage` → `{"_type": "BaseMessage", "role": ..., "content": ...}`
  - `BaseModel` → `obj.model_dump()`
  - `Path` → `str(path)`
  - `datetime` → ISO8601
  - **`UUID`** → `str(uuid)`
  - **`Decimal`** → `str(decimal)`（保留精度）
  - **`set` / `frozenset`** → `list(sorted)`（JSON 不支持 set）
  - 未知对象兜底：`{"_repr": repr(obj), "_warning": "unsupported_type"}`（明确标识降级 + 保留文本形式）
- **改动点**：新建 `callbacks/serialize.py` 放 `to_jsonable_dict()`；所有 emit context 的 event（PhaseStart/PhaseEnd/RunStarted/RunEnded）通过这个 helper
- **估时**：1 小时

#### T-A4 LLMCallEvent.response_data 经常为 None

- [ ] 当前 `response_data` 是可选字段但上游没填。应改为必填 / default-dict 装 usage / stop_reason / model_name
- **改动点**：`callback_bridge.py` 的 LLMCall emit 处从 langchain response 提取元信息填入
- **估时**：45 分钟

### 二-2 B 档 — 完全缺失的事件（**P1，Studio MVP 需要**）

#### T-B1 RunStarted/RunEnded
- [ ] harness.run() 边界。区分 fresh vs resume
- **Gemini 决议**（Q5）：**全量保存** `initial_context` / `final_context`（已通过 T-A3 的 `to_jsonable_dict` 归一化）。理由：context 是任务执行唯一真源，磁盘成本 < 事后无法对齐的风险
- 字段：`run_id` / `thread_id` / `is_resume: bool` / `initial_context` (全量) / `final_context` (全量, 仅 RunEnded)
- **估时**：30 分钟

#### T-B2 ModelResolvedEvent
- [ ] resolver.resolve 返回后。记 tier / role_name / resolved_model_code / thinking_enabled / model_override / fallback_chain
- **估时**：30 分钟

#### T-B3 ToolsBoundEvent（**Gemini: 可选**）
- [ ] create_agent 之前。记 tools: list[str] 该 phase 绑定的工具名
- **Gemini 评**：可选，信息可从 ToolCall 事件反推。降到 P2
- **估时**：15 分钟

#### T-B4 AgentLoopIterationEvent（Gemini: 必须）
- [ ] DeerFlow agent 每次 before_model 前。加 iteration 号到 LLMCall/ToolCall
- **估时**：1 小时（需钩 DeerFlow 中间件）

#### T-B5 ValidationPassEvent（Gemini: 必须）
- [ ] validator 返回 (True, []) 时。跟 ValidationFail 对称
- **估时**：15 分钟

#### ~~T-B6 CheckpointWrittenEvent~~（**Gemini: 不要加**）
- ~~LangGraph 写 checkpoint 时~~
- **Gemini 评**："太碎、太底层，对业务分析和 Studio 渲染无实际意义"。**决定不做**。如果真需要 checkpoint 可观测性，交给 LangGraph 自己的 logging。

#### T-B7 ThreadCleanedUpEvent（**Gemini: 可选**）
- [ ] D-2.8 `delete_thread` 调用前。记 thread_id / checkpoint_count_at_cleanup
- **Gemini 评**：只是运维信号，不是业务事件。降到 P2
- **估时**：15 分钟（D-2.8 一起做）

#### T-B8 Subgraph Boundary enter/exit
- [ ] 父 harness 跑子 skill 前后。让 Studio 能按 subgraph 折叠 timeline
- **Gemini 决议**（Q6）：**子 skill 的所有事件合并写到父 tracing.jsonl**（单文件结构让 Studio 渲染统一时间轴，避免多文件句柄带来的 timestamp 对齐难题）
- 子 skill 的 harness 需要接收父的 `trace_dir` 做 append 模式；enter/exit 事件标记边界
- **估时**：30 分钟

#### T-B9 ParallelMapGroup start/end
- [ ] `builtin/parallel_map.py` fan-out 前后。显式的 group 边界标记
- **Gemini 决议**（Q7）：**全部合并到父 tracing.jsonl，以 group_key 做逻辑分类**（Studio 通过 group_key 可在 UI 上折叠/展开并发组；保证单次会话事件顺序性）
- **估时**：15 分钟

#### T-B10 ArtifactSavedEvent
- [ ] StorageManager.save_artifact / IOManager fallback 保存后。记 path / bytes / phase / name
- **估时**：15 分钟

#### T-B11 Interrupted/Resumed
- [ ] harness.resume 入口 + interrupt 触发时。HITL 场景核心
- **估时**：45 分钟（涉及 DeerFlow 中间件 wrap）

#### T-B12 RetryExhaustedEvent（Gemini: 必须）
- [ ] `current_retries >= max_retries` 时。跟 Retry 对称，标记强制降级那一刻
- **估时**：15 分钟

#### T-B13 HeartbeatEvent（Gemini 补充 — 必须）
- [ ] 长耗时任务（视频生成、大长篇）需要心跳包，防止 Studio 前端因 WebSocket 长时间无消息误判任务挂掉
- **Gemini 设计**（Q1 决议）：
  - 频率：**30 秒**（平衡 UI 存活反馈与日志冗余）
  - 触发：**asyncio 后台任务**在 harness.run() 启动时拉起；不在 middleware（主 loop 被同步工具阻塞时心跳仍然要有）
  - Payload：`current_phase` + `elapsed_seconds` + **`memory_usage_mb`**（内存膨胀比 phase 停滞更隐蔽致命）
- **估时**：45 分钟

#### T-B14 InternalErrorEvent（Gemini 补充 — 必须）
- [ ] 捕获非业务逻辑的 Python 异常（OOM / NetworkTimeout / 未预期的框架层错误）。区分"任务业务失败"和"引擎崩溃"两种语义
- **Gemini 设计**（Q2 决议）：**三个入口点各加独立 try/except**
  - `harness.run()`
  - `harness.resume()`
  - `subgraph.run()`（嵌套子图崩溃不能让父图"死得不明不白"）
  在每个入口的 outermost try/except 里捕获 `Exception`，emit 后 re-raise
- **估时**：30 分钟（因为三处而非一处）

### 二-3 C 档 — 可选增强（**P2，Studio 特殊需求再加**）

- [ ] T-C1 ContextMappingResolvedEvent — debug `{input.xxx}` 没填上
- [ ] T-C2 SubSkillToolCalledEvent — 区别于普通 tool_call
- [ ] T-C3 StepTagEnteredEvent — 依赖 D-5.4

---

## 三、本次会话新发现的基础设施缺口

#### I-1 HITL 状态同步 API (`get_thread_status`)

- [ ] **来源**：Gemini 上一轮审阅指出这是 Studio 下一个卡点
- **设计已定**（Gemini 给出具体代码）：
  ```python
  def get_thread_status(self, thread_id) -> {"status": "AWAITING_INPUT"|"COMPLETED"|"RUNNING"|"NOT_FOUND"|"CRASHED", "clarification": {question, clarification_type, options}}
  ```
  挂在 `GraphAgentHarness` 实例方法，读 checkpointer state 反查 interrupt 信号
- **估时**：1 小时

#### I-2 snapshot_diff.py 黄金数据对比脚本

- [ ] **来源**：Gemini 建议，作为 Step 7 拆分的 regression 安全网
- **设计已定**（Gemini 给了归一化逻辑）：
  - 剥掉 `timestamp` 字段
  - UUID 类（`sub_run_id` / `group_key` / `tool_call_id`）转顺序占位符 `uuid_1`, `uuid_2`, ...
  - 位置 `scripts/snapshot_diff.py`
- **估时**：1 小时

#### I-3 Golden baseline 录制

- [ ] **依赖**：I-2 必须先做
- **Gemini 选定的 3 个 skill**（覆盖 Linear / Loop / Concurrent 拓扑）：
  1. `text-segmentation`（线性多 phase）
  2. `batch-analysis`（Agent Loop + 重试）
  3. `adaptation_v1`（parallel_map 并发）
- **下一步**：用 mock LLM 跑这三个 skill，保存 `tracing.jsonl` + `final_context` 为 `golden/{skill}.json`
- **估时**：1-2 小时（含 mock LLM 设置）

#### I-4 版本锁定 → pyproject.toml

- [ ] **当前状态**：已有 `requirements-dev.txt`（60 行，pip freeze 生成）
- **升级路径**：写一个极简 `pyproject.toml` 主要 deps + `requirements-dev.txt` 作为开发锁定
- **关键约束**（从 DeerFlow 上游考证得出）：
  ```
  langchain>=1.2.3,<1.2.11      # 1.2.11+ 要求 langgraph>=1.1.5，冲突
  langgraph>=1.0.6,<1.0.10       # DeerFlow 明确约束
  langgraph-prebuilt<=1.0.8      # 1.0.9+ 要 ExecutionInfo 但 langgraph 1.0.x 没
  ```
- **估时**：20 分钟

#### I-5 顶层 recap txt 处理

- [ ] `2026-04-08-114030-userssevenxdocumentscodingai-narrated-recap.txt` — 用户 re-added，跟 Task 1.3 删除的同名。需问用户：保留 / 移动 / 删除
- **估时**：1 分钟决策 + 几秒执行

---

## 四、总体优先级（建议执行顺序）

### 第一梯队（本轮必做）— 按 Gemini "骨架优先于肉" 调整

**Gemini Q8 commit 粒度决议**：tier 1 拆 **3 个 commits**（1. 核心生命周期 2. 数据 + Proxy 增强 3. 并发 + 子图边界），适中的粒度兼顾 review 效率和 regression 定位。

1. **I-5** recap txt 归档到 `docs/archive/`（已完成 `b18bdcf`）✅
2. **I-4** 写 pyproject.toml 锁定版本（20 分钟）
3. **D-7.0** RunContext dataclass（1 小时，**Gemini 建议尽早引入，后续所有 emit 点都复用它**）
4. **T-B 档骨架**（Gemini 建议先补骨架，后补肉）：
   - T-B1 RunStarted/RunEnded（30 分钟）
   - T-B2 ModelResolvedEvent（30 分钟）
   - T-B5 ValidationPassEvent（15 分钟）
   - T-B8 SubgraphBoundary（30 分钟）
   - T-B9 ParallelMapGroup（15 分钟）
   - T-B10 ArtifactSavedEvent（15 分钟）
   - T-B12 RetryExhaustedEvent（15 分钟）
   - T-B13 HeartbeatEvent（45 分钟，Gemini 补充）
   - T-B14 InternalErrorEvent（30 分钟，Gemini 补充）
5. **T-A 档肉**（骨架稳定后补详细 payload）：
   - T-A1 WorkingMemoryUpdate 加 content 字段（30 分钟）
   - T-A2 Compaction 加 summary + 外链 artifacts/history/（1 小时）
   - T-A3 PhaseEndEvent.context 通过 `to_jsonable_dict()` 归一（1 小时）
   - T-A4 LLMCallEvent.response_data 填真实 usage（45 分钟）
6. **I-2** snapshot_diff.py 脚本（1 小时）
7. **I-3** 录 golden baseline 3 份——用用户的 test data + .env API key 真跑（1-2 小时）
8. **D-2.8 + T-B7** cleanup_on_finish 收尾（45 分钟）

### 第二梯队（紧接着做）
9. **D-6.2 / D-6.3 / D-6.4** peer_model_groups + 熔断参数化（2-3 小时合计）
10. **T-B4 AgentLoopIterationEvent**（1 小时，需 DeerFlow 中间件钩）
11. **T-B11 Interrupted/Resumed**（45 分钟）
12. **I-1 get_thread_status HITL API**（1 小时）
13. **D-8.3** 用 test data 端到端跑 subgraph 样板（2-3 小时）
14. **T-B3 ToolsBoundEvent**（可选，15 分钟，Gemini 说可从 ToolCall 反推）

### 第三梯队（可以 batch 到一个尾声 commit）
15. **D-5.4** `<step>` 标签 parser（1 小时）
16. **D-5.2** W-python-glue-orchestrator（3-4 小时，含 Gemini 设计）
17. **D-5.6** bad-samples/ 测试套件（1-2 小时，依赖 D-5.4）
18. **D-9.1** 多模态单测（30 分钟）
19. **T-C1-C3** 三个可选增强

### 第四梯队（独立分支，大重构）
20. **D-7.1 ~ D-7.6** Harness 拆分 + 物理重组（2-3 天，独立分支 `refactor/harness-split`）

### 第五梯队（跨项目协调）
21. **D-8.1** 老版 story-deconstruction 移 bad-samples（host 项目迁好再做）

---

## 五、总耗时预估

- 第一梯队: **约 1 天**
- 第二梯队: **约 1 天**
- 第三梯队: **半天**
- 第四梯队: **2-3 天独立分支**
- 第五梯队: 视 host 项目进度

**一到三梯队全部做完约 2.5 天**，此时 graph_agent 的 Studio MVP 支撑能力完整就绪；Step 7 harness 拆分独立推。

---

## 六、Gemini 最终审阅结论（2026-04-23）

**判定：总分 8.5/10，Studio MVP 对接可启动，无结构性 blocker**。

### 6.1 分项评分
- **trace 作为事后分析单一真源**：9/10（扣分：golden baseline 只录了 1/3）
- **declarative composition 替代 Python 胶水码**：8/10（Compiler 规则已全部 landed，规范 + 强制校验双轨）
- **HITL pause/resume 就绪度**：8.5/10

### 6.2 7 个偏离点判定
1. HeartbeatEvent threading 而非 asyncio — **接受**（harness.run 是同步）
2. Golden baseline 只录 1/3 — **需改**（Gemini 怀疑线程池泄漏；实际是 dev 环境 claude/codex/gemini CLI 并存导致宿主线程耗尽，非框架 bug —— 需在干净环境补录）
3. RunContext frozen=True 仅阻 rebind — **待观察**（业务若不主动 mutation 内部 dict，风险可控）
4. Compaction sidecar per-run idx — **接受**
5. ValidationFailEvent str payload 强转 — **接受**（务实兼容）
6. AgentLoopIterationEvent 挂 before_model — **接受**（定位精确，侵入最小）
7. Harness 拆分延后独立分支 — **接受**（没 baseline 覆盖就拆是灾难）

### 6.3 Studio 对接四条军规（前端实施时遵守）
1. **容错解析**：`tracing.jsonl` 中遇到未知 `event_type` 不得崩整条 timeline
2. **心跳超时告警**：收不到 HeartbeatEvent 超 60 秒 → 前端告警 "worker 可能僵死"
3. **大对象懒加载**：RunStartedEvent.initial_context / Compaction 外链 → 不要列表时全渲染
4. **HITL 状态边界**：thread status=`CRASHED` → 不暴露 Resume 按钮

### 6.4 Gemini 指出的新 gap（Q4 遗漏）
**Artifact retention 与 ArtifactSavedEvent 的 staleness 问题**：
- StorageManager 依据 `history_retention` 清理老目录；但 tracing.jsonl 里已发出的 ArtifactSavedEvent 仍持 path
- 历史 run 被清理后，Studio 拿 path 请求会 404
- **责任分配**：Studio 后端返回 trace 时做 `os.path.exists` 校验，不存在的 artifact 前端标注"已归档/清理"不可点
- **引擎侧是否需要改**：暂时不需要；path 的"历史指针"语义是正确的，retention 清理是有意为之；但需要文档里明写这个契约

### 6.5 剩余阻塞项（对 Studio MVP 影响）
- **无结构性 blocker**（Gemini 原话）
- golden baseline 补齐（I-3 剩两个 skill）可与 Studio 对接并行推进
- Harness 拆分（D-7.1-7.4）独立分支，不阻塞对接

---

## 七、2026-04-24 联合审阅：后续问题清单

由 Claude（代码落地质量审计，via Explore agent）+ Gemini（设计层面后续动作审阅）并行审出，本节为下一阶段 action list，按 P0/P1/P2 + backlog 分档。

### 7.1 P0 — 必修项（阻塞 Studio MVP 正式对接或下阶段 refactor）

#### P0-1 Golden baseline 全量覆盖缺失（I-3 补齐）
- **现状**：只录了 `text-segmentation` 56 events，`batch-analysis` / `adaptation_v1` 缺失
- **阻塞**：D-7.1-7.4 harness 拆分没有回归安全网 → 拆了是盲飞
- **根因争议**：Gemini 怀疑 `parallel_map` 线程池未 shutdown，但实际是 dev 环境 claude/codex/gemini CLI 并存耗尽宿主线程 —— **需先 verify**（跑一次 htop 看 python 进程 thread 数）
- **动作**：
  1. 新建干净 shell（退出其他 CLI）或用 docker 隔离
  2. 跑 `batch-analysis` + `adaptation_v1` 各一次，录制 golden
  3. 若仍崩，查 `parallel_map` / DeerFlow subagent executor 线程池 shutdown 路径
- **估时**：2-4 小时

#### P0-2 RunContext 实际未投入使用（D-7.0 半成品）
- **现状**：`harness.py:472` 构造了 `RunContext` 赋值到 `self._active_run_context`，但**代码全局无读取点** → 14 个 tier-1 event 的 emit 仍走老的 `self._runtime_local.options` 字典
- **风险**：D-7.1-7.4 harness 拆分启动时会发现 RunContext 渗透不完整，拆分时还得先补齐
- **动作**：
  1. `harness.py` 所有 emit 点改用 `self._active_run_context.thread_id / trace_dir / runtime_inputs` 读值
  2. 或者：明确声明 RunContext 只是"预留容器"，拆分 PR 里再统一切
- **估时**：2 小时（如果现在做）；否则列入 D-7.1 开工前第一件事
- **责任人建议**：和 D-7.1-7.4 同分支做更自然

### 7.2 P1 — 应尽快修但不阻塞对接

#### P1-1 HeartbeatPulser 生命周期健壮性
- **Gemini 发现**：`HeartbeatPulser` 非 daemon 线程 + `stop()` 仅 flag，Ctrl+C 时解释器可能挂起
- **Claude 补充**：`_safe_memory_usage_mb()` `except Exception: pass` 无日志（违反 logging.md 铁律）
- **动作**：
  1. `threading.Thread(daemon=True)` 确认或改
  2. `harness.run` / `harness.resume` 的 finally 加 `pulser.stop(); pulser.join(timeout=1.0)`
  3. 所有 silent swallow 补 `logger.debug()` 说明降级原因
- **估时**：30 分钟

#### P1-2 Silent swallow 扫盘（logging.md 铁律）
- **Claude 发现**：3 处 `except Exception: pass` 无日志
  - `src/core/graph_agent/core/harness.py:637` — `_safe_memory_usage_mb`
  - `src/core/graph_agent/core/compiler.py:947,965` — `_known_roles` / `_known_models`
  - `src/core/graph_agent/callbacks/serialize.py:81,97` — `to_jsonable_dict` 的 fallback 分支
- **动作**：各加 `logger.debug("<场景> failed: %s, degrading to <fallback>", e)`
- **估时**：20 分钟

#### P1-3 子图 compile-time cycle detection（Gemini D1 变体）
- **现状**：`loader.py:288-290` 有 runtime guard（cyclic 加载时抛 `SkillLoadError`），但 compile-time 未扫 `subgraph:` 字段静态图 → 作者无法在 compile 时提前发现
- **动作**：compiler `_check_structure` 扫所有 `subgraph:` 字段构图，DFS 检测环，抛 `F-subgraph-cycle` FATAL
- **估时**：1 小时
- **注**：优先级低于 P0（因为运行时已有安全网），但对作者体验 valuable

#### P1-4 harness.py 两个巨型函数拆分
- **Claude 发现**：
  - `_build_phase_node()` 502 行（阈值 40）
  - `_build_context_from_io()` 187 行
- **风险**：D-7.1-7.4 harness 拆分的第一步，目前的 monolithic 结构是真正的债
- **动作**：作为 D-7.1-7.4 的前置拆分项目，不单独改
- **估时**：计入 D-7.1-7.4 的 2-3 天整体

#### P1-5 测试覆盖补齐
- **Claude 发现空洞**：
  - `_HeartbeatPulser`（timer / stop 机制）
  - `_save_compaction_sidecar()`（外链写入）
  - `AgentLoopIterationMiddleware`（before_model hook + 计数器）
  - `to_jsonable_dict()` 已有 18 tests 覆盖 ✅
  - `RunContext` 已有 4 tests 覆盖 ✅
  - `get_thread_status` 已有 7 tests 覆盖 ✅
- **动作**：补前三个的单测，每个 1-2 个 happy-path test 即可
- **估时**：1-1.5 小时

### 7.3 P2 — 长期架构债（可进 backlog）

#### P2-1 Harness 拆分（D-7.1-7.4，独立分支）
- 2-3 天 refactor/harness-split 分支
- 前置：P0-1 golden baseline 补齐 + I-2 snapshot_diff 已 landed ✅
- 目标：GraphBuilder / PhaseExecutor / RetryRouter / NudgeInjector 剥离 + RunContext 全链路透传 + 彻底干掉 `threading.local`

#### P2-2 Pydantic event schema 向前兼容策略
- **Gemini 发现**：`schema_version: Literal["1.0"]` 硬编码，未来加字段时 Studio 旧版本 DB 解析会崩
- **动作**：写一份 `docs/event-schema-evolution.md`，规定：
  - 只允许新增 Optional 字段，不升 version
  - Breaking change 必须升 `schema_version` 至 `"1.1"` + Studio 写 migration
- **估时**：30 分钟（纯文档）

#### P2-3 events.py 的 `__future__ import annotations` 省略注释
- **Claude 发现**：故意跳是为了让 Pydantic discriminator 类定义时求值，但维护者看不出来
- **动作**：模块头加 3 行注释说明
- **估时**：5 分钟

### 7.4 P3 — 需验证是否是真问题（Gemini D 档原始盲点）

| 盲点 | 验证结论 | 是否需处理 |
|------|---------|-----------|
| D1 嵌套 subgraph 循环 | `loader.py:288-290` 有 runtime guard，但 compile-time 未检测 | ✅ 真 gap，列入 P1-3 |
| D2 `model_override` 透传到 parallel_map 子 agent | **误判**：parallel_map 故意不透传，子 skill 自己决定 model —— 这是正确的语义隔离 | ❌ 无需处理 |
| D3 HITL resume 导致 checkpointer DB 膨胀 | LangGraph 内部机制（sqlite/postgres backend），不在引擎 scope 内 | ⚠️ 长期监控，不列 action |

### 7.5 Studio 侧责任清单（非引擎代码，但需明确契约）

下列是**引擎层不处理、由 Studio 后端或前端承担**的事项。写在这里以确保对接时不漏：

1. **Artifact retention staleness**（6.4 重复强调）— `/api/traces/{run_id}` 返回时对 `ArtifactSavedEvent.path` 和 `CompactionEvent.content_ref` 做 `os.path.exists` 校验
2. **未知 event_type 容错**— 解析 `tracing.jsonl` 不得因单个未识别事件崩整条 timeline
3. **心跳超时告警**— 60 秒收不到 HeartbeatEvent → UI 标 "worker 可能僵死"
4. **大对象懒加载**— RunStartedEvent.initial_context / Compaction 外链，列表不预渲染
5. **HITL 状态边界**— thread status=`CRASHED` 不暴露 Resume 按钮
6. **W-python-glue-orchestrator 警告透传**— 编排 UI 对含此 Warning 的 Skill 给出"不保证并发安全"提示

### 7.6 总览表（用于看板追踪）

| 优先级 | 项 | 估时 | 阻塞范围 |
|--------|----|------|---------|
| P0 | Golden baseline 2/3 补齐 | 2-4h | harness 拆分 |
| P0 | RunContext 渗透式投入使用 | 2h（或并入 P2-1）| harness 拆分 |
| P1 | HeartbeatPulser daemon + join | 30m | — |
| P1 | Silent swallow 扫盘 | 20m | — |
| P1 | 子图 compile-time cycle | 1h | — |
| P1 | 测试覆盖补齐（3 项）| 1-1.5h | — |
| P2 | Harness 拆分 | 2-3 天（独立分支）| — |
| P2 | Schema evolution 文档 | 30m | Studio 升级 |
| P2 | events.py 注释 | 5m | — |

**P0 + P1 合计约 5-6 小时**；P2 harness 拆分是独立专项。
