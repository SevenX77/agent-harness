---
status: FROZEN
---
<!-- DO NOT EDIT: Golden principle contract baseline. Any divergence is strictly prohibited unless explicitly approved. -->

# graph_skill 文件格式 GROUND TRUTH（唯一权威定稿）

> **⚠️ 这是 PM 拍板的 graph_skill 5 类文件格式的唯一真相源。**
> 任何 spec / fixture / 代码 / design 跟本文冲突，以本文为准。
> 本文之外的格式描述（含 `01`~`12` skill-spec 其他文档、tests/fixtures、round-N design、代码实现）若与本文冲突，一律视为污染版本，须以本文修正。
>
> **来源**：session `027acc48` + `397ab0bb`，PM 逐文件拍板 2026-05-22T04:34 → 2026-05-24T12:25。每条附 PM 原话 + 时间戳。
> **历史教训**：此前两次走丢——(1) commit `e485261`(5-23) 把 GRAPH.md body `<phase>` XML 写成纯 frontmatter YAML，违背"phase 写 body XML"拍板；(2) 5-24 双轨定稿只落 `/tmp` 随 crash 丢失。本文落正式 docs 永久保存。

---

## 核心原则 R1.1（PM 2026-05-22）

> **YAML frontmatter 仅含引擎配置（名字注册 / io schema / 开关 / 资源注册）；`phases/*/` 下 XML body 仅含 phase 内部业务意图（拓扑连线 / 执行顺序 / prompt 内容）。**

---

## §0 全局规则（适用所有 phase 文件）

- **无 `mode:` 字段**：phase 类型由物理文件名唯一决定（`SKILL.md`=agent / `LOGIC.md`=logic / `SUBGRAPH.md`=subgraph）。loader 从文件名推导并注入 AST 内部 mode，**作者不写、引擎不要求写**。（a1+a2+a3 三方一致论证：手写 mode 冗余违反 SSOT；AST 层 `Literal["agent"/"logic"/"subgraph"]` 保留作内部 discriminator）
- **phase 文件不写** `schema_version` / `graph_skill_id` / `phase_id`：100% 依赖 GRAPH.md + 物理路径（PM 5-24）
- **phase name = 物理目录名**：mismatch → FATAL `[F-v3-graph-phase-name-mismatch]`（PM 5-24，从 WARN 升级）
- **每个 phase 都有 `validator: boolean`**（选填默认 false，字段名统一）（PM 5-24"validator 应该是每一个 phase 都需要"）

---

## §1 GRAPH.md（根拓扑文件）

### 模版

```markdown
---
schema_version: "v0.3.0"
phases: [material_preparation, generate_scripts, final_review]
# ↑ frontmatter 只是 phase 名字注册 list[str]，自动列出 phases/ 下子目录名

io:
  inputs: {<JSON Schema dict>}
  outputs: {<JSON Schema dict>}
# ↑ io 直接 dict 写 frontmatter，不用 io_inputs_ref / io_outputs_ref，不要外部 io 文件
---

<phase depends_on="input">material_preparation</phase>
<phase depends_on="material_preparation">generate_scripts</phase>
<phase depends_on="generate_scripts" output>final_review</phase>
```

### 双轨制（关键，曾被 e485261 删错）

- **frontmatter `phases:`** = 名字注册 `list[str]`（自动对应 `phases/` 下子目录名）
- **body `<phase>` XML** = DAG 拓扑主体（`depends_on` 连线 + `output` 结束节点）

两者都必须有，body `<phase>` XML 不是可选、不是 GUI 例外。

### 字段规则

| 元素 | 规则 |
|---|---|
| `schema_version` | **`"v0.3.0"`（带 v，PM 2026-05-22T04:34 "升级成 v0.3.0" 定稿，已确认）**。代码 `manifest.py:106` 写 `"0.3.0"` 无 v = 实现偏差须改回 |
| `phases:` frontmatter | `list[str]` 仅名字，自动列出 `phases/` 子目录名 |
| `io:` frontmatter | inline dict（inputs+outputs JSON Schema），**禁止** `io_inputs_ref`/`io_outputs_ref`/外部 io 文件 |
| `<phase depends_on="X">name</phase>` body | `depends_on` 必填（拓扑连线）；第一个节点也必须填，填 `input`；可指向并联多节点 |
| `output` 属性 | 结束节点在 `<phase>` 标签加 `output`；可多个 phase 标 |
| name 一致性 | body `<phase>` 包裹的 name = frontmatter `phases:` 注册名 = 物理目录名，否则节点无效 |
| `type: graph` | 不需要写 |

