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

**2026-08-12 补:这个猜的后果已经录成基线**(`tests/data/endpoint_probe_wire_baseline.json`,
协议 × 主机 × endpoint 名的 100 条实录)。它不是"偶尔猜错",而是**主机名压过用户声明的协议**:

| endpoint 配置 | 探测实际发出的请求 |
|---|---|
| `protocol: anthropic_compatible`,base_url 在 `api.deepseek.com` | `POST /v1/chat/completions`,OpenAI 形状的 `messages` 体 |
| `protocol: google_genai`,base_url 在 `api.deepseek.com` | 同上,一样的 OpenAI chat 请求 |
| `protocol: openai_compatible`,主机中性,endpoint **取名**含 `deepseek` | 预算字段从 `max_completion_tokens` 变成 `max_tokens` |

前两行是**用户明说了协议、代码不听**;第三行是**用户起的名字改变了发出去的字段**。
名字是标签不是事实,主机名也只是线索;判断"这条 endpoint 说哪种话"的权威来源应当是
catalog 的 `endpoint_method_candidates`——它本来就是为这件事存在的表。

注意这不等于"主机名一概不可用":`api.deepseek.com` + `openai_compatible` 确实**就是**
DeepSeek 的 OpenAI 兼容面,主机名在这里是提供方身份而不是猜测。真正的缺陷是三条:
拿主机名去**推翻**用户声明的协议、拿用户起的**名字**当事实、把这套判断**硬写成 if 链**
而不放进已有的表。`host_overrides` 的表结构本身就挡住了第一条——每条规则都限定在
`protocols` 之内,跨协议改写在这张表里根本表达不出来。

**同期录到的第三方冲突(留待 P3 裁决,证据先钉在这里)**:同一个 ARK 提供方,今天有三种发法——
生产 `call/dispatch.py:395` 的 `_call_ark_runtime` 走官方 SDK 的 `chat.completions.create`,
用 `max_tokens` + `reasoning_effort`;A2 探测发 `POST /api/v3/responses`,用 `reasoning: {effort}`;
A3 的 `ark_chat` 方言发 `POST /api/v3/chat/completions`,用 `thinking: {type}`。
接口选择上生产与 `ark_chat` 一致(都是 chat completions),**思考参数的写法三者互不相同**。
仓内没有 ARK 的权威参数文档可引,不许在重构里替它选一个——这条只能由真机对 ARK 各发一次问出来,
排进 P3/P4 的真机验收。

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
  errors.py       结构化异常(跨域共用词汇,不是域)
  events.py       事件 DTO(跨域共用词汇,不是域)
  registry/       真相:凭据/端点/路由/能力的定义、身份、边界、存储 port、状态投影
  resolve/        解析:从角色/请求推出一条具体路由链(lint / profile / handoff / fallback / 错误分类)
  role/           角色物化:角色 → 已贴合这条路由的调用设置
  dialect/        方言:五家 provider 的请求/响应形状(生产与探测唯一共用实现)
  call/           调用:客户端、chat model、dispatch、本次调用的设置与下场、predict 拦截
  probing/        测量:问什么(questions)、谁执行(executors)、怎么判(judge)、写进哪(evidence)
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
| `storage_contracts.py` | `registry/config_store.py` | 见下方 2026-08-11 订正 |
| `registry/storage.py` | `registry/fingerprint.py` | 见下方 2026-08-11 订正 |
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
| `settings_probe.py` | `call/pre_call_probe.py` | 见下方订正 5(依赖方向不允许它进 probing) |
| `registry/probe_contracts.py` | `probing/contracts.py` | |
| `events.py` | 根部原位 | 见下方订正 7(它是跨域词汇,不是域) |
| `tracing.py` | `call/tracing.py` | 见下方订正 7 |
| `exceptions.py` | `errors.py` | 根部,同样是跨域词汇 |

#### D5 的 2026-08-11 订正(P1a 实施中发现,已按新写法落地)

