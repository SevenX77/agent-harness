# Skill Studio — 项目对齐文档

> **本文档是 Skill Studio 项目的起点文档，写给两类读者：**
>
> - **产品经理（PM）**：只读"第一部分 Studio 是什么"和"第二部分 graph_agent 和 skill 基础概念（白话版）"。大约 15-20 分钟能看明白 Studio 能帮你做什么、一个 skill 长什么样、你以后怎么用它。
> - **开发人员**：读完整文档，重点看"第三部分 MVP Roadmap"。你能知道要做什么、每个功能的边界、和 graph_agent 引擎交互的接口在哪里。
>
> **本文档不是**：
> - 不是 Kiro spec（Kiro spec 在本文档确认后基于它写，更详细）
> - 不是 graph_agent 框架内部设计文档（那份文档在 `docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md`）
> - 不是实施 checklist（Superpowers plan 里有带复选框的 task 清单）
>
> **状态定调**：本文档假设 graph_agent 核心引擎**已经完整交付、所有内置能力就绪、所有已知 bug 已修复**。Studio 开发人员读到的是一个成熟稳定的底层框架，只需要专注于 Studio UI 和交互实现。
>
> **最后更新**：2026-04-23

---

## 目录

1. [Studio 是什么](#第一部分-studio-是什么)
2. [graph_agent 和 skill 基础概念](#第二部分-graph_agent-和-skill-基础概念)
3. [Studio MVP Roadmap 和需求](#第三部分-studio-mvp-roadmap-和需求)
4. [附录](#第四部分-附录)

---

## 第一部分：Studio 是什么

### 1.1 一句话定位（北极星）

**Skill Studio 让产品经理不写 Python 代码就能独立完成 graph_agent skill 的设计、修改、测试和交付。从 PM 有一个新想法到跑出第一个能用的 skill，全流程不需要工程师参与。**

Studio 是 graph_agent 框架的配套工具。graph_agent 是底层引擎（负责把声明式的 SKILL.md 文件跑成一个多阶段 Agent），Studio 是给 PM 用的图形界面（负责让 PM 用对这个引擎）。

### 1.2 Studio 解决的核心问题

**没有 Studio 之前**，一个 PM 想做新 Agent 功能（比如"自动写产品说明书"），流程是：PM 把需求写成文档 → 工程师看需求、学 LangGraph、写 Python 代码 → PM 跑一下发现效果不对 → PM 告诉工程师哪里不对（通常说不清楚）→ 工程师改代码 → 反复几轮 → 上线。

**这个循环最致命的四个问题**：

1. **翻译损耗**：PM 说业务语言、工程师说技术语言，中间翻译错很正常
2. **黑盒难调**：PM 看不到 Agent 每一步的 prompt 和 LLM 实际输出，只能凭感觉说"不对"
3. **迭代慢**：工程师一改就几天，每次反馈都要等
4. **无基线对比**：改完新旧版本哪个好只能凭感觉

**Studio 解决这四个问题的方式**：

| 问题 | Studio 的方案 |
|------|--------------|
| 翻译损耗 | PM 用自然语言对话 Copilot（Claude Code / Cursor / 任何他熟悉的工具），Copilot 把自然语言翻译成规范 SKILL.md，不经手工程师 |
| 黑盒难调 | Studio 把每次 run 的完整 trace、每次 LLM 调用的 prompt 三元组（模板 / 变量 / 最终文本）、每个 phase 的耗时和 tokens 全部可视化 |
| 迭代慢 | PM 自己改 SKILL.md 一键 Run 立刻看反馈，**测试通过的 SKILL.md 就是生产直接运行的文件** — 不需要工程师二次翻译成生产代码 |
| 无基线对比 | 内置 Golden baseline 工作流（PM + Copilot 先打磨理想输出 → 每次 run 后自动和基线对比），Copilot 给差异分析 |

**这里最关键的是第三点**：测试环境和生产环境**跑的是同一个底层引擎、同一份 SKILL.md**，PM 在 Studio 里测试满意的那一刻就是可以上线的那一刻。不存在"测试版和生产版代码不一致"的问题，也不存在"开发重构导致逻辑变形"的风险。

### 1.3 典型用户旅程（一个 PM 从零做 skill 到上线）

假设 PM 张三要做"产品说明书生成器" skill。输入是产品的基本参数（比如 iPhone 15 的规格表），输出是面向消费者的营销性说明书。完整流程如下。

**Day 1 - 创建 skill**

张三打开 Studio，看到 skill 列表。他点"新建 skill"，在对话框里说：

> 我想做一个 skill，输入是产品参数表（JSON），输出一份面向普通消费者的产品说明书。说明书要分三段：产品亮点、使用场景、购买建议。

Copilot（在 Studio 侧边栏，或者在 PM 熟悉的 Cursor / Claude Code 里）接到描述后，会问几个问题确认细节（比如"说明书语气要正式还是活泼？""需不需要生成配图？"），然后自动生成初始 SKILL.md 文件。

张三点 Lint，看到绿色"通过"。

**Day 1 - 准备测试素材 + 打磨理想输出**

张三上传 3 份测试输入（iPhone 15 / 小米 14 Pro / 华为 Mate 60 的规格表）。

Studio 提示："在正式跑 skill 之前，建议先用这 3 份素材打磨一份你心目中的理想输出，之后每次跑都可以和它对比。"（这是 Studio 内置的方法论）

张三同意。Copilot 带他一起打磨 iPhone 15 的理想说明书 — **不是让 LLM 生成**，而是 PM 和 Copilot 一起讨论"你希望这份说明书长什么样"，手工把期望的输出字面写出来。三份素材都打磨完后，Studio 存为 "golden baseline"。

**Day 1 - 第一次跑**

张三点 [Run]，选 iPhone 15 规格表作为输入。Studio 右边的 Trace Timeline 实时展开：

- Phase 1：`extract_highlights`（提取产品亮点）— 3.2 秒
- Phase 2：`write_scenarios`（撰写使用场景）— 4.1 秒
- Phase 3：`synthesize_report`（合成最终说明书）— 2.8 秒

总耗时 10.1 秒，花了 1.5k tokens。

张三发现 Phase 2 的输出有点空洞。他点开这个 phase，在 Prompt Inspector 里看到 LLM 实际收到的 prompt（三个标签页：原始模板、变量字典、注入后最终文本）。**一看就明白了**：模板里没有告诉 LLM 要具体举例，LLM 就只写了抽象概念。

**Day 1 - 修改**

张三有两种改法：

- **方式一**：在 Studio 的 Monaco 编辑器里直接改 SKILL.md 源码，给 `write_scenarios` 的 `<system_prompt>` 加上"至少举 3 个具体使用场景"。保存后 Studio 立刻 Lint 通过
- **方式二**：张三更熟悉 Cursor，在 Cursor 里打开 SKILL.md 和 AI 对话："给 write_scenarios 加上 3 个具体场景的要求"。Cursor 改完保存，Studio 通过 FileWatcher 自动检测变更，立刻重新 Lint，画布上 Phase 2 亮一下表示"已更新"

两种方式都可以，Studio 不绑定任何一种编辑工具。

**Day 1 - 再跑一次**

张三又点 [Run]。新输出里 Phase 2 果然多了 3 个场景。他切到"对比"面板，选择"这次 run vs golden baseline"，Copilot 给出分析："本次输出覆盖了所有 golden 里的要点，但在第 2 个场景的描述上比 golden 更啰嗦。建议调整模板要求输出简洁。"

**Day 2 - 继续迭代**

张三按 Copilot 建议改 prompt，又跑了 5-6 次，每次都更接近 baseline。有一次他非常满意 — 他给这次 run 的目录加 `.golden` 后缀，锁定为"new baseline"。Studio 的 history 自动清理机制不会删这个目录。

期间有一次 Phase 3 因为 LLM 超时断了，张三不用重头跑 —— 在 History 面板点 [Resume]，skill 从 Phase 3 断点继续跑（前面 Phase 1/2 的产出保留），第二次成功。

**Day 3 - 交付**

张三用剩下两份测试素材（小米、华为）跑了一遍，结果都满意。他把 skill 交给工程师，**工程师直接部署到生产环境**（生产端同样从这个 SKILL.md 加载 skill 运行，没有任何代码差异）。

**整个流程里，工程师只在最后"部署"环节出现**。设计、修改、测试、打磨全部由 PM 张三独立完成，Studio 是他的辅助工具。

### 1.4 核心功能清单

按用户旅程组织 Studio 要提供的能力：

**创建类功能**：
- 新建 skill 向导（和 Copilot 对话生成初始 SKILL.md）
- skill 列表（看所有已有 skill）
- 从模板 Fork（把公共模板复制到自己的工作空间）

**浏览类功能**：
- 拓扑可视化（React Flow 画 phase 之间的依赖关系，subgraph phase 可以双击下钻看子 skill 的拓扑）
- 详情面板（看某个 phase 的 prompt / tools / validator / output schema 等所有配置）
- 跨 skill 导航（点 subgraph 跳到子 skill 的 Studio 视图）

**编辑类功能**：
- Monaco 源码编辑（直接改 SKILL.md）
- FileWatcher 响应外部编辑器（Cursor / Claude Code / VS Code 改了文件，Studio 自动刷新）
- 实时 Lint（编辑器边改边检查，错误可点击跳行）
- P2+ 探索结构化表单辅助编辑，但 SKILL.md 源码始终是单一事实源

**运行类功能**：
- 一键 Run（选输入、跑 skill、看实时 trace）
- Trace Timeline（WebSocket 流式展示每一步事件）
- Prompt Inspector（三标签页：原始模板 / 变量字典 / 注入后最终）
- 失败 phase 定位（哪个 phase 失败、失败原因、LLM 当时的 raw output）
- **重试可视化**（某个 phase 重试了 N 次、每次 validator 失败的原因、nudge 次数都在画布和 timeline 上标出）
- 成本/耗时面板（每次 run 消耗的 tokens 和时间）
- **断点重试 + 人工接入点**（Resume 按钮 / 改 context 后继续跑 / agent loop 问问题时 PM 回答）

**测试类功能**（体现"先打磨理想输出"方法论）：
- 测试素材管理（上传、存储、复用）
- Golden baseline 打磨（PM + Copilot 交互式产出理想输出）
- History 管理（每次 run 自动归档）
- 对比分析（选两次 run 对比，或选一次 run 和 baseline 对比，Copilot 给分析）
- `.golden` 锁定机制（重要 run 不被自动清理）

**协作类功能**：
- Copilot 集成（MVP1 阶段支持任何 coding assistant，通过 FileWatcher 响应变更；MVP3 做 CCB 式多 Copilot 切换，Gemini 做设计 + Claude Code 做实现）
- 共享/Fork（PM 之间分享 skill）
- User ID 隔离（P1.5 上线，每个 PM 一个独立工作空间）

### 1.5 差异化优势

**和 Dify / Coze / n8n / Langflow 等画布式 Agent 编排工具的区别**：

那些工具的节点是**原子组件**（"调 API 的节点"、"调 LLM 的节点"、"条件判断的节点"），业务逻辑分散在各个节点的配置里，节点之间用数据线连。这种模式对简单流程（客服机器人、邮件处理）够用，但碰到需要复杂推理、递归嵌套、多阶段协作的任务就力不从心。

Studio + graph_agent 的每个 phase 可以是一个完整的 Agent（有自己的 prompt、工具、validator、甚至可以递归嵌套另一个完整 skill），业务逻辑集中在 SKILL.md 声明 + Python 工具函数里，可以用 git 做版本管理。适合**复杂 Agent 工作流**（多步推理、长上下文、质量审核、递归分解）。

**和直接让 PM 学 Python 写 Agent 的区别**：

PM 写 Python 有学习成本，而且写出来的代码往往不够工程化（没有 trace、没有 callback、没有 validator 循环、没有模型 fallback）。Studio + graph_agent 把这些工程能力都内置了，PM 只管在 SKILL.md 里声明"我要做什么"，不用关心"怎么保证稳定性"。

**和在 Claude Code / Cursor 里直接编辑 SKILL.md 的区别**：

Claude Code 和 Cursor 是通用代码编辑工具，能改 SKILL.md 但不能给 PM 这些能力：看 skill 拓扑图、看实时运行 trace、看 Prompt Inspector 三标签页、对比多次 run 的结果、管 history 和 golden baseline、断点重试和人工接入。

Studio 做的是**运行观察 + 测试 + 基准管理**层面的事，Copilot 做的是**编辑辅助**层面的事，两者互补。PM 既用 Studio，也用 Copilot，不是二选一。

### 1.6 核心优势总结

| 优势 | 说明 |
|------|------|
| **标准化引擎：测试与生产一致** | PM 在 Studio 里测试通过的那份 SKILL.md，就是线上生产环境直接运行的代码。同一套底层引擎既跑测试也跑生产，**不存在"测试完工程师还要重写一遍生产代码"的二次工作**，也没有"开发重构导致逻辑变型"的风险。PM 测试满意那一刻就是上线那一刻 |
| **业务与核心解耦（职责分明）** | PM 在 SKILL.md 里安心写业务逻辑，工程师专心维护底层的 graph_agent 引擎和内置工具。**PM 改不到系统核心代码**，不用担心把系统弄崩；工程师也不用反复看 PM 的业务逻辑帮忙加 phase。各自做擅长的事，不再错位沟通 |
| **快速迭代与极短反馈流** | PM 从"写需求等工程师排期"变成"边改边测立刻看结果"。改完 prompt 一键 Run，Trace Timeline 马上展开，Prompt Inspector 能看到 LLM 实际收到的每一个字。**这条反馈流的短度直接决定了 PM 的迭代效率** |
| **支持复杂任务的 Agent-Loop** | 内置认知循环约束：强制 LLM 先写 working memory 规划、再调工具执行、最后结构化 finish_task 自检。针对主观审美任务（文案、剧本、质量审核），通过模板化 Prompt 架构 + 专业 validator 节点，agent loop 在最后一公里拿到远超单次 LLM 调用的结果 |
| **多模型与格式自愈（md2json）** | 允许 LLM 用自然的 Markdown 交流，底层通过 `md2json` 强转 JSON。像 DeepSeek 这类逻辑强、便宜、可本地部署但 JSON 格式偶尔出错的模型，因为有这层自愈能够进入严谨生产流水线，**扩大了框架可用的模型池** |
| **Copilot 分工集成** | 终极形态支持 Gemini 做深度技能方案设计（专业领域分析、方法论讨论），Claude Code 做严谨实现（把设计翻译成规范 SKILL.md）。PM 可切换使用不同 Copilot，MVP 阶段通过 FileWatcher 用任何自己熟悉的编辑器 |

---

## 第二部分：graph_agent 和 skill 基础概念

### 2.1 白话版（写给 PM 看）

#### 什么是 graph_agent

graph_agent 是一个跑多阶段 Agent 的引擎。你可以把它理解成一个"说明书执行器"——你写一份说明书（SKILL.md），告诉它"这个任务要分几步、每一步要做什么、用哪些工具、用什么模型、失败了怎么办"，它就按说明书一步一步执行。

它和 ChatGPT 之类的"一次对话一次回答"不一样。graph_agent 适合**复杂任务**——任务需要拆成多步、每步的输出是下一步的输入、有些步骤要做质量审核、失败了要重试。

#### 什么是 skill

一个 skill 就是一份 SKILL.md 文件 + 一些 Python 工具代码。SKILL.md 是**给 graph_agent 看的说明书**，Python 工具代码是**说明书里会被调用的具体功能**（比如"读取文件"、"调外部 API"）。

一个 skill 放在自己的目录里。典型的 skill 目录长这样：

```
skills/my-skill/
├── SKILL.md                    # 说明书
├── script/                     # Python 工具代码
│   └── my_tools.py
├── references/                 # （可选）参考资料，比如规则文档
│   └── rules.md
└── data/                       # （可选）参考数据
```

一个项目里可以有很多 skill，它们可以互相调用（一个 skill 的某一步可以"跳到"另一个 skill 跑完再回来）。

#### SKILL.md 长什么样

SKILL.md 分两部分：**顶部**是 YAML 格式的元数据（叫 frontmatter），写这个 skill 叫什么、描述什么、需要什么输入、产出什么输出；**下面**是 XML 风格的标签，每个标签定义一个 phase 的具体行为。

最简单的例子：

```markdown
---
name: hello-world
description: 最简单的打招呼 skill
type: simple
io:
  inputs:
    - name: user_name
      type: str
      source: runtime
---

<phase_config>
name: greet
tier: balanced
tools:
  - script.greet.generate_greeting
</phase_config>

<system_prompt>
你是一个友善的助手。请调用 generate_greeting 工具生成问候语，然后调用 finish_task 结束。
</system_prompt>

<user_prompt>
请为 {user_name} 生成问候语。
</user_prompt>
```

这个 skill 只有一个 phase（greet），要求 agent loop 调用一个叫 `generate_greeting` 的 Python 工具函数生成问候语。Python 工具函数在 `script/greet.py` 文件里，由 Copilot 根据 skill tools 规范编写，写完由 compiler 编译校验保证格式正确。

#### Phase 的三种模式

每个 phase 是三种模式之一：

- **Agent-Loop 模式**：如果你发现"只让大模型回答一次，结果总是有点粗糙或者少点什么"，那就用这个模式。在这个 phase 里，大模型不是简单地"一问一答"，而是会被引擎**强迫按你设定的 step 来执行**：先写规划、再调用工具查资料、最后按给定的标准做自我检查。这个闭环让 agent loop 在最后一公里拿到比单次 LLM 调用更靠谱的结果，适合**主观审美要求高、非严谨逻辑推导**的任务（比如文案打磨、剧本改编、质量审核）。写了 `<system_prompt>` 标签就是这种模式。
- **Subgraph 模式**：这个 phase 直接委派给另一个完整的 skill 去跑。`<phase_config>` 里写 `subgraph: 另一个 skill 的路径`。PM 做 "pipeline 编排" 的时候用这个，让某一步调用一个成熟的子 skill。
- **Code-only 模式**：这个 phase 只是纯计算（不需要 agent loop），框架直接按顺序跑 tools 列表里的 Python 工具函数。适合"准备数据"、"合并结果"这种不需要 LLM 判断的步骤。

三种模式**互斥**，一个 phase 只能是其中一种。这是框架的硬规则（见 `docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md` 第 4 节）。

#### 一个 skill 怎么调用另一个 skill

两种方式：

**方式一：静态委派（subgraph 模式）**

在父 skill 的某个 phase 里写 `subgraph: ../child-skill/SKILL.md`，运行到这一步就去跑子 skill。这是"确定性"的 —— 父 skill 一定会调用子 skill，不可跳过。

**方式二：动态工具调用（sub_skills 或 builtin parallel_map）**

在父 skill 的某个 Agent-Loop 模式 phase 里声明子 skill 作为"工具"，让 agent loop 在对话中自己决定调不调、什么时候调、参数是什么。适合"PM 也不确定要不要调子 skill、让 agent loop 判断"的场景。

`builtin parallel_map` 是 graph_agent 内置的一个工具，专门用于**并发调用同一个子 skill 多次**的场景 —— 比如"对一批 scene 分别提取 beats"，agent loop 调一次这个内置工具就能并发跑多次子 skill，不用手写 Python 胶水。**默认并发数 3**（和 DeerFlow 内置 subagent 一致，保守起步，后续视稳定性再逐步放开）。

#### 一个 skill 怎么跑

三种跑法：

- **独立跑**：任何 skill 都可以独立运行 `run_skill("skills/my-skill/SKILL.md", input_data)`，不需要父 skill。独立跑的时候产出落到 Studio 约定的工作空间里
- **被嵌入跑**：这个 skill 被另一个 skill 用 `subgraph:` 委派调用，作为父 skill 流程的一部分
- **生产环境跑**：production 环境用同样的 `run_skill()` 接口，产出路径由 production 代码决定（比如写到数据库、写到 S3）

**同一份 SKILL.md 这三种场景下行为完全一致**，只是产出去哪不同。Studio 负责独立跑的场景，production 代码负责生产环境跑的场景。**这也是 Studio 最大的优势之一** — PM 在 Studio 里测试通过的 SKILL.md 就是生产直接跑的文件，不存在"测试版和生产版代码不一致"的问题。

#### 两种把 SKILL.md 拆文件的方式的区别

在 SKILL.md 里有两个机制看起来都像"引用另一个文件"，但作用完全不同：

- **`<ref path="phases/01_setup.md" />`** 是**纯文件拼接**。parser 看到这个标签就去读那个文件的内容，**把文件内容整个贴进当前位置**，拼完一个大字符串后再交给 loader。它的作用只是"主 SKILL.md 太长不好读，拆到几个子文件"。拆和不拆**运行时行为完全一样**
- **`subgraph: 另一个 skill 的路径`** 是**委派另一个独立 skill 跑**。loader 递归加载另一个完整 SKILL.md 成为一个子 harness，运行时这个 phase 跑起来会完整跑一遍子 skill 的所有 phase。子 skill 可以独立测试、独立复用

**建议**：默认**不用** `<ref>`（所有 phase 直接 inline 写在主 SKILL.md 里），只有当某个 phase 的 prompt 特别长（超过 100 行）才用 `<ref>` 拆文件。这样 skill 结构最清楚，Copilot 生成也最稳定。**需要组合复用别的 skill 时用 `subgraph:` 或 `sub_skills:`**，不要用 `<ref>` 去模拟 skill 组合。

#### 系统级标准

graph_agent 在工程层面有几条硬性规定，帮 PM 省掉很多后期返工。

**① 输入输出严格定义 + phase 间 context 必须对得上**

每个 skill 的 `io.inputs` 和 `io.outputs` 都要显式写清楚（字段名、类型、来源）。phase 之间通过一块叫 **context** 的"大黑板"传数据 —— 第一个 phase 把结果写在黑板上，第二个 phase 从黑板上读出来接着干活。**每个 phase 声明的输入字段必须在前面某个 phase 的输出里出现过**，否则 compiler 直接 Lint 失败（规则 P006）。这种严格匹配让 PM 不会写出"第二步要用一个第一步没产出的字段"这种运行时才暴露的隐蔽错误。

Studio 的画布会把 phase 间的 context 字段匹配关系可视化（哪个字段从哪个 phase 流到哪个 phase），PM 一眼就能看出数据流是否通畅。

**② md2json 格式自愈**

在多 phase 的工作流里，上一个 phase 要给下一个 phase 输出严谨的结构化数据（JSON 字段），下一个 phase 的 Python 代码才能消费。但对于主流大模型来说，**强制直接吐出完美无缺的巨大 JSON 效果很差** —— LLM 天然更习惯用 Markdown（列表、小标题、`key: value` 这种）表达复杂内容。

这里最典型的例子是 **DeepSeek**。DeepSeek **逻辑推理强、价格低廉、稳定、支持本地部署**，是批处理和复杂推理的首选模型。但它有一个致命痛点：**JSON 格式经常出错**（少写括号、转义失败、在 JSON 里夹杂分析过程）。这让 DeepSeek 在很多严谨生产流水线里变得不可用。

`md2json` 工具就是为了解决这个痛点而生的。在 SKILL.md 里你让 DeepSeek 自然地用它最擅长的 Markdown 格式输出分析过程和结果，底层引擎自动调用 `md2json` 把这段 Markdown 文本"翻译"并校验成严谨的 JSON 数据。

即使遇到 ~5-10% 的极端格式错误情况，系统会无缝触发 `md-patch` 做精准的**局部外科手术式修复**（surgical repair），修复的只是错字段，不用重跑整个长耗时任务。

通过这一机制，**DeepSeek（以及具有类似特性的 Gemini 等模型）从"不可用于严谨工作流"变成了"主力且可靠的生产模型"**，极大降低了复杂 Agent 应用的运行成本。

**③ Phase 三模式互斥强约束**

一个 phase 要么是 Agent-Loop 模式，要么是 Subgraph 模式，要么是 Code-only 模式。PM 在 Studio 里用 Copilot 新建 phase 时，Copilot 会让 PM 先选模式，然后只给他填这个模式相关的字段，避免模式混搭导致的静默错误。这条硬约束保证每个 phase 的职责唯一，不会出现"这个 phase 又想委派给子 skill 又想自己跑 LLM"的模糊状态。

#### 断点重试和人工接入点

跑一个复杂 skill 经常会遇到"跑了 10 分钟在第 5 个 phase 断了"或"agent loop 需要 PM 帮忙判断一个分类问题"。graph_agent 对这类场景提供了完整的支持。

**① Graph 层断点**

如果某个 phase 因为 validator 校验失败、工具异常、网络问题等导致失败，Studio 不会要求 PM 从头重跑。PM 在 History 面板里看到失败的那次 run 后，可以点 **[Resume]** 按钮从失败的 phase 重新开始 —— 前面已经跑完的 phase 的产出全部保留，只重跑断掉的那一段。底层靠 LangGraph Checkpointer 持久化每个 phase 完成后的完整 state，`thread_id` 唯一定位。

**② Agent Loop 层 checkpoint**

上面的 Graph 层断点是"整个 phase 失败了重跑"。更细一层是：在某个 Agent-Loop 模式的 phase 内部，agent loop 本身也会每一轮（每次 LLM 调用后）持久化 state。即使 phase 执行中途异常退出，重跑时可以从 agent loop 的上一轮继续，而不是从这个 phase 的第一轮从头开始。

**③ 人工接入点（Human-in-the-loop）**

agent loop 遇到**需要人判断的问题**时可以主动暂停等 PM 输入。skill 里的 Python 工具可以调用 `request_human_input()` 或 `ask_clarification()` 让 agent loop 暂停。Studio 检测到暂停后弹窗："agent 问你一个问题：XX。请回答："PM 输入答案后点 [Resume]，答案作为 ToolMessage 注入回 agent loop 继续跑。

这个能力对"主观审美任务"特别关键 —— 比如 skill 处理到"从三个方向中选哪一个"时让 PM 决策，而不是 agent loop 自己瞎猜。

**PM 手动接入**：更进一步，PM 可以主动在某次 run 里暂停，手动改 context 里某个字段（比如改 prompt、替换某个 phase 的输出），然后 Resume 继续跑。这给 PM 提供了"快速测试不同参数对后续结果影响"的灵活性，特别适合 Golden Baseline 打磨阶段反复微调。

断点重试和人工接入点的 UI 在 **MVP2** 交付（底层机制 graph_agent 已完整提供，Studio 只做 UI 暴露）。

#### 几个你会经常听到的词

- **Phase**：skill 的一个执行阶段，是框架的最小执行单元。在 SKILL.md 里用 `<phase_config>` 标签声明；`type: graph` 的 skill 用 `<phase>` 标签把多个 phase 串起来，phase 之间通过 `depends_on` 声明依赖关系
- **Tool**：Python 函数，被 agent loop 在 Agent-Loop 模式的 phase 里调用
- **Validator**：校验函数，检查 phase 输出是否合格，不合格就触发重试
- **Context**：phase 之间传递数据的"大黑板"。每个 phase 读写这个 context
- **Context Bridge**：父子 skill 之间传数据的映射规则（父 skill 的哪个字段传给子 skill 的哪个输入，子 skill 的哪个字段回写到父 skill 的哪个字段）
- **Artifact**：phase 的产出物，可以落盘为文件（JSON、文本、图片等）
- **Trace**：一次 run 的完整执行记录（每一步的 prompt、LLM 回答、工具调用、耗时、tokens）
- **Run ID**：一次运行的唯一标识，Studio 用它区分历次运行
- **Checkpoint**：某次 run 中某个 phase 完成后或 agent loop 某一轮后持久化的完整 state，可用于断点续跑
- **Golden baseline**：PM 手工打磨好的"理想输出"，之后每次 run 都和它对比

### 2.2 技术版（写给开发人员看）

以下是给开发者的 graph_agent 技术细节。完整的框架机制讲解见 `docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md`。这里只做要点重复。

#### 核心架构（双层控制）

- **外层 GraphAgentHarness**（`src/core/graph_agent/core/harness.py`）：LangGraph 驱动的 phase 编排 + planning nudge + selfcheck nudge + checkpoint compaction + finish gate
- **中间层 Middleware**（`cognitive/middlewares.py`）：WorkingMemory / DeadEndPruning / Clarification / DanglingToolCall
- **内层 DeerFlow Agent Loop**（vendored in `deerflow/`）：LLM 调用 + tool 执行 + 流式输出

#### SKILL.md 的 6 种标签

| 标签 | 用途 | 处理代码 |
|------|------|---------|
| `<phase>` 或 `<phase_config>` | phase 定义或配置 | `core/parser.py` 正则提取 + `core/loader.py` YAML 解析 |
| `<system_prompt>` | Agent-Loop 模式的系统 prompt | `core/loader.py` 读入 `Phase.system_prompt` |
| `<user_prompt>` / `<user_prompt_builder>` | 用户 prompt 模板，支持 `{key}` 占位符 | 同上 |
| `<data_architecture>` | 数据结构说明（给 LLM 看） | 同上 |
| `<ref path="..." />` | 文件级字符串替换 | `core/parser.py` L160-186 `_resolve_refs()` |
| （frontmatter）| YAML 元数据 | `core/parser.py` YAML load |

#### Phase 三模式的代码依据

`core/loader.py` L565：

```python
requires_llm = (system_prompt is not None) and (subgraph_harness is None)
```

执行器二分在 `core/harness.py` L384-387：

- `phase.subgraph is not None` → `_build_subgraph_node(phase)` → `subgraph.py:build_subgraph_node()` → `child.run()`
- `phase.requires_llm` → `_build_phase_node(phase)` → DeerFlow agent loop
- 否则 → `_build_code_only_node(phase)` → 顺序调用 tools

#### 断点重试和人工接入的代码依据

- **Checkpointer 支持**：`deerflow/config/checkpointer_config.py`（memory/sqlite/postgres 三种 backend），`deerflow/agents/checkpointer/provider.py` + `async_provider.py`
- **Harness 调用**：`core/harness.py` L159-186 默认 `checkpointer="auto"`，L413 `graph.compile(checkpointer=self._checkpointer)`
- **Resume 接口**：`core/harness.py` L320-380 的 `resume(state, human_input, thread_id, ...)` 方法，自动找到最近的 `request_human_input` tool_call，注入 ToolMessage 后从 checkpoint 继续
- **Clarification 中断机制**：`deerflow/agents/middlewares/clarification_middleware.py` L84-151，通过 LangGraph `Command(goto=END)` 实现异步等待

#### 几条硬红线

1. 不改 DeerFlow 源码（所有增量走外层 wrapper）
2. Framework 不执行业务逻辑（F006 规则：`context_mapping` 禁止 `$func()`）
3. Kitchen-Pass 出餐口模式（framework 不依赖 host project 的存储实现）
4. 双层认知控制架构（外层 / 中间层 / 内层 三层分工）
5. 认知控制权唯一（Phase 三模式互斥）
6. SKILL.md 跨工具可移植（graph_agent + Claude Code + Cursor 共用格式）

---

## 第三部分：Studio MVP Roadmap 和需求

这部分只讲 **Studio 本身的实现**。

### 3.1 整体节奏

| 阶段 | 名称 | 时长估计 | 交付目标 | 有无硬 gate |
|------|------|---------|---------|-----------|
| MVP1 | 最小可用（单用户） | 6 周 | PM 能跑通设计 → 修改 → 测试完整闭环 | 无 |
| MVP2 | 测试增强 + 断点重试 + Copilot 进阶 | 5 周 | PM 能 Golden baseline 方法论迭代 + 断点续跑 + 人工接入 | 无 |
| MVP3 | CCB 式多 Copilot + 意图偏离检测 | 4 周 | Gemini 做设计 + Claude Code 做实现的双对话框协作 | 无 |
| P1.5 | 用户隔离 | 2 周 | PM 之间互不干扰 | **强制 gate**：启动前必须通过 dogfood 验证 |
| P2+ | 按真实反馈决定 | — | — | — |

MVP1 + MVP2 + MVP3 加起来约 15 周，加上 P1.5 共 17 周左右。

### 3.2 MVP1：最小可用（6 周）

#### 3.2.1 MVP1 交付目标

PM 能在 Studio 里完成以下事情：
- 看到所有已有的 skill（列表 + 每个 skill 的拓扑图）
- 新建一个 skill（通过 Copilot 对话生成 + Studio 模板辅助）
- 直接在 Studio 里改 SKILL.md 源码（Monaco 编辑器），或者在外部工具（Cursor / Claude Code / VS Code）里改，Studio 自动检测变更并重新 Lint
- 跑 Lint（一键，错误可点击跳行）
- 跑 skill（一键，看实时 trace）
- 看 trace 每一步（phase_start/end / LLM 调用 / tool 调用 / validator 结果 / 失败节点）
- 看 Prompt Inspector 三标签页（原始模板 / 变量字典 / 最终注入文本）
- 看每次 run 的产出文件（StorageManager 自动落盘）
- 看每次 run 的 tokens 和耗时

#### 3.2.2 MVP1 功能清单

**前端（Web UI，本地浏览器访问）**：
- skill 列表页 `/` — 扫 `skills/` 目录返回 skill 卡片列表
- skill 详情页 `/skills/{id}` — React Flow 只读画布 + 右侧详情面板 + Monaco 编辑器 + Trace Timeline + Run 按钮
- Monaco 源码编辑器 — 编辑当前选中的 SKILL.md，保存后触发 Lint
- 只读 React Flow 画布 — 渲染 phase 拓扑，subgraph phase 用特殊样式标记，点击 phase 展开详情
- 详情面板 — 展示 phase 的 `<system_prompt>` / `<user_prompt>` / tools / validator / output_schema 等
- Trace Timeline — WebSocket 订阅 CallbackEvent 流，按时间顺序展示
- Prompt Inspector 弹窗 — 点击 `prompt_captured` 事件打开，三标签页对比
- 成本/耗时小面板 — 每次 run 结束后显示 tokens / elapsed

**后端（本地 FastAPI server，单用户，port 8787）**：
- `GET /api/skills` — 扫 skills/ 目录返回 skill 列表
- `GET /api/skills/{id}` — 返回单个 skill 的完整信息（从 `load_workflow_from_md()` 拿 harness 实例的结构化描述）
- `POST /api/skills/{id}/lint` — 调用 `compile_skill()`，返回结构化的错误列表（含行号）
- `POST /api/skills/{id}/run` — 后台 spawn 一个 subprocess 跑 `run_skill()`，返回 run_id；WebSocket `/ws/run/{run_id}` 推送实时事件
- `GET /api/skills/{id}/runs` — 列出某个 skill 的所有历史 run（从 StorageManager 的目录结构读）
- `GET /api/skills/{id}/runs/{run_id}` — 返回某次 run 的完整 trace.jsonl + final context + artifacts 列表
- FileWatcher — 后台监听 `skills/` 目录，文件变更通过 WebSocket broadcast `skill_changed` 事件给所有连接的前端
- `POST /api/skills/{id}/new` — 新建 skill（从模板 Fork 或通过 Copilot 生成）

**Copilot 基础资产**（MVP1 也要做）：
不强制使用，但提供给 PM 选用。PM 在任何支持 skill 的 Copilot 工具（Claude Code / Cursor）里加载这些 skill，就获得 graph_agent 专属的新建/扩展能力：
- `create-skill` skill — 从自然语言描述创建新 skill 的向导（会问：几个 phase、每个 phase 是什么模式、要不要 subgraph 嵌套子 skill）
- `add-phase` skill — 给现有 skill 插入新 phase，自动处理 `depends_on` 和 context 字段串接

**必要的集成工作**：
- 前端通过 HTTP + WebSocket 连接后端
- 后端调用 graph_agent 的 public API（`run_skill`、`compile_skill`、`load_workflow_from_md`）
- 后端订阅 graph_agent 的 CallbackEvent，转发给前端
- Monaco 编辑器集成 SKILL.md 的 syntax highlighting（基础 Markdown + XML 标签高亮）

#### 3.2.3 MVP1 明确不做的事

- 不做 user 隔离（所有人共用 `skills/` 和 `workspaces/default/`，P1.5 做）
- 不做 Golden baseline 打磨工作流（MVP2 做）
- 不做 history 对比面板（MVP2 做）
- 不做断点重试和人工接入点 UI（MVP2 做）
- 不做 Copilot 进阶 skill 集（refactor-phase、convert-to-subgraph、slash commands 放 MVP2）
- 不做 CCB 式多 Copilot 双对话框切换（MVP3 做）
- 不做结构化表单辅助编辑（P2+ 探索）
- 不做画布拖拽改 DSL（MVP1-MVP3 都不做，画布只读）
- 不做意图偏离检测（MVP3 做）

#### 3.2.4 MVP1 的 UI 草图（文字描述）

**页面 1：skill 列表**

```
┌────────────────────────────────────────────────────┐
│ Skill Studio                            [+ 新建]    │
├────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│ │text-segm.│ │ event-ex.│ │batch-ana.│            │
│ │3 phases  │ │4 phases  │ │5 phases  │            │
│ │ [Lint]   │ │ [Lint]   │ │ [Lint]   │            │
│ │ [Run]    │ │ [Run]    │ │ [Run]    │            │
│ └──────────┘ └──────────┘ └──────────┘            │
└────────────────────────────────────────────────────┘
```

**页面 2：skill 详情（左-画布 + 中-编辑器 + 右-trace）**

```
┌────────────────┬─────────────────┬──────────────────┐
│ React Flow     │ SKILL.md        │ Trace Timeline   │
│ (phase 拓扑)   │ (Monaco 编辑器) │ (WebSocket 流)   │
│                │                 │                  │
│ ┌──────┐       │ ---             │ ▶ phase_start:  │
│ │phase1│       │ name: my-skill  │   segmentation   │
│ └──┬───┘       │ type: graph     │ ▶ llm_call:     │
│    │           │ ---             │   1.2k tokens    │
│ ┌──▼───┐       │                 │ ▶ prompt_capt:  │
│ │phase2│       │ <phase id="...  │   [click to see] │
│ └──────┘       │ ...             │ ▶ finish_task   │
│                │                 │                  │
│ [Lint]  [Run]  │                 │ Tokens: 2.3k     │
│                │                 │ Time: 8.2s       │
└────────────────┴─────────────────┴──────────────────┘
```

### 3.3 MVP2：测试增强 + 断点重试 + Copilot 进阶（5 周）

#### 3.3.1 MVP2 交付目标

两大目标：
1. PM 能在 Studio 里运用"先打磨 Golden baseline 再测试"的方法论，形成"改 → 跑 → 对比 → 迭代"的回归工作流
2. 长耗时 skill 跑飞或 agent loop 需要人工判断时，PM 能**断点续跑 + 人工接入**，不用从头重跑

#### 3.3.2 MVP2 功能清单

**测试类新增功能**：
- 测试素材管理面板（`skills/{id}/test_inputs/`，上传 / 查看 / 命名 / 删除）
- Golden baseline 打磨工作流
  - PM 选一份测试素材
  - Studio 引导："先打磨一下你期望的输出？"
  - 进入打磨页面（PM + Copilot 合作产出 golden JSON / Markdown）
  - 存到 `skills/{id}/golden/<input_name>/baseline.json`
- Run 时可选"对比 golden baseline"
  - 跑完后 Studio 把 run 的产出和 baseline 自动 diff
  - Copilot 分析差异给出评述（"本次输出覆盖所有 golden 要点但结构稍偏"）
- History 面板
  - 看某个 skill 的所有历次 run
  - 每次 run 可点击查看完整 trace / artifacts / metrics
  - 可以选两次 run 对比（Copilot 辅助分析差异）
- `.golden` 锁定 UI
  - PM 在 History 面板里选中某次 run 点"锁定为 golden"
  - Studio 把目录重命名加 `.golden` 后缀
  - 清理机制自动跳过 `.golden` 目录
- FileWatcher 自动 Lint 提示
  - FileWatcher 检测到 SKILL.md 变更后，自动触发一次 Lint
  - 右下角 toast 显示 Lint 结果（绿/红）

**断点重试和人工接入点（新增，三合一）**：
底层机制 graph_agent 完整提供（LangGraph Checkpointer + `harness.resume()` + `request_human_input` / `ask_clarification` 工具），MVP2 做对应的 UI 层暴露。
- **Resume 按钮**：History 面板里看到失败或被中断的 run，点 Resume 从失败 phase 重新开始跑；前面成功 phase 的产出保留
- **改 context 再 Resume**：PM 可以在 Resume 之前展开某个 phase 产出的 context 字段，手动修改某个值（比如改 LLM 上一轮输出的文本、替换某个 dict 字段），然后继续往下跑
- **人工接入答题**：skill 里的 Python 工具调用 `request_human_input()` 或 `ask_clarification()` 暂停 agent loop 时，Studio 弹窗显示问题，PM 输入回答后点 Resume，答案作为 ToolMessage 注入回 agent loop

**Copilot 进阶资产（MVP2 新增）**：
- `refactor-phase` skill — 重构某个 phase（改 prompt / 改 tools / 加 validator），保持 phase 的 input/output 契约
- `convert-to-subgraph` skill — 把 code-only phase 里用 Python 胶水调用其他 skill 的代码改造成 `subgraph:` 声明式组合
- `/lint` slash command — 一键跑 compiler，输出错误清单
- `/run-phase <phase_name>` slash command — 单独跑某个 phase 调试
- `/explain-trace` slash command — 读最近一次 trace 用自然语言解释每一步
- `/compare-with-golden` slash command — 跑当前 skill 和 golden baseline 对比

#### 3.3.3 MVP2 不做的事

- 不做完整的 diff 算法（用简单 JSON diff 或文本 diff，复杂语义 diff 交给 Copilot 的 LLM 判断）
- 不做自动化回归（MVP2 是手动对比，自动化 P2 考虑）
- 不做可视化的"哪一个 phase 导致输出变差"归因（依赖 trace 自己判断，P2 考虑加 phase 级 diff）
- 不做 CCB 式双 Copilot 切换（MVP3 做）
- 不做意图偏离检测（MVP3 做）

### 3.4 MVP3：CCB 式多 Copilot + 意图偏离检测（4 周）

#### 3.4.1 MVP3 交付目标

PM 在 Studio 里形成 **Gemini 做深度设计 + Claude Code 做严谨实现** 的分工协作工作流；agent 的实际行为是否和 SKILL.md 声明的意图一致可以被自动检测。

#### 3.4.2 MVP3 功能清单

**CCB 式多 Copilot 切换**：
- Studio 侧边栏提供 Copilot 对话框，PM 可以在一个界面里和两个 Copilot 协作
- 支持多 Copilot backend：Claude Code SDK + Gemini CLI（通过 CCB 协议桥接）
- **分工协作模式**：
  - **Gemini 做设计**：PM 和 Gemini 讨论业务需求、方法论、领域专业知识 → 产出设计文档或 skill 结构草案
  - **Claude Code 做实现**：把 Gemini 的设计交给 Claude Code，Claude Code 按 skill tools 规范把设计翻译成规范的 SKILL.md
  - PM 可以随时在两个 Copilot 之间切换，也可以让一个 Copilot 直接把上下文传给另一个
- PM 也可以只用一个 Copilot（不强制分工）

**意图偏离检测**：
- 对比 SKILL.md 里 `<description>` 声明的意图 + `plan_checklist`（来自 finish_task）vs 实际 trace
- 高亮跑题的步骤、不在计划里的工具调用、没按顺序执行的 phase
- Copilot（LLM judge）给出偏离度评分和建议修复方向
- PM 可以在 History 面板里对任何一次 run 触发"跑意图偏离检测"

**自动运行报告**（提前做）：
- Run 结束后可导出 HTML 报告（耗时/tokens/成本分布、validator 通过率、重试次数、nudge 次数、fallback 发生次数与原因）
- 方便 PM 分享给团队或写评估文档

#### 3.4.3 MVP3 不做的事

- 不做 Agent 行为 vs 设计意图的实时干预（只检测不实时打断）
- 不做完整的 Golden set 自动化回归（P2+）
- 不做团队协作功能（评论、diff 审批，P2+）

### 3.5 P1.5：用户隔离（2 周，强制 dogfood gate 之后开始）

#### 3.5.1 P1.5 交付目标

多个 PM 同时用 Studio 互不干扰。每个 PM 有自己的 skill 工作空间，看到的 skill 列表是自己的，跑 skill 的产出也只写入自己的目录。

#### 3.5.2 P1.5 功能清单

- 文件系统：`workspaces/<user_id>/skills/` 是每个 PM 的私人 skill 目录
- 文件系统：`skills/` 顶层目录改为只读的"公共模板库"（PM 可以 Fork 到自己的 workspace）
- 认证：HTTP header `X-Studio-User-ID` 标识用户（不做真 SSO，只是"声明身份"，适合 trusted 内部环境）
- 前端登录页：PM 输一个用户名存 localStorage，以后请求都带这个 header
- 后端 API：所有 API 接受 `X-Studio-User-ID` header，返回该 PM 的 workspace 里的数据
- Fork 功能：PM 在公共模板上点 "Fork to my workspace"，把模板复制到自己的 skills 目录下
- StorageManager：`workspace_root` 参数由 Studio 后端拼好（`workspaces/<uid>/`）传给 `run_skill()`

#### 3.5.3 P1.5 的硬 dogfood gate

**P1.5 启动前的强制条件**：
- MVP1-MVP3 交付完成
- 2-3 个真实 PM 做过至少 2 周的 dogfood
- 收集到的指标包括：PM 自主完成 skill 改动的成功率、Lint 首次通过率、UX 摩擦点 top 3
- 指标满足预设阈值（阈值在 MVP3 最后一周由内部工程师模拟 PM 校准）

不满足上述条件**不允许启动 P1.5 的任何开发**，先改进 MVP1-MVP3。

### 3.6 P2+：按真实反馈决定

以下是**候选方向**，不是承诺清单。P1.5 结束后根据 PM 反馈从中选 1-2 个做：

- 结构化表单辅助编辑（把常见字段做成表单控件补充 Monaco 源码模式）
- Working Memory 一致性评分（PM 在 skill 设计目标 vs agent 实际写入的 working_memory，维度评分）
- 自动化 Golden set 回归（每次改动自动跑所有 golden，diff 高亮）
- Agent 行为 vs 设计意图实时干预（检测到偏离主动打断）
- 画布部分编辑能力（拖拽 phase 顺序、增删 subgraph phase、改 retry_target）
- 团队协作（PM 之间分享 skill、评论、diff 审批）

### 3.7 需求矩阵（映射到 plan.md 原始需求）

| 原始需求（plan.md） | 在 Studio 的哪个阶段落地 | 交付形式 |
|------|--------|---------|
| R1 PM 最后一公里（不写 Python）| 贯穿 MVP1-P1.5 | 整个 Studio 的存在 |
| R2 任何 PM 动手的地方都是 markdown 或可视化 | MVP1 | Monaco + React Flow 只读画布 |
| R3 PM 快速创建 skill | MVP1 | 新建 skill 向导 + create-skill Copilot 辅助 skill |
| R4 PM 修改 skill | MVP1 | Monaco + FileWatcher + add-phase Copilot skill |
| R8 直观看到 LangGraph 图 | MVP1 | React Flow 画布 |
| R9 能看到每个 agent/skill 内容 | MVP1 | 详情面板 + 只读 Monaco |
| R10 设置系统输入 | MVP1 | Run 对话框的输入选择器 |
| R11 管理输入/输出路径 test | MVP1 + MVP2 | StorageManager 默认路径 + 测试素材管理 |
| R12 每步操作 trace | MVP1 | Trace Timeline + WebSocket |
| R13 每个 phase 的输入输出标准 | MVP1 | 详情面板展示 io / output_schema |
| R14 LLM fallback 排序展示 | MVP3 | 成本/耗时面板扩展 |
| R15 熔断情况展示 | MVP3 | 成本/耗时面板扩展 |
| R19 Run 实时 metrics | MVP1 | 成本/耗时小面板 |
| R20 Token 和耗时记录 | MVP1 | 成本/耗时小面板 + trace 持久化 |
| R21 回放模式 | MVP2 | History 面板 + trace 回放 |
| R22 每步快照 | MVP2 | History 面板的对比视图 |
| R23 Prompt 三标签页 | MVP1 | Prompt Inspector 弹窗 |
| R24 Agent loop 步骤可视化 | MVP1 | Trace Timeline |
| R25 自动运行报告 | MVP3 | HTML/JSON 导出 |
| R26 意图偏离检测 | MVP3 | LLM judge + plan_checklist 对比 |
| R27 Working Memory 一致性评分 | P2+ | LLM judge |
| R28 Golden set 回归 | MVP2 | Golden baseline 打磨 + 对比分析 |
| R29 Copilot 集成 Claude Code / Gemini CLI | MVP1 基础（通用）+ MVP3 深度（CCB 式切换）| FileWatcher + CCB 多 Copilot |
| R30 Copilot 加强 skill/command | MVP1 基础（create/add-phase）+ MVP2 进阶（refactor/convert + slash commands） | 辅助 skill + slash command 集 |
| R37 User ID 隔离 | P1.5 | workspaces/<uid>/ + HTTP header |
| 新方法论 打磨理想输出作 baseline | MVP2 | Golden baseline 打磨工作流 |
| 断点重试 + 人工接入点 | MVP2 | Resume UI + 改 context + 人工答题 |

### 3.8 Studio 的技术栈

- **前端**：React 18 + Vite + TypeScript + React Flow（只读画布）+ Monaco Editor + xterm.js（MVP3 的 CLI）
- **后端**：Python 3.12 + FastAPI + uvicorn + WebSocket
- **文件监听**：watchdog（Python 标准库兼容）
- **Copilot 集成**：FileWatcher（MVP1）+ Claude Agent SDK / Gemini CLI 子进程通过 CCB 协议桥接（MVP3）
- **本地部署**：`graph-agent-studio serve --port 8787` 启动本地 server，浏览器访问 `http://localhost:8787`

### 3.9 Studio 和 graph_agent 引擎的依赖关系

Studio 是 graph_agent 的 **纯消费者**，只通过公开 API 和框架交互：

- `from graph_agent import run_skill, compile_skill, load_workflow_from_md` — Studio 后端调用这些 API
- `graph_agent.callbacks.base.Callback` — Studio 实现自己的 Callback 订阅事件
- `graph_agent.io.StorageManager` — Studio 用这个管产出落盘
- `graph_agent.core.harness.GraphAgentHarness.resume()` — Studio 的 Resume 按钮调用这个

Studio 永远不碰 graph_agent 的内部实现（不改 DeerFlow、不改 loader / harness / compiler），只从 public API 消费。

---

## 第四部分：附录

### 4.1 读者导航

- **产品经理（PM）**：读 1.1 北极星 / 1.2 解决什么问题 / 1.3 典型用户旅程 / 2.1 skill 白话版。15-20 分钟
- **工程师（准备实施 Studio）**：读全文，特别是第 2.2 技术版 / 第 3 部分 MVP Roadmap / 3.8 技术栈 / 3.9 依赖关系。60-90 分钟
- **工程师（只是想知道 graph_agent 是什么）**：读 2.1 白话版就够。也可以直接去 `docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md` 看深度

### 4.2 相关文档

- `docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md` — graph_agent 框架的完整技术文档（对开发者 friendly）
- `docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md` — 怎么写 SKILL.md（针对 skill 作者）
- `docs/graph_agent_docs/ARCHITECTURE.md` — graph_agent 原作者视角的架构概述
- `plan.md` — 项目讨论的原始对话记录（所有需求的权威来源）

### 4.3 术语表（按字母序）

- **Agent Loop** — 一次 LLM 调用 → 看工具 → 决定调什么 → 调完看结果 → 再调 LLM → 直到完成的循环。graph_agent 里由 DeerFlow 实现
- **Agent-Loop 模式** — Phase 的三种模式之一，有 `<system_prompt>` 且无 `subgraph:` 的 phase。agent loop 在最后一公里拿到比单次 LLM 调用更靠谱的结果
- **Baseline** — 理想输出，作为之后运行结果的对比基准
- **Callback** — graph_agent 在运行过程中发出事件的机制，Studio 订阅这些事件渲染 UI
- **Checkpoint** — 某次 run 中某个 phase 完成后或 agent loop 某一轮后持久化的完整 state，可用于断点续跑
- **Code-only 模式** — Phase 的三种模式之一，没有 `<system_prompt>` 也没有 `subgraph:` 的 phase，纯计算不调 LLM
- **Compiler** — graph_agent 的 Lint 工具，检查 SKILL.md 是否合法
- **Context** — Phase 之间传递数据的"大黑板"，共享 dict
- **Context Bridge** — 父子 skill 之间的 context 字段映射规则
- **CCB** — Claude Code Bridge，多 Copilot 协议桥，让 Studio 同时接 Claude Code SDK 和 Gemini CLI
- **DeerFlow** — graph_agent 内嵌的 agent loop 实现（vendored in `deerflow/`），不改它
- **Frontmatter** — SKILL.md 顶部的 YAML 元数据块
- **Golden** — 加在 run 目录后缀的标记（`<run_id>.golden`），StorageManager 清理时跳过
- **Human-in-the-loop** — agent loop 运行中可以暂停等 PM 输入，PM 回答后继续跑的机制（靠 `request_human_input` / `ask_clarification` 工具）
- **Kitchen-Pass** — graph_agent 的 I/O 设计原则：phase 先写 context，落盘由 IOManager + caller 注入的 saver 完成
- **LangGraph** — Python 的 stateful graph 执行库，graph_agent 外层用它
- **md2json** — graph_agent 内置工具，把 LLM 用 Markdown 输出的内容转成严谨 JSON；显著提升了 DeepSeek 等高性价比模型在严谨流程中的鲁棒性，扩大了框架可用的模型池
- **md-patch** — md2json 解析失败时的局部外科手术式修复 skill
- **Nudge** — 认知循环里对 LLM 的提示（比如"先调 update_working_memory 再执行"）
- **Phase** — skill 的一个执行阶段，是框架的最小执行单元。三种模式：Agent-Loop / Subgraph / Code-only
- **Phase 三模式互斥** — 一个 phase 只能是三种模式之一，由 `loader.py` L565 硬约束
- **Pipeline** — 一种使用习惯，**不是框架概念**。指"多个 skill 组合成一条完整业务流程"的约定
- **Prompt Capture** — Studio 核心调试能力之一：记录每次 LLM 调用前的三元组（原始模板 / 变量字典 / 最终文本）
- **`<ref>` 标签** — SKILL.md 里的文件级字符串替换指令，只为解决主文件太长。和 skill 组合无关
- **Resume** — 在某次 run 失败或暂停后，基于 checkpoint 继续跑的能力
- **Run ID** — 一次运行的唯一标识（时间戳 + 随机后缀）
- **`sub_skills:` 字段** — 父 phase 声明里把子 skill 包成 LangChain Tool 给 agent loop 动态调用
- **`subgraph:` 字段** — 父 phase 声明里委派给完整子 skill 跑
- **StorageManager** — graph_agent 内置的 default artifact saver
- **Subgraph 模式** — Phase 的三种模式之一，有 `subgraph:` 字段的 phase，委派子 skill 完整跑一遍
- **Tier** — 模型角色（premium / balanced / fast），在 `llm_roles.yaml` 里映射到具体模型
- **Trace** — 一次 run 的完整执行记录（一堆 CallbackEvent 组成）
- **Workspace** — PM 的私人工作空间（`workspaces/<user_id>/`），P1.5 引入

---

## 结语

本文档是 Studio 项目正式开发的起点。在此之后会有：

1. **Kiro spec**：基于本文档的 MVP1 写详细的 requirements / design / tasks / research 四件套，放在 `.kiro/specs/studio-mvp1/`
2. **Superpowers plan**：基于 Kiro spec 写 checkbox 驱动的执行 plan，放在 `docs/superpowers/plans/2026-04-XX-studio-mvp1.md`
3. **MVP1 启动 kickoff**：确认开发人员、分工、时间线

本文档不固定，可以随认知更新修改。每次大的修改需要和 Owner 再对一次。

**对本文档的任何疑问或修改建议，直接在对话里提出**。
