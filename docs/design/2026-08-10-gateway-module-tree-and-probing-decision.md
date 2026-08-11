# 网关按域成树,测试只有一套方言(2026-08-10 决议)

> 状态:已批准(用户,2026-08-10),分期实施中。
> 前置决议:[运行时配置是偏好](2026-08-10-runtime-settings-are-preferences-decision.md)、
> [偏好贴合路由](2026-08-10-preferences-fit-the-route-decision.md)。本决议不改写它们的任何一条,
> 只回答它们没覆盖的两个问题:**测试能力应该有哪几种**,以及**网关的代码应该按什么分家**。
> 范围:`packages/graph-agent-gateway`(主体)、`apps/studio/backend`(探测编排与 HTTP 边界)、
> `packages/graph-agent`(仅 import 路径跟随)。

## 0. 一句话

五家 provider 的差异只有一处——**请求/响应方言**;方言写一份,生产调用和能力探测共用它。
测试能力按"要不要出网、出网问什么、答案怎么判"分成四层,每层一个显式接口,任意组合。
网关按**领域**成树,每个域的公共契约就是它的包入口,域外不许深入别人的文件。

## 1. 证据

### B1. 同一套方言在仓里有两份实现

拿一条最小的规则量:"effort 怎么进请求体"这一句话,在仓里有 **8 处赋值、分布在 5 个函数**:

| 侧 | 函数 | 赋值处 |
|---|---|---|
| 生产 | `ordinary_chat.py:221` `_call_openai_compatible` | `:254` `kwargs["reasoning_effort"] = reasoning_effort` |
| 生产 | `ordinary_chat.py:287` `_call_openai_responses` | `:308` `kwargs["reasoning"] = {"effort": reasoning_effort}` |
| 生产 | `ordinary_chat.py:392` `_call_ark_runtime` | `:423` |
| 探测 | `registry/provider_probe.py:318` `_request_model_generation` | `:367`(responses 形)、`:379`(chat 形) |
| 探测 | `registry/provider_probe.py:434` `_request_official_call_method_generation` | `:462`、`:478`、`:569` |

发送方式也是两套:生产走官方 SDK(`ordinary_chat.py:262`
`client.chat.completions.create(**kwargs)`),探测手搓 httpx(`registry/provider_probe.py:380`
`client.post(...)`)。

后果不是多写了代码,而是**探测通过不等于生产能跑**:两条路的默认头、参数名、重试与错误解析
都不是同一份,任一侧改动都不会让另一侧失败。

### B2. 探测根本没有工具调用这一问

`registry/provider_probe.py` 全文没有 `tools` 字样(1025 行,零命中)。而引擎运行时真正依赖的
就是工具调用——`graph_agent/core/llm_provider.py:137` 的 `bind_tools` 是每个 agent 循环的入口。
也就是说:今天四个 Test 按钮没有一个能回答"这条路由能不能进 ReAct 循环"。

### B3. "这是哪家"靠猜主机名

`registry/provider_probe.py:264-280` 的 `endpoint_probe_backend` 用
`if "deepseek" in base_host` / `if "deepseek" in endpoint_id` 推断方言。
方言没被显式建模,才需要这种猜。

### B4. 存在一个自述"为了向后兼容"的别名壳

`probe_catalog.py:1-5` 原文:实现"currently reuses the legacy import-draft store types for
backward compatibility"。全文 39 行,只做改名转发。项目铁律是没有向后兼容——旧路径必须在同一次
变更里删掉,不留别名。这一层今天还有 16 处外部 import 依赖它。

### B5. 平铺的模块表,让内部结构成了公共契约

`graph_agent_gateway/` 下 24 个平铺模块 + `registry/` 17 个;外部(studio backend + engine + 三套
测试)对网关的 import 语句共 **531 条**,其中直接深入内部文件的占绝大多数
(`registry.schema` 一处就被 import 146 次)。这意味着任何内部整理都会波及三个模块——
不是因为耦合必须这么紧,而是因为**没有域级入口可依赖**,调用方只能逐文件深入。

### B6. 已经存在两个互不相识的探测家族

- `settings_probe.py`(147 行,"One cheap question, asked before the expensive one"):在**生产路径上**
  用同一个 chat model 发 1-token 问题,判定哪一项设置会被拒。
- `registry/provider_probe.py`(1025 行):在**生产路径之外**手搓 httpx,判定端点/路由/调用方式是否可用。

两者问的是同一类问题("这条路由收不收这个请求"),却没有任何共享结构。

### B7. 有一个不发请求就写实测证据的接口

