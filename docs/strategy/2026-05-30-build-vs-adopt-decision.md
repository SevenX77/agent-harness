# Build-vs-Adopt 决策:graph-agent vs LangChain 生态

> **日期**: 2026-05-30
> **背景**: 评估是否继续自建 graph-agent 引擎,还是采纳现成方案;结论用于把精力重新分配到 KB/H-D 层。
> **方法**: 4 个后台 agent —— 1 轮 deep-research 竞品(110 agent / 25 claim 全过)、1 轮产品调研、1 次 graph-agent↔deepagents 架构 diff、1 次 graph-agent 代码深审。
> **未过 Gemini**:用户指示——本系统设计多由 Gemini 出,且其倾向迎合,故由 Claude 独立审。

---

## 0. 核心问题
graph-agent 是**自用引擎**(造 story-forge 长篇内容 / spec-coding),首要目的不是卖。问:有没有现成品已满足需求,让我不必继续自建?
- **采纳门槛(用户定)**:① 可嵌入 SDK ② 测/产一致 ③ PM-copilot ⑤ 全链路可观测;④ document-driven 降为软性(好 UX 可替)。
- **核心技术深度 E–H**:agent loop 作单元 / 嵌套 subgraph / loop 内编排 subagent / loop 内调用 skill。
- **最深护城河**:KB-as-control 的**假说-演绎(H-D)自进化系统**(见 `knowledge-base/docs/evolution_architecture.md`)。

---

## 1. 决策(TL;DR)
1. **不采纳 deepagents 替代**:架构异构(§4),迁移=L,会丢差异化。
2. **不再打磨编排层**:该层正被 deepagents/Fleet 免费商品化;你领先但战争不在此。
3. **从 deepagents 取 4 件**(免费 MIT),keystone = **RubricMiddleware**(§5)。
4. **先清半成品**:近期"拿回中间层"是半成品(§6)——summarization/loop_detection 调用点传 `True` 却落在禁用 no-op;双运行时分裂。先收口再加料。
5. **主力投 KB/H-D 层**:闸门已建(RetryRouter/finish_task/+ 将来的 Rubric),**"脑"未建**(因果存储 + diagnose/deduce/置信度)。这是唯一没人有的东西。

---

## 2. 竞品格局(deep-research)
- **最重要发现**:LangChain 近 6–12 月已补出"可嵌入 SDK + E-H 深度 + PM-copilot"的组合(Claude 先验"无单品做到"被证伪):
  - **deepagents**(MIT, `pip install deepagents`, `create_deep_agent()`):库层 E-H 齐(loop / 隔离上下文 subagent / progressive-disclosure skills / 把任意 `CompiledStateGraph` 当 subagent → 递归)。源:github.com/langchain-ai/deepagents
  - **LangSmith Fleet**(原 Agent Builder,2026-03-19 改名):no-code 对话搭 agent,建在 deepagents 上,可从自己 app 调用 + 自托管(Beta)。
