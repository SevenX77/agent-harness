---
doc: 00-architecture-overview
status: drafted（2026-06-03 三层解耦:契约 A / 机制 B / API契约 C）
owns: Graph Agent 完整模块地图 · 契约-机制-API契约 三层 · 编译-装配-运行 生命周期 · 关键决策 · 待设计清单
ground_truth:
  - packages/graph-agent（file:line 须复核）
  - docs/engine/mvp0/workspace-spec（workspace 户型基线,待迁 physical-layout;skill-spec 契约已迁 mvp1)
---

# Graph Agent MVP1 架构总览(设计北极星)

> 本文是 engine mvp1 的**完整模块地图**。第一性原理:整个系统按 **三层** 解耦——**契约层 A**(声明式 skill 语言/规则/数据形状)→ **机制层 B**(引擎实现)→ **API 契约层 C**(engine↔studio 操作边界)。机制层按真实生命周期 **编译 → 装配 → 运行** 组织,运行再分 **外层图编排 / 内层 agent loop**。每个模块要么标「♻️ 沿用 mvp0」,要么指向它的 V4 设计——**不允许 silent omission**。本文只做 **地图 + 决策**,机制细节**链接各模块专文、不复制**(SSOT)。

## 0. 术语(正式名)

- **Graph Agent**(旧称 "engine"):**文档驱动的 agent 运行时**——主体由 LangGraph 确定性路由驱动,最大特点用文档(Graph Skill)驱动,比写 LangGraph 代码简单。
- **Graph Skill**(skill):跑在 Graph Agent 上的一整套 skill 文件(`GRAPH.md` + `phases/...`)。
- **Graph Studio**(studio):创作 / 编译 / 测试 Graph Skill 的软件。

> 目录 `docs/engine/`、包名 `graph-agent` 暂不改(避免动路径/import)。

## 1. 第一性原理:三层解耦

**判据(litmus)**:
- 能**喂 copilot / 作者要写**的声明式 skill 语言/规则/数据形状 = **契约层 A**——定义「**skill 是什么**」。
- 引擎**内部怎么实现** = **机制层 B**。
- engine↔studio 的**操作 API**(宿主怎么驱动引擎:run/predict/compile 签名 + 事件 + 端点)= **API 契约层 C**——定义「**怎么调引擎**」。

> A 是输入侧领域契约,C 是操作侧 API 契约,B 在中间。mvp0 早有 A/B 之分(`skill-spec/` 契约 vs `engine/{5子模块}` 机制);C = engine↔studio 边界(api-engine-studio-contract,第2趴)。

机制层 B 按真实管线(`compile-rules` §2 三段生命周期契约,已自承载)分三段:
- **编译期**:Loader 读 skill 源码 → DAG/IO/mention/purity 校验 → 可信 AST(或聚合 `[F-v3-*]`)。
- **装配期**:AST → 跑 reference reader、渲染 cognitive 模板 → 可运行 LangGraph 节点。
- **运行时**:`graph.invoke` → StateMapper slice/merge → 跑 phase。**运行时再分外/内,是组织铁律**(两层机制各一套:checkpoint、delta/compact、action/tool,混写=bug)。

## 2. 契约层 A(5 — 声明式 skill 语言/规则/数据形状)

| 模块 | 管什么 | 现状 |
|---|---|---|
| `physical-layout` | **整个磁盘文件结构**:skill 源码树 + `.workspace` 运行时树(**golden 在 workspace**) | ♻️ + delta |
| `skill-syntax` | skill 文件**内容/语法**(四 phase 字段 + body XML + mention + io/iterate 声明 + cognitive 模板)——只管"文件里写什么" | ♻️ + delta |
| `compile-rules` | 编译/装配/运行**生命周期契约** + 全部校验规则 + `[F-v3-*]` 错误码全表 | ♻️ + delta |
| `data-contracts` | **我们的**数据形状(BusinessData/FrameworkState/WorkflowState/result/ErrorPayload),**建在 langgraph 原语上**(原语是底座,不是我们的契约) | ✅ + delta |
| `invalidation` | 源变更 → 失效 的变更轴 + 消费者矩阵(golden/checkpoint/cache) | ⏳ |

## 3. 机制层 B(17 — 引擎实现, 按生命周期)

