# Strict Compile Rules v2（v3 范式 + IO 对齐）

> 作者：Claude
> 日期：2026-04-28
> 状态：post-Gemini-review（已吸收 2026-04-28 Gemini 独立审视的 6 节反馈）
> 目标：把 PR-1~7 在 text-segmentation v3 上验证过的范式转化为 framework 强制规则，确保所有 SKILL 在 compile 期把输入输出对齐，杜绝 e2e 时再撞接口契约不一致。

## 0. 修订记录（与 Gemini 审视的对照）

| Gemini 反馈点 | 是否采纳 | 落地形式 |
|---|---|---|
| 遗漏 unattended 模式与交互工具静态互斥 | 是 | 新增 W-UNATTENDED-WITH-CLARIFICATION-TOOL |
| 遗漏 hoist_to 与 finish_task payload 字段名一致性 | 是 | 新增 F-FINISH-TASK-PAYLOAD-NAME-MISMATCH |
| F-IO-INPUT-NOT-CONNECTED 过严，应降级 W | 是 | 改为 W-IO-INPUT-NOT-CONNECTED |
| F-LLM-PHASE-NO-OUTPUT-CHANNEL 误伤 router phase | 是 | LLMPhase 新增字段 `is_router: bool = False` 豁免 |
| 跨域 #7 用 Markdown 严格 type 校验风险高误报 | 是 | 降维为 W-PIPELINE-FIELD-COVERAGE，仅做"字段 key 存在性"浅层比对；Pydantic 严格化作为 follow-up |
| IO 标准缺空值语义/兜底路由 | 是 | IoInput/IoOutput 新增 `allow_empty` / `default` / `on_empty` 字段 + W-IO-FIELD-MISSING-EMPTY-POLICY |
| 终态用 Pydantic shared schemas + pipeline.yaml | 部分 | 列入 follow-up，本 PR 沿用 Markdown DSL 过渡方案 |
| 实施顺序：内部基建 → 自我声明 → 闭环溯源 → 跨域 | 是 | Step A 按此顺序实现 |

---

## 1. 背景：为什么需要 v2

PR-1~7 在 text-segmentation v3 上跑通了一套范式（退出契约 + Schema-by-Example + Output Hoisting + 业务 Validator + 极简 agent_tools）。但其他 5 个业务 SKILL（event-extraction / batch-analysis / global-synthesis / story-deconstruction / adaptation_v1）都还停在 v0 老范式：

- 仍用 `store_*` / `safe_*` / `backup_*` 工具流落盘业务数据，而不是 v3 的 `finish_task(business_data_md=…)` + ValidationMiddleware 自动 hoist
- prompt 没有"⚠️ 退出契约"块，导致 LLM 反复 parse 0 events 后撞 LangGraph recursion 上限
- 上下游 SKILL 接口契约靠口头约定，没有显式 schema：text-segmentation 输出 `[{index, type, content, start_line, end_line, …}]`，下游 event-extraction 直接 `segmentation.get('paragraphs', [])` 假定结构，运行时就拿到 `0 paragraphs` 卡死
- io.outputs 没有 schema/example，compiler 无法做静态对齐校验

e2e chain 测试的两轮失败（aggregate 撞 recursion / setup 拿不到 paragraphs）都是上述问题的直接表现，全部应当在 compile 期就被拦截。

---

## 2. v3 范式（PR-1~7 验证）核心 6 条

每条都对应一个 strict rule。

