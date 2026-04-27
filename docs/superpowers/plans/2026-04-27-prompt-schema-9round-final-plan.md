# Prompt Schema 重构 + Cohesion 修复最终架构案（9 轮辩论收敛）

**日期**：2026-04-27
**驱动**：产品 owner SevenX 与 Gemini 经过 9 轮结构化辩论达成的最终架构案
**主控**：Claude（项目经理 + 监工）
**方案设计**：Gemini（按 ccb-collaboration.md 4.4 任务分发模式主导）
**审查者**：SevenX（每轮反驳引导收敛）
**实施**：Codex（按 ccb-collaboration.md 角色铁律：编码专职）

---

## 一、9 轮辩论摘要（持久化记忆）

### Round 1: 初版规划
Gemini 提议把 `LLMPhase.steps` 改名 `workflow`、把内层 markdown 全面重构为 XML、提供 `producer/review` 的 bypass 模式。

### Round 2: SevenX 反驳命名 + XML 嵌套权重
**SevenX 反驳**：
- 拒绝 `workflow` 命名——Graph 层已占用 workflow 语义（pipeline 严格执行），LLMPhase 内层 step 是 LLM plan 柔性参考，**两种语义截然不同**
- 拒绝"嵌套 markdown 在 XML 框架里权重被冲淡"的判断——deerflow 自己有 progressive disclosure，agent-harness 也有 cognitive template 的 `<skill_section>` 嵌套机制

**Gemini 承认两点错判**：完全推翻 round 1 的 workflow 命名 + markdown→XML 重构建议。

### Round 3: SevenX 反驳"维持现状" + "向后兼容" + 漏调查
**SevenX 反驳**：
- 嵌套 XML 不仅"不丢权重"，更是"加强权重"——是另一个维度的论点
- compiler 的核心意义是把组织松散的 prompt 标准化结构化，**不要向后兼容 producer/review**
- Round 2 漏调查 deerflow 的具体 prompt 注入模式 + 渐进式披露模式

**Gemini 完全采纳**：拥抱嵌套 XML 重构 + 强制 producer/review 迁移到 schema + 给出具象推演。

### Round 4: SevenX 截图质问"丢弃 deerflow prompt 框架?"
Gemini 澄清是节选排版误会——**外层 cognitive 标签全部保留，只是把内层 markdown 升级为嵌套 XML**。

### Round 5: SevenX 4 个尖锐质问
**SevenX 质问**：
1. Role 为什么要重复（外层 `<role>` + 内层又一个 `<role>`）
2. `<protocol_citation>` 跟 `<rules>` 是不是语义重复
3. 为什么 round 3 又用 `<workflow>` 标签（违背 round 2 承诺）
4. "要适应他的 prompt 模板，现在是什么鬼"——内层标签必须协调外层 cognitive schema

**Gemini 真诚承认两个失误**：违背 step 承诺 + 闭门造车不研读 cognitive template。给出**最终内层 5 标签锁钥设计**：
- `<domain_expertise>`（不撞外层 `<role>`）
- `<task_objective>`
- `<domain_protocols>`（**锁钥对接外层 `<protocol_citation>`**）
- `<steps>`（兑现 round 2 命名承诺）

### Round 6: SevenX 4 个新质问
**质问**：
1. phase 输出格式注入在哪里
2. review-and-retry 机制放哪
3. 并发 subskill 的 schema
4. 上下文污染 deerflow 没设计吗

**Gemini 4 个颠覆性发现**：
1. **agent-harness 完全绕过 deerflow `make_lead_agent` + 13 个 middleware**——直接调 `langchain.agents.create_agent`
2. **MemoryMiddleware 即使挂了也不解决 phase 内污染**（只异步存长效记忆）
3. **`output_schema` 是虚假契约**——loader 没注入 system prompt
4. **`<protocol_citation>` 是虚空设计**——cognitive 强制要求引用 protocol 但系统没提供协议库

**新增**：内层标签 `<output_format>`、新 phase mode `parallel_delegate`、确认 retry 走 user message 注入不需要新加 prompt 标签。