1. **两个 storage 不合并。** 初稿写"存储 port 只有一份"是按文件名判的,读进去才发现它们是两件事:
   `storage_contracts.py` 是**配置真相的 Port**(`ConfigTruthStore` 协议 + 内存实现),
   `registry/storage.py` 是**凭据指纹计算**(`compute_credential_fingerprint`,一个纯函数)。
   合并只会造出一个"和"式模块。各自改成名副其实的 `registry/config_store.py` 与
   `registry/fingerprint.py`。
2. **`probe_catalog` 这一层删除后,活下来的是新名字。** 别名壳里 `ProbeCatalogStore = ImportDraftStore`,
   两侧都在用。按"一个概念一个名字",保留 catalog 侧命名,`ImportDraftStore` /
   `MaterializedImportDraftCandidates` / `materialize_import_draft_candidates` 三个 legacy 名整体消失。
   `tests/test_probe_catalog.py` 随之删除——它守的正是"两个门面不许互相暴露对方的名字"这条只在
   别名层存在时才有意义的规则;存储行为测试改名 `tests/test_registry_catalog.py` 继续守行为。
3. **发现 `materialize_role` 同名两物,本期不裁决。** 设计源
   `docs/mvp1-three-module-interface-design-and-changes-2026-06-11/01-design.md:102` 写的是
   `materialize_role(request) -> MaterializedRole`;代码里有两个:
   `registry/projection.py:132` 签名是 `(role, routes, projections) -> MaterializedRole`(返回设计命名的类型,
   但今天只有测试在用),`role_materialization.py:39` 签名是 `(request) -> MaterializedRoleResult`
   (返回设计没提过的类型,但 studio 生产在用)。两个都不完全等于设计。本期只做搬迁,
   registry 域按设计名原样导出前者,**裁决留给 `role/` 域那一期**(P1b),届时对着设计源收敛成一个。
4. **`materialize_role` 同名两物的裁决(P1b 执行,补 D5 订正 3)。** 把两个都读完之后,
   它们不是重复实现,而是**一个契约被拆成了两半**:
   - `registry/projection.py` 那个持有设计命名的类型 `MaterializedRole`,**并且带着设计的不变量**
     ——空 fallback chain 必须显式带终态错误码(旧测试 `test_productization_route_state_contracts.py`
     断言不带 `error_code` 时构造直接 `ValidationError`);但它今天只有测试在用。
   - `role_materialization.py` 那个是 studio 生产真正在调的,`error_code` 在整个文件里零命中
     ——它可以返回一个空的 fallback chain 而不说任何理由。
   
   于是一个角色所有路由都挂掉时,网关交回去的是一个沉默的空列表,而调用方只有在真去跑的时候
   才会撞上 `resource.no_available_route`。裁决:**保留生产那一个的输入输出(它算得更全:自己算投影、
   应用角色意图、产出带 runtime_settings 的 `RoleRouteEntry`),把设计的名字和不变量搬到它身上**——
   `MaterializedRoleResult` 改名 `MaterializedRole`,改成 Pydantic 模型并带 `model_validator`:
   空链必须带 `error_code`;`materialize_role` 空链时返回 `NO_AVAILABLE_ROUTE`。
   `registry/projection.py` 的重复三件套(`MaterializedRole` / `materialize_role` /
   `RouteWarning`)与从无调用者的 `MaterializeRoleRequest`(user_id/role/include_diagnostics)一并删除,
   两条旧契约测试搬到 `tests/test_role_materialization_terminal_error.py` 用存活的 API 重写。
   
   **`error_payload` 不保留**:旧那一个需要它是因为它的入参只有一个角色名、没有别的地方放细节;
   存活的这一个带着 `materialization_report`(每条路由被怎么处理、warning、skipped 明细),
   再开第二个 payload 通道就是同一事实两个 owner。错误码是**对整个角色的判决**,细节留在报告里。
   Studio 侧由 adapter 把判决并进它交给前端的那份报告(`materialization_report.error_code`),
   前端类型同步加上;**具体怎么显示是另一件事**,见台账 P1b-UI。

