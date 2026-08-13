# graph-agent-gateway 使用手册

> **这份文档回答的问题**:我是一个要调大模型的应用,装上这个包之后,**具体怎么用它**——
> 我要自己提供什么、从哪个入口进、五件常做的事各写几行代码。
>
> **它不回答**:这个包为什么这样划分(那是
> [`README.md`](../../packages/graph-agent-gateway/README.md) §2 的边界判据),
> 也不回答某个模块的内部设计(那是 [`mvp1/`](./mvp1/) 里各模块的 `mvp1-alignment.md`)。
>
> 本文所有代码路径与函数签名均取自 `packages/graph-agent-gateway/src/graph_agent_gateway/`
> 当前实现;与实现不符即为本文缺陷,以实现为准并修本文。

---

## 1. 装配:宿主必须提供的两样东西

这个包**不碰存储、不碰网络配置**。它需要宿主给两样东西,给完就能用。

### 1.1 一份 `RegistrySnapshot`——所有真相的入口

`RegistrySnapshot`(`registry/schema.py`)是端点、路由、角色、模型档案与运行策略的**内存快照**。
包里没有任何代码去读文件或数据库:快照从哪来,由宿主决定。

```python
from graph_agent_gateway.registry import RegistrySnapshot

snapshot = RegistrySnapshot(
    provider_endpoints={...},   # endpoint_id -> ProviderEndpoint
    provider_routes={...},      # route_id    -> ProviderRoute
    roles={...},                # role_name   -> RoleEntry
)
```

Studio 的做法是从本地 JSON 文件读出来再构造(`apps/studio/backend/app/services/llm_credentials.py`),
但那是 Studio 的选择,不是本包的要求。

**注意快照里的模型是本包定义的那一套,不是宿主的。** 例如 `ProviderEndpoint` 只有
`endpoint_id` / `protocol` / `base_url` / `api_key` / `provider_kind` 这类**调用需要**的字段,
**没有 `display_name`**——给人看的名字是 UI 的事。Studio 需要它,所以 Studio 在自己那边
继承出一个子类加上去(`app/models/llm_config.py:77`),而不是往 SDK 里塞。你的宿主可以照做。

### 1.2 一个凭证提供者——密钥永远不进快照

`CredentialProviderProtocol`(`registry/contracts.py:33`)只有两个方法,宿主实现:

```python
class CredentialProviderProtocol(Protocol):
    def describe(self, ref: str) -> CredentialDescriptor:
        """给出这份凭证的非密文状态,供配置页/就绪检查读。"""

    def get(self, ref: str) -> SecretStr | str:
        """只在真要发请求的那一刻返回密文。"""
```

分成两个方法是刻意的:**问「这把 key 配好了吗」不需要拿到 key**。
配置检查、就绪投影、lint 全走 `describe`;只有实际发请求的那一步走 `get`。

包内自带一个够用的实现 `EndpointCredentialProvider`(从 `ProviderEndpoint` 上取 `api_key`),
想接自己的密钥库就换掉它。

---

## 2. 六个域,各管一件事

包按**领域**成树,每个域的公共契约就是它的包入口。域外只从包入口导入
(`from graph_agent_gateway.<域> import X`),不深入别人的文件——这条由
`tests/test_gateway_package_boundary.py` 的 AST 门禁强制。

| 域 | 一句话职责 | 什么时候你会用到它 |
|---|---|---|
| `registry` | **真相**:端点/路由/凭证/能力的定义、身份、边界、状态投影 | 造快照、算端点 id、读能力、投影 UI 状态 |
| `resolve` | **选路**:从角色推出一条有序的路由链,含 lint / profile 选择 / fallback 决策 / 错误分类 | 要知道「这个角色该用哪条路由」 |
| `role` | **角色物化**:角色 → 已贴合这条路由的调用设置 | 要把角色的意图落成具体参数 |
| `call` | **调用**:拿路由真正发一次请求(两张脸:LangChain 的和不要 LangChain 的) | 要真的调模型 |
| `dialect` | **线路语言**:每家 provider 的请求/响应形状 | 一般不直接用;探测与生产共用它 |
| `probing` | **问一个小到值得问的问题**:端点通不通、路由认不认、这档 effort 收不收 | 要测一条配置是否可用 |