### PM 原话

- **[05-22T04:34]** "1.schema_version 升级成 v0.3.0; 2.type:graph 不需要; 3.io_inputs_ref/io_outputs_ref 没必要写; 4.phases: list[str] 自动列出子文件夹名 + `<phase depends_on="input">material_preperation</phase>`；depends_on 必须填，第一个填 input；phase name 必须等于注册名否则节点无效"
- **[05-22T05:12]** "最后的节点在 phase 标签里加 output：`<phase depends_on="..." output>...</phase>`"
- **[05-22T05:32]** "graph.md 和其他节点一样写 io dict，io 文件不需要了；同名就报错必须改名"

---

## §2 LOGIC.md（Python action phase）

### 模版

```markdown
---
# 无 mode 字段（文件名 LOGIC.md 决定类型）

io:
  inputs: {<JSON Schema dict>}
  outputs: {<JSON Schema dict>}

actions: [action1_name, action2_name]
# ↑ frontmatter 注册 action 名字；两种来源：
#   (1) 本 logic phase 路径下 actions/ 文件夹的 action_name.py
#   (2) studio 或 engine 内注册的通用 action

validator: true   # boolean；true → validator.py 放本 phase 目录下 phases/<phase_id>/validator.py
---

<action>action1_name</action>
<action>action2_name</action>
# ↑ 按标签顺序执行；body XML 兼顾多步 action 调用
```

### PM 原话

- **[05-22T05:12]** "LOGIC.md：frontmatter 写 io dict；action 注册同 phase，两种来源直接写名字；标签 `<action>action1</action><action>action2</action>` 按顺序执行"
- **[05-22T05:15]** "validator 字段保留，值改成 boolean，validator.py 放 logic phase 路径下"

---

## §3 SUBGRAPH.md（子图委派 phase）

### 模版

```markdown
---
# 无 mode 字段（文件名 SUBGRAPH.md 决定类型）

target_skill: <已注册 skill 的 name>
# ↑ subgraph 文件不在当前 graph skill 路径内，从 studio 后端注册表找物理地址

io:
  inputs: {<JSON Schema dict>}
  outputs: {<JSON Schema dict>}

validator: false   # boolean，每 phase 都有
---

（无 body XML）
```

### PM 原话

- **[05-21T18:52]** "subgraph phase 可能真不需要 body xml"
- **[05-22T06:08]** "subgraph 文件不在当前路径中，需从注册的 skills 找到他…注册表放 studio 后端，编译时请求后端拿物理地址"

---

## §4 SKILL.md（Agent phase）

### 模版

```markdown
---
# 无 mode 字段（文件名 SKILL.md 决定类型）

llm_role: analyst        # 判断用哪个 LLM 大模型（跟 cognitive template 的 role 两码事）
validator: false         # boolean，每 phase 都有
max_iterations: 10       # agent loop 最大迭代次数（1~50）

# ↓↓↓ 资源注册（全在 SKILL.md frontmatter，见 manifest.py:152-156）↓↓↓
tools: [tool_a, tool_b]                          # 通用 tool 名字 list[str]
subagents:                                        # 可调用的子 skill（作为 tool）
  - {name: producer_reviewer, target_skill: producer-review-skill, description: "审核评分"}
subgraphs:                                        # 子图委派注册（AgentRegistryItem）
  - {name: sub_x, target_skill: some-skill, description: "..."}
references:                                       # reference 资源注册（ReferenceSpec）
  - {id: R1, path: references/domain.md, summary: "领域知识"}
examples:                                         # 只注册 document 扩展案例库（inline 案例写 body <example>，不在此注册）
  - {id: E2, path: examples/e2.md, summary: "复杂边界案例"}
---

<role>agent 角色描述</role>
<goal>agent 目标描述</goal>

<step id="S1" name="parse_chapter">读章节按 A/B/C 三类分段，遵循 @protocol:P1.</step>
<step id="S2" name="producer_review">调用 @subagent:producer_reviewer 审核评分.</step>

<protocol id="P1">A类-设定：解释世界规则；B类-事件：现实物理时间线；C类-次元：脱离物理世界</protocol>

<example id="E1">边缘情节判定示范：人物做梦（物理时间流逝但场景虚幻）判 B 类，不是 C 类；只有完全切断物理时间的内心独白才是 C 类。</example>
```