5. **`settings_probe.py` 留在 `call/`,不去 `probing/`(P1b 查依赖方向时发现)。** D5 初稿把它排给
   `probing/`,理由是 B6 那条"两个探测家族互不相识"。但依赖方向不允许:
   `gateway_chat_model.py:42` 从它拿 `probe_call_settings`(call → probing),而它自己要用
   `call_settings` 与 `route_chat_model_factory`(probing → call)——分成两个域就是互相依赖,
   等于没分。**"贵问题前先问个便宜的"是一次调用自身生命周期的一部分**(同设置、同构造器、
   预算换成 1),不是对路由的能力测绘;`probing/` 只管面向 registry 的测量。
   B6 那条病的治法是**共用同一份方言与同一个裁决器**(P2/P3),不是把两个模块塞进同一个目录——
   共处一室不等于共用实现。

6. **没有 `observe/` 这个域;事件 DTO 与异常留在根部当共用词汇(P1c 查依赖方向时发现)。**
   初稿把 `events.py` + `tracing.py` 划成 `observe/` 域。但 `tracing.py:81`
   `emit_call_settings_event(outcomes: Sequence[SettingOutcome])` 是**拿一次调用的事实去造事件**,
   而 `SettingOutcome` 来自 `settings_outcome`,后者又依赖 `call_settings`;
   同时 `gateway_chat_model` 要调 tracing 发事件。三条连起来就是 call ⇄ observe 的包级循环。
   根因是划分标准错了:**`observe/` 想圈的不是一组共同不变量,而是"这些代码看起来都跟观测有关"**——
   按名字相似分家,正是 D4 明令要避免的。改法:`tracing.py` 与 `settings_outcome.py` 跟着
   `call/` 走(发生在一次调用之内、也只描述这次调用),`events.py` 与 `errors.py` 留在根部,
   和 `__init__.py` 一样是**跨域共用词汇**——纯 DTO / 异常类型,不依赖任何域,谁都可以用。
   域是有不变量的责任单位;词汇不是域。

7. **文档里的旧路径不在每期回写。** 全仓 docs 约 120 处提到被搬走的模块名,其中多处在带哈希锁的
   audited MVP1 设计文件里。树还要再动四期,每期扫一遍是五倍工作量且反复触发哈希锁重钉;
   改为**树定形后一次扫完**(台账新增 P1z)。

#### D5 的 2026-08-12 补记(P2b 实施中发现)

P2 拆成三步走:**P2a** 先录基线(#709,11 个官方方法 × 4 种设置 × 有图/无图 = 88 条请求
逐字段钉死),**P2b** 建 `dialect/` 域并把 A3(`probe_official_call_method` 的请求构造)
切过去,**P2c** 再收 A1/A2、抽 `judge`、把 `provider_probe.py` / `probe_contracts.py`
移进 `probing/`。判据始终是那 88 条基线一行不变——**行为要变就得让基线出现 diff,
不许藏在重构里**。P2b 落地时发现三件事:

8. **`dialect/` 是叶子域:不依赖网关里任何东西。** 它只收「最终 base_url + 密钥 + 模型 id +
   一轮提示 + 想思考多少」,吐一个**渲染好但没发出去**的 `WireRequest`。"这个方法存不存在"
   和"它用哪个 base_url"是 registry 的事实,由调用方先问 catalog、再把结果交给 dialect;
   dialect 反过来 import registry 会做成包级循环(和订正 6 里 `observe/` 死掉的原因同款)。
   代价是方法 id 在 catalog 和方言表里各列一次,由一条测试钉住两张表必须相等——
   **重复的事实靠门禁对齐,不靠 import 绑死**。

9. **`anthropic_messages` 的 base_url transform,探测侧原来没应用。** catalog 给它登记的是
   `anthropic_compatible`,而 A3 里只有 deepseek / ark 两支调了 `apply_call_method_base_url`。
   现在改成对所有方法一律先过 catalog transform。之所以还能保证基线逐字节不变:
   canonicalize 会把结尾的 `/v1` 摘掉,而随后的路径拼接又会把 `/v1/messages` 补回去,
   两者对任何非 deepseek 主机同解;真正的差别只在"给 deepseek 主机配 `anthropic_messages`"
   这种反常配置上,而那种情况下新写法给出的才是生产会用的那个 URL。