**编译**
| 模块 | 管什么 | 现状 |
|---|---|---|
| `01-compile` | loader/parser/校验器实现(DAG/IO/mention/**purity 扫描器**)/`module_sandbox`(导入隔离)/cache/serializer | ⏳ |
| `02-resolver` | `SkillResolverProtocol` DI 接缝(stable skill id → 本地 root;studio 注入,DI 不得隐式全局化) | ⏳ |

**装配**
| `03-assemble` | `graph_assembler`(phase→节点)/`_build_skill_node`(AGENT 闭包)/cognitive 模板渲染/`reference-reader`(装配期 builtin) | ⏳ |

**运行·外层(图编排,确定性)** `04-run-outer/`
| `01-graph-exec` | StateMapper slice/merge · 拓扑调度 · **LOGIC 执行**(action 范式)· SUBGRAPH 调用 | ⏳(LOGIC 已 live,待消 spec-code drift) |
| `02-iterate` | 循环原语(batch/loop/图级);**图级 loop = B**(引擎包 loop-body) | ✅ |
| `03-checkpoint` | 共享 base(**建外层,经 `checkpoint_ns` 内外层共用同一个**)+ 外层 blackboard 存储/delta/有界 + durability | ✅ |

**运行·内层(agent loop,LLM 驱动)** `05-run-inner/`
| `01-agent-loop` | `create_agent` 编排(model↔tool ReAct) | ⏳ |
| `02-middleware` | 6 槽链基础设施 + loop 卫生槽(ExecutionControl/LoopDetection);域专槽逻辑归各域(见 §6) | ✅ |
| `03-cognitive` | finish_task 处理(显式提交)+ 输出解析/patch(md2json) | ✅ |
| `04-tools` | agent 工具绑定/执行(StructuredTool)+ builtin read 工具;**action/tool 不统一 capability(2026-06-04 已定)** | ⏳ |
| `05-exit-control` | `after_agent` 退出闸 + NudgeInjector + 耗尽显式失败(**phase 不静默成功**) | ⏳ |
| `06-golden-eval` | 期望输出 逐节点 diff/eval(**读 `.workspace/golden`**) | ⏳ |
| `07-subagent` | 运行期子代理派发(`wrap_tool_call` 中间件;区别于 SUBGRAPH 编译期子图) | ⏳ |
| `08-messages-state` | 内层 messages 持久化(DeltaChannel,经 `ns="<id>/agent"` 挂 checkpoint base)+ summarization + HITL/resume | ✅ / ⏳ |

**接缝** `06-seam/`
| `01-models` | LLM 接缝(`GatewayChatModel`,provider 差异归 gateway)+ predict-mock chat model | ✅ |
| `02-observability` | 可观测**事件流**(34 类 typed event)+ trace.jsonl + metrics(= callbacks 系统;**不是"所有消息"**) | ✅ |

**入口**
| `07-runtime` | `run_skill`/`predict_skill` 两个执行**模式** + bootstrap + public API surface(`__all__`) | ⏳ |

## 4. API 契约层 C(1 — engine↔studio 操作边界)

| 模块 | 管什么 | 现状 |
|---|---|---|
| `03-api-contract` | `run_skill`/`predict_skill`/`compile_skill` 签名 + typed 事件协议(34 类 → trace.jsonl/WS)+ studio HTTP 端点 + `RunResult` 返回契约;共享接口 SSOT、consumer 只链接 | ✅ |

> 它是引擎的**对外操作面**:`runtime`(B)实现它、`observability`(B)供它事件流、`data-contracts`(A)供它 `RunResult` 形状——三处双向引用。**和契约层 A 不同类**:A 是"skill 是什么",C 是"怎么调引擎"。

## 5. 关键设计决策(已锁,别重开,只搬进模块)

| ID | 决策 | 动机 |
|---|---|---|
| ARCH1 | **三层** 契约 A / 机制 B / API契约 C(litmus:skill语言 / 引擎实现 / 操作API) | 三种东西三类受众,混层=drift(已踩:C 被并进 A) |
| ARCH2 | 机制 B 按 编译/装配/运行 生命周期;运行再分外/内,两层机制各一套 | checkpoint/delta-compact/action-tool 混写=bug(已踩) |
| CK | checkpoint **一个共享 base 建在外层**,内外层经 `checkpoint_ns` 共用;**各管各 state**(外=blackboard,内=messages) | 统一 resume;agent loop 也 checkpoint 才有 HITL;两层 state 分治 |
| GOLDEN | **golden 在 `.workspace`,不写进 skill 本体**(会失效的临时优化产物);失效校验从编译期移到 eval 期 | PM 2026-06-03 反转(原决策 A 作废):golden 非 skill 定义的一部分 |
| PREDICT | predict 是**执行模式**(run/predict),非独立域;mock→models、入口→runtime、golden 内容→golden-eval | "predict 只是一个无情的机器" |
| GRAPH-LOOP | 图级 loop = **B**(引擎把 DAG 包成 loop-body,一 thread + ns/iter) | DAG-only,用户画不出回边 |
| EXIT | phase 不静默成功:`after_agent` 闸,要么合格 finish_task、要么显式失败 | 静默 END 让下游看见空 BusinessData 却不知原因 |
| ACTION-TOOL | action(LOGIC,确定性,引擎调)vs tool(AGENT,LLM 调)= 两套;是否统一 `capability` 待决 | 外/内主轴;取舍写 tools 域时定 |
| SANDBOX | 运行期工具沙箱 = **伪需求**;purity = compile-rules 的一条**规则**,purity 扫描器/`module_sandbox` = `compile` 机制 | 引擎跑可信 skill 工具 + purity 编译期已挡;deerflow 那种运行期 jail 是不可信 bash 才需要 |

## 6. 跨切纪律(防 drift)

- **SSOT**:一个事实只在一处 owner 写实现,别处只链接。
- **跨切内容写法**:非本模块 scope 的部分**写完整逻辑 + 引用 detail 落点**(不裸链、不复制),**A↔B 两侧双向引用**。典型跨切点:
  - middleware 域专槽:CognitiveFlow→`cognitive`、Tracing→`observability`、ToolError→`tools`(逻辑归域,`middleware` 只写槽位+概述+双向链)。
  - checkpoint 共享 base:`03-checkpoint`(外/base)↔ `08-messages-state`(内/messages)。
  - purity:`compile-rules`(规则)↔ `01-compile`(扫描器实现)。
  - golden:`06-golden-eval`(eval)↔ `physical-layout`(.workspace 落点)↔ `invalidation`(失效)。
  - api 面:`03-api-contract`(C)↔ `07-runtime`/`02-observability`/`data-contracts`。

## 7. 待设计清单(❌/⏳)

- **⚠️ 校正(2026-06-04 verify)**:`LOGIC 执行`并非空白——`_build_logic_node` 已 live、真实 skill 在用;真问题是 **spec-code drift**(action 签名 `run(state_slice)` FROZEN vs `<name>(context)` live)+ 删死簇,**非 from-scratch 设计**。`07-runtime` 同理(`run_skill` live 在 runner.py,缺的是顶层契约文档,非代码)。
- **进展(2026-06-04)**:① **LOGIC 已定**——`纯返回 / 硬禁 / 反写`(干净 action 契约:只读 inputs→返回 dict、禁 mutation/run_skill/FS;live drift = refactor-target;反写解冻 `03-logic-md-spec`;见 `graph-exec` LE1-3)。② **action/tool capability = 不统一**(spec 已固定 Action≠Tool,纯 action(read-only dict)vs StructuredTool 本质不同)。
- **真·待定**:③ `07-runtime` 顶层契约成文(run_skill/bootstrap/public API,均 live);④ `04-tools` builtin/binding/ToolError 文档化(live,待 doc + 校 drift)。原则:**code 向干净设计对齐,不拿 live 当真理**。
- **⏳ 成段化**:`01-compile`/`02-resolver`/`03-assemble` 实现机制;`invalidation`(golden-stale 移 eval);`06-golden-eval` 按 golden→workspace 改写。(`skill-syntax`/`compile-rules` 已自承载迁出 mvp0,见 `INDEX.md` §2)

## 交叉引用(链接, 不复制)
README(章节去向)· 契约层 A(5)· 机制层 B(17)· API契约层 C(1)· mvp0/skill-spec(契约已迁 mvp1,留底)· mvp0/workspace-spec(workspace 户型待迁)· ../design/agent-loop-planA-create-agent-migration(迁移叙事)