- **关键裂缝**:E-H 递归嵌套在 deepagents **代码层**有;**产品层(Fleet)只暴露扁平 subagent 分解,递归嵌套未产品化给 PM**(GitHub #1698)。n8n 是唯一在可视化层做了 agent-as-tool 多层嵌套,但卡 A/B。
- **覆盖缺口**:Dify / Coze / DeerFlow / Copilot Studio 本轮零幸存证据,未判(最大局限)。

---

## 3. 三个 LangChain 产品
- **LangSmith Studio**(←LangGraph Studio):可视化**调试器**,`langgraph dev` 连本地运行,time-travel。**不是搭建器**。免费,工程师用。
- **LangSmith Deployment**(←LangGraph Platform):托管**运行时/基建**,部署+扩容(Assistants/Threads/Runs)。GA,付费(有 dev 档),可自托管(企业版整平台进自有云)。工程师/运维用。
- **LangSmith Fleet**(←Agent Builder):**无代码**搭 agent,瞄**业务办公自动化**(邮件/Slack/CRM act-on-behalf),不可自托管(SaaS),免费档 1 agent/50 runs → $0.05/run。唯一面向非工程师;有导出成 deepagents 代码的路径。
- **栈**:Fleet → 跑在 Deployment → 跑在 deepagents/langgraph。
- **对你**:Studio ≠ 威胁(只是调试器);Fleet 是唯一对照物,但在干**办公自动化**这个不同的活 + 卡 A/B(不可嵌/不可自托管);Deployment 与"嵌入式 SDK"用法无关。**你"可控内容/spec 流水线 + 领域 KB + 可嵌自托管"的缝,三者一个没占。**

---

## 4. 架构 diff:graph-agent vs deepagents —— 异构(非同构)
- **deepagents** = 单 in-process ReAct agent + 扁平 middleware + 运行时 `task` 工具开 subagent;其 "SKILL.md" = 模型按需 `read_file` 的文档,**无编译 / 无 phase / 无 DAG**。
- **graph-agent** = **文档编译成多阶段 StateGraph**(`GRAPH.md` + typed AST:logic/subgraph/agent/skill),编译成带 `depends_on` / retry / IO-schema 的固定 DAG。
- 两边 SKILL.md **仅 `name`+`description` 共享,不可互迁**。
- graph-agent 强:递归 subgraph DAG、跨 provider fallback、文档编译器 + 静态校验、确定性路由、可观测、认知中间件。deepagents 强:文件系统工具组、prompt caching、DeltaChannel checkpoint 压缩、live 摘要、Rubric、todo、async/远程 subagent。
- **定位:你=控制端,deepagents=自主端。** 行业漂向自主,你刻意站控制 —— 与"企业要确定性 workflow"的开局论点自洽。**用户已确认:自用也要重控制。**

---

## 5. 该从 deepagents 取什么(代码审 Part C)
| 取? | 件(deepagents 文件) | 为何 | 工 | 优先 |
|---|---|---|---|---|
| ✅ | **RubricMiddleware** (`middleware/rubric.py`) | 自动 LLM-grader **退出闸**(你的 `cognitive/critic.py` 只是可选工具);**H-D 的天然底座:rubric=假说, grader=验证**;接你已有的 finish_task→validate→retry 缝 | M | **最高** |
| ✅ | **DeltaChannel** checkpoint 压缩 (`graph.py` L22/66) | 修真实 bug:你 checkpoint O(N²) 增长;纯 state 注解,不碰控制流 | S | 高 |
| ✅ | **live SummarizationMiddleware** (`middleware/summarization.py`) | 补你半成品:compaction sidecar 持久化已建、缺触发器(就是这个) | M | 高 |
| ⚠️ | **Anthropic prompt caching** | 你零缓存;但需在 gateway 层(`client_manager`)注入,非现成 append | M | 中 |
| ❌ | 文件系统 写/改/glob/grep、execute sandbox、TodoList、MemoryMiddleware、async/远程 subagent、HarnessProfile/ProviderProfile | 要么打架"控制优先"(文件突变/shell/自主规划),要么已被 gateway 注册表 / SKILL frontmatter / WorkingMemory 覆盖 | — | 忽略 |

---

## 6. 代码审关键发现(健康度)
- **双运行时分裂(最大结构问题)**:① **harness 运行时**(flat SKILL.md,成熟,full middleware/retry/checkpointer);② **V2.1 / GRAPH.md 运行时**(`core/graph_assembler.py`,多阶段 DAG,8-turn 手写 ReAct `MAX_REACT_TURNS=8`,**无 checkpointer**,有 subagent)。**你的旗舰多阶段架构跑在更不成熟的 V2.1 上。**
- **checkpoint**:harness 路径 **FULL**(`core/checkpointer.py`,memory/sqlite/postgres,`resume()`/`get_thread_status`)——你没记错;但 **V2.1 路径无 checkpointer**;且无 size 优化(O(N²),无 DeltaChannel)。
- **半成品(看着 wired,实为 no-op)**:`llm_phase_node.py` L276-289 调 `create_custom_middlewares(summarization=True, loop_detection=True, ...)`,但两者都落在 `cognitive/middlewares.py` L438/L466 "disabled in MVP-0" 的 no-op 日志分支。dead code:`_ProfiledSummarizationModel` 从不被调。
- **中间层迁移半截**:MVP-3 的 `factory.build_middleware_chain` 本该是正统,但 live 路径仍用"legacy" `create_custom_middlewares` 手拼;`ExecutionControlMiddleware`/`LoopDetectionMiddleware` 只在测试里 wired,`LoopDetectionMiddleware` 是 5 行 no-op stub。**这是"拿回中间层"留下的最明显残迹。**
- **subagent**:harness 里死、V2.1 里活 —— 两运行时对"是否有 subagent"不一致。
- **工具面最小**:只读 `read_file`(沙箱到 references/,200KB);无 write/edit/glob/grep/execute(故意,控制优先)。
- **成熟且完整**:gateway 多 provider fallback(最成熟子系统)、HITL、RetryRouter、编译期 validators、finish_task(×2)、IOManager kitchen-pass、可观测 callbacks。
- **最高杠杆内部清理**:先收口 MVP-3 中间件迁移(把 `factory.build_middleware_chain` 接进 `LLMPhaseNode`,或删掉未接的 stub),让 summarization/rubric 落在一条链;并给 V2.1 运行时加 checkpointer。

---

## 7–8. KB / H-D 设计 → 已移至独立文档

KB 控制钩子(plan-gate / review-gate / KB 本体 / 置信度更新)、两层(工业底座 + 风格)进化、master 修正闭环、发散建议,全部移入 **kb 项目**:

> `knowledge-base/docs/hd-engine-hooks-and-style-design.md`(2026-05-30)

⚠️ **重要纠正**:原 §8 关于"风格层靠流量/播放数据反馈、核心难题是归因"的表述**已被用户纠正** —— 风格反馈来自 **master 在 artifact 上的直接修正**(copilot 对话),不是播放数据;master 本人即验证器,归因难题随之消解。纠正版与完整设计见上述独立文档。

---

## 9. 收费/开源(pricing 调研)
- **库层 = 免费真开源 MIT**:langgraph / deepagents / langchain。可商用 / 自托管 / 无限制 → **取 deepagents 中间件零授权成本**。
- **产品层 = 付费/闭源 SaaS**:LangSmith(可观测)、Deployment、Fleet。自托管 = 企业版(Fleet 自托管 Beta)。
- **Studio** = 闭源但免费(需登录,本地跑)。
- **n8n** = **非 OSI 开源**(fair-code / Sustainable Use License):自托管免费(仅内部用),**禁止拿它对外做 SaaS 卖** → 你"将来可能产品化"被授权堵死;MIT 的 langgraph/deepagents 无此限。

---

## 10. 待办 / 开放项
- 补查 Dify / Coze / DeerFlow / Copilot Studio(本轮零证据)。
- **内部清理**:收口 MVP-3 中间件迁移 + 给 V2.1 运行时加 checkpointer + 统一双运行时的 subagent。
- **KB/H-D**:先建 L1 规则/分类器公理层(复用现有闸门),再啃 L2 归因难题。
- Fleet GA/定价以官网为准(部分来自二手源);LangChain 命名数月一变,能力结论有 1–3 月时效窗。
- 4 个 agent 完整输出在 `/private/tmp/.../tasks/*.output`(易失),关键结论已并入本文件。