### Round 7: SevenX 让 Gemini 系统深挖更多颠覆性发现
**Gemini 9 个发现**（3 颠覆性 + 2 严重 + 3 中度 + 1 轻微）：
1. 🔴 绕过 deerflow Middleware → token 爆炸 + 死循环
2. 🔴 跨 phase 历史清空 + 微薄 working_memory 张力 → 业务上下文断裂
3. 🔴 并发机制缺失 → fake concurrency
4. 🟠 `<protocol_citation>` + `output_schema` 双虚假契约
5. 🟠 `ask_clarification` 逃生舱缺失
6. 🟡 `ToolErrorHandling` 重复造轮子
7. 🟡 `finish_task` 弱类型自检形同虚设
8. 🟡 `few_shot_examples` NotImplemented 陷阱
9. 🟢 业务侧 vs schema 侧 LogicPhase Retry 认知脱节

### Round 8: SevenX 3 个设计 input + 整体审查
**SevenX 定调**：
1. examples + references 都需要，语义功能不同
2. finish_task + 诊断 + md_to_json 物理熔接（LLM 输出 markdown，脚本转 JSON）
3. phase 间默认强隔离（`messages = []` by-design）+ 按需挖掘机制（context_access opt-in）

**Gemini 给完整设计哲学（5 条）+ 完整 schema 蓝图 + 完整 prompt 渲染蓝图 + P0/P1/P2 修复路径表 + 2 个开放问题**。

### Round 9: SevenX 补充 LLM 字段
**SevenX 补充**：phase 还有一个 LLM 字段——指定 agent loop 用哪个 LLM 模型，可缺省（沿用全局），可单独设置（应用不同 role），跟 config 配合。

**Gemini 给出**：
- 现状诊断：当前 schema 的 `tier: Literal["premium", "balanced", "fast"]` 只有 3 个值，但 config/llm_roles.yaml 的 `roles:` 实际有 13 个角色——**Schema 封闭性 vs Config 开放性的 gap**
- 重设计：新增 `llm_role: str` + 保留 `model_override: str`（工程逃生舱）
- 字段类型 `str`（不用 Literal），通过 Pydantic model_validator 在 compile 期动态加载 yaml 校验
- 跟 cognitive `<role_prefix>` 自动协调：PM 写 `llm_role: architect` → loader 自动抓 config 里 `system_prompt_prefix` 注入 `<role_prefix>` 标签

---

## 二、5 条设计哲学（Round 8 §A 收敛）

1. **Schema 驱动一切**：PM 不写 XML，只配 YAML。所有 prompt XML 标签和结构化都由 Compiler 统一生成，实现行为高可预测性
2. **严丝合缝的 Artifact 对接**：Phase 间默认彻底隔离记忆（`messages = []`）。依赖明确声明的 IoInput/IoOutput 传递核心数据
3. **输出即校验（Output as Validation）**：LLM 用 markdown 输出 → 框架在 finish_task 关口用 Pydantic 强校验并转 JSON → 不合规直接驳回 → LLM 修后重试
4. **渐进式披露 + 主动挖掘**：巨大知识（references）+ 前序上下文不塞 prompt → 给 LLM 发 `read_file` / `read_artifact` 工具按需拉取
5. **敬畏底层框架**：绝不绕过 deerflow 核心 middleware（压缩、防循环），发挥其最大威力

---

## 三、完整 LLMPhase Schema 蓝图（Round 8 §B + Round 9 LLM 字段）

### LLMPhase 字段表