| # | 范式 | 来源 PR | 当前 rule | 升级目标 |
|---|---|---|---|---|
| 1 | **退出契约头部块**：`## ⚠️ 退出契约（最高优先级）` 出现在 phase prompt 顶部，明示 finish_task 必填字段 + 调用顺序 | PR-7 | W-FINISH-TASK-VISIBILITY (warn) | **F-FINISH-TASK-CONTRACT-MISSING (FATAL)** |
| 2 | **Schema-by-Example**：LLM phase 用 `output_example: \|` 块声明数据形态（替代 Python class） | PR-4 | 无 | **F-OUTPUT-EXAMPLE-MISSING-WHEN-HOISTING (FATAL)** |
| 3 | **Output Hoisting**：phase 用 `hoist_to: <key>` 让 finish_task 自动写入 ctx | PR-2 | 无 | **F-LLM-PHASE-NO-OUTPUT-CHANNEL (FATAL)** |
| 4 | **业务 Validator**：复杂 schema 必须配 `validator: <fn>` | PR-6 | F-VALIDATOR-MISSING-FOR-COMPLEX-SCHEMA + W-VALIDATOR-MISSING | 维持现状 |
| 5 | **极简 agent_tools**：禁止 `store_*` / `safe_*_store_*` / `backup_*` 这种"老式落盘工具"，统一走 finish_task hoist | PR-1 | 无 | **W-LEGACY-DATA-PIPING-TOOL (WARNING)**，提供迁移指引；下个版本升级 FATAL |
| 6 | **References 显式声明**：`references: [...]` 而不是用 base_dir 隐式查 | PR-2 | F-tool-path-not-found | 维持现状 |

## 3. IO 对齐规则（v2 新增）

用户最强调的部分：**SKILL 必须写 io 标准；compile 前把输入输出对齐**。

### 3.1 SKILL 内 io.outputs schema 强制声明

每个 GraphSkillDef 的 `io.outputs` 字段必须满足：

```yaml
io:
  outputs:
    - name: <key>          # 必填
      type: <python-type>  # 必填
      target: file | artifact | runtime  # 必填
      path: "..."          # target=file 时必填
      schema_ref: phases.<phase_name>.output_example   # 与 phase output_example 互引（推荐）
      # 或者
      example: |                                       # 直接 inline
        <output_example name="...">
        ## <key>
        - field (type, required): description
        ...
        </output_example>
```

新规则：

- **F-IO-OUTPUT-NO-SCHEMA**（FATAL）：`io.outputs[*]` 没有 `schema_ref` 也没有 `example`
- **F-IO-OUTPUT-SCHEMA-REF-DANGLING**（FATAL）：`schema_ref` 指向不存在的 `phases.X.output_example`

### 3.2 SKILL 内 io.inputs schema 强制声明

每个 GraphSkillDef 的 `io.inputs` 字段必须满足：

```yaml
io:
  inputs:
    - name: <key>
      type: <python-type>      # 必填
      source: runtime          # 必填
      schema_ref: <namespace>.<skill_name>.outputs.<key>   # 跨 SKILL 引用上游 output
      # 或者
      example: |
        <output_example name="...">
        ...
        </output_example>
```

新规则：

- **F-IO-INPUT-NO-SCHEMA**（FATAL）：`io.inputs[*]` 没有 `schema_ref` 也没有 `example`（runtime 输入需要 schema 才能在 compile 期校验）

### 3.3 跨 SKILL pipeline 对齐校验

当某个 SKILL 的 `io.inputs[*].schema_ref` 指向另一个 SKILL 的 outputs 时，compiler 必须：

1. 解析两端的 `output_example`（PR-4 的 `parse_output_example` 已实现）
2. 比对字段集（必填字段必须全有；可选字段可缺）
3. 比对类型（int/str/list/dict 等基础类型必须一致）

新规则：

- **F-PIPELINE-CONTRACT-MISMATCH**（FATAL）：上游 output schema 缺失下游 input 必填字段，或字段类型不一致

> 实现注：这是**单向静态溯源**，不强制 compiler 知道全局 pipeline 拓扑——只要下游 SKILL 主动声明 `schema_ref` 指向上游路径，compiler 就能逐对验证。

### 3.4 io.inputs 对应 ctx 来源闭环

当前 `check_template_variables`（PR-5）已经做"模板变量必须有上游 producer"的静态校验，但只覆盖 `user_prompt_template` 引用的 `{var}`。新规则扩展：

- **F-IO-INPUT-NOT-CONNECTED**（FATAL）：`io.inputs[*].name` 不出现在 `context_mapping` 任何赋值表达式中（说明根本没接到 ctx，纯死字段）

---

## 4. 派生规则细节

### 4.1 F-FINISH-TASK-CONTRACT-MISSING（升级 W-FINISH-TASK-VISIBILITY）

判定条件（同时满足）：