### frontmatter 注册字段（manifest.py:152-156，曾全漏）

| 字段 | 结构 | 用途 |
|---|---|---|
| `tools` | `list[str]` | 通用 tool 名字 |
| `subagents` | `[{name, target_skill, description}]` | 可调用子 skill（作为 tool） |
| `subgraphs` | `[{name, target_skill, description}]` | 子图委派绑定 |
| `references` | `[{id, path, summary}]` | reference 资源（id 须大写开头） |
| `examples` | `[{id, path, summary}]`（**只注册 document 扩展案例库**；inline 案例写 body `<example>`，不在 frontmatter） | read_example 调用的扩展库 |
| `llm_role` | `str?` | 选用 LLM 角色 |
| `validator` | `bool` | 默认 false |
| `max_iterations` | `int` 1~50 | 默认 10 |

### body 标签规则

| 标签 | 数量 | 必填 | 备注 |
|---|---|---|---|
| `<role>` | 1 | ✅ | agent 角色 |
| `<goal>` | 1 | ✅ | agent 目标 |
| `<step id name>` | 0..N | 选填 | **单数标签直接写**（无 `<steps>` 复数壳包裹，不需脱壳）；canvas 按 step 顺序拓扑渲染 |
| `<protocol id>` | 0..N | 选填 | **单数标签直接写**（无 `<protocols>` 复数壳包裹） |
| `<example id>` | 0..N | 选填 | **inline 案例直接写 body**（不是 frontmatter 注册，那是反逻辑）；cognitive `{skill_examples_inline}` 引用其内容 |

- **明令禁止**：复数壳 `<steps>`/`<protocols>`（所以是单数标签直接写，装配时无"脱壳"动作，直接拼入 cognitive template）
- **明令禁止**：`<exit_contract>` 写进 SKILL.md ——「exit_contract 不用在 skill.md 里面再写一遍」（只在 §5 cognitive template hardcode）

### PM 原话

- **[05-22T07:36]** "`<role>` 必填; `<goal>` 必填; step 脱壳放进模版 canvas 按顺序渲染; `<protocol id>`"
- **[05-22T07:57]** "steps 脱壳…protocol 同样逻辑；exit contract 直接写进模版不用引用"
- **[5-24]** "exit_contract 我让你直接写进模版意思就是不用在 skill.md 里面再写一遍"

---

## §5 Cognitive Template（引擎装配模版，完整不省略）

引擎把 SKILL.md 的 role/goal/steps/protocols + knowledge_base subagent 输出 + references/examples 注册，装配成最终 system prompt。exit_contract **只在这里** hardcode。占位符版（来源 session line 1663 占位符 + line 3522 demo，PM 5-22T11:07 "没问题了，定稿"）：