| 字段 | 类型 | 优先级 | 缺省 | 含义 | 注入位置 |
|---|---|---|---|---|---|
| `name` | str | P0 已有 | - | Phase 名 | 框架使用 |
| `prompt` | str | P0 已有 | None | 业务逻辑说明 | → `<domain_expertise>` |
| `agent_tools` | list[str] | P0 已有 | [] | 业务工具列表 | LLM 可调用 |
| `steps` | list[str] | P0 已有（PR #9） | [] | 柔性计划参考 | → `<steps>` |
| **`domain_protocols`** | list[str] | **P0 新增** | [] | 业务规则库（编号 [P1][P2]）| → `<domain_protocols>` 锁钥对接外层 `<protocol_citation>` |
| `output_schema` | str | P0 已有但**未 wire** | None | Pydantic 模型路径 | → `<output_format>` + finish_task 后台校验 |
| **`few_shot_examples`** | list[str] | **P1 新增** | [] | 内联 markdown 样例 | → `<examples>` |
| **`references`** | list[str] | **P1 新增** | [] | references/ 目录文件路径列表 | → `<knowledge_base>` + 自动挂 `read_file` 工具 |
| **`context_access`** | list[Literal["artifact","working_memory"]] | **P2 新增** | [] | 主动挖掘权限 opt-in | → `<context_access>` + 自动挂 `read_artifact` / `query_working_memory` 工具 |
| **`llm_role`** | str | **P0 重设计** | None（→ deerflow_default）| 指定逻辑角色（来自 config/llm_roles.yaml） | 决定 model 链 + temperature + 自动注入外层 `<role_prefix>` |
| `model_override` | str | P1 已有 | None | 强制锁定具体模型代号 | 逃生舱：覆盖 llm_role 关联的 active_model |
| `dead_end_threshold` | int | P0 已有 | None | DeadEndPruning 阈值 | middleware |
| `retry_target` | str | P0 已有 | None | Graph 层 retry 跳转目标 | validator 失败时跳 |
| `max_iterations` | int | P0 已有 | None | agent loop 最大轮数 | middleware |
| `max_retries` | int | P0 已有 | None | 最大重试次数 | retry routing |
| `max_nudges` | int | P0 已有 | None | nudge 上限 | (待验证 wire) |
| `subagent_enabled` | bool | P0 已有 | False | 启用临时 subagent | 自动挂 deerflow task_tool |
| `adopted_persona` | str | P0 已有 | None | 引用 persona skill | 注入 persona prompt |
| `validator` | str | P0 已有 | None | validator 函数路径 | 用于 retry 决策 |

### 兼容现有 `tier` 字段
- `tier` 标记为 **Deprecated alias** 指向 `llm_role`
- compile 期把 `tier: balanced` 自动 map 到 `llm_role: balanced`
- 保留 deprecation 周期至少 2 个 release，期间打 DeprecationWarning

### 新增 Phase Mode
**`mode: parallel_delegate`**（**P1 新增**）—— 真并发 subskill 调度
- `subgraphs: list[str]`：要并发执行的子 skill 路径列表
- `tolerance: float`：失败容忍率（如 0.2 = 允许 20% subskill 失败）
- `reducer: str`：聚合函数路径（合并 N 个并发结果到 phase 输出）
- 框架用 LangGraph 的 `Send` API 做物理并发

### 新增 builtin tools（依赖 schema opt-in）
- `read_file(path)`：当 `references` 非空时自动挂载
- `read_artifact(name)`：当 `context_access` 含 `"artifact"` 时自动挂载
- `query_working_memory()`：当 `context_access` 含 `"working_memory"` 时自动挂载
- `ask_clarification(question)`：默认挂载（找回 deerflow 逃生舱）

---

## 四、完整 Prompt 渲染蓝图（Round 8 §C 收敛）

### 重构后的 SystemMessage 完整模板

```xml
<!-- === DeerFlow / Cognitive 外部刚性护栏 === -->
<role>你是 GraphAgent 的执行节点，当前阶段：{phase_name}。</role>

<role_prefix>
{config/llm_roles.yaml 里 roles.{llm_role}.system_prompt_prefix}
（自动从 llm_role 字段映射注入，PM 不需要手写）
</role_prefix>

<thinking_style>
- 行动前先做简短策略思考...
- 区分"事实"与"推断"...
- 对关键判断给出依据...
- 先规划后执行...
- 思考用于规划；对外输出必须给出可执行结果...
</thinking_style>

<ambiguity_feedback>
当你发现规则不清晰、输入不足或存在多种合理解释时...
1. 优先调用 log_ambiguity 记录...
2. 然后继续按"最保守且可解释"的方案执行
</ambiguity_feedback>

<protocol_citation>
做判断时必须标注协议依据。推荐格式：[protocol:P1] ...
</protocol_citation>

<!-- === Skill 内部业务插件 (Loader 根据 Schema 字段生成) === -->
<skill_section>
  <domain_expertise>
    {prompt 字段渲染：业务逻辑说明 + 角色背景}
  </domain_expertise>

  <task_objective>
    {核心任务目标，由 prompt 提取或独立字段}
  </task_objective>

  <domain_protocols>
    [protocol:P1] {domain_protocols[0]}
    [protocol:P2] {domain_protocols[1]}
    ...
  </domain_protocols>

  <output_format>
    必须在 finish_task 的 business_data_md 中提供以下 markdown 结构：
    {output_schema 字段：自动从 Pydantic 模型推导字段说明}
  </output_format>

  <examples>
    <example id="1">{few_shot_examples[0]}</example>
    <example id="2">{few_shot_examples[1]}</example>
    ...
  </examples>

  <context_access>
    （仅当 context_access 非空时渲染）
    如果在当前输入中发现信息缺失，你被授权使用以下工具追溯前序上下文：
    {context_access 列表对应的工具名}
  </context_access>

  <knowledge_base>
    （仅当 references 非空时渲染）
    本地有以下参考文件，请在需要时调用 read_file 查阅：
    {references 列表的相对路径}
  </knowledge_base>

  <steps>
    1. {steps[0]}
    2. {steps[1]}
    ...
  </steps>
</skill_section>

<critical_reminders>
- 调用 finish_task 时，必须在 diagnostics_md 字段提供：执行总结 / 计划核对表 / 遗留问题
- 你的 business_data_md 必须严格遵循 <output_format> 的结构要求，否则将被系统拒绝
- 当你不确定规则边界时，先 log_ambiguity，再继续执行
</critical_reminders>
```