1. phase 是 LLMPhase（mode: llm）
2. phase.prompt 不含字符串 `## ⚠️ 退出契约` 或 `# ⚠️ 退出契约` 或等价标记（如 `## EXIT CONTRACT`）
3. 且 prompt 长度 > 200 字符（短 prompt 不强求）

### 4.2 F-OUTPUT-EXAMPLE-MISSING-WHEN-HOISTING

判定条件：

1. phase 有 `hoist_to: <key>` 字段
2. 但 phase 没有 `output_example` 块

### 4.3 F-LLM-PHASE-NO-OUTPUT-CHANNEL

判定条件：

1. phase mode = llm
2. 既没有 `hoist_to`，也没有 `output_schema`，也没有 `agent_tools` 中包含明显的"落盘工具"（heuristic：name 含 `store` / `save` / `write`）

含义：LLM phase 必须有明确的输出通道，否则其计算结果无处可去。

### 4.4 W-LEGACY-DATA-PIPING-TOOL

判定条件：

1. phase 的 `agent_tools` 里出现了 `store_*` / `safe_*_store_*` / `backup_*` / `finalize_*` 这种命名
2. 同时 phase 没有 `hoist_to`

含义：建议迁移到 v3 范式，让 finish_task + ValidationMiddleware 接管落盘。

---

## 5. 实施分两步

### Step A：实现新规则 + 不强制升级 FATAL

只实现 detection + 列出来，全部走 WARNING。让所有 SKILL 编译完看到一份完整违规清单。

### Step B：分批升级 FATAL + 用 Gemini 系统迁移

按 SKILL 一个一个迁移：

1. event-extraction（最近正在解的 chain bug，最高优先）
2. batch-analysis（多 phase 复杂）
3. global-synthesis（中等复杂）
4. story-deconstruction（要同步把 E-NESTED-RUN-SKILL 重写成 delegate）

每个 SKILL 迁移：

- Claude：跑新 compiler 列出违规
- Gemini：基于违规清单 + v3 范式 + io 对齐设计稿，重写 SKILL.md
- Claude：跑新 compiler 验证零 FATAL/WARN
- Claude：跑 chain e2e 一段验证运行时通

---

## 6. 与现有 cohesion 规则的关系

cohesion plan 2026-04-26（commit 5f60862）已经有：

- `_check_phase_names_unique` — phase 名唯一性
- `_check_retry_targets_resolve` — retry_target 引用闭环
- `check_persona_resolution` — adopted_persona 解析
- `check_tool_paths` — agent_tools/validator/execute_steps dot-path 解析
- `check_context_bridge` — DelegatePhase 父子 IO 类型校验
- `check_subgraph_cycles` — Delegate 链路无环
- `check_template_variables`（PR-5）— `{var}` 模板变量上游 producer
- `check_validator_required`（PR-6）— 复杂 schema 必须有 validator
- `check_prompt_quality` — prompt 重复/finish_task 可见性/setup phase 反模式

v2 增加的是：**phase 输出契约 + io 字段 schema + 跨 SKILL pipeline 对齐**。两套规则不冲突。

---

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 升级 FATAL 后所有老 SKILL 立刻不能编译 → 框架瘫痪 | Step A 全部 WARN，先暴露问题；Step B 一个 SKILL 一个 SKILL 迁移完再升级对应 rule 到 FATAL |
| schema_ref 跨 SKILL 引用解析复杂 | 第一版只解析 `<skill_name>.outputs.<key>` 同 repo 内的引用；不支持远程 SKILL |
| `output_example` 解析失败导致 false positive | 已有 `parse_output_example`（PR-4）成熟逻辑，新规则复用即可 |
| W-FINISH-TASK 的"# ⚠️ 退出契约" 标记字符串硬编码不灵活 | 暴露常量 `EXIT_CONTRACT_MARKERS = [...]` 可配置 |

---

## 8. 验收标准

- 7 个活跃 SKILL（除 archive 外）全部 0 FATAL 0 WARNING
- chain e2e（text-seg → event-extr → batch-anal → global-syn）能在 1 章上跑通，每段输出符合 io.outputs 声明
- pytest ≥ 643（baseline）+ 新规则单测 ≥ 8 个

