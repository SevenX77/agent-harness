# graph_skill 文件格式 GROUND TRUTH（唯一权威定稿）

> **⚠️ 这是 PM 拍板的 graph_skill 5 类文件格式的唯一真相源。**
> 任何 spec / fixture / 代码 / design 跟本文冲突，以本文为准。
> 本文之外的格式描述（含 `01`~`12` skill-spec 其他文档、tests/fixtures、round-N design）若与本文冲突，一律视为污染版本，须以本文修正。
>
> **来源**：session `027acc48`，PM 逐文件拍板 2026-05-22T04:34 → 2026-05-24T12:25。
> - 完整 5 模版打印：line 1663（2026-05-24T09:35）
> - 后续修正：line 1663 之后 PM 确认 + line 2165（§A1-A11）
> - 每条附 PM 原话 + 时间戳，杜绝二次走丢。
>
> **历史教训**：此前两次走丢——(1) commit `e485261`(5-23) 把 GRAPH.md body `<phase>` XML 写成纯 frontmatter YAML，违背"phase 写 body XML"拍板；(2) 5-24 双轨定稿只落 `/tmp` 临时文档随 crash 丢失。本文落正式 docs 永久保存。

---

## 核心原则 R1.1（PM 2026-05-22）

> **YAML frontmatter 仅含引擎配置；`phases/*/` 下 XML body 仅含 phase 内部业务意图（prompts / 拓扑 / 顺序）。**

这是 5 个文件格式的总纲：frontmatter = 机器配置（名字注册 / io schema / 开关），body XML = 业务逻辑主体（拓扑连线 / 执行顺序 / prompt 内容）。

---

## §1 GRAPH.md（根拓扑文件）

### 模版

```markdown
---
schema_version: "v0.3.0"
phases: [material_preparation, generate_scripts, final_review]
# ↑ frontmatter 只是 phase 名字注册 list[str]，自动列出 phases/ 文件夹下子文件夹名

io:
  inputs: {<JSON Schema dict>}
  outputs: {<JSON Schema dict>}
# ↑ io 直接 dict 写 frontmatter，不用 io_inputs_ref / io_outputs_ref，不要外部 io 文件
---

<phase depends_on="input">material_preparation</phase>
<phase depends_on="material_preparation">generate_scripts</phase>
<phase depends_on="generate_scripts" output>final_review</phase>
```

### 双轨制（关键，曾被删除）

GRAPH.md 是**双轨**：
- **frontmatter `phases:`** = 名字注册 `list[str]`（自动对应 `phases/` 下子目录名）
- **body `<phase>` XML** = DAG 拓扑主体（`depends_on` 连线 + `output` 结束节点）

两者都必须有。body `<phase>` XML 不是可选、不是 GUI 例外。

### 字段规则

| 元素 | 规则 |
|---|---|
| `schema_version` | `"v0.3.0"`（PM 原话用 `v0.3.0`；**待确认**：现有代码写 `0.3.0` 无 `v`，以哪个为准） |
| `phases:` frontmatter | `list[str]` 仅名字，自动列出 `phases/` 子目录名 |
| `io:` frontmatter | inline dict（inputs + outputs JSON Schema），**禁止** `io_inputs_ref` / `io_outputs_ref` / 外部 io 文件 |
| `<phase depends_on="X">name</phase>` body | `depends_on` 必填（拓扑连线）；第一个节点也必须填，填 `input`；`depends_on` 可指向并联多节点 |
| `output` 属性 | 结束节点在 `<phase>` 标签加 `output` 标识；可多个 phase 标 output |
| phase name 一致性 | body `<phase>` 包裹的 name 必须 = frontmatter `phases:` 注册名 = 物理目录名，否则节点无效不显示在 canvas |
| `type: graph` | 不需要写 |

### PM 原话

- **[05-22T04:34]** "1.schema_version 升级成 v0.3.0; 2.type:graph 不需要; 3.io_inputs_ref 和 io_outputs_ref 没必要写，默认且必须写在这个位置; 4.`<phase>` 标签怎么写：1.formatter 注册 phases: list[str]，自动列出 phases 文件夹中的子文件夹名; 2.`<phase depends_on="input">material_preperation</phase>...`；depends_on 代表拓扑连线，不填代表不连线，所以必须填，第一个节点也必须填 input；phase 标签包裹 phase name，phase name 必须等于 formatter 中注册的 phase name，否则该节点无效"
- **[05-22T05:12]** "最后的节点在 phase 标签里加一个 output，例如 `<phase depends_on="..." output>...</phase>`，多个 phase 写 output 代表"
- **[05-22T05:32]** "graph.md 和其他节点一样写 io dict，io 文件不需要了；同名就报错，必须改名"

---

## §2 LOGIC.md（Python action phase）

### 模版