### 重构后 finish_task 工具签名

```python
def finish_task(
    diagnostics_md: str,    # 强制要求的诊断说明（合并 execution_summary/plan_checklist/unresolved_issues）
    business_data_md: str   # 强制要求的 markdown 业务数据（按 output_schema 模板）
) -> str:
    """LLM 输出 markdown，框架后台用 md_to_json + Pydantic 校验。
    校验失败 → 拒绝完成 + 返回 Tool Error 让 LLM 修 business_data_md 重试。
    """
```

### Retry 时的 UserMessage 注入

```text
{原 user prompt 内容}

--- 校验反馈 ---
以下是上一轮输出的校验错误，请仔细阅读后修正你的输出：
- 错误：{errors[0]}
- 评分 4/10：{errors[1]}
```

注：retry 走 user message 末尾追加机制（`phase_executor.py:283-289` 已实现），**不需要在 schema 层加 `<review_directive>` 标签**。

---

## 五、P0/P1/P2 修复路径表

### P0 救火（必须立刻做，影响系统存活率 + 核心契约兑现）

#### P0-1: 接通 DeerFlow Middleware（解决 Round 7 颠覆性发现 1+2）
- **方案选择**：**B 选项（维持 create_agent + 显式挂载 SummarizationMiddleware + LoopDetectionMiddleware）**
- **A 选项（改用 make_lead_agent）已被否决**：因为 deerflow lead_agent 自带 SYSTEM_PROMPT_TEMPLATE 会跟 cognitive_template 双重叠加冲突，违背 9 轮辩论建立的设计
- **改动**：
  - `phase_executor.py:366-373` `create_custom_middlewares` 调用——补全 deerflow `SummarizationMiddleware` + `LoopDetectionMiddleware`
  - 验证 deerflow middleware 跟现有 `WorkingMemory` + `DeadEnd` 兼容
- **测试**：长 phase（batch-analysis 5+ 轮 tool call）验证 token 不爆炸 + 死循环被阻止
- **工作量**：中

#### P0-2: finish_task + md_to_json 物理熔接（解决 Round 7 中度发现 7 + Round 6 虚假契约）
- **改动**：
  - `tools/builtin/finish_task.py`：重构工具签名为 `diagnostics_md: str + business_data_md: str`
  - 内部集成 `md_to_json(business_data_md, schema)` + Pydantic 校验
  - 校验失败抛 Tool Error 让 LLM 修
- **测试**：构造合规 + 不合规的 markdown 输出验证打回机制
- **工作量**：中

#### P0-3: 完善 Loader 的 XML 渲染（schema 字段扩展 + cognitive template 标签扩展）
- **改动**：
  - `manifest.py`：LLMPhase + AgentProfile 新增字段 `domain_protocols: list[str]` + `references: list[str]` + `few_shot_examples: list[str]`（PersonaSkillDef 已有）+ `context_access: list[str]` + 把 `tier` deprecate 为 `llm_role: str` 别名
  - `cognitive/prompt.py`：cognitive template 新增 `<role_prefix>` 自动注入 + 内层 `<skill_section>` 内嵌套渲染逻辑
  - `loader.py`：把 schema 字段渲染为对应 XML 标签，注入到 `<skill_section>` 内
  - `loader.py:435`：删除 `few_shot_examples` 的 `NotImplementedError` 陷阱（解决 Round 7 中度发现 8）
  - `phase_executor.py`：当 `references` 非空 → 自动挂 `read_file` 工具；当 `context_access` 非空 → 自动挂对应工具