---

## 3. 五条常做的路径

### 3.1 角色 → 路由链

```python
from graph_agent_gateway.resolve import resolve_role

resolved = resolve_role(
    snapshot,
    "graph_agent",
    credential_provider=provider,        # 可选;不给就只做不需要密钥的部分
    route_override="vendor:gpt-5",       # 可选;绕开角色的 fallback 链直接指定
)
```

返回 `ResolvedRole`,三样东西一起给:

- `routes`:一条**有序**的 `ResolvedRoute` 链,第一条是首选;
- `skipped_diagnostics`:每条**被跳过的**路由和跳过的理由码(`SkippedRoute`,
  `route_missing` / `route_not_executable` / …);
- `lint_results`:这条链上每个「你依赖了一项没人验证过的能力」级别的告警。

跳过原因是一等返回值,不是日志——它就是「这个角色为什么没用你以为的那条路由」的答案。

角色没配抛 `RegistryResolutionError`,fallback 链空了也抛
(`resolve/resolver.py:224`);**它不会悄悄回退到某个默认模型**。

### 3.2 路由链 → 一次调用

```python
from graph_agent_gateway import GatewayChatModel

model = GatewayChatModel(
    role_name="graph_agent",
    resolved_role=resolved,
    max_tokens=4096,
    credential_provider=provider,
)
answer = await model.ainvoke([HumanMessage(content="...")])
```

`GatewayChatModel` 是一个标准的 LangChain `BaseChatModel`,所以任何吃 `BaseChatModel` 的
东西(agent 循环、工具绑定、结构化输出)都能直接吃它。它在内部按链逐条尝试、按错误分类
决定要不要换下一条、记熔断与用量。

**只想要路由、自己去调**也可以:`resolve_role` 的结果就是完整交接契约,拿着 `ResolvedRoute`
用自己的 SDK 发请求,不必用 `GatewayChatModel`。Studio 的 copilot 走的就是这条。

### 3.3 不想碰 LangChain:同一条链,朴素的进出

```python
from graph_agent_gateway import chat_plainly

answer = chat_plainly(
    resolved,                                        # 3.1 解析出来的那个
    [{"role": "user", "content": "..."}],            # 普通字典,不用构造任何对象
    credential_provider=provider,
)
answer.text        # 回答
answer.route_id    # 哪条路由答的——链走过之后,这不是可有可无的信息
answer.usage       # {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...}
answer.reasoning   # 有思考内容就在这儿,不会被拌进 text 里
```

**LangChain 不是普世标准**,一大批 app 直接用普通 chat 协议调模型,根本不 import 它。
这条路径就是给它们的:**进出没有一个 LangChain 类型**,`PlainAnswer` 是个普通的
frozen dataclass。

它和 3.2 不是两套实现,是同一条链的两张脸——**同样会逐条试 fallback、同样跳过熔断中的
路由、同样记用量**。跳过 LangChain 不该顺带把网关的本事也跳过了;真想连调用都自己来,
那是 3.2 末尾说的 route handoff,不是这条。

只给同步版:编排一路到底是同步的,异步版只会是 `asyncio.to_thread` 的一层包装——
那是你一行就能写的东西,由网关提供反而像是在假装有真异步。

### 3.4 探一个端点:这把 key + 这个 URL 对不对得上话

```python
from graph_agent_gateway.probing import probe_provider_endpoint

result = await probe_provider_endpoint(endpoint, api_key=secret, timeout=8.0)
# result.status:  ok / invalid_key / network_error / protocol_unsupported / ...
# result.model_ids:  这个端点自己报出来的模型清单
```

它发一次列模型请求。**能列模型不等于能生成**——余额耗尽的账号照样能列清单。所以
「这条路由能用吗」要用下面那个。

