# Graph Agent Harness 产品说明书大纲

这份文档是说明书的章节结构依据。`writing-brief.md` 负责写作规范；本文负责章节顺序、每章主题和必须覆盖的内容。

## 总体原则

整份说明书围绕以下核心原则展开：

1. **三模块协同产品**：本项目是一个由 **Engine (图执行引擎)**、**Gateway (模型路由与配置真相大脑)** 和 **Studio (创作与消费工作台)** 三者共同组合的产品。说明书必须在各模块的职责、设计意图和协作边界上保持高度一致。
2. **开发与生产一致性**：Studio 是 Skill 的设计入口；在 Studio 里设计出来的 Skill，使用同一套 Graph Engine 语义在生产端执行。
3. **物理分卷，隔离视角**：为解决“使用者（PM/业务架构师）”与“工程师（系统开发与集成）”阅读时的视角混乱问题，说明书在最顶层做**物理分卷（三册）**。每一卷只服务于一类特定的目标读者，拥有独立的阅读主线 and 叙述语境。
   * **第一卷：Skill Studio 设计与打磨手册**：完全基于 GUI 界面、交互操作、业务规则与打磨方法。使用通俗易懂的语言，屏蔽底层技术实现的复杂度。
   * **第二卷：GraphAgent Harness 架构与机制手册**：专门面向需要部署、运维、集成或研究底层的工程师。使用严谨的技术术语、数据契约、状态转移机和时序图。
   * **第三卷：二次开发与扩展指南**：面向需要基于 Harness 进行业务定制、开发自定义节点或 Tool/Action 的开发工程师。

---

## 📦 第一卷：Skill Studio 设计与打磨手册

本卷只讲“产品界面、工作流、设计规则、调优方法、发布流程”，完全面向 PM 和 Skill 设计者，屏蔽底层 Python 实现、DTO 契约、Fencing Token 或租约锁等技术细节。

### 第 1 章：起步：打开工作区与引导修复
*   **主要读者**：PM、Skill 设计者。
*   **必须讲清楚**：
    *   “本地文件夹即工作区”的 IDE 心智模型，无中心化注册表。
    *   **引导修复（Repair）机制**：打开非标准 Skill 文件夹时不予硬性卡死，而是引导 PM 通过 Copilot 辅助将其重构修复为标准 Skill 的步骤与交互。
*   **建议图示**：
    *   Welcome 页面 / 打开文件夹的交互示意图。
    *   Repair 状态下的工作区提示与 Copilot 交互位置。

### 第 2 章：配置：API 凭证与模型就绪检查
*   **主要读者**：PM、Skill 设计者。
*   **必须讲清楚**：
    *   在 Settings 中配置 API 密钥和映射模型 Role（角色）的前置逻辑。
    *   **模型可用性（Availability）的 6 态颜色心智**：红（failed，出错要修，如配置缺口、测试失败）、灰（untested/off/cooling_down，非错误的不可用，如未测试、手动关闭、熔断冷却中）、绿（ready，测试通过可用）、蓝（historical_ready，以前联通过但当前未测）。
    *   “模型弃用/不再提供”时的 off 状态展示以及单模型 re-probe 捞回规则。
*   **建议图示**：
    *   Settings 四 Tab 交互位置。
    *   6 态标签与颜色对照表。

### 第 3 章：设计：编辑 Skill、Steps 与属性白名单
*   **主要读者**：PM、Skill 设计者。
*   **必须讲清楚**：
    *   `GRAPH.md`（定义图拓扑）、`SKILL.md`（Agent 节点）、`LOGIC.md`（逻辑节点）的文件事实来源。
    *   **画布直读/直写源码**：画布修改直接写回本地 Markdown，不依赖编译临时包。
    *   **编辑边界**：属性面板（Properties）仅操作白名单属性，不负责 Golden 和步骤正文编辑；Agent 节点具体的运行 Steps（XML）在画布的子节点中拖拽重排和编辑。
    *   **同名 Key 顺序覆盖规则**：下游节点在黑板中覆盖同名变量时，画布会标红，需在消费侧显式勾选允许覆盖。
*   **建议图示**：
    *   主图 Canvas 拖拽。
    *   Properties 面板与 Agent L3 步骤结构编辑器对比。
    *   同名 Key 覆盖警告在 Canvas 的视觉呈现。

### 第 4 章：检验：一键编译与分级门控
*   **主要读者**：PM、Skill 设计者。
*   **必须讲清楚**：
    *   实时 Lint 轻度警告（不打断书写，防抖 800ms）与手动编译 Compile 弹出 Drawer（显示详细错误并方便一键复制给 Copilot）的配合。
    *   **分级门控契约**：Compile 通过解锁 Predict，Predict 通过解锁 Run。
