# 偏好贴合路由,不是被路由拒绝(2026-08-10 决议)

> 状态:已批准(PM,2026-08-10),尚未实施。
> 前置决议:[运行时配置是偏好,不是命令](2026-08-10-runtime-settings-are-preferences-decision.md)
> (下称「前决议」)。本决议不改写它的任何一条,只补它没覆盖的一段:**在"被拒"发生之前,
> 先让偏好落进这条路由接得住的范围**。
> 范围:`packages/graph-agent-gateway`(主体)、`apps/studio/backend`(角色写入边界 + 探测编排)、
> `apps/studio/frontend`(effort 控件)。

## 0. 一句话

用户写下的每一项偏好,出门前先按**这条路由的已知边界**贴合:
数值越界取最近的边界,枚举不认取最近的档位,贴合过的项记为 `adjusted` 并照实报出来。
**"值超范围"不再是一次失败,也不再需要走"被拒→摘掉→重发"那条昂贵的路。**

前决议解决的是「provider 拒收时不要判路由死刑」;本决议解决的是「一开始就别递一个它接不住的值」。
两者的顺序是:**先贴合,贴合不了才谈拒收**。

## 1. 证据

### B1. 「模型上限」这个概念在代码里只到协议粒度,不到模型粒度

`temperature.py:7-13` 是全仓唯一一张温度上限表:

```python
_PROVIDER_TEMPERATURE_MAX_BY_PROTOCOL = {
    "anthropic_compatible": 1.0,
    "openai_compatible": 2.0,
    "ark_runtime": 2.0,
    "google_genai": 2.0,
    "wavespeed_any_llm": 2.0,
}
```

`provider_temperature_from_authored`(同文件 16-28 行)拿它做**等比缩放**,不做钳制:
authored 3.0 在 openai 协议上变成 3.0(超 2.0),在 anthropic 协议上变成 1.5(超 1.0)。
authored 值本该是 0..2 的"百分比",越出这个区间时缩放的语义就崩了——
**缩放假设了输入在量程内,而没有人保证这件事**。

### B2. 「按上限取」对 max_output_tokens 也没实现

`call/settings.py:259-265` 已经能读出模型的输出上限:

```python
def budget_cap(route: ResolvedRoute) -> int | None:
    """The most output tokens this route's model can be asked for, if it says."""
    capability = route.capabilities.get("max_output_tokens")
```

但它只被用在**一个**地方——`call/chat_model.py:146-148` 的预算翻倍:

```python
def _next_budget(self) -> int:
    doubled = self.budget * 2
    return min(doubled, self.cap) if self.cap is not None else doubled
```

也就是说:上限只约束"升级后的预算",不约束"起始预算"。
`initial_budget`(`call/settings.py:245-256`)一路读到用户写的值就直接返回,不看 cap。
用户在角色里填一个超过模型上限的输出长度,今天原样出门吃 400。

### B3. 能力槽位齐全,但没有人往里填

`capabilities.py:20-32` 的 `RUNTIME_SETTING_DESCRIPTORS` 已经声明了
`temperature` / `top_p` / `reasoning.effort` 三项的描述符,
`_runtime_setting_capability`(同文件 339-348 行)也已经会读 `min` / `max` / `default` / `values`。
缺的是**数据来源**:`raw_capabilities` 来自各家的 model-list 接口,那个接口不报温度区间、
不报 effort 枚举。实测本机 `llm_credentials.json`,所有路由的这三项描述符全是
`min: null, max: null, allowed_values: [], source: "unknown"`。

### B4. effort 各家枚举确实不同,而给 Anthropic 根本发不出去

查证结果(2026-08-10,来源见文末):

| 家 | 请求字段 | 取值 | 默认 |
|---|---|---|---|
| Anthropic | `output_config.effort` | `low` `medium` `high` `xhigh` `max`,**各型号支持子集不同** | `high` |
| OpenAI | `reasoning_effort` | 按型号:gpt-5 `minimal/low/medium/high`;5.2 加 `xhigh`;5.6 `none/low/medium/high/xhigh/max` | `medium` |
| DeepSeek | OpenAI 方言 `thinking.type`;Anthropic 方言 `reasoning.effort`;Responses 方言 `output_config.effort` | v4-pro **实测收全七档**(见下方 2026-08-10 实测),文档另称 `low/high/max` 且 `medium`→`high`、`xhigh`→`max` 服务端折叠 | `high` |
| Gemini | 3 代 `thinking_level`(`MINIMAL/LOW/MEDIUM/HIGH`);2.5 代 `thinking_budget`(整数) | — | HIGH |

