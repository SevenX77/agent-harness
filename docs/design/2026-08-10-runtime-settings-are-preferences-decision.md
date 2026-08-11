# 运行时配置是偏好，不是命令(2026-08-10 决议)

> 状态:已批准(PM,2026-08-10),尚未实施。
> 范围:`packages/graph-agent-gateway`(主体)、`packages/graph-agent`(事件镜像)、
> `apps/studio/backend`(报告汇总)、`apps/studio/frontend`(trace 呈现)。

## 0. 一句话

用户给的运行时设置(temperature / thinking / max_output_tokens / …)是**偏好**:
网关尽力把它落到 provider 请求上,落不上就照常跑完,但必须把「你要的」和
「实际的」一起报出来,对不上的地方记 warning。**任何一项设置都不得成为调用失败的理由。**

## 1. 为什么现在要做:两条实测证据

### B1. 推理被丢了几个月,没有任何人吭声

2026-08-09 实测:同一条路由 `deepseek-official:deepseek-v4-pro`,不带任何 thinking 参数的
普通流式调用,**原始 SSE 里带 147 字 `reasoning_content`**;而经过我们自己的封装之后,
分片的 `additional_kwargs` 是空的。推理一直在送,我们在落地后一层把它扔了(已由 PR #691 修复)。

这个缺陷能瞒这么久的唯一原因是:**系统在丢东西的时候不吭声**。一个只在成功时说话、
失败时沉默的系统,看起来永远是对的。

### B2. 参数被拒 = 整条路判死(当前最硬的硬关)

同日实测,给同一条路由发一个 provider 不接受的参数值:

```
message=Failed to deserialize the JSON body into the target type:
        thinking: invalid type: boolean `true`, expected struct ThinkingOptions
→ AllProvidersFailedError: [F-v3-gateway-all-providers-failed]
  All providers failed for role=analyst: 1 provider candidates failed
```

一个参数写错,结论是「所有 provider 都失败了」。根因是异常分类只按**路由健康**
一个维度看世界(`call/chat_model.py` 的候选走查 + `classify_exception`),
它分不清「这条路挂了」和「这条路活着,只是不吃这个参数」。

这比静态能力标记危险得多:它**伪装成路由故障**,看报错的人不会想到去检查设置。

### B3. 探针已经存在,但问错了问题

`GatewayChatModel.probe_before_call` 默认 `True`(`call/chat_model.py:154`),
每次 LLM 调用在挑候选路由时,正式请求之前先探一次(`call/chat_model.py:279`)。
探针内容是写死的最小请求(`call/clients.py:333`):

```python
openai_client.chat.completions.create(
    model=route.provider_model_id,
    messages=[{"role": "user", "content": "."}],
    max_tokens=1,
    temperature=0,
)
```

**用户的设置一个都没带。** 所以它能回答「这条路活着、凭据有效」,
对「这些参数认不认」一无所知。探的位置已经对了,缺的是让它带上真实设置去问。

## 2. 决策

### D1. 配置是偏好,不是命令

网关尽力落配置;落不上照常跑完;差异必须被报出来。
**禁止**因为某项设置不被支持/不被接受而使调用失败。

### D2. 参数被拒 ≠ 路由不可用

provider 因为某个参数拒收请求时,正确处理是:**摘掉那一项、记 warning、
继续用这条路由重发**,而不是把路由标记为 down、不是换路、更不是判定全部 provider 失败。
路由健康与参数可接受性是两个维度,异常分类必须能分开它们。

**2026-08-10 P1 实施补记(实测倒逼的设计更正):「摘掉」必须只有一个地方能决定发什么。**
P1 首次实测(真实 api.deepseek.com,路由设 `top_p=5.0`,provider 400
`Invalid top_p value, the valid range of top_p is (0, 1.0]`)拿到的结果是:
重发确实发生了,但**第二次仍然带着 `top_p`,被同一条错误再拒一次**。
根因是同一次请求有两个设置合成者——网关走查这一层合成一份,
`route_chat_model_factory._runtime_kwargs` 又通过 `_caller_or_effective` /
`_effective_value` 从 `route.effective_runtime_settings` 再读一份补空缺,
于是「调用方故意不传」和「调用方没提到」在工厂眼里长得一模一样,摘掉的项被原样补回。
这与 D4 同源(报告与事实必须同源),也是底座一的直接违反。
更正:**工厂只做映射,不做决定**——那两个函数已删除,工厂只认调用方交给它的值;
一次调用发什么,唯一由 `call_settings.compose_call_settings` 说了算。
更正后同一脚本同一设置的实测:`retried_without_rejected_settings` → `answered`,
拿到真实答案;对照组(`main`)同条件为 `failed_terminal` → `AllProvidersFailedError`。

### D3. 每项设置的结果是一个封闭枚举(五态)

| 结果 | 含义 | 是否 warning |
|---|---|---|
| `applied` | 送出去了,且回包能印证它生效 | 否 |
| `sent` | 送出去了,但这一项没有可观测的回执 | **否** |
| `unsupported` | 这条路由/协议的请求体里没有位置表达它,因此没送 | 是 |
| `rejected` | 送了,provider 明确拒收,已摘掉后重发 | 是 |
| `ignored` | 送了且被接受,但回包反证它没生效 | 是 |

**为什么必须把 `sent` 和 `applied` 分开:沉默不是证据。** 绝大多数参数
(temperature、seed、top_p)发出去后,回包里没有任何能反推它是否生效的东西。
把「无法印证」报成「已生效」是撒谎,报成「没生效」是冤枉——两种都会让这张表
失去可信度,而一张不可信的表比没有更糟。

今天唯一能判到 `ignored` 的是推理:要了推理、整个回答一个推理分片都没有,这是能被反证的。

### D4. 「实际发了什么」只能从真正出门的那个 payload 读

**不另立一张「这个协议支持哪些参数」的手工清单去比对。**
理由与 2026-08-09 prompt variables 的教训同源:报告与事实必须同源,
否则手工清单会在某次加参数时忘记同步,这张表开始撒谎,而它撒谎的样子和说真话一模一样。

实现约束:请求构造那一层把**成品 payload 的键**交出来,比对函数只看它。

### D5. 判定分两个时刻,各判各能判的

- **探针时刻(正式调用前)**:探针带上本次真实设置去发。定 `unsupported`(静态即知)
  与 `rejected`(provider 明确拒收)。被拒项摘掉后照常继续用这条路由。
  这是「以免卡在长任务里」的落点:错在开跑前一个 token 就暴露,而不是跑两分钟才炸。
- **答案收口时刻**:定 `ignored`。探针判不了它——1 token 的探针不足以观测「有没有推理」。

诚实的边界:探针能提前抓到「拒收」,抓不到「收了但没照做」。两个时刻都要,缺一个漏一类。

**2026-08-10 P2 实施补记(探针怎么才算"带着真实设置"):**

判据不是"代码里把设置传给了探针",而是**探针发出去的那一条请求与正式调用同源**。
今天的探针是在 `client_manager` 里手搓的第二份请求构造器(openai 一份、anthropic 一份,
写死 `max_tokens=1` 且不带用户任何设置),与工厂那条正式路径并列——
和刚修掉的"两个设置合成者"是同一类病:并列的构造器必然各说各话。

更正:**探针 = 正式请求构造器 + 1 token 预算**。
`CallSettings.as_cheap_question()` 产出同一份设置、把预算换成 1、并摘掉 tools
(工具不是设置,带上它问的就是另一个问题,而这个问题的答案不该由工具背锅);
构造仍走 `RouteChatModelFactory`,且**构造器由调用方注入**,保证探针与它前置的那次调用
出自同一个 builder。副产物:探针从"只覆盖 openai/anthropic 两种协议"变成工厂支持的全部协议;
`client_manager` 里那两份手搓请求已删除,它只留健康状态(标记 down / 冷却)这一件事。

**探针的超时不能跟着正式调用走。** `RuntimePolicy.probe_timeout_seconds`(默认 5s)存在的
唯一理由就是"别在这儿卡住";工厂因此新增 `timeout_seconds` 覆盖参数,只有问便宜问题的调用方会传。

**追问只在该追问的时候发生。** 第一问被拒后,先看异常分类的 `scope`:
不是 `request`(凭据、模型不存在、限流、连不上)就直接收工——路由根本没读到设置,再问一遍是白花钱;
是 `request` 才摘掉偏好层再问一次,能答就逐项问(一次只带一项)把被拒项点名。
常规情况(全都接受)永远只有一问。

### D6. 独立事件,不挂在路由决策上

新增一个每次 LLM 调用一条的**步骤帧**事件(落盘、占 seq、可回放),
载荷是逐项的 `{设置项, 用户要的值, 结果, 原因}`。

不并进 `LLMRouteDecisionEvent`:那条讲「走了哪条路由、为什么换」,
这条讲「这次调用按什么参数跑的」——两件事,两个被改动的理由。

发送时机在答案收口时(因为 `ignored` 要等回包),两个时刻的判定累积成一条完整事件。

### D7. 三处呈现,各管一段

- **trace 步骤条目**:逐项显示「你要的 → 实际的」,任一项为 warning 级时条目整体呈 warning
  (复用现成的 `eventSeverity(event)`)。
- **`report.md` 新增 `## Routes` 段**:本次运行用到的每条路由,各自「设置 → 结果」汇总,
  warning 集中列在那里。与已有的 `## Nodes` / `## Tools` 并列。
- **不做运行结束弹窗/汇总提示**:否则每跑一次都抬一堆「这条协议不支持 seed」的噪音,
  真正值得看的会被淹掉。

### D8. 只报用户显式设置过的项

角色/路由/节点上真的写了值的才进这张表;没设置的走 provider 默认、不进表。
否则每次调用十几行全是 `sent`,真正的 warning 被淹掉。

### D9. 顺手拆模块:一个文件只围绕一件事

`call/chat_model.py` 现有 1196 行,`_answer` 一个方法 255 行,同时承担四件事:
候选路由走查策略、预算与升配、effective settings 合成、结果组装。新功能若继续往里堆,
只会让它更没法读。**改到哪拆到哪**(不做与本决议无关的大爆炸重构):

- **设置合成独立成模块**:现有的 `_effective_*` / `_runtime_*` / kwarg 强制转型
  共约 20 个函数搬进独立模块,新功能读的正是它——新代码因此有天然的家。
- **设置结果判定独立成模块**:五态判定 + 与 payload 的比对,与「怎么调用 provider」无关,
  应能脱离网络单测。
- **结果组装独立成模块**:`_as_answer` / `_usage_from_*` / `_build_chat_result*`。
- 候选走查策略留在 chat model,但它只剩「走查」这一件事。

判据不是行数,而是:**改动 A 的内部实现,B 不需要跟着改**;设置合成与结果判定
可以被测试直接调用,不需要起 provider。

## 3. 验收判据

因果验证:每条都要有动作**之后**的可观察结果作证;测试通过或实施者自报不单独成立。

1. **参数被拒不再打死调用**:一次真实运行中,给某项设置一个 provider 不接受的值,
   调用**照常完成**,且该项在事件中为 `rejected` —— 以该次运行的 `trace.jsonl` 实际内容为证。
   对照组是 B2 的实测记录(今天同样条件直接 `AllProvidersFailedError`)。
2. **探针带着真实设置出门**:实测**探针请求的成品 payload** 中含有本次调用的设置项 ——
   以抓到的请求体为证,**不接受**「代码里传了参数」这类上游断言(B1 的教训:
   上游看似传了、实际没到)。
3. **`ignored` 可被判出**:要求推理而 provider 未返回任何推理分片时,该项判为 `ignored` ——
   真实运行的 trace 为证。
4. **不报未设置项**:用户没显式设置过的项不出现在事件里 —— 真实运行的 trace 为证。
5. **报告汇总**:`report.md` 出现 `## Routes` 段,列出本次运行用到的每条路由及其设置结果,
   且其中的数字与同一次运行 trace 中的事件一致(两处不得各说各话)。
6. **前端呈现**:trace 条目逐项显示「你要的 → 实际的」,任一项为 warning 级时条目呈 warning 色 ——
   真机截图为证。
7. **模块化落地**:设置合成与设置结果判定各自可被单元测试**直接调用**(不起 provider、
   不发网络);`call/chat_model.py` 的候选走查方法不再同时承担设置合成与结果组装。
8. **既有行为不倒退**:`uv run pytest packages/graph-agent-gateway/tests` ·
   `packages/graph-agent/tests` · `apps/studio/backend/tests` 全绿,
   `mypy --strict` 两个 SDK 全绿,前端四件门禁全绿。

## 4. 明确不做

- **不做「配置必须生效」的强校验**:落不上就 warning,绝不失败(D1)。
- **不预造扩展点**:只覆盖网关今天真会映射的设置项;将来加参数时再加,不留空 hook。
- **不为已落盘的旧 run 补写这段事件**:依 `AGENTS.md` 不向后兼容原则,旧 run 数据可丢弃。
- **不做大爆炸重构**:D9 的拆分只覆盖本决议改到的代码路径。

## 5. 落地顺序(顺序有讲究)

| 步 | 内容 | 为什么排这个位置 |
|---|---|---|
| 1 | 参数被拒 ≠ 路由不可用(D2) | 它是当前唯一会真正打死调用的硬关;不先拆掉,后面几步都建在「参数一错就全盘皆输」的地基上 |
| 2 | 探针带上真实设置,定 `unsupported` / `rejected`(D5 前半) | 依赖第 1 步:探针带了设置才可能被拒,被拒必须先能被正确处理 |
| 3 | 收口时定 `ignored`,发设置事件(D3/D6) | 依赖前两步产出的判定结果 |
| 4 | `report.md` 的 `## Routes` 汇总(D7) | 依赖第 3 步的事件 |
| 5 | 前端 trace 逐项呈现(D7) | 依赖第 3 步的事件 |

D9 的模块拆分**不单独成步**,在 1-3 步改到对应代码时同轮完成。