10. **`openrouter_anthropic_messages` 原来会先发一个错方言的请求再拒绝。** 它
    `official_probe: false`,但旧代码的 11 分支链末尾是**兜底当 openai chat 发**,
    直到取 backend 时才 `ValueError`——也就是说 provider 那边真收到过一个不该发的请求。
    现在查方言表查不到就在发之前拒绝。基线记录的结果(refused)不变,少发一个请求。
    这也是"兜底分支"的典型代价:**它把"没人认识这个方法"翻译成了"当最常见的那种发"**。

11. **A2(`_request_model_generation`)这期没切,因此暂时留着两份重复规则。** 它按 backend
    名(`claude`/`ark`/…)挑 wire,不知道自己在测哪个 call method,所以问不了方言;
    `_anthropic_thinking_payload` 与 `_google_thinking_config` 作为它手搓的最后两块留在原地,
    并在代码里注明去向。P2c 让它先认领 call method、再随 A1 一起归位时删除。
    没有就地把它接到方言上,是因为两者对 effort 的处理本就不同(A2 从不发 `output_config`),
    接上去等于**在一次"逐字节不变"的搬迁里偷改一条没被基线钉住的线路**。

#### D5 的 2026-08-13 补记(P2c-2:猜测删除后,判据从"协议"来)

12. **一个 `backend` 原来在回答两个问题,拆成两个函数。** 「这条 endpoint 是哪一家的」
    (决定官方方法菜单)与「跟它怎么说话」(决定请求长什么样)是两个问题,原来共用
    `endpoint_probe_backend` 一个答案,于是**主机名能推翻用户声明的协议**。
    现在:`probe_wire_backend(protocol)` 回答后者——依据是**生产就按协议分派**
    (`call/dispatch.py:189` 的 `route.protocol == "ark_runtime"`,随后
    `_call_openai_compatible` / `_call_anthropic_compatible` / `_call_google_genai`);
    `endpoint_probe_backend` 继续回答前者,但只认 url 里的厂商身份,**不再看 endpoint 的名字**。

    中途差点做错一次,记下来:先做的版本把两个问题合并成"一律按协议",跑完 studio 全量才发现
    `routers/llm.py:4100` 的官方探测候选菜单正是按这个 backend 取
    `app/data/probe_candidates.json` 的——合并等于**悄悄删掉 DeepSeek 的官方方法菜单**。
    教训不是"要跑全量测试"(那是兜底),而是:**删一个概念之前先问它在替谁回答问题**;
    这里它替两个人回答,只是从名字上看不出来。
    厂商判定同时收窄了两处:必须是 `deepseek.com` 这个域(原来是 url 里出现 "deepseek" 子串就算),
    且协议必须是 DeepSeek 真的发布过的那两个面(openai / anthropic 兼容)——
    一条 `ark_runtime` 的 url 落在 deepseek 主机上,它不是 DeepSeek 的面。

    100 条基线中 37 条变化,全部归因于三件事:声明的协议不再被主机名推翻(anthropic / google
    落在 deepseek 主机的两组)、endpoint 的名字不再决定菜单和字段、以及下面第 13 条。
    **DeepSeek 的 openai 兼容 endpoint 一条都没变**(含 backend 标签),这正是第 13 条要保证的。