- **测试**：每个新字段单独测试 + 完整 SystemMessage 端到端测试
- **工作量**：大（这是 foundation PR，blast radius 最广）

### P1 校准（应该做，对齐设计原则）

#### P1-4: Examples + References 双轨实装（落地，跟 P0-3 schema 字段配套）
- **改动**：
  - `references` 注入 `<knowledge_base>` 标签 + 框架自动加载 references 文件并提供给 `read_file` 工具
  - `few_shot_examples` 内联到 `<examples>` 标签
- **依赖**：P0-3
- **工作量**：小（schema 已扩，只是 wire 起来）

#### P1-5: 激活 Clarification 逃生舱
- **改动**：
  - `phase_executor.py`：默认注入 `ask_clarification` 工具
  - 验证或挂 deerflow 的 `ClarificationMiddleware`
- **工作量**：小

#### P1-6: 并发模式原语 `parallel_delegate`
- **改动**：
  - `manifest.py`：新增 `DelegatePhase` 子类 `ParallelDelegatePhase`（含 `subgraphs` / `tolerance` / `reducer`）
  - `loader.py` + `phase_executor.py`：用 LangGraph 的 `Send` API 实现物理并发调度
- **依赖**：无（独立）
- **工作量**：大（涉及 LangGraph 高级 API）

### P2 进化（可选）

#### P2-7: 上下文主动挖掘（解决 Round 8 Input 3）
- **改动**：
  - 实现 `read_artifact(name)` + `query_working_memory()` builtin tools
  - 基于 P0-3 的 `context_access` schema 字段 opt-in 挂载
- **依赖**：P0-3
- **工作量**：中

#### P2-8: 清洗 producer/review 历史黑盒
- **改动**：
  - 把 `skills/producer/review/SKILL.md` 强制迁移到 `PersonaSkillDef`
  - `<role>` → `role` 字段 / `<rules>` → `evaluation_rubrics` 或 `constraints` / `<context>` → `metadata`
- **依赖**：P0-3 + P1-4（references）
- **工作量**：中（业务迁移 + 框架机制）

---

## 六、PR 拆分建议（项目经理 Claude 的工程判断）

按"独立性 + foundation 优先 + Codex 大 prompt 易挂死"原则拆 7 个 PR：

### PR-1：Schema 字段扩展骨架（P0-3 子集，最 foundation）
- `manifest.py` 新增 `domain_protocols` / `references` / `few_shot_examples` / `context_access` 字段定义 + `tier` deprecate 为 `llm_role` 别名 + 删除 `few_shot_examples` NotImplementedError
- `cognitive/prompt.py` 新增 `<role_prefix>` 自动注入 + cognitive template 骨架扩展
- `loader.py` 实现新字段 → `<skill_section>` 内嵌套 XML 渲染
- 测试覆盖每个字段的渲染 + 兼容现有 SKILL.md
- **窄焦点 + foundation**：blast radius 局限于 manifest/cognitive/loader，不涉及 middleware/finish_task

### PR-2：finish_task + md_to_json 熔接（P0-2）
- `tools/builtin/finish_task.py` 重构签名 + 内部熔接 md_to_json + Pydantic 校验 + Tool Error 打回
- 业务 SKILL.md 配套更新（让现有的 finish_task 调用兼容新签名 / 或 graceful migration）
- 测试构造合规 + 不合规 markdown
- **独立**：不依赖 PR-1
**实施状态（2026-04-27）**：v2 签名已落地，业务 SKILL.md 迁移留作后续 cleanup PR。

### PR-3：Middleware 接通（P0-1，B 选项）
- `phase_executor.py` `create_custom_middlewares` 补全 `SummarizationMiddleware` + `LoopDetectionMiddleware`
- 验证跟现有 `WorkingMemory` + `DeadEnd` 兼容
- 测试长 phase token 控制 + 死循环阻止
- **独立**：不依赖 PR-1/PR-2
**实施状态（2026-04-27）**：B 选项落地，LoopDetection + Summarization middleware 已挂载到 create_custom_middlewares。Gemini quota 不可用，主控 self-review 通过。