对照 `call/factory.py` 的 `_PROVIDER_KEYS`:
`anthropic_compatible` 的映射表里**没有 effort 这一项**——给 Claude 路由设 effort,
今天在请求构造那一步就被丢掉,一个字节都不会出门。而给 DeepSeek 发的是
`reasoning_effort`(按 openai_compatible 处理),与 DeepSeek OpenAI 方言文档所写的
`thinking.type` 不是同一个字段;探针实测它**收下没报错**,但"收下"不等于"照做"
(前决议 D3 的 `sent` 与 `ignored` 之分)。

**2026-08-10 实测修正了本表一行(B2 落地后的第一次真机测量)**:对
`deepseek-official:deepseek-v4-pro` 逐档探测,七档全部返回 ok。为排除"参数根本没上路"
这一同样能解释 7/7 的读法,在同一条路径上抓了请求体并故意问了一个不存在的档位:

```
asked effort='high'   -> ok
  request body: {"model": "deepseek-v4-pro", "max_tokens": 1, "reasoning_effort": "high"}
asked effort='banana' -> invalid_model
  HTTP 400 (invalid_request_error): Failed to deserialize the JSON body into the target
  type: reasoning_effort: unknown variant `banana`, expected one of `none`, `minimal`,
  `low`, `medium`, `high`, `xhigh`, `max`
```

两件事同时被坐实:参数确实出门了(请求体里就是 `reasoning_effort`),provider 确实在
校验它(不认的名字 400 并把完整枚举写在错误里),而它认的这七个名字与探测收下的七档
完全一致。**所以这一行文档过时,以实测为准**——这正是 D-A 说"随模型变的枚举要探"的原因:
文档写的是某一时刻某一方言的子集,API 自己才知道现在收哪些。

需要分清的一点:能力记录的是"**这个名字它收不收**",不是"每一档行为是否真的不同"。
服务端仍可能把几档折叠成同一种行为;贴合需要的恰恰是前者(别递一个会被 400 的名字),
而后者属于 `sent` 与 `ignored` 之分(前决议 D3),不由这次测量回答。

### B5. UI 上没有 effort 入口,现有的值是探针副产品

LLM 角色面板没有任何 effort 控件。今天 DeepSeek 路由上那个
`reasoning.effort = "low"` 来自 `registry/resolver.py:465-488`
`_apply_profile_runtime_overrides` 读取路由的 verified profile;
该 profile 的 `runtime_overrides` 由我们自己的能力探测写入
(`metadata.source = "official_test"`,`max_output_tokens: 16` 是探测用的极小预算)。
**探测参数被提升成了运行默认值**,用户既看不见也改不了。

## 2. 决策

### D-A. 边界是路由的事实,来源按"变不变"分两类

- **文档常量**(随协议/API 版本固定:温度量程、top_p 上限):写进代码里的
  provider-doc 表,`source = "provider_doc"`。仓里已有此范式
  (`capabilities.py:169-198` 的 `reasoning_budget_tokens {min:1024, default:4096}`)。
  这类值探一万次也是同一个数,探它是白花钱。
- **随模型变且文档给不出统一答案的枚举**(effort):**探**。凭据验证/路由测试时
  逐个候选档位各发一次 1-token 请求,收下的进 `values`,写进
  `capabilities["reasoning_effort"] = {"supported": true, "values": [...]}`。

判据不是"能不能探",而是"**探能不能给出文档给不出的信息**"。

**实现时补的三条(2026-08-10,随 B2 落地)**:

1. **问谁**:候选档位 = 该协议的文档词表,协议没有词表(openai_compatible)才问整条
   ladder。拼不出来的名字不值得花一次往返去被告知拼不出来。
2. **问哪些路由**:只问自称会思考的路由(`thinking_protocol` 等能力为真)。不推理的
   模型对每一档都会拒,且每次拒绝都要付钱——effort 是"想多用力",没有思考就没有力可用。
3. **什么算"不卖"**:只有请求本身被拒才算不卖。限流、配额、网络错误、超时、密钥无效
   这类失败与所问档位无关,**整轮测量作废**(不写能力),否则一次限流就会把这条路由
   真正卖的档位删掉——把"没测出来"写成"它不支持"是最贵的一种错。

### D-B. 贴合发生在请求构造之前,结果是第六态 `adjusted`

前决议 D3 的五态表补一行:

| 结果 | 含义 | 是否 warning |
|---|---|---|
| `adjusted` | 用户给的值超出这条路由的已知边界,已贴合到边界后送出 | 是 |

它既不是 `applied`(用户要的那个值并没有生效),也不是 `rejected`(压根没被拒),
更不是 `unsupported`(这条路支持这一项,只是不接受那个值)。**少一态就必然有一类事实被报错。**