```xml
<role>
{skill_role}
</role>

{llm_role_prefix_section}   ← 可选，从 llm_roles.yaml 的 system_prompt_prefix

<goal>
{skill_goal}
</goal>

<thinking_style>
- 行动前先做简短策略思考：目标是什么、输入是否充分、输出标准是什么
- 区分"事实"与"推断"，不要把推断当作事实写入结果
- 对关键判断给出依据，不要无依据臆测
- 先规划后执行：明确步骤，再调用工具
- 思考用于规划；对外输出必须给出可执行结果，而不是只描述计划

建议步骤：
{skill_steps_splat}          ← SKILL.md body 的 <step> 标签序列直接拼入（无脱壳）
</thinking_style>

<knowledge_base>
【垂直领域知识修正报告】(系统已为你提前查阅相关资料并提取核心差异)：
{aligned_concepts_and_critical_corrections_markdown}
# ↑ 占位符必须是这个名字（不是 {reference_reader_subagent_output_markdown}）
# ↑ 内容是 knowledge_base 装载 subagent 在装配期跑完输出的"修正报告"（哪些理解一致🟢/哪些必须修正🔴），不是静态 reference 清单

如果上述提炼不足以支撑判断，或你需要阅读未被精炼的其他原始语料，
可自主调用 read_reference subagent 工具，传入 R-id 从完整 Reference 库获取。
当前可用 Reference 注册清单：{reference_registry_listing}
</knowledge_base>

<examples>
以下案例仅用于辅助理解业务逻辑，你的最终输出格式必须严格遵守 <exit_contract> 的 Schema，不要照搬案例结构。
【内联示范】：{skill_examples_inline}    ← 引用 SKILL.md body 的 <example> 标签内容（直接拼入，像 steps），不是 frontmatter
【扩展案例库】(遇棘手边界可调用 read_example subagent)：{example_registry_listing}   ← frontmatter 注册的 document 案例
</examples>

<ambiguity_feedback>
当你发现规则不清晰、输入不足或存在多种合理解释时，不要静默跳过：
1. 优先调用 log_ambiguity 记录问题、类型、你的决策和理由
2. 然后继续按"最保守且可解释"的方案执行
这不是阻塞流程的澄清请求，而是用于改进技能定义的反馈回路（PM 5-22T06:55"必须有专门链路提取并反馈给前端"）。
</ambiguity_feedback>

<protocol_citation>
做判断时必须标注协议依据，例如 [protocol:P1]。若无明确协议，需在自检说明写明并调用 log_ambiguity。
必须遵守的协议：
{skill_protocols_splat}       ← SKILL.md body 的 <protocol> 标签序列直接拼入（无脱壳）
</protocol_citation>

<critical_reminders>
- 调用 finish_task 前，先检查关键工具返回值是否与预期一致；不一致先修复再 finish
- 对每个关键结论给出规则依据或数据依据
- 不确定规则边界时，先 log_ambiguity 再继续
- finish_task 必须提供 diagnostics_md（自检诊断）+ business_data_md（业务输出，遵循 output_schema）
- business_data_md 经 md_to_json 强校验，失败会收到错误反馈，按反馈修正后重新 finish_task
</critical_reminders>

<exit_contract>
回答必须调用 finish_task，输出符合下方 Schema 的结构化结果。business_data_md 遵循 output_schema 列业务字段；diagnostics_md 写自检诊断。
（↑ 固定 prompt 文本，hardcode 写死在 cognitive template，**不从 skill.md 引用**——skill.md 没有 exit_contract 可引用）
强制输出 Schema：
{output_schema}                ← 末尾拼接该 phase 的 io.outputs schema
</exit_contract>
```

### Knowledge Base 双路径（PM 明示"单独"，物理分两个 subagent，不合并）

1. **Knowledge Base 装载 subagent**（装配期，agent loop 启动前）：独立 builtin subagent，读 knowledge_base 文档修正领域理解，输出"哪些一致🟢/哪些必须修正🔴"，填进 `{aligned_concepts_and_critical_corrections_markdown}`
2. **`read_reference` runtime subagent tool**（loop 内主动调）：跑一半要查 reference 库时调用，传 R-id 取精准局部解析
3. **`read_example` runtime subagent tool**：跑一半要查 example 注册库时调用

### 失败降级（PM 5-22 demo C5）

knowledge_base 装载 subagent 报错（token 超限/网络超时）→ 不阻断 Agent 启动，截原始 reference 前 3000 tokens + 顶部加警告"系统无法完成知识精炼，以下为原始未处理片段"塞 system prompt。

### PM 原话

- **[05-22T06:55]** "`<role>` 贴 skill.md role; thinking_style 最后加 -建议步骤:{步骤}; ambiguity feedback 必须有专门链路提取反馈前端; protocol 加'必须遵守的协议:{protocol}'; 漏了 exit contract"
- **[05-22T10:18]** "单独把 knowledge base 提取，最一开始用 subagent 读 knowledge base 修正领域理解…agent loop 之前调用，结果输入 system prompt"
- **[05-22T10:46]** "两种方式并存，组装时总结领域知识放 `<knowledge_base>`，再加一句如需更多可调 subagent 从 reference 获取；step 中也可 @reference"
- **[05-22T11:07]** "没问题了，定稿"