### PR-4：references + read_file builtin tool（P1-4）
- 实现 `read_file` builtin tool
- `phase_executor.py` 当 `references` 非空时自动挂载
- `loader.py` 渲染 `<knowledge_base>` 标签
- **依赖**：PR-1 (schema 字段)
**实施状态（2026-04-27）**：read_file builtin tool 实现 + phase_executor 自动挂载（references 非空时）。Gemini quota 仍不可用，主控 self-review 通过。

### PR-5：Clarification 逃生舱（P1-5）
- 默认挂 `ask_clarification` 工具
- 验证 `ClarificationMiddleware` 接入
- **独立**

### PR-6：context_access + read_artifact / query_working_memory（P2-7）
- 实现 `read_artifact` + `query_working_memory` builtin tools
- 基于 PR-1 的 `context_access` schema opt-in 挂载
- `loader.py` 渲染 `<context_access>` 标签
- **依赖**：PR-1

### PR-7：parallel_delegate phase mode（P1-6）
- `manifest.py` 新 `ParallelDelegatePhase` 子类
- `loader.py` + `phase_executor.py` 用 LangGraph `Send` API 实现
- **独立**：不依赖前面 PR

（PR-8: producer/review 迁移留作 P2 后置 PR，依赖 PR-4 references 落地）

---

## 七、还没解决的开放问题（需要 SevenX 拍板）

### 开放问题 1：LogicPhase 的重试状态继承
**问题**：当 `LogicPhase` 触发 `retry_target`，messages 是否也清空？LogicPhase 是 Python 脚本不是 LLM——它怎么感知"我是被重试调用的"？怎么拿上一次的错误信息？

**候选方案**：
- 选项 a：在 `RunContext` 里维持一个 `_retry_feedback: list[str]` 字段，LogicPhase 函数签名能访问
- 选项 b：跟 LLMPhase 一致走 messages 清空，LogicPhase 函数自己负责从 artifacts/working_memory 重新读取
- 选项 c：LogicPhase 不支持 retry（schema 层禁止 `retry_target` 在 LogicPhase 上设置）

### 开放问题 2：output_schema 的自动 markdown 提示生成
**问题**：当 PM 填 `output_schema: "script.models.CharacterState"`，Loader 是**自动**把 Pydantic 模型转 markdown 提示词说明（如"需要包含 1. name (字符串) 2. age (数字)"），还是 PM 在 `prompt` 里自己写格式要求？

**候选方案**：
- 选项 a：自动从 Pydantic 模型 introspect 字段名/类型 → 生成 markdown 模板。PM 友好，工程实现略复杂
- 选项 b：PM 自己在 `domain_protocols` 或 `examples` 里手写格式说明，框架仅做后台校验

### 开放问题 3：tier → llm_role deprecation 周期
- 多久彻底移除 `tier` 别名？保留几个 release？

### 开放问题 4：role 跟 context_access 的耦合
- Round 9 Gemini 提议"高级 role（analyst）默认开 context_access / 初级 role（fast）保持隔离"——这层耦合要不要？还是 role 跟 context_access 完全正交？

---

## 八、实施纪律

1. **每个 PR 独立可 build + 测试通过**：不能"半成品 PR" 留给下个 PR 修
2. **PR 之间依赖关系明确**：上面已标
3. **窄焦点 brief 给 Codex**：按 memory `feedback_codex_prompt_size.md` 教训，**不发全量 diff + rubric 打分**，给 3-4 个文件 + 具体改动 + 测试要求
4. **Codex 实施完每个 PR 后**：Gemini round-trip plan-review + code-review（按 Peer Review Framework）
5. **完成 1 个 PR 立即 merge**：避免大 PR 堆积
6. **每个 PR commit 之间都跑测试**：保证项目 always buildable

---

## 九、参考资料

- 9 轮辩论的 brief 原文：`/tmp/gemini-round*-*.md`（这次 session 的临时文件）
- 当前项目状态：main 顶部 commit `19e4873`
- 上一个 cohesion plan：`docs/superpowers/plans/2026-04-26-graph-agent-cohesion-plan.md`