`apps/studio/backend/app/routers/llm.py:1425-1444`:`POST /routes/{id}/probe` 不带 `force` 时,
直接把请求体里的 capabilities 标成 `source="probed_verified"` 并把路由置为 `verified`——
证据来源是入参,不是测量。前端无人调用(唯一调用点 `AvailableModelsSidebar.tsx:152` 恒传 `force: true`),
但接口开着。

## 2. 决策

### D1. 测试能力分四层,每层一个显式接口

| 层 | 名字 | 出网 | 问什么 | 产出 |
|---|---|---|---|---|
| T0 | 静态校验 | 否 | key 空 / base_url 空 / 端点被禁用 / 协议与 URL 冲突 | 拒绝理由,或"可以出网" |
| T1 | 可达性 | 是(1 次 GET) | 这把 key + 这个 URL + 这个协议对不对得上话 | 可达状态 + 模型清单 + 清单自带能力 |
| T2 | 能力测绘 | 是(1..N 次生成) | 这条路由接不接受这个请求形状 | 每问一条 `Measurement` |
| T3 | 行为测试 | 是(多轮) | 工具调用回不回来 / ReAct 闭环收不收敛 | 行为级 `Measurement` |

**T2 不拆成"跑通一次"和"全量测绘"两个能力,而是同一能力的深度参数**:深度 0 = 一次最小生成,
深度 N = 逐问枚举(可用调用方式、模态、thinking 形态、effort 枚举、输出上限、温度/top_p 接受域)。
理由:方言相同、判据相同、写入口相同,不同的只有问题清单;拆成两个能力必然长出第二份实现,
正是 B1 的成因。

**T3 必须走生产同一条调用路径**(网关 dispatch + `LLMProviderChatModel.bind_tools`),不得手搓 HTTP。
分两级:L1 单轮(发 tools,看回不回 tool_call),L2 闭环(把工具结果回给它,看它继续并收敛出终答)。
`apps/studio/backend/app/services/copilot.py:1849` 的 CLI 测试是 L2 的一个执行器变体,收编进 T3。

**不属于测试能力的**:角色 Test 不是新原子,它是"拿一组已 fit 的设置跑 T2 深度 0(将来加 T3)";
B7 那个不发请求就写证据的分支删除。

### D2. 方言唯一实现,生产与探测共用

新增 `dialect/` 域:每家 provider 一个 adapter,只回答两件事——**怎么把一次调用意图拼成这家的请求**、
**怎么把这家的响应读成统一结果**。生产调用与探测调用是同一个 adapter 的两个调用方,
区别只在预算(1 token vs 真实预算)与是否带工具。

判据:**探到什么 = 生产会发什么**。做不到这一条,后面所有测量都不算数。

方言的选择由端点的 `protocol` 显式决定,删除按主机名猜测(B3)。

### D3. 测量结果只有一个写入口

`Measurement[] → CapabilityValue(source="probed_verified")` 的转换只允许存在一处
(`probing/evidence.py`)。任何"我知道它支持"的写法都必须来自一次真实测量;不发请求就不许写证据。

### D4. 网关按域成树,域的公共契约就是包入口

七个域,划分依据是**一组共同的不变量**,不是文件名相似:

```
graph_agent_gateway/
  __init__.py     极薄:只 re-export 各域已定的公共 API
  errors.py       结构化异常
  registry/       真相:凭据/端点/路由/能力的定义、身份、边界、存储 port、状态投影
  resolve/        解析:从角色/请求推出一条具体路由链(lint / profile / handoff / fallback / 错误分类)
  role/           角色物化:角色 → 已贴合这条路由的调用设置
  dialect/        方言:五家 provider 的请求/响应形状(生产与探测唯一共用实现)
  call/           调用:客户端、chat model、dispatch、本次调用的设置与下场、predict 拦截
  probing/        测量:问什么(questions)、谁执行(executors)、怎么判(judge)、写进哪(evidence)
  observe/        事件与追踪
```