### 代码实现偏差（待修）

代码 `prompt.py apply_v030_cognitive_template` 偏离定稿：thinking_style 漏"建议步骤:{steps}"、knowledge_base 只简单插值漏完整文本、steps 被独立成 `<steps>` slot（定稿应放 thinking_style）、占位符没用 `{aligned_concepts...}`、`exit_contract` 占位符写 `{skill_exit_contract_inline}` 但应 hardcode 固定文本（skill.md 无可引用源）。须按本节修正。

另：`manifest.py ExampleSpec` 把 inline 案例放 frontmatter `content` 字段 = 反逻辑（PM 2026-05-25）。inline 案例应在 SKILL.md body 用 `<example id>` 标签写（loader 像解析 `<step>` 一样解析 body `<example>`），frontmatter `examples` 只注册 document 扩展案例库（id/path/summary）。须修 manifest + loader。

---

## §6 跨文件统一规则（5-24 拍板 A7-A11）

| # | 规则 | PM 来源 |
|---|---|---|
| A7 | phase name = 物理目录名，mismatch FATAL `[F-v3-graph-phase-name-mismatch]` | 5-24 |
| A8 | phase 文件不写 `schema_version`/`graph_skill_id`/`phase_id`，依赖 GRAPH.md + 物理路径 | 5-24 |
| A9 | 3 类 phase 都加 `validator: boolean` 默认 false，字段名统一 | 5-24 |
| A10 | validator 失败：AGENT nudge 重试（扣 max_iterations）；LOGIC+SUBGRAPH 抛异常阻断（正常应 predict 阶段就检查抛出） | 5-24 |
| A11 | gateway 分离独立 SDK package（已 PR α 完成） | 5-24 |
| **mode** | **作者不写 mode frontmatter；loader 从文件名注入 AST mode**（a1+a2+a3 三方一致：冗余违反 SSOT，文件名已唯一决定类型；删 `_validate_mode_matches_filename`） | 2026-05-25 论证 |

---

## §7 字段确认状态

| 字段 | 状态 |
|---|---|
| `schema_version` | ✅ 已定 `"v0.3.0"`（带 v，PM 历史确认） |
| `mode` frontmatter | ✅ 已定**删除**（a1+a2+a3 论证，PM 待最终拍） |
| `SkillResolverProtocol` | ✅ PM 认可"功能正常即可" |
| `target_skill` key 名 | ✅ PM 认可（agent 设计，功能正常即可） |
| `@type:NAME` mention 语法 | ✅ PM 无异议（agent 设计，功能正常即可） |
| 错误码 `[F-v3-*]` 字典 | ✅ PM 认可（agent 设计，功能正常即可） |
| exit_contract 缺 md 格式约定 | ⏳ **待补**（5-25 你提的验证点）。md2json (`md2json.py:22/61/88`) 只认 `## 字段名` 二级标题 + 值放标题下 + object 用 ` ```json fence` + 嵌套用 `- 子key: 值` bullet；现有 prompt 只说"遵循 output_schema"没教这套格式 → LLM 易吐纯 JSON → 切段失败 → 校验 fail → patcher 兜底。需把"md 字段→`## 标题`映射"写进 exit_contract 措辞（设计阶段你跟 a2 定文本） |

---

## 确认方式

请确认 §0-§6（对/错/错在哪）+ 拍 §7 剩余 3 个 ⏳ 字段。确认后我以本文为唯一权威：(1) 修正 `01`~`12` skill-spec（尤其 `02-graph-md-spec.md` 回归双轨）；(2) 重做 round-14（当前把 body `<phase>` XML 删了是错的，且 mode/注册字段全偏）；(3) 修代码（schema_version 加 v / 删 mode frontmatter+校验 / cognitive template 按 §5 重写）。本文长期保留 `docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md`。