13. **OpenAI 兼容面的预算字段改成 `max_tokens`,理由是生产就发这个。**
    `call/dispatch.py:239` 的 `_call_openai_compatible` 对**所有** openai 兼容路由
    (含 OpenAI 自己)发 `"max_tokens"`,从不发 `max_completion_tokens`;而探测侧原本对
    "openai" 发 `max_completion_tokens`、对 "deepseek" 发 `max_tokens`。也就是说
    **探测替 OpenAI 造了一个生产从不发的字段,却替 DeepSeek 发对了**。
    这一改让两边一致:A3 基线只动 8 行(`openai_chat_completions` 的 8 个用例),
    A2 侧 deepseek 主机的请求体一字未变——**没有任何一条路由因为删掉猜测而变得更不像生产**。
    附带结论:`openai_chat_completions` 与 `deepseek_chat_completions` 在线路上至此完全相同,
    只剩 `provider_backend` 一字之差;要不要合并是 catalog 的题,不在本期动。

14. **"能不能发"与"官方探测给不给选"分开。** `provider_probe_backend_for_method` 原本把
    「方法不存在」和「这个方法没有官方探测」都报成 `Unknown official call method`,
    于是 openrouter 的 endpoint 一问 backend 就炸。现在拆成
    `provider_backend_for_method`(任何已知方法都能问)与
    `call_method_is_officially_probeable`(A3 入口自己检查并在发请求之前拒绝);
    方言表相应扩到 catalog 的全部方法,包括 `official_probe: false` 的那个——
    **一条线路能不能渲染,和某个入口愿不愿意提供它,是两个问题。**

#### D5 的 2026-08-14 补记(P2c-3:树合拢)

15. **`probing/` 落地,`_AWAITING_REHOME` 清空,树至此完整。** 六个域各就各位:
    `registry`(真相)、`resolve`(选路)、`role`(角色物化)、`call`(调用)、
    `dialect`(线路语言)、`probing`(问一个小到值得问的问题)。域内再分三块:
    `wire.py`(问哪一个问题、怎么描述这次尝试)、`judge.py`(答案是什么意思)、
    `results.py`(报回去什么)。判据 = 两份基线(88 + 100)一行未动。

16. **`probe_contracts.py` 不搬,直接删。** 它是 7 行的转发壳,把 `registry/schema.py`
    的 `ProbeResult` 原样再导出一次,**全仓零个 import**——和 P1a 删掉的 `probe_catalog.py`
    同一物种。`ProbeResult` 是"记在 import draft 上的探测结果",属于持久化的 registry 真相,
    留在 schema 里不动。

17. **两个公开入口原来叫 `test_*`。** `test_provider_endpoint` / `test_provider_route`
    以 `test_` 开头,于是**谁把它们 import 进测试模块,pytest 就把它们当测试用例收集**
    (写 P2c-1 基线时当场撞上,报"fixture 'endpoint' not found")。随本期搬迁改名
    `probe_provider_endpoint` / `probe_provider_route`,与 `probe_official_call_method`
    对齐——**"test" 在这个仓里已经是测试框架的保留词,不该再拿来当动词用**。

18. **留一个未决:`endpoint_probe_backend` 现在住在 `probing/`,但它回答的不是探测的问题。**
    "这条 endpoint 是哪一家的"是对**已配置对象的识别**,不涉及发任何请求;它的返回类型
    `ProviderProbeBackend` 也本来就定义在 `registry/call_methods.py`。按 D4 的划分标准
    (域按不变量而不是按名字相似),它更像 registry 的事实。本期不动,是因为它会再牵一次
    studio 的 import;归位放进 P4——那一期正要重排"哪个入口问哪些问题",顺势一起做。

19. **域边界门禁又抓到一次深导入。** 搬完 `probing/` 后它立刻报
    `probing/wire.py` 还在 `from graph_agent_gateway.registry.call_methods import ...`;
    改成走 `registry` 包入口时发现 `ProviderKind` / `ProviderProbeBackend` 两个名字
    **压根不在 registry 的 `__all__` 里**——之前能用,是因为大家都在深导入。
    补进契约即可,这正是 D4 想暴露的那类欠账。

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
| P1 | 按域成树的纯搬迁(自底向上,一域一 PR:registry → resolve/role → call;probing 并入 P2 一起做) | 全门禁绿;新增深导入 lint 测试通过;`git diff` 内除 import 与文件位置外无逻辑改动 |
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