### 3.5 探一条路由:让它真答一句

```python
from graph_agent_gateway.probing import probe_provider_route

result = await probe_provider_route(
    endpoint,
    route,
    api_key=secret,
    runtime_settings={"reasoning": {"enabled": True, "effort": "high"}},  # 可选
)
```

它**用生产同一个工厂造出模型**,问一句 `ping`、`max_tokens=1`。这一条是刻意的:
探针发出去的请求就是真跑时发的那条,所以「探得通」和「跑得起来」不会各说各话。

要一次问一组问题(例如逐档试 effort),用 `probing` 的问题集:

```python
from graph_agent_gateway.probing import accepted_effort_levels, ask_each, effort_questions

answers = await ask_each(effort_questions(endpoint.protocol), my_asker)
levels = accepted_effort_levels(answers)   # None = 这批答案什么也没定
```

`effort_questions` 除了真实档位,**还会多问一档根本不存在的**
(`EFFORT_CONTROL_LEVEL`)。这是对照组,不是冗余:一个压根不校验该参数的 provider
会把每一档都收下,答案长得跟「这七档我全卖」一模一样。所以对照档被收下时
`accepted_effort_levels` 返回 `None`——**这批答案关于任何一档都不算证据**,
按「不确定就不写」处理,而不是记下一张没人核过的清单。对照档永远不会出现在返回值里。

`ask_each` 收一个「怎么问」的函数,而不是自己去发请求——因为**「现在允不允许问」和
「怎么告诉用户正在问」是应用的事**:端点被用户禁用要当场拒、界面要显示探测进行中,
这些网关不该知道,也不该替你跳过。

### 3.6 答案有三种,不是两种

`ProviderProbeStatus`(`probing/judge.py`)里,**只有两个成员是「问出答案了」**:

| status | 意思 |
|---|---|
| `ok` | 问出来了,答案是能 |
| `capability_unsupported` | 问出来了,答案是不能——模型自己说它不支持 |
| 其余七个 | 没问出答案,区别只在为什么(key / 余额 / URL / 时机 / 模型 id) |

第二行是容易被吃掉的那一个。实测(2026-08-11,Ark):塞图进去,provider 答
HTTP 400 "Model only support text input" —— 模型在、文本调用照常能跑,它只是不吃图。
这句话若落进 `invalid_model`,记下的是「没有这个模型」;若落进 `error`,记下的是
「我们没问出来」。两种都是把一个确定的回答改写成别的事,而这份记录是要往社区分享的。

**答案怎么变成能力,由网关给**,宿主不要自己拼:

```python
from graph_agent_gateway.registry import measured_image_input

measured = measured_image_input(accepted=result.status == "ok")
# 认图:{"vision": True, "input_modalities": ["text", "image"]}
# 不认:{"vision": False}                     ——都带 source="probed_verified"
route.capabilities.update(measured)
```

**正反两个答案都要写下来**,和 `measured_effort_capability` 同一条理由:能力位空着
读作「还没人问过」,会招来同一笔重复开销;而 catalog 那句 `provider_doc` 的「支持图像」
若不被实测覆盖,就会一直站在那儿。

**落点不对称,这是有意的**:`vision` 是「认不认图」的是非答案,两个方向都写它;
`input_modalities` 是一份**下界**清单(宿主通常把文档声称与已验证 profile 的清单并起来),
所以正答往里加 `image` 撑得住,负答却不能把它改写成 `["text"]` —— 一次被拒的图证明不了
音频、pdf 或文档列的其他任何一项。**要判断一条 route 是不是实测认图,读 `vision` 且要求
`source == "probed_verified"`,不要去数模态清单里有没有 `image`**:清单里那一项可能来自文档。

### 3.7 HTTP 状态码是 provider 的选择,答案的含义不是

同一件事——**这把 key 是坏的**——两家的答法不一样(实测 2026-08-12):