贴合规则:

- 数值超上/下界 → 取最近的边界。
- 枚举不在 `values` 里 → 取最近的档位(按档位强弱有序,向下取最接近的受支持档;
  没有更低档时取最低档)。DeepSeek 服务端自己就是这么折叠的。
- **边界未知时原样送**,由前决议那套拒收兜底。不知道边界就编一个,比不贴合更糟。

### D-C. 起始预算与升级预算共用同一个上限

`initial_budget` 必须与 `_next_budget` 一样受 `budget_cap` 约束。
一个上限有两条执行路径而只有一条真的执行,这本身就是缺陷
(呼应「同一业务规则只允许一个权威定义」)。

### D-D. authored 温度是"量程内的百分比",越界在写入时就被归一

温度有两层边界,**各有唯一 owner**:

- **authored 量程 0..2**:这是 Studio 自己的刻度(前端滑块 0-100% × 2),
  与任何 provider 无关。它的 owner 是 **Studio 写入边界**——
  `PUT /api/llm/roles/{role}` 收到越界值时**归一到量程内后存盘**,不是 422 拒绝、
  也不是原样存下。理由:量程是我们自己的定义,存进一个自己定义之外的值没有任何意义;
  而按前决议"配置不该让调用失败"的精神,拒绝写入也不是正确反应。
- **provider 量程**:由网关在出门前按 D-B 贴合。

两层修完之后,`temperature = 3.0` 这种值在任何一层都无法留存。

### D-E. effort 成为一等设置,请求形状按协议各表述各的

`_PROVIDER_KEYS` 每个协议加一行,把 `reasoning_effort` 映射到该协议的字段名。
**不需要嵌套路径机制**——2026-08-10 实测,嵌套是 adapter 的职责,不是我们的:

```
ChatAnthropic(effort="medium")._get_request_payload(...)
→ {'model': ..., 'max_tokens': 16, 'output_config': {'effort': 'medium'}}
```

`ChatAnthropic.effort` 的类型标注是 `Literal['max','xhigh','high','medium','low']`,
`ChatGoogleGenerativeAI.thinking_level` 是 `Literal['minimal','low','medium','high']`,
与 B4 查到的文档完全一致。所以映射只是 `reasoning_effort → effort` /
`reasoning_effort → thinking_level` 两行平铺键名。

**教训**:动手前先问"这一层是不是已经有人做了"。按 B4 的文档直接推导会得出
"要建嵌套路径机制"的结论,而事实是那一层已经存在——**文档说明协议长什么样,
不说明我们的依赖已经替我们做到哪一步**。

副产物:协议本身就限定了 effort 词表(能不能拼写出这个名字),
这是文档常量,按 D-A 进 provider-doc 表;探测结果(这个模型到底卖哪几档)优先级更高,
有实测就以实测为准。

### D-F. effort 进 UI,top_p 不进

- **effort 进**:控件是角色级的一个下拉(与 temperature、max output tokens 同排),
  选项 = 该角色所有路由报出的档位并集,按强弱排序——只有 `low/high/max` 的模型
  就只显示这三档,不显示一个选了也没用的 `medium`。角色只选一次,各路由在
  materialize 时各自贴合到自己卖的那一档(见 D-B),所以并集不会让某条路由收到
  它拼不出来的名字。
