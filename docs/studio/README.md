# Skill Studio — 项目对齐文档

> **本文档是 Skill Studio 项目的起点文档，写给两类读者：**
>
> - **产品经理（PM）**：只读"第一部分 Studio 是什么"和"第二部分 skill 基础概念（白话版）"。你可以在 15 分钟里看明白 Studio 能帮你做什么、一个 skill 长什么样、你以后怎么用它。
> - **开发人员**：读完整文档，特别注意"第三部分 MVP Roadmap"和"第四部分 技术细节（引用源码）"。你能知道要做什么、每个功能的边界、和 graph_agent 引擎的哪些地方有依赖。
>
> **本文档不是**：
>
> - 不是 Kiro spec（Kiro spec 在确认本文档后基于它写，更详细）
> - 不是 graph_agent 框架内部设计文档（那份文档在 `docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md`）
> - 不是实施 checklist（Superpowers plan 里有带复选框的 task 清单）
>
> **最后更新**：2026-04-23

---

## 目录

1. [Studio 是什么](#第一部分-studio-是什么)（写给 PM 和开发者）
2. [graph_agent 和 skill 基础概念](#第二部分-graph_agent-和-skill-基础概念)（PM 看白话版，开发者看技术版）
3. [Studio MVP Roadmap 和需求](#第三部分-studio-mvp-roadmap-和需求)（以开发者为主，但 PM 也可以看"交付的功能"部分）
4. [附录：读者导航](#第四部分-附录)

---

## 第一部分：Studio 是什么

### 1.1 一句话定位（北极星）

**Skill Studio 让产品经理不写 Python 代码就能独立完成 graph_agent skill 的设计、修改、测试和交付。从 PM 有一个新想法到跑出第一个能用的 skill，全流程不需要工程师参与。**

Studio 是 graph_agent 框架的配套工具。graph_agent 是底层引擎（负责把声明式的 SKILL.md 文件跑成一个多阶段 Agent），Studio 是给 PM 用的图形界面（负责让 PM 用对这个引擎）。

### 1.2 Studio 解决的核心问题

**在 Studio 之前**，一个 PM 想做一个新的 Agent 功能（比如"自动写产品说明书"），要经过以下几步：

1. PM 把需求写成文档交给工程师
2. 工程师看需求，学 LangGraph、学 DeerFlow、写 Python 代码
3. 工程师写完，PM 跑一下发现效果不对
4. PM 告诉工程师哪里不对（通常说不清楚）
5. 工程师改代码
6. 重复 3 到 5 多次
7. 上线

这个循环有几个问题。**第一**，PM 描述需求的语言和工程师理解的语言不是一回事，中间翻译损耗大。**第二**，PM 没办法看到 Agent 内部到底在想什么、调了什么工具、每一步的 prompt 长什么样，所以很难准确提出改进意见，只能说"感觉不对"。**第三**，工程师一改就要几天，PM 每次等反馈都要等很久。**第四**，改完之后也不好对比"新版本和旧版本哪个好"，只能凭感觉判断。

**在 Studio 之后**，同样的流程变成：

1. PM 在 Studio 里点"新建 skill"，和 Copilot（Claude Code / Cursor / 或其他编辑器里的 AI 助手）对话描述需求
2. Copilot 帮 PM 生成初始的 SKILL.md 文件
3. PM 在 Studio 里一键跑一下看效果
4. 如果效果不对，PM 在 Studio 里点开 Prompt Inspector 能看到每一次 LLM 被问了什么、回答了什么
5. PM 和 Copilot 对话修改 SKILL.md（或者 PM 直接在 Studio 的编辑器里改），保存后 Studio 立刻重新 Lint 给反馈
6. 反复迭代，对比每次运行的结果
7. 定下一个"理想输出"当做基准（baseline），以后每次改动都对比这个基准看有没有退化
8. 交付上线

整个过程里，**工程师不参与**。PM 用自然语言和 Copilot 对话，Copilot 负责把自然语言翻译成规范的 SKILL.md；Studio 负责让 PM 看到 Agent 运行的全过程，辅助 PM 判断改得对不对。

### 1.3 典型用户旅程（一个 PM 从零做 skill 到上线）

假设 PM 张三要做一个"产品说明书生成器" skill，输入是产品的基本参数（比如 iPhone 15 的规格表），输出是一份面向消费者的营销性说明书。下面是完整的使用流程。

**Day 1 - 创建 skill**

张三打开 Studio，看到 skill 列表。他点"新建 skill"，在对话框里说：

> 我想做一个 skill，输入是产品参数表（JSON），输出一份面向普通消费者的产品说明书。说明书要分三段：产品亮点、使用场景、购买建议。

Copilot（在 Studio 侧边栏，或者在 PM 熟悉的 Cursor / Claude Code 里）接到这个描述后，会问他几个问题确认细节（比如"说明书的语气要偏正式还是偏活泼？""需不需要生成配图？"），然后自动生成初始的 SKILL.md 文件。

张三点 Lint 按钮，看到绿色的"通过"状态。

**Day 1 - 准备测试素材**

张三上传 3 份测试输入（iPhone 15 的规格表、小米 14 Pro 的规格表、华为 Mate 60 的规格表）到 Studio。

Studio 提示张三："在正式跑 skill 之前，建议先用这 3 份素材打磨一份你心目中的理想输出，之后每次跑都可以和它对比。"（这是 Studio 内置的方法论）

张三同意。Copilot 带他一起打磨 iPhone 15 的理想说明书 — 不是让 LLM 生成，而是 PM 和 Copilot 一起讨论"你希望这份说明书长什么样"，手工把期望的输出字面写出来。三份素材都打磨完后，Studio 把它们存为 "golden baseline"。

**Day 1 - 第一次跑**

张三点 [Run]，选 iPhone 15 的规格表作为输入。

Studio 右边的 Trace Timeline 实时展开：

- Phase 1：`extract_highlights`（提取产品亮点）— 3.2 秒，调用了 LLM，返回了一段文字
- Phase 2：`write_scenarios`（撰写使用场景）— 4.1 秒
- Phase 3：`synthesize_report`（合成最终说明书）— 2.8 秒

总耗时 10.1 秒，花了 1.5k tokens。

张三发现 Phase 2 的输出有点空洞。他点开这个 phase，在 Prompt Inspector 里看到 LLM 实际收到的 prompt（三个标签页：原始模板、变量字典、注入后的最终文本）。一看就明白了：模板里没有告诉 LLM 要具体举例，LLM 就只写了抽象概念。

**Day 1 - 修改**

张三可以选择两种方式修改 skill：

**方式一**：直接在 Studio 的 Monaco 编辑器里改 SKILL.md 源码，把 `write_scenarios` 的 `<system_prompt>` 加上"至少举 3 个具体使用场景"这句话。保存后 Studio 立刻 Lint 通过。

**方式二**：张三更熟悉 Cursor，他在 Cursor 里打开 SKILL.md，和 Cursor 的 AI 说"给 write_scenarios 加上'至少举 3 个具体使用场景'的要求"。Cursor 改完保存。Studio 通过 FileWatcher 检测到变更，立刻重新 Lint，画布上 Phase 2 亮了一下表示"已更新"。

两种方式都可以，Studio 不强制用某一种编辑工具。

**Day 1 - 再跑一次**

张三又点 [Run]。新的输出里 Phase 2 果然多了 3 个场景。

张三切到 "对比" 面板，选择"这次 run" vs "golden baseline"，Copilot 给出分析："本次输出覆盖了所有 golden 里的要点，但在第 2 个场景的描述上比 golden 更啰嗦。建议调整模板要求输出简洁。"

**Day 2 - 继续迭代**

张三按 Copilot 的建议改了 prompt，又跑了 5-6 次，每次跑都比上次接近 golden baseline。

终于有一次跑得张三非常满意。他给这次 run 的目录加 `.golden` 后缀，锁定为"new baseline"。Studio 的 history 自动清理机制不会删这个目录。

**Day 3 - 交付**

张三用剩下两份测试素材（小米、华为）跑了一遍，结果都满意。他把 skill 交给工程师，工程师直接部署到生产环境（生产端同样从这个 SKILL.md 加载 skill 运行，没有任何代码差异）。

**整个流程里，工程师只在最后"部署"环节参与**。设计、修改、测试、打磨全部由 PM 张三独立完成，Studio 是他的辅助工具。

### 1.4 核心功能清单

基于上面的用户旅程，Studio 要提供以下能力：

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
- 结构化表单编辑（P2+，把常见字段做成表单控件，但这不是 MVP1 的目标）

**运行类功能**：
- 一键 Run（选输入、跑 skill、看实时 trace）
- Trace Timeline（WebSocket 流式展示每一步事件）
- Prompt Inspector（三标签页：原始模板 / 变量字典 / 注入后最终）
- 失败节点定位（哪个 phase 失败、失败原因、LLM 当时的 raw output）
- 成本/耗时面板（每次 run 消耗的 tokens 和时间）

**测试类功能**（体现"先打磨理想输出"方法论）：
- 测试素材管理（上传、存储、复用）
- Golden baseline 打磨（PM + Copilot 交互式产出理想输出）
- History 管理（每次 run 自动归档）
- 对比分析（选两次 run 对比，或选一次 run 和 baseline 对比，Copilot 给分析）
- `.golden` 锁定机制（重要 run 不被自动清理）

**协作类功能**：
- Copilot 集成（MVP 阶段支持任何 coding assistant，通过 FileWatcher 响应变更；终极形态是 CCB 式深度集成多个 Copilot 可切换）
- 共享/Fork（PM 之间分享 skill）
- User ID 隔离（P1.5 上线，每个 PM 一个独立工作空间）

### 1.5 差异化优势

**和 Dify / Coze / n8n / Langflow 等画布式 Agent 编排工具的区别**：

那些工具的节点是**原子组件**（"调 API 的节点"、"调 LLM 的节点"、"条件判断的节点"），业务逻辑分散在各个节点的配置里，节点之间用数据线连。这种模式对简单流程（客服机器人、邮件处理）够用，但碰到需要复杂推理、递归嵌套、多阶段协作的任务就力不从心。

Studio + graph_agent 的每个 phase 可以是一个完整的 Agent（有自己的 prompt、工具、validator、甚至可以递归嵌套另一个完整 skill），业务逻辑集中在 SKILL.md 声明 + Python 工具函数里，可以用 git 做版本管理。适合**复杂 Agent 工作流**（多步推理、长上下文、质量审核、递归分解）。

**和直接让 PM 学 Python 写 Agent 的区别**：

PM 写 Python 有学习成本，而且写出来的代码往往不够工程化（没有 trace、没有 callback、没有 validator 循环、没有模型 fallback）。Studio + graph_agent 把这些工程能力都内置了，PM 只管在 SKILL.md 里声明"我要做什么"，不用关心"怎么保证稳定性"。

**和在 Claude Code / Cursor 里直接编辑 SKILL.md 的区别**：

Claude Code 和 Cursor 是通用代码编辑工具，能改 SKILL.md 但不能给 PM 以下能力：

- 看 skill 的拓扑图
- 看实时运行 trace
- 看 Prompt Inspector 三标签页
- 对比多次 run 的结果
- 管 history 和 golden baseline

Studio 做的是**运行观察 + 测试 + 基准管理**层面的事，Copilot 做的是**编辑辅助**层面的事，两者互补。PM 既用 Studio，也用 Copilot，不是二选一。

### 1.6 核心优势总结

| 优势 | 说明 |
|------|------|
| **PM 友好 + 工程师友好** | 同一套 SKILL.md 文件 PM 能改，工程师也能改，用 git 版本管理 |
| **开箱即用** | 内置 StorageManager 自动落盘、内置 compiler Lint、内置 history 清理，PM 不用配置什么就能开始 |
| **可观测** | Prompt Capture、全量 trace 落盘、Golden baseline 对比、成本/耗时面板 |
| **跨 Copilot 工具** | SKILL.md 格式同时兼容 graph_agent / Claude Code / Cursor，PM 用任何工具都能编辑 |
| **递归嵌套** | 一个 skill 可以把其他 skill 作为子模块嵌入（subgraph），模块化可复用 |
| **质量门** | compiler Lint 不过不算完成，用强制校验保证 skill 质量 |
| **内置方法论** | "先打磨理想输出作为 baseline 再测试"的工作流嵌在 Studio 里，引导 PM 正确做事 |

---

## 第二部分：graph_agent 和 skill 基础概念

### 2.1 白话版（写给 PM 看）

#### 什么是 graph_agent

graph_agent 是一个跑多阶段 Agent 的引擎。你可以把它理解成一个"说明书执行器"——你写一份说明书（SKILL.md），告诉它"这个任务要分几步、每一步要做什么、用哪些工具、用什么模型、失败了怎么办"，它就按说明书一步一步执行，每一步都调用 LLM（大模型）做决策，最后给你结果。

它和 ChatGPT 之类的"一次对话一次回答"不一样。graph_agent 适合**复杂任务**——任务需要拆成多步、每步的输出是下一步的输入、有些步骤要做质量审核、失败了要重试。

#### 什么是 skill

一个 skill 就是一份 SKILL.md 文件 + 一些 Python 工具代码。SKILL.md 是**给 graph_agent 看的说明书**，Python 工具代码是**这个说明书里需要调用的具体功能**（比如"读取文件"、"调外部 API"）。

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

SKILL.md 分两部分。**顶部**是 YAML 格式的元数据（叫 frontmatter），写这个 skill 叫什么、描述什么、需要什么输入、产出什么输出。**下面**是 XML 风格的标签，每个标签定义一个阶段（phase）的具体行为。

一个最简单的例子：

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

这个 skill 只有一个阶段（greet），要求 LLM 调用一个叫 `generate_greeting` 的 Python 工具函数来生成问候语。Python 工具函数在 `script/greet.py` 文件里，由 Copilot 根据skill tools规范来写, 写完通过compiler编译保证格式正确。

#### Skill 的三种阶段模式

每个 phase 可以是三种模式之一：

- **Agent-Loop 模式**(这里要根据agent loop改一下, 不是LLM单词调用,这么些会有歧义, 下面所有的LLM模式都要改成agent loop模式,范式不一样)：这一步需要 LLM 思考、调用工具、做决策。写了 `<system_prompt>` 标签就是这种模式。
- **Subgraph 模式**：这一步直接委派给另一个完整的 skill 去做。`<phase_config>` 里写 `subgraph: 另一个skill的路径`。PM 做"pipeline 编排"的时候用这个，让每一步调用一个成熟的子 skill。
- **Code-only 模式**：这一步只是纯计算（不需要 LLM），就直接跑一个 Python 工具函数。适合"准备数据"、"合并结果"这种不需要 LLM 判断的步骤。

三种模式**互斥**，一个 phase 只能是一种。这是框架的硬规则。

#### 一个 skill 怎么调用另一个 skill

两种方式：

**方式一**：静态委派（subgraph 模式）

在父 skill 的某个 phase 里写 `subgraph: ../child-skill/SKILL.md`，运行到这一步就去跑子 skill。这是"确定性"的 —— 父 skill 一定会调用子 skill，不可跳过。

**方式二**：动态工具调用（sub_skills 或 builtin parallel_map）

在父 skill 的某个 LLM 模式 phase 里声明子 skill 作为 "工具"，让 LLM 在对话中自己决定调不调、什么时候调、参数是什么。适合 "PM 也不确定要不要调子 skill、让 LLM 判断"的场景。

`builtin parallel_map` 是 graph_agent 内置的一个工具，专门用于**并发调用同一个子 skill 多次**的场景 —— 比如"对一批 10 个 scene 分别提取 beats"，LLM 调一次这个内置工具就能并发跑 10 次子 skill，不用手写 Python 胶水。 (并发不要那么多, 根据deerflow内置的subagent数量只给了3个并发, 那我们也先只给3个并发,保守一点,如果可以再慢慢加)

#### 一个 skill 怎么跑

三种跑法：

- **独立跑**：任何 skill 都可以独立运行 `run_skill("skills/my-skill/SKILL.md", input_data)`，不需要它有父 skill。独立跑的时候产出落到 Studio 约定的工作空间里。
- **被嵌入跑**：这个 skill 被另一个 skill 用 `subgraph:` 委派调用，作为父 skill 流程的一部分。
- **生产环境跑**：production 环境用同样的 `run_skill()` 接口，产出路径由 production 代码决定（比如写到数据库、写到 S3）。

**同一份 SKILL.md 这三种场景下行为完全一致**，只是产出去哪不同。Studio 负责独立跑的场景，production 代码负责生产环境跑的场景。

#### 几个你会经常听到的词

- **Phase**：skill 的一个阶段。(有个很大的命名歧义, skill.md里写的都是node标签,文件夹也是node, 但是表述一直是phase,如果phase语意更加贴切,那就统一用phase,否则会混乱)
- **Tool**：Python 函数，被 LLM 在 phase 里调用。
- **Validator**：校验函数，检查 phase 输出是否合格，不合格就触发重试。
- **Context**：phase 之间传递数据的 "黑板"。每个 phase 读写这个 context。
- **Context Bridge**：父子 skill 之间传数据的映射规则（父 skill 的哪个字段传给子 skill 的哪个输入，子 skill 的哪个字段回写到父 skill 的哪个字段）。
- **Artifact**：phase 的产出物，可以落盘为文件（JSON、文本、图片等）。
- **Trace**：一次 run 的完整执行记录（每一步的 prompt、LLM 回答、工具调用、耗时、tokens）。
- **Run ID**：一次运行的唯一标识，Studio 用它区分历次运行。
- **Golden baseline**：你手工打磨好的"理想输出"，之后每次 run 都和它对比。

### 2.2 技术版（写给开发人员看）

以下内容是给开发者看的 graph_agent 技术细节，如果 PM 读到这里已经超出必要，可以跳到第三部分。完整的框架机制讲解见 `docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md`。这里只做要点重复。

#### 核心架构（双层控制）

- **外层 GraphAgentHarness**（`src/core/graph_agent/core/harness.py`）：LangGraph 驱动的 phase 编排 + planning nudge + selfcheck nudge + checkpoint compaction + finish gate
- **中间层 Middleware**（`cognitive/middlewares.py`）：WorkingMemory / DeadEndPruning / Clarification / DanglingToolCall
- **内层 DeerFlow Agent Loop**（vendored in `deerflow/`）：LLM 调用 + tool 执行 + 流式输出

#### SKILL.md 的完整结构和 6 种标签

见 `FRAMEWORK_UNDERSTANDING.md` 第 2 节和第 4 节。关键代码路径：

- `<ref path="..." />` — parser 阶段字符串替换（`core/parser.py` L160-186）
- `subgraph:` 字段 — loader 阶段递归加载子 harness（`core/loader.py` L519-560）
- `sub_skills:` 字段 — loader 阶段包装成 LangChain StructuredTool（`core/loader.py` L586-596）
- Phase 三模式判定（`core/loader.py` L565）
- Phase 执行器分叉（`core/harness.py` L384-387）

#### 几条硬红线（不能碰）

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
| MVP2 | 测试和迭代增强 | 4 周 | PM 能用 Golden baseline 方法论和对比分析 | 无 |
| MVP3 | Copilot 能力增强 | 4 周 | Copilot 加强 skill 集落地，多 Copilot 切换 | 无 |
| P1.5 | 用户隔离 | 2 周 | PM 之间互不干扰 | **强制 gate**：P1.5 启动前做 dogfood 验证 |
| P2+ | 按真实反馈决定 | — | — | — |

MVP1 + MVP2 + MVP3 加起来 14 周，加上 P1.5 共 16 周左右。大阶段之间可以重叠启动（比如 MVP2 做一半的时候 MVP3 可以预研）。

### 3.2 MVP1：最小可用（6 周）

#### 3.2.1 MVP1 的交付目标

PM 能在 Studio 里完成以下事情：

- 看到所有已有的 skill（列表 + 每个 skill 的拓扑图）
- 新建一个 skill（通过 Copilot 对话生成 + Studio 模板辅助）
- 直接在 Studio 里改 SKILL.md 源码（Monaco 编辑器）
- 或者在外部工具（Cursor / Claude Code / VS Code）里改，Studio 自动检测变更并重新 Lint
- 跑 Lint（一键，错误可点击跳行）
- 跑 skill（一键，看实时 trace）
- 看 trace 的每一步（phase_start/end / LLM 调用 / tool 调用 / validator 结果 / 失败节点）
- 看 Prompt Inspector 的三个标签页（原始模板 / 变量字典 / 最终注入文本）
- 看每次 run 的产出文件（StorageManager 自动落盘到约定路径）
- 看每次 run 的 tokens 和耗时

#### 3.2.2 MVP1 的功能清单

**前端（Web UI，本地浏览器访问）**

- skill 列表页 `/` — 扫 `skills/` 目录返回 skill 卡片列表
- skill 详情页 `/skills/{id}` — React Flow 只读画布 + 右侧详情面板 + Monaco 编辑器 + Trace Timeline + Run 按钮
- Monaco 源码编辑器 — 编辑当前选中的 SKILL.md，保存后触发 Lint
- 只读 React Flow 画布 — 渲染 phase 拓扑，subgraph phase 用特殊样式标记，点击节点展开详情
- 详情面板 — 展示 phase 的 `<system_prompt>` / `<user_prompt>` / tools / validator / output_schema 等
- Trace Timeline — WebSocket 订阅 CallbackEvent 流，按时间顺序展示
- Prompt Inspector 弹窗 — 点击 `prompt_captured` 事件打开，三标签页对比
- 成本/耗时小面板 — 每次 run 结束后显示 tokens / elapsed

**后端（本地 FastAPI server，单用户，port 8787）**

- `GET /api/skills` — 扫 skills/ 目录返回 skill 列表
- `GET /api/skills/{id}` — 返回单个 skill 的完整信息（从 `load_workflow_from_md()` 拿 harness 实例的结构化描述）
- `POST /api/skills/{id}/lint` — 调用 `compile_skill()`，返回结构化的错误列表（含行号）
- `POST /api/skills/{id}/run` — 后台 spawn 一个 subprocess 跑 `run_skill()`，返回 run_id；WebSocket `/ws/run/{run_id}` 推送实时事件
- `GET /api/skills/{id}/runs` — 列出某个 skill 的所有历史 run（从 StorageManager 的目录结构读）
- `GET /api/skills/{id}/runs/{run_id}` — 返回某次 run 的完整 trace.jsonl + final context + artifacts 列表
- FileWatcher — 后台监听 `skills/` 目录，文件变更通过 WebSocket broadcast `skill_changed` 事件给所有连接的前端
- `POST /api/skills/{id}/new` — 新建 skill（从模板 Fork 或通过 Copilot 生成）

**必要的集成工作**

- 前端通过 HTTP + WebSocket 连接后端
- 后端调用 graph_agent 的 public API（`run_skill`、`compile_skill`、`load_workflow_from_md`）
- 后端订阅 graph_agent 的 CallbackEvent，转发给前端
- Monaco 编辑器集成 SKILL.md 的 syntax highlighting（基础 Markdown + XML 标签高亮）

#### 3.2.3 MVP1 明确**不做**的事

- 不做 user 隔离（所有人共用 `skills/` 和 `workspaces/default/`）
- 不做 Golden baseline 打磨工作流（MVP2 做）
- 不做 history 对比面板（MVP2 做）
- 不做 Copilot 加强 skill 集（MVP3 做）
- 不做 CCB 式深度多 Copilot 切换（MVP3 做）
- 不做结构化表单编辑（P2+ 考虑）
- 不做画布可编辑（可能永远不做，至少 MVP1-3 不做）
- 不做意图偏离检测（P2+）

#### 3.2.4 MVP1 的 UI 草图（文字描述）

页面 1：skill 列表

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

页面 2：skill 详情（左-画布 + 中-编辑器 + 右-trace）

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
│ │phase2│       │ <node id="...   │   [click to see] │
│ └──────┘       │ ...             │ ▶ finish_task   │
│                │                 │                  │
│ [Lint]  [Run]  │                 │ Tokens: 2.3k     │
│                │                 │ Time: 8.2s       │
└────────────────┴─────────────────┴──────────────────┘
```

### 3.3 MVP2：测试和迭代增强（4 周）

#### 3.3.1 MVP2 的交付目标

PM 能在 Studio 里运用"先打磨 Golden baseline 再测试"的方法论，形成一个"改 → 跑 → 对比 → 迭代"的回归工作流。

#### 3.3.2 MVP2 的功能清单

**新增功能**

- 测试素材管理面板（`skills/{id}/test_inputs/`，上传 / 查看 / 命名 / 删除）
- Golden baseline 打磨工作流
  - PM 选一份测试素材
  - Studio 引导："先打磨一下你期望的输出？"
  - 进入打磨页面（PM + Copilot 合作产出 golden JSON / Markdown）
  - 存到 `skills/{id}/golden/<input_name>/baseline.json`
- Run 时可选 "对比 golden baseline"
  - 跑完之后 Studio 把 run 的产出和 baseline 自动 diff
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

#### 3.3.3 MVP2 不做的事

- 不做完整的 diff 算法（用简单 JSON diff 或文本 diff，复杂语义 diff 交给 Copilot 的 LLM 判断）
- 不做自动化回归（MVP2 是手动对比，自动化 P2 考虑）
- 不做可视化的 "哪一个 phase 导致输出变差" 归因（依赖 trace 自己判断，P2 考虑加 phase 级 diff）

### 3.4 MVP3：Copilot 能力增强（4 周）

#### 3.4.1 MVP3 的交付目标

Copilot 在 graph_agent skill 开发场景下的能力大幅增强，PM 用任何 Copilot 工具（Claude Code / Cursor / Gemini）都能享受到一套**graph_agent 专属的 skill 和 slash command**。

#### 3.4.2 MVP3 的功能清单

**第一组：Copilot 辅助 skill（可被任何支持 skill 的工具使用）**

注意这一组是"开发成 skill 供 Copilot 加载"，Studio 本身不直接实现这些 skill 的功能，而是提供它们作为资产。PM 在 Cursor 里让 Cursor 加载这些 skill，Cursor 就获得了 graph_agent skill 开发能力。

- `create-skill` skill：从自然语言描述创建新 skill 的向导（会问 PM：几个 phase、每个 phase 是什么模式、要不要 subgraph 嵌套）
- `add-phase` skill：给现有 skill 插入新 phase，自动处理 `depends_on` 和 `context_mapping`
- `convert-to-subgraph` skill：把 code-only phase 里调用其他 skill 的 Python 胶水改造成 `subgraph:` 组合
- `refactor-phase` skill：重构某个 phase（改 prompt、改 tools、加 validator）

**第二组：slash command**

- `/lint` command：跑现有 compiler skill，输出错误清单
- `/run-phase <phase_name>` command：单独跑某个 phase 调试
- `/explain-trace` command：读最近一次 trace 用自然语言解释每一步
- `/compare-with-golden` command：跑一次当前 skill 和 golden baseline 对比

**第三组：Studio 里的 CCB 式多 Copilot 切换**

- Studio 侧边栏提供 Copilot 对话框（不是必须的，PM 也可以在 Cursor 里对话）
- 支持多 Copilot backend（Claude Code SDK / Gemini CLI / Cursor）
- PM 可以切换用哪个 Copilot 聊

**MVP3 前置依赖**

- MVP1 和 MVP2 已经稳定

#### 3.4.3 MVP3 里**真实需要做哪些 Copilot 加强** 由 MVP1-MVP2 dogfood 反馈决定

上面列的 4 个辅助 skill + 4 个 slash command 只是候选清单。实际 MVP3 做哪些、以什么顺序做，**必须看 MVP1 和 MVP2 期间 PM 在真实使用中最痛的点是什么**。不要提前拍死清单。

### 3.5 P1.5：用户隔离（2 周，强制 dogfood gate 之后开始）

#### 3.5.1 P1.5 的交付目标

多个 PM 同时用 Studio 互不干扰。每个 PM 有自己的 skill 工作空间，看到的 skill 列表是自己的，跑 skill 的产出也只写入自己的目录。

#### 3.5.2 P1.5 的功能清单

- 文件系统：`workspaces/<user_id>/skills/` 是每个 PM 的私人 skill 目录
- 文件系统：`skills/` 顶层目录改为只读的"公共模板库"（PM 可以 Fork 到自己的 workspace）
- 认证：HTTP header `X-Studio-User-ID` 标识用户（不做真 SSO，只是"声明身份"，适合 trusted 内部环境）
- 前端登录页：PM 输一个用户名存 localStorage，以后请求都带这个 header
- 后端 API：所有 API 接受 `X-Studio-User-ID` header，返回该 PM 的 workspace 里的数据
- PTY 终端（如果 MVP3 做了 Open CLI 功能）：cwd 强制锁在当前 PM 的 workspace 里，防止跨用户目录访问
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

- 结构化表单编辑（对 Monaco 源码编辑的补充，某些常见字段做成表单控件）
- 意图偏离检测（LLM judge + plan_checklist 结构化对比）
- 自动运行报告生成（HTML + JSON，覆盖耗时/成本/fallback 分布）
- Agent 行为 vs 设计意图一致性评分
- 画布部分编辑能力（拖拽 step 顺序、增删 subgraph 节点）
- 团队协作（PM 之间分享 skill、评论、diff 审批）

### 3.7 需求矩阵（映射到原始需求清单）

下表列出 Studio 部分需求和 plan.md 里 Owner 最初提出的需求的对应关系。

| 原始需求（plan.md） | 在 Studio 的哪个阶段落地 | 交付形式 |
|------|--------|---------|
| R1 PM 最后一公里（不写 Python）| 贯穿 MVP1-P1.5 | 整个 Studio 的存在 |
| R2 任何 PM 动手的地方都是 markdown 或可视化 | MVP1 | Monaco + React Flow 只读画布 |
| R3 PM 快速创建 skill | MVP1 + MVP3 | 新建 skill 向导 + create-skill 辅助 skill |
| R4 PM 修改 skill | MVP1 | Monaco + FileWatcher |
| R8 直观看到 LangGraph 图 | MVP1 | React Flow 画布 |
| R9 能看到每个 agent/skill 内容 | MVP1 | 详情面板 + 只读 Monaco |
| R10 设置系统输入 | MVP1 | Run 对话框的输入选择器 |
| R11 管理输入/输出路径 test | MVP1 + MVP2 | StorageManager 默认路径 + 测试素材管理 |
| R12 每步操作 trace | MVP1 | Trace Timeline + WebSocket |
| R13 每个 phase 的输入输出标准 | MVP1 | 详情面板展示 io / output_schema |
| R14 LLM fallback 排序展示 | MVP3 或 P2 | 成本/耗时面板扩展 |
| R15 熔断情况展示 | MVP3 或 P2 | 成本/耗时面板扩展 |
| R19 Run 实时 metrics | MVP1 | 成本/耗时小面板 |
| R20 Token 和耗时记录 | MVP1 | 成本/耗时小面板 + trace 持久化 |
| R21 回放模式 | MVP2 | History 面板 + trace 回放 |
| R22 每步快照 | MVP2 | History 面板的对比视图 |
| R23 Prompt 三标签页 | MVP1 | Prompt Inspector 弹窗 |
| R24 Agent loop 步骤可视化 | MVP1 | Trace Timeline |
| R25 自动运行报告 | P2+ | Run 结束后导出 HTML/JSON 报告 |
| R26 意图偏离检测 | P2+ | LLM judge + plan_checklist 对比 |
| R27 Working Memory 一致性评分 | P2+ | LLM judge |
| R28 Golden set 回归 | MVP2 | Golden baseline 打磨 + 对比分析 |
| R29 Copilot 集成 Claude Code / Gemini CLI | MVP1 基础（通用）+ MVP3 深度（CCB 式切换）| FileWatcher + MVP3 多 Copilot |
| R30 Copilot 加强 skill/command | MVP3 | 辅助 skill + slash command 集 |
| R37 User ID 隔离 | P1.5 | workspaces/<uid>/ + HTTP header |
| 新方法论 打磨理想输出作 baseline | MVP2 | Golden baseline 打磨工作流 |

### 3.8 Studio 的技术栈

- **前端**：React 18 + Vite + TypeScript + React Flow（只读画布）+ Monaco Editor + xterm.js（MVP3 的 CLI）
- **后端**：Python 3.12 + FastAPI + uvicorn + WebSocket
- **文件监听**：watchdog（Python 标准库兼容）
- **Copilot 集成**：FileWatcher（MVP1）+ Claude Agent SDK / Gemini CLI 子进程（MVP3）
- **本地部署**：`graph-agent-studio serve --port 8787` 启动本地 server，浏览器访问 `http://localhost:8787`

### 3.9 Studio 和 graph_agent 引擎的依赖关系

Studio 是 graph_agent 的 **纯消费者**，只通过公开 API 和框架交互：

- `from graph_agent import run_skill, compile_skill, load_workflow_from_md` — Studio 后端调用这些 API
- `graph_agent.callbacks.base.Callback` — Studio 实现自己的 Callback 订阅事件
- `graph_agent.io.StorageManager` — Studio 用这个管产出落盘

Studio 永远不碰 graph_agent 的内部实现（不改 DeerFlow、不改 loader / harness / compiler），只从 public API 消费。

---

## 第四部分：附录

### 4.1 读者导航

- **产品经理（PM）**：读 1.1 北极星 / 1.2 解决什么问题 / 1.3 典型用户旅程 / 2.1 skill 白话版。15-20 分钟。
- **工程师（准备实施 Studio）**：读全文，特别是第 2.2 技术版 / 第 3 部分 MVP Roadmap / 3.8 技术栈 / 3.9 依赖关系。60-90 分钟。
- **工程师（只是想知道 graph_agent 是什么）**：读 2.1 白话版就够。也可以直接去 `docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md` 看深度。

### 4.2 相关文档

- `docs/graph_agent_docs/FRAMEWORK_UNDERSTANDING.md` — graph_agent 框架的完整技术文档（对开发者 friendly）
- `docs/graph_agent_docs/SKILL_AUTHORING_GUIDE.md` — 怎么写 SKILL.md（针对 skill 作者）
- `docs/graph_agent_docs/ARCHITECTURE.md` — graph_agent 原作者视角的架构概述
- `plan.md` — 项目讨论的原始对话记录（所有需求的权威来源）

### 4.3 术语表（按字母序）

- **Agent loop** — 一次 LLM 调用 → 看工具 → 决定调什么 → 调完看结果 → 再调 LLM → 直到完成的循环。graph_agent 里是 DeerFlow 实现的。
- **Baseline** — 理想输出，作为之后运行结果的对比基准。
- **Callback** — graph_agent 在运行过程中发出事件的机制，Studio 订阅这些事件渲染 UI。
- **Compiler** — graph_agent 的 Lint 工具，检查 SKILL.md 是否合法。当前实现是 `skills/compiler/` 里的一个 skill（自举）。
- **Context** — Phase 之间传递数据的共享 dict。
- **Context Bridge** — 父子 skill 之间的 context 字段映射规则。
- **DeerFlow** — graph_agent 内嵌的 agent loop 实现（vendored in `deerflow/`），不改它。
- **Dispatcher**（模式）— 在 Python tool 里手动读子 skill 的 SKILL.md 提取 prompt 再调 LLM 的一种模式（例子见 `skills/adaptation_v1/tools/beat_dispatcher.py`）。业务场景合理。graph_agent 也提供 `parallel_map` 内置工具做类似功能。
- **Frontmatter** — SKILL.md 顶部的 YAML 元数据块。
- **Golden** — 加在 run 目录后缀的标记（`<run_id>.golden`），StorageManager 清理时跳过。
- **Kitchen-Pass** — graph_agent 的 I/O 设计原则：phase 先写 context，落盘由 IOManager + caller 注入的 saver 完成。
- **LangGraph** — Python 的 stateful graph 执行库，graph_agent 外层用它。
- **Nudge** — 认知循环里对 LLM 的提示（比如"先调 update_working_memory 再执行"）。
- **Phase** — skill 的一个阶段，三种模式：LLM / Subgraph / Code-only。
- **Pipeline** — 一种使用习惯，不是框架概念。指"多个 skill 组合成一条完整业务流程"的约定。
- **Prompt Capture** — Studio 核心调试能力之一：记录每次 LLM 调用前的三元组（原始模板 / 变量字典 / 最终文本）。
- **`<ref>` 标签** — SKILL.md 里的文件级字符串替换指令，只为解决主文件太长。和 skill 组合无关。
- **Run ID** — 一次运行的唯一标识（时间戳 + 随机后缀）。
- **`sub_skills:` 字段** — 父 phase 声明里把子 skill 包成 LangChain Tool 给 LLM 动态调用。
- **`subgraph:` 字段** — 父 phase 声明里委派给完整子 skill 跑。
- **StorageManager** — graph_agent 内置的 default artifact saver。
- **Tier** — 模型角色（premium / balanced / fast），在 `llm_roles.yaml` 里映射到具体模型。
- **Trace** — 一次 run 的完整执行记录（一堆 CallbackEvent 组成）。
- **Workspace** — PM 的私人工作空间（`workspaces/<user_id>/`），P1.5 引入。

---

## 结语

本文档是 Studio 项目正式开发的起点。在此之后会有：

1. **Kiro spec**：基于本文档的 MVP1 写详细的 requirements / design / tasks / research 四件套，放在 `.kiro/specs/studio-mvp1/`
2. **Superpowers plan**：基于 Kiro spec 写 checkbox 驱动的执行 plan，放在 `docs/superpowers/plans/2026-04-XX-studio-mvp1.md`
3. **MVP1 启动 kickoff**：确认开发人员、分工、时间线

本文档不固定，可以随认知更新修改。每次大的修改需要和 Owner 再对一次。

**对本文档的任何疑问或修改建议，直接在对话里提出**。