| provider | HTTP | body |
|---|---|---|
| DeepSeek | 401 | `invalid_request_error` / "Authentication Fails, Your api key: \*\*\*\*de40 is invalid" |
| Google | **400** | `INVALID_ARGUMENT` / "API key not valid. Please pass a valid API key." / `details[0].reason: "API_KEY_INVALID"` |

余额耗尽也一样:Anthropic 用 HTTP 400 说 "credit balance is too low",而不是 402/403。

所以 `probe_status` 在 400/404 分支里**先问账户级的两件事**——余额、凭据——再去看模型:

```python
# probing/judge.py,400/404 分支的顺序
_is_billing_error(answer)              -> "quota_exceeded"
_is_credential_error(answer)           -> "invalid_key"
_rejects_our_payload(answer)           -> "error"                    # 被拒的是我们发的东西
_refuses_the_capability_asked(answer)  -> "capability_unsupported"   # 被拒的是问题本身
...                                    -> model_not_found_status     # 到这儿才轮到模型
```

**为什么顺序是这个**:余额和 key 替**整个端点**作答——该端点下每个模型都会这样答。把它
记成 `invalid_model`,记下的是「这个模型不存在」,并且因为 `invalid_model` 是**确定的**
答案(不在 `INCONCLUSIVE_PROBE_STATUSES` 里),一批**连门都没进**的能力探测会被读成
「这条路由就卖这几档」。

**宿主要做的事**:把 `invalid_key` / `quota_exceeded` / `protocol_unsupported` 当作**结构性**
失败——它们会拒掉端点上每一个模型,所以批量探测应当就地短路,而不是逐个模型再问一遍。
`invalid_model` 不属于这一族:它是模型级的,换个模型 id 仍值得一试。

**四张标记词表都按实测原文长**(账单 / 凭据 / payload 被拒 / 能力被拒),新 provider 的
措辞实测到一条加一条。判据读的是 provider 说的**全部**内容——`type`、`code`、`message`,
以及 Google 放条件的 `details[].reason`(`google.rpc.ErrorInfo` 的标识符,天生给程序读,
而 `message` 是给人读的散文且可本地化)。

**同一件事在运行时也认得**:账单与凭据这两条**账户级条件**的词表放在
`graph_agent_gateway/account_conditions.py`,探测判据(`probing/judge.py`)与运行时判据
(`resolve/error_classification.py`)读同一份——一句话不能因为谁读到而有两种含义。运行时
认出它的后果是**继续走 fallback 链**:key 坏了值得换一个账户再试,重试同一个没有意义。

收进那份词表的门槛是「**与请求无关**」:余额和 key 对每个模型、每次调用都给同一个答案。
「这个模型不吃图」「这个参数不认识」换个模型换次调用就变,不进去,留在各自的消费者那里。

---

## 4. 这个包不做什么

- **不读写任何存储**:快照与密钥都由宿主注入,包内没有文件路径与数据库连接。
- **不做 UI 与产品策略**:不决定默认推荐谁、什么算「弃用」、状态显示什么颜色。
- **不替你决定调用方式**:三张脸并列摆着——要 LangChain 生态用 `GatewayChatModel`(3.2),
  不要 LangChain 用 `chat_plainly`(3.3),连调用都想自己来就只拿 `ResolvedRoute`(route
  handoff)。选哪张是宿主的事,网关不替你选。
- **不保留向后兼容**:本仓未发布,schema 与 API 可以整体替换;不写迁移垫片,旧数据的处置
  是重新生成,不是双格式读取。

---

## 5. 相关文档

| 想知道 | 去哪 |
|---|---|
| 为什么这样划分边界 | [`packages/graph-agent-gateway/README.md`](../../packages/graph-agent-gateway/README.md) §2 |
| 某个模块的目标设计 | [`mvp1/<模块>/mvp1-alignment.md`](./mvp1/) |
| 域树与探测能力怎么定下来的 | [`docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md`](../design/2026-08-10-gateway-module-tree-and-probing-decision.md) |
| 当前在做什么、卡在哪 | [`docs/development/DELIVERY_LEDGER.md`](../development/DELIVERY_LEDGER.md) |