```markdown
---
io:
  inputs: {<JSON Schema dict>}
  outputs: {<JSON Schema dict>}

actions: [action1_name, action2_name]
# ↑ frontmatter 注册 action 名字，同 phase 名字注册逻辑
# 两种来源：(1) 本 logic phase 路径下 action/ 文件夹的 action_name.py
#         (2) studio 或 engine 内注册的通用 action

validator: true
# ↑ boolean；true 时 validator.py 放在本 phase 目录下（phases/<phase_id>/validator.py）
---

<action>action1_name</action>
<action>action2_name</action>
# ↑ 按标签顺序执行；body XML 兼顾多步 action 调用
```

### 字段规则

| 元素 | 规则 |
|---|---|
| `io:` frontmatter | inline dict（同 GRAPH.md） |
| `actions:` frontmatter | `list[str]` 注册名字；来源二选一（本 phase `action/` 目录 .py / 通用注册 action） |
| `validator:` frontmatter | boolean；true → `validator.py` 放本 phase 目录下 |
| `<action>name</action>` body | 按标签顺序执行，支持多步 |

### PM 原话

- **[05-22T05:12]** "LOGIC.md：1.frontmatter 写 io 的 schema 直接写 dict；2.action 注册同 phase 注册，两种情况直接写名字：logic phase 路径下 action 文件夹下的 action_name.py，注册在 studio 或 engine 内的通用 action；标签写法 `<action>action1</action><action>action2</action>`，按标签顺序执行"
- **[05-22T05:15]** "validator 字段保留，值改成 boolean，validator.py 文件放在 logic phase 路径下"

---

## §3 SUBGRAPH.md（子图委派 phase）

### 模版

```markdown
---
target_skill: <已注册 skill 的 name>
# ↑ subgraph 文件不在当前 graph skill 路径内，从 studio 后端注册表找物理地址

io:
  inputs: {<JSON Schema dict>}
  outputs: {<JSON Schema dict>}
---

（无 body XML）
```

### 字段规则

| 元素 | 规则 |
|---|---|
| `target_skill:` frontmatter | 已注册 skill 的 name；编译期从 studio 后端注册表解析物理地址（**待确认**：`target_skill` 这个 key 名是 PM 拍的还是主控起的） |
| `io:` frontmatter | inline dict |
| body XML | **无**（subgraph phase 不需要 body XML） |

### PM 原话

- **[05-21T18:52]** "subgraph phase 可能真不需要 body xml"
- **[05-22T06:08]** "subgraph 的文件不在当前 graph skill 的路径中，需要从注册的 skills 里找到他…如果 skill 的注册表全部放在 studio 后端，编译的时候需要请求后端拿到注册表里的物理地址才能读到文件"

---

## §4 SKILL.md（Agent phase）

### 模版

```markdown
---
mode: agent          # 三选一 agent/logic/subgraph，用于双向校验物理布局（待确认 key 名）
llm_role: analyst    # 判断用哪个 LLM 大模型，跟 cognitive template 的 role 两码事
validator: false     # boolean，每 phase 都有（见 §6）
---

<role>agent 角色描述</role>
<goal>agent 目标描述</goal>

<step id="S1" name="parse_chapter">读章节按 A/B/C 三类分段，遵循 @protocol:P1.</step>
<step id="S2" name="producer_review">调用 @subagent:producer_reviewer 审核评分.</step>

<protocol id="P1">A类-设定：解释世界规则；B类-事件：现实物理时间线；C类-次元：脱离物理世界</protocol>
```

### body 标签规则

| 标签 | 数量 | 必填 | 备注 |
|---|---|---|---|
| `<role>` | 1 | ✅ 必填 | agent 角色 |
| `<goal>` | 1 | ✅ 必填 | agent 目标 |
| `<step id name>` | 0..N | 选填 | **单数**，脱壳；canvas 按 step 顺序拓扑渲染 |
| `<protocol id>` | 0..N | 选填 | **单数**，脱壳 |

- **明令禁止**：复数壳标签 `<steps>` / `<protocols>`
- **明令禁止**：`<exit_contract>` 写进 SKILL.md ——「**exit_contract 直接写进模版，不用在 skill.md 里面再写一遍**」（exit_contract 只在 §5 cognitive template hardcode）

### PM 原话

- **[05-22T07:36]** "1.`<role>` 必填; 2.`<goal>` 必填; 3.`<step id name>`…steps 只是一个壳，脱壳放进模版；canvas 根据 step 顺序拓扑渲染; 4.`<protocol id>`"
- **[05-22T07:57]** "`<steps>` 包裹脱壳…protocol 遵循一样的逻辑；exit contract 直接写进模版，不用引用"
- **[5-24，修正]** "exit_contract 我让你直接写进模版意思就是不用在 skill.md 里面再写一遍"

---

## §5 Cognitive Template（agent 装配模版，8 大插槽）

exit_contract **只在这里** hardcode，不从 SKILL.md 引用。

