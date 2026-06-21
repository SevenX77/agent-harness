# Graph Agent Explainer 写作准则

这份 brief 是后续撰写 Graph Agent Harness 产品说明书的写作准则。每次写新章节或改章节之前，先读它。

## 读者

这份说明书同时写给两类人。

工程师要看清楚架构、契约、数据流、错误边界、扩展点和排错入口。他们关心的是：哪个模块负责哪件事，接口传什么形状，哪个状态是事实来源，哪些逻辑不能在别处重复实现。

skill 使用者和运营者要知道怎么用 Studio 把一个 skill 从想法做成可运行、可评估、可发布的东西。他们关心的是：每个操作是什么意思，点完会发生什么，失败时看哪里，怎么从设计走到真实运行。

每章都要同时照顾这两类读者，但不能把内部术语和操作说明硬混在一起。先讲产品概念，再在需要解释行为或防止误用的地方补工程契约。

## 语气

这是产品说明书，不是开发交接文档。

不要使用这些开发过程词：

- MVP、target、baseline、alignment、frozen、owner、TODO、未实现、待落地、drift、测试锚点。
- “应该”“不应该”“未来会”“当前缺失”“目标是”这类计划语气。
- ③a / ③b 这类内部归属标签，除非是在工程附录里专门解释内部架构。

使用直白的产品陈述句：

- Studio 将编译诊断展示在错误抽屉、节点、字段旁和编辑器行标记中。
- Engine 使用设计阶段同一套语义运行 skill。
- Gateway 把 provider credential 和 fallback 行为从 skill 定义里隔离出去。

如果底层设计文档用了实现状态语言，写说明书时要翻译成稳定的产品行为。

## 核心承诺

整份说明书的核心承诺是：

Studio 是 skill 的设计入口；在 Studio 里设计出来的 skill，使用同一套 Graph Engine 语义进入真实运行。

Studio 不是 demo runtime。它是建立在真实 skill 契约之上的工作台。一个 skill 在 Studio 里完成编译、试飞、真实运行和评估，意味着它一直在按生产运行语义被塑形。

第 1 章必须讲清楚这个承诺。后续章节也要不断回到这个承诺。

## 三个模块的本质

Studio 让人设计、查看、调试、评估和发布 skill。它负责产品工作流和用户可见的操作面。

Engine 定义并执行 skill 的运行语义。它读取 skill 文件、检查结构、组装图、执行 logic 和 agent 节点、产出 trace、写运行产物，并支持恢复执行。

Gateway 是模型连接与调度层。它的意义是把 provider、endpoint、credential、capability、fallback 等模型供应商细节从 skill 定义和 Engine 运行逻辑里拿出去。route 是 Gateway 解析后的调用计划，不是 Gateway 的本质。

Golden 评估属于 Studio 的优化闭环。Engine 产出可审计的运行结果；Studio 用 golden 基准与运行结果做对比，展示差异，并让用户或 Copilot 继续打磨 skill 和 golden 数据。

Publish 和 Golden 是两个主题。Publish 关闭版本保存和分发闭环；Golden 支持评估和调试。

## 已确认的章节方向

Agent Loop 单独成章。

Gateway 放在 Agent Loop 之后讲，因为读者先理解 agent 节点何时需要模型调用，Gateway 的位置才自然。

Golden 靠近 Copilot、Trace、Debug、Resume 讲，因为它属于设计和调试闭环，不属于 Publish。

Publish 章节要包含版本保存机制。描述发布和版本工作流时，需要加入 Gitee 版本保存机制。

准备工作章节不仅讲 skill 文件，也要讲 Properties 面板和定义 skill 时会用到的基础编辑面。

## 每章写作规则

每章开始前先回答：这一章的本质是什么？

然后只加入能把这个本质讲清楚的细节。深度不是把所有 UI 区域和内部模块都列出来，而是选择真正解释逻辑的细节。

默认按这个顺序组织：

1. 产品概念：这一章帮用户解决什么问题。
2. 系统行为：Studio、Engine、Gateway 之间实际发生什么。
3. 用户工作流：用户怎么操作，会看到什么反馈。
4. 工程契约：哪些稳定形状、状态和边界必须讲清楚。
5. 错误和边界：什么会失败，怎么呈现，用户或工程师怎么处理。

不要把每章硬套成同一模板。有的章节适合时序图，有的适合状态机，有的适合契约表，有的适合具体 Studio 操作 walkthrough。

## 细节标准

一个细节只有在解释行为、防止错误理解、帮助操作或帮助排错时，才应该放进章节。

有价值的细节：

- 编译诊断会出现在错误抽屉、节点、字段旁和编辑器行标记中，因为这些位置分别对应不同的修复面。
- Predict 会真实执行 logic 节点，但 mock agent 节点，所以它能验证结构和数据流，同时避免真实模型调用。
- Gateway 使用 model role，让 skill 不需要硬编码 provider credential 或 fallback chain。

无价值的细节：

- 在总览章列出所有 Studio 面板，但没有说明它们服务哪个核心概念。
- 重复内部模块归属标签。
- 提及未完成的实现状态。
- 说某个组件“不应该发明契约”，而不是直接说明产品行为。

## 术语

统一使用 skill、Studio、Engine、Gateway、Agent Loop、Predict、Run、Trace、Golden、Publish。

解释无真实模型调用的预运行检查时，可以说“试飞”或 Predict。必须讲清楚 Predict 验证结构和数据流，但不触发真实 agent 模型调用。

需要和 Predict 区分时，用“真实运行”解释 Run。

解释 Gateway 时优先使用“model role”。skill 请求的是角色；Gateway 把角色解析成具体模型调用。

Gateway 章节之前尽量不展开 route。到 Gateway 章节再把 route 定义成 Gateway 解析出的调用计划。

## 截图和图示

截图和图示必须服务理解。

Studio UI 尚未完成时，可以先放 mock 示意图，但要标明是示意图，后续替换成真实截图。

不要为了装饰加图。每张图都要回答一个问题：用户在哪里操作，反馈在哪里出现，数据如何流动。

## 章节开写前检查

写任何章节前，先检查：

1. 读完这一章，读者必须理解的单一核心是什么？
2. 这一章是不是产品说明书语气，而不是开发交接语气？
3. 哪些内容服务使用者，哪些内容服务工程师？
4. 章节里每个行为的事实来源是哪一个模块？
5. 细节是在解释本质，还是只是在把章节写长？
6. 是否泄漏了设计文档里的实现状态词？
7. 是否出现 stale 边界，尤其是 Golden、Gateway、Publish、Agent Loop？