*   **建议图示**：
    *   错误诊断 Drawer 与 Canvas 节点内联标红对比。

### 第 5 章：试飞：Predict 模拟运行与 409 守卫
*   **主要读者**：PM、Skill 设计者。
*   **必须讲清楚**：
    *   Predict 试飞不消耗真 Token，Logic 确定性节点真跑，Agent 节点自动按 Golden 状态选用 Mock 数据（有 Golden 吐 Golden，无 Golden 吐启发式占位数据）。
    *   **409 守卫**：Predict 产生的假数据 Trace 绝对不可被提升/保存为 Golden 期望值，防止闭环假数据污染。
*   **建议图示**：
    *   I/O 面板导入测试文件并触发 Predict 的操作入口。

### 第 6 章：真跑：Run 真实执行与事件状态灯
*   **主要读者**：PM、Skill 设计者。
*   **必须讲清楚**：
    *   Run 是真实执行，会烧 Token。批量运行入口同样在 I/O 面板，批量某项失败时显式上报，不静默失败。
    *   画布上节点呼吸灯、边框动画与后台运行事件（WS 事件）的同步规则。
    *   **Autocommit 安全网**：成功运行后本地 Git 会自动做一次 commit 存档，失败则不提交。
*   **建议图示**：
    *   I/O 面板单次/批量运行触发器。
    *   画布节点呼吸灯状态流转。

### 第 7 章：去黑盒：Trace 瀑布流、线上 Dot 与人能读文档
*   **主要读者**：PM、Skill 设计者。
*   **必须讲清楚**：
    *   **线上 Dot（状态机转移点）的交互**：点击连线中间的小圆点，看那一刻黑板数据的精确 JSON 切片以及节点间的聚合操作。
    *   流式 Trace 的“可折叠分类摘要”与 Monaco 承载的轻格式 Trace 人能读文档。
    *   顶部 Tab 多模型对比。
*   **建议图示**：
    *   线上 Dot 点击效果图。
    *   Trace Timeline 与人能读 Monaco 虚拟文档分屏示意。

### 第 8 章：调试：节点 Resume 续跑与 HitL 人工注入
*   **主要读者**：PM、Skill 设计者。
*   **必须讲清楚**：
    *   就地节点级 Resume：不重跑上游，使用 checkpoint 已有数据续跑。
    *   **脏断点失效置灰**：修改了上游代码/拓扑/Schema 后，下游的 `Resume` 按钮自动置灰，防止用脏数据续跑。
    *   **HitL（人类介入）交互**：Agent 请求输入时，就地在节点上方弹出富文本框，PM 答完点 Resume。
    *   **上下文篡改**：点击边 Dot，将 Trace 里的 Monaco 编辑器切成可写模式，手改黑板 JSON 存盘，诱导下游节点 Resume。
*   **建议图示**：
    *   节点上方悬浮的 HitL 输入框。
    *   边 Dot 触发编辑器可写状态。

### 第 9 章：打磨：基于 Golden 的比对评估
*   **主要读者**：PM、Skill 设计者。
*   **必须讲清楚**：
    *   🔘未测试 $\rightarrow$ 🟡逻辑 OK $\rightarrow$ 🟢有 golden 三态心智。
    *   Golden 仅在 Output Schema 变更导致缺少必要字段时才失效并触发编译报错。
    *   实际输出与 Golden 的字段级差异（diff）只在 Editor（编辑器）分屏进行，不在 Properties。
*   **建议图示**：
    *   Editor 中实际输出与 Golden 的分屏 Diff 对照。

### 第 10 章：发布：Artifact Release 与版本提交
*   **主要读者**：PM、Skill 设计者。
*   **必须讲清楚**：
    *   **发布 ≠ Git Push**。本地源码版本控制（Git）与成品库发布（Artifact Registry Commit）双命名空间完全隔离。
*   **建议图示**：
    *   Publish 时的发布包版本生成与 Registry 推送流程。

---

## 💻 第二卷：GraphAgent Harness 架构与机制手册

本卷专门面向系统集成工程师、平台运维、Engine 核心开发人员。介绍三模块（Engine/Gateway/Studio）的物理边界、依赖倒置设计、数据三线分治存储及 LangGraph 图引擎内部机制。