```xml
<role>{skill_role}</role>
<goal>{skill_goal}</goal>

<thinking_style>
- 行动前先做简短策略思考；区分"事实"与"推断"；先规划后执行；对外输出可执行结果
- 建议步骤：
    {skill_steps_splat}        ← 脱壳后的 <step> 序列
</thinking_style>

<knowledge_base>
【垂直领域知识修正报告】：
{aligned_concepts_and_critical_corrections_markdown}
# ↑ 占位符必须是这个名字（不是 {reference_reader_subagent_output_markdown}）
如需更多原始语料，可自主调用 read_reference subagent 传入 R-id。
当前 Reference 注册清单：{reference_registry_listing}
</knowledge_base>

<examples>
内联示范：{skill_examples_inline}
扩展案例库（调用 read_example subagent）：{example_registry_listing}
</examples>

<ambiguity_feedback>
... （必须有专门链路提取并反馈给前端）
</ambiguity_feedback>

<protocol_citation>
必须遵守的协议：{skill_protocols_splat}   ← 脱壳后的 <protocol> 序列
</protocol_citation>

<exit_contract>
{skill_exit_contract_inline}   ← hardcode 写进模版，末尾引用 output_schema
</exit_contract>
```

### Knowledge Base 双路径（PM 明示「单独」，不能合并）

1. **Knowledge Base 装载 subagent**（装配期，agent loop 启动前）：独立 builtin subagent，读 knowledge_base 文档修正领域理解，填进 `{aligned_concepts_and_critical_corrections_markdown}`
2. **`read_reference` runtime subagent tool**（agent loop 内主动调）：跑一半要查 reference 库时调用，传 R-id 取精准局部解析
3. **`read_example` runtime subagent tool**：跑一半要查 example 注册库时调用

→ knowledge_base 装载 subagent 与 read_reference subagent **物理分离两个文件**，不可合并。

### PM 原话

- **[05-22T06:55]** "1.`<role>` 贴 skill.md 的 role; 3.thinking_style 最后加 -建议步骤:{步骤}; 4.ambiguity feedback 必须有专门链路提取并反馈前端; 5.protocol 加'必须遵守的协议:{protocol}'; 6.漏了 exit contract"
- **[05-22T10:18]** "单独把 knowledge base 提取出来，最一开始用一个 subagent 读 knowledge base 修正领域理解…在 agent loop 之前调用，结果直接输入 system prompt"
- **[05-22T10:46]** "两种方式应该并存，组装时总结领域知识放进 `<knowledge_base>`，再加一句如需更多可调用 subagent 从 reference 获取；step 中也可 @reference"
- **[05-22T11:07]** "没问题了，定稿"

---

## §6 跨文件统一规则（5-24 拍板 A7-A11）

| # | 规则 | PM 来源 |
|---|---|---|
| A7 | phase name 必须 = 物理目录名，mismatch 从 WARN 升级 **FATAL**，错误码 `[F-v3-graph-phase-name-mismatch]` | 5-24 |
| A8 | phase 文件（SKILL/LOGIC/SUBGRAPH.md）**不**写 `schema_version` / `graph_skill_id` / `phase_id`，100% 依赖 GRAPH.md + 物理路径 | 5-24 "需要判断每一个 phase 是否都要写 schema version、graph_skill_id、phase_id" |
| A9 | 3 类 phase 都加 `validator: boolean` 选填默认 false，字段名**统一** | 5-24 "validator 应该是每一个 phase 都需要" |
| A10 | validator 失败处理：**AGENT** 失败 nudge 重试（扣 max_iterations）；**LOGIC + SUBGRAPH** 失败抛异常阻断（且正常应在 predict 阶段就检查抛出） | 5-24 "logic 和 subgraph 应该在 predict 阶段就检查抛出异常" |
| A11 | gateway 从 engine 分离成独立 SDK package（已在 PR α 完成） | 5-24 |

---

## §7 待你确认的字段（PM 未明确拍过，疑似主控自创）

这些字段当前代码在用，但 session 里找不到你明确拍板，请确认是否认可 / 改名 / 删除：

1. `schema_version` 值：`"v0.3.0"`（你原话带 v）还是 `"0.3.0"`（现有代码无 v）？
2. `mode:` 字段（agent/logic/subgraph 三选一）：key 名 `mode` 是你拍的还是主控起的？
3. `target_skill:` 字段（SUBGRAPH.md）：key 名是你拍的还是主控起的？
4. 错误码 `[F-v3-*]` 字典体系：你没拍过具体错误码命名，是否认可现有命名？
5. `@type:NAME` mention 语法（@protocol / @subagent / @reference 等）：你 5-22T08:40 提过 7 类（subagents/tools/subgraph/protocol/steps/reference/example），是否就是这套？
6. SkillResolverProtocol 接口：你没拍过，是否认可？

---

## 确认方式

请逐节确认 §1-§6（对 / 错，错在哪），并拍 §7 的 6 个待确认字段。确认后：
1. 我以本文为唯一权威修正 `01`~`12` skill-spec（尤其 `02-graph-md-spec.md` 回归双轨）
2. 重审 round-14（当前 design/src 把 body `<phase>` XML 删了，是错的）
3. 本文长期保留在 `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`，以后任何格式争议先查本文。