- **档位从哪条通道来(2026-08-10 落定,取代本节初稿的"由
  `RuntimeSettingDescriptor.allowed_values` 供给")**:走
  `ProviderModelOption.capabilities["reasoning_effort"].value.values`,
  即 registry 响应里 model group 的路由能力投影。理由:两条通道都是同一份
  registry 真相的按路由投影,而 capabilities 这条已经铺到角色卡片、
  旁边那个 max output tokens 控件正是从它读上限的;`route_runtime_settings`
  这条今天前端没有任何消费者,选它等于为一个控件把新 prop 穿过四层组件。
  同一批数据、更短的路径,取短的。
- **协议词表在读时补齐,不落盘**:路由能力里没有 `reasoning_effort` 时,
  studio 后端在投影 model group 的那一刻按端点协议补上文档词表
  (`_provider_route_ui_capabilities` → `documented_effort_levels`),
  `source = "provider_doc"`。写进路由并持久化会随词表更新而变陈旧,
  而"这个协议能拼出哪些名字"是读时随时可答的常量;实测结果(`probed_verified`)
  一旦存在就原样保留,不被文档值覆盖。
- **空态**:协议没有文档词表(如 openai_compatible,各型号档位不同)且探测未跑过时,
  控件禁用并说明"该角色下没有模型报出档位",不臆造一份枚举。这里**不给"去测"入口**:
  B2 落地后 effort 确实会被测(强制路由探测 `POST /routes/{id}/probe?force=true` 通过后
  逐档追问),但**今天前端触发这条 API 的地方只有 Available Models 里"重探一条 off 路由"
  这一个动作**——把空态文案指向一个健康路由点不到的按钮,还是一个空承诺。
  **未决**:健康路由要不要一个"测一测这个模型"的入口(以及它是复用现有 re-probe 动作
  还是新加一个),是产品决定,单独定;在它定下来之前空态只陈述事实,不给指路。
- **top_p 不进**:它与 temperature 同向作用(一个改概率分布陡峭度,一个改候选池大小),
  各家文档均建议二选一。既然温度已有控件,再给一个会互相抵消的旋钮是增加误配面积。
  schema 里保留字段(路由/协议层仍需表达它),但没有 UI 写入口。

### D-G. 模块化:边界与贴合是独立的一件事

新增 `registry/bounds.py`,只负责"这条路由对这一项的边界是什么"与"把一个值贴合进去",
纯计算、无 IO、可离线测。`compose_call_settings` 调它,不自己长出一套 min/max 判断。
provider-doc 常量表并入该模块,`temperature.py` 现有的协议表迁入后删除
(不留并列的第二张表)。

## 3. 验收判据

1. 角色里写 `temperature = 3.0`:存盘后读回是 `2.0`(D-D 归一);
   发给 anthropic 路由的请求体里 `temperature` 是 `1.0`,不是 `1.5`。
2. 角色里写 `max_output_tokens` 超过该路由 `capabilities.max_output_tokens`:
   出门的请求体里是 cap 值,且该项报 `adjusted`。
3. 给 DeepSeek v4-pro 路由设 `effort = "xhigh"`:出门是 `max`,该项报 `adjusted`,
   调用正常返回(不是 400)。
4. 给 Claude 路由设 effort:请求体里出现 `output_config.effort`(今天一个字节都没有)。
5. 边界未知的路由:行为与今天完全一致(原样送 + 前决议的拒收兜底),无新增失败。
6. LLM 角色面板出现 effort 控件:有实测档位的路由显示实测那几档,没实测但协议有文档
   词表的显示文档词表,两者都没有则控件禁用并说明原因;选中的档位存进角色 intent,
   materialize 后各路由的 `runtime_settings.reasoning.effort` 是各自贴合过的值;
   top_p 无控件。
7. 四道门禁全绿:ruff / mypy --strict ×2 / pytest ×3 / 前端 lint+typecheck+test+build。

## 4. 明确不做

- **不做"探温度上限"**:它是协议常量,探不出新信息(D-A)。
- **不把 authored 温度改成整数百分比存盘**:归一 + 贴合两层修完后,越界值已无法留存,
  改存储格式不再带来任何正确性收益,只带来一次无收益的数据迁移。
- **不缓存 effort 探测结果之外的运行期判定**:每次调用的贴合是纯计算,不需要缓存。
- **不为 Gemini 2.5 的 `thinking_budget` 与 3 代 `thinking_level` 做自动换算**:
  两者互斥且语义不同,按路由能力分别表达,不做跨代猜测。

## 5. 落地顺序

- **A1 边界与贴合(网关)**:`registry/bounds.py` + `compose_call_settings` 接入 +
  `initial_budget` 受 cap 约束 + 温度协议表迁入。对应验收 1(后半)、2、5。
- **A2 写入归一(Studio 后端)**:角色写入边界归一 authored 温度。对应验收 1(前半)。
- **B1 effort 请求形状(网关)**:`_PROVIDER_KEYS` 支持嵌套路径 + 四家形状落表。对应验收 4。
- **B2 effort 探测(网关 + 后端编排)**:候选档位探测写入 `capabilities`。对应验收 3。
- **B3 effort 控件(前端)**:描述符驱动的档位选择。对应验收 6。

前决议的 P3(逐项事件)/ P4(`report.md ## Routes`)/ P5(前端逐项呈现)在此之后,
`adjusted` 随 P3 的事件一起呈现;在 P3 落地之前,贴合结果先进
`actual_runtime_settings`(答案已有的回执通道),不另开第二条上报路径。

---

**来源**(2026-08-10 查证):

- Anthropic effort:<https://platform.claude.com/docs/en/build-with-claude/effort>
- OpenAI reasoning:<https://developers.openai.com/api/docs/guides/reasoning>
- DeepSeek thinking mode:<https://api-docs.deepseek.com/guides/thinking_mode/>
- Gemini thinking:<https://ai.google.dev/gemini-api/docs/thinking>