### 第 1 章：系统架构与三模块物理边界
*   **主要读者**：集成工程师、系统开发。
*   **必须讲清楚**：
    *   Engine（执行原语）、Gateway（模型路由与配置真相）与 Studio（设计与消费应用）的协作拓扑。
    *   **SDK + 薄 Adapter 模型**：Engine 和 Gateway 都是纯 SDK，本身不带 API；Studio 提供了 `EngineAdapter` 和 `GatewayAdapter` 作为适配器外壳。这使得部署拓扑可以自由切换（本地 execution $\rightarrow$ HTTP loopback 远程执行 $\rightarrow$ 生产 Headless 运行）。
*   **建议图示**：
    *   三模块架构拓扑与 Adapter 结构关系图。

### 第 2 章：存储三线分治机制与成品库（底座二）
*   **主要读者**：系统开发、存储模块实现者。
*   **必须讲清楚**：
    *   **配置真相线（ConfigTruthStore）**：数据小、强一致、**无缓存**，真相在 Gateway，Studio 仅消费投影。
    *   **运行产物线（RunArtifactStore）**：内容寻址哈希（ArtifactRef）、写完不改，在 Engine 读写。
    *   **运行态线（RuntimeStateStore）**：Checkpoint 断点、基于租约锁（Lease + Heartbeat）和 Fencing Token 的多 worker 防脑裂保护。
    *   **成品库**：只装已发布的冻结成品（内容寻址哈希），生产端只认成品。
*   **建议图示**：
    *   数据三线分治与成品库的存储流动路径图。

### 第 3 章：Gateway 健康状态投影与路由大脑
*   **主要读者**：系统开发。
*   **必须讲清楚**：
    *   Gateway 是配置真相与可用性的唯一大脑，计算出 Availability（可用性六态投影）与 Capability（能力四态，如 unknown/partial/known）正交的双轴健康模型。
    *   探测结果回写（SqliteLlmHealthStore.open_circuit）与证据库（EvidenceRecord）的写入规范。
    *   LLM 路由决策与 Fallback 动态降级链算法。
*   **建议图示**：
    *   Gateway 状态投影逻辑和熔断判定图。

### 第 4 章：Engine 运行时：LangGraph 串联与事件流协议
*   **主要读者**：系统开发、Engine 开发者。
*   **必须讲清楚**：
    *   Engine 是如何动态解析 `GRAPH.md`，并在 LangGraph 中装配执行图的。
    *   **共享黑板上下文（Blackboard Context）** 与边（Edge/线上 Dot）操作在内部执行器的实现。
    *   运行事件流（EventEnvelope）的数据结构、Cursor 续接、Seq 去重及 Gap 错误恢复协议。
*   **建议图示**：
    *   LangGraph 内部状态与共享黑板的数据流转示意。

### 第 5 章：HitL 与 Resume 异步中断恢复协议
*   **主要读者**：前端与后端联调工程师。
*   **必须讲清楚**：
    *   HitL（Human-in-the-Loop）在 Engine 执行中断、Checkpoint 留存、通过 Adapter 向 Studio 前端派生暂停事件、直至用户回写答案并触发 Resume 续跑的**端到端异步交互时序图**。
    *   状态脏检查（Dirty Check）的传导与失效置灰算法。
*   **建议图示**：
    *   HitL 触发至恢复执行的端到端异步时序图。

### 第 6 章：三模块稳定边界与错误纪律
*   **主要读者**：系统开发。
*   **必须讲清楚**：
    *   统一 `ResponseEnvelope` 机器错误码设计。
    *   **统一恢复纪律**：只允许硬失败或显式降级，禁止任何形式的静默降级（如凭证过期静默成空路由等）。

---

## 🛠️ 第三卷：二次开发与扩展指南

本卷面向需要基于 Harness 引擎进行业务定制、开发自定义节点或 Tool/Action 的开发工程师。

### 第 1 章：自定义 Logic 节点开发
*   **主要读者**：业务开发工程师。
*   **必须讲清楚**：
    *   如何继承底层 SDK 编写自定义确定性 Logic 逻辑。
    *   如何在 Studio 节点白名单中注册，并在画布中加载使用。

### 第 2 章：自定义 Tool 与 Action 编写
*   **主要读者**：业务开发工程师。
*   **必须讲清楚**：
    *   为 Agent 节点的 L3 智能流（Agent Loop）编写自定义工具。
    *   定义 Tools 契约与 Actions 的物理区别，以及在 `SKILL.md` 中进行声明式绑定。

### 第 3 章：自定义 Engine Middleware（中间件）
*   **主要读者**：业务开发工程师。
*   **必须讲清楚**：
    *   如何拦截 LangGraph 的节点变迁。
    *   编写“敏感词审查、Token 实统计、自定义日志”等全局 Pipeline 中间件的代码规范与挂载方法。