保留 `registry` 这个名字:它是 AGENTS.md 与 MVP1 设计源里已定义的术语("credential / route / registry
TRUTH"),改名只会制造词汇漂移。变化的是它的**范围**——解析、探测、调用从中迁出,它只留真相。

**域级契约规则(本决议新增的硬约束)**:域外只允许 `from graph_agent_gateway.<域> import X`,
不允许 `from graph_agent_gateway.<域>.<文件> import X`。每个域的 `__init__.py` 就是它的公开契约,
域内文件怎么拆是域自己的事。这条规则由一条 lint 测试守住(遍历三个模块的源码,断言没有深导入)。

### D5. 搬迁映射(纯搬,不改行为)

| 现在 | 去处 | 备注 |
|---|---|---|
| `registry/schema.py` `registry/contracts.py` | `registry/` 原位 | |
| `registry/canonical.py` `registry/route_identity.py` | `registry/identity.py` | 两者都只做身份归一,合并 |
| `registry/base_url.py` `registry/endpoints.py` `registry/credentials.py` | `registry/` 原位 | |
| `registry/capabilities.py` `registry/call_methods.py` | `registry/` 原位 | |
| `registry/storage.py` + `storage_contracts.py` | `registry/storage.py` | 存储 port 只有一份 |
| `import_draft_store.py` | `registry/catalog.py` | `probe_catalog.py` 删除(B4) |
| `state_projection.py` | `registry/projection.py` | 真相 → UI 状态的投影 |
| `settings_bounds.py` | `registry/bounds.py` | 边界是路由的事实 |
| `credential_resolver.py` | `registry/credential_resolver.py` | |
| `registry/resolver.py` `registry/lint.py` `registry/profile_selector.py` | `resolve/` | |
| `route_handoff.py` `fallback_decision.py` `registry/error_classification.py` | `resolve/` | |
| `role_materialization.py` | `role/materialization.py` | |
| `ordinary_chat.py` 的 `_call_*` | `dialect/*.py` | P2 拆,先整体搬到 `call/dispatch.py` |
| `client_manager.py` | `call/clients.py` | |
| `gateway_chat_model.py` `route_chat_model_factory.py` | `call/chat_model.py` `call/factory.py` | |
| `provider_profiles.py` `models.py` `predict_interception.py` | `call/profiles.py` `call/models.py` `call/predict.py` | |
| `call_settings.py` `settings_outcome.py` | `call/settings.py` `call/outcome.py` | |
| `resolver.py` `protocol.py` | `call/resolver.py` `call/protocol.py` | 运行时平面入口与它的 Port |
| `registry/provider_probe.py` | `probing/wire.py` | P1/P3 再拆成 dialect + questions |
| `settings_probe.py` | `probing/pre_call.py` | 与 wire 探测同域(B6) |
| `registry/probe_contracts.py` | `probing/contracts.py` | |
| `events.py` `tracing.py` | `observe/` | |
| `exceptions.py` | `errors.py` | |

### D6. 同期删除(不留别名、不留兼容)

- `probe_catalog.py` 整个别名层(B4);
- `POST /routes/{id}/probe` 的非 force 分支(B7);
- `endpoint_probe_backend` 的主机名猜测(B3);
- 探测侧手搓的 httpx 请求体构造(B1),由 dialect 取代。

### D7. 分期与验收判据

每期一个 PR,自己跑完 CI 全门禁 + 真机验证,通过即自动推进下一期(用户 2026-08-10 授权)。

| 期 | 内容 | 验收判据 |
|---|---|---|
| P0 | 本决议落盘 | 文档合并 |
| P1 | 按域成树的纯搬迁(自底向上,一域一 PR:registry → resolve/role → call → probing → observe) | 全门禁绿;新增深导入 lint 测试通过;`git diff` 内除 import 与文件位置外无逻辑改动 |
| P2 | 抽 `dialect/` + `judge`,**探测侧先切** | 现有探测测试全绿(它们就是护栏);新增 wire 契约测试:每家拼出的请求体逐字段断言 |
| P3 | 生产 `dispatch` 切到同一组 dialect | 切换前先给现有 6 个 `_call_*` 补齐请求体契约测试(录制当前 body 作为基线),切换后逐字段不变;真机跑一次完整 run |
| P4 | `questions`/`runner` 落地,四个 HTTP 入口改成选题;effort 测量归位到"测试模型";删 B7 分支 | 真机点四个 Test 各一次,产出逐项报告(动作/预期/实测/截图);effort 档位在"测试模型"后可见变化 |
| P5 | T3:ToolCall(L1) → ReactLoop(L2);copilot CLI 收编为第三种执行器 | 真机对至少两家 provider 各跑一次 L1/L2,结果写进路由能力 |

P3 不押后。它动的是所有真实推理的出口,风险最高,但"探测=生产"这条保证只有它能给;
押后就等于前面几期做完仍不知道探出来的结论算不算数。风险由契约测试兜底,不由延期兜底。

## 3. 不做什么

- 不为搬迁保留旧 import 路径的转发壳(项目铁律:没有向后兼容);
- 不在本决议内改变任何对外 HTTP API 的语义(P4 只改"哪个入口问哪些问题",不改响应契约);
- 不引入新的 provider 支持,不改动任何 provider 的现有行为;
- 不把 studio 专属的关注点搬进网关——studio 侧留下的是 HTTP 边界与真相落盘,不是探测逻辑。
