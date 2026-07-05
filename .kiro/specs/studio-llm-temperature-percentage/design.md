# Design Document — Studio LLM 温度百分比化 + 跨 provider 兼容

> **STATUS: IMPLEMENTATION IN PROGRESS ? 2026-07-05 ?? A(linear remap)?**
> PM ?? "go/??" ?????? A: ?????? 0..2 ??? 0..100%, gateway ????? route ?????? provider protocol ??????, ????????? temperature?

## 0. 2026-07-05 ????

- ?? A(linear remap), ??? Anthropic-only clamp?
- Studio UI ????????: slider ??/???? provider-neutral ??? 0..2?
- gateway ??????? `provider_temperature_from_authored`: Anthropic-compatible 0..2 -> 0..1; OpenAI-compatible / Gemini / Ark / WaveSpeed / generic ?? 0..2?
- ?? ordinary-chat ???????? 0.7; `None` ?????, provider ????????

## 1. 现状证据 —— 温度是"裸值原样透传",且有两条运行时路径

### 1.1 存储:裸浮点、无上限

- role 侧生成设置 schema:
  `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:129`
  > `temperature: float | None = None`
- node 侧覆盖模型:
  `apps/studio/backend/app/models/node_llm_params.py:27`
  > `temperature: float | None = Field(default=None, ge=0)`  ← 仅挡负数,**无上限**
- 前端两处滑条现取 `min=0 max=2 step=0.1`:
  `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx`(`LlmNodeParamsField`)
  与 `.../settings/llm-roles/RoleSettingsDialog.tsx:164-182`(`RoleSettingsFields`)。

### 1.2 有两条到达 provider 的运行时路径(关键)

**路径 X — LangChain 工厂**
`route_chat_model_factory.py`:温度在 `_runtime_kwargs`(:97-106)按
`caller_or_effective` 合成 `common["temperature"]`,下游三个 provider 分支
(`_openai_runtime_kwargs` :126 / `_anthropic_runtime_kwargs` :143 /
`_google_runtime_kwargs` :156)各自 `if common.get("temperature") is not None`
时原样塞进 kwargs。**未设置 → None → 省略(此路径无 0.7 伪造)。**

**路径 Y — 裸 SDK ordinary_chat**
`ordinary_chat.py`:`_openai_chat`/`_anthropic_chat`/`_google_chat`/`_ark_chat`
各以 `temperature: float` 必填参数,直接塞进 provider kwargs
(如 :240 `"temperature": temperature`、:299、:345、:408、:492、:591)。
由 `gateway_chat_model.py` 喂:未设置时 `_effective_float(first_route, "temperature", 0.7)`
(:142-146)**伪造 0.7 真实温度**发出。

> ⇒ 任何"按 provider 换算"的方案,**两条路径都要覆盖**,且路径 Y 存在
> `temperature=0.7` 伪造默认(见 §3)。

### 1.3 换算必须"每候选、按 protocol"做

一个 role fan-out 到多条候选、可能不同 provider(fallback)。温度是**单个授权值**。
`gateway_chat_model._generate`(:112 起)按候选循环重试。因此"授权值 → 真实温度"
**只能在每条候选的最后一公里、按该候选 protocol 换算**,不能在 role 层一次算定
(否则 fallback 到异构 provider 的候选就换错了)。

### 1.4 物化报告 ≠ 运行时生效值(别改错地方)

- `role_materialization.py:315-317` 写的是 `entry_report["resolved_settings"]`,
  这是给 UI 的**报告/投影**(注释 :291「temperature is written through」)。
- 运行时工厂/ordinary 读的是 `route.effective_runtime_settings`
  (`route_chat_model_factory.py:122`、`gateway_chat_model.py:696+`),
  由**另一处** `registry/resolver.py:_effective_runtime_settings`(:348,经 :181 挂上)生成。
- ⇒ 只改 `role_materialization` 会"报告改了、真发出去的没改"。**运行时映射点不在这里。**

## 2. Provider 温度量程(换算所需的唯一新数据)

registry 里**没有**存过任何 per-model / per-protocol 温度上限
(核查 `registry/capabilities.py` `RUNTIME_SETTING_DESCRIPTORS`:20-22 只把 temperature
声明为 "number";`registry/lint.py:97-104` 只做数值 lint,无上限)。因此需**新增**一张
「protocol → 温度上限」小表(gateway 内常量):

| protocol | 上限 | 说明 |
|---|---|---|
| `openai_compatible` / `ark_runtime` | 2.0 | OpenAI 系 |
| `google_genai` | 2.0 | Gemini |
| `anthropic_compatible` | 1.0 | Claude |
| generic / 未知 | 2.0(保守假设 OpenAI 兼容) | 见 §6 风险 |

## 3. `temperature=0.7` 伪造默认这个刺

路径 Y 在未设置时伪造 0.7 真实温度(§1.2)。任何按 provider 换算的方案都要回答:
**这个 0.7 算不算要被换算的授权值?**
- 若算 → Claude 未设置从 0.7 变 0.35(方案 A 若不处理),这是**跨所有未设置调用的静默行为变化**。
- 干净解 → 未设置就**不发温度**(None),让 provider 用原生默认(OpenAI/Claude 均 1.0)。
  这是方案 A 采纳的做法(§5),也更符合第一性原理(凭什么替用户编 0.7)。
- 方案 B 因为不动 ≤1 的值、`0.7 ≤ 1`,**天然不碰这个刺**。

## 4. 前端设计(A/B 无关的公共部分)

- **百分比 ↔ 内部值换算**:内部授权值仍走 `0~2` 刻度(见 §5 各方案对存储的处理),
  读数 = `Math.round(内部值 / 2 * 100)%`;滑条 `min=0 max=2 step=0.1` 不变,只改**读数渲染**。
  未设置 → `—`。
- **"?" 说明**:复用 `HelpTooltip`(与 thinking 栏一致),文案随 A/B 定稿(§5 各给了文案)。
- **debounce 落库**:抽一个 `useDebouncedCallback`(或复用现有 hook,先查
  `apps/studio/frontend/src/hooks/` 有没有)。**只 debounce 落库副作用**
  (node `persist` / role `onSubmit`),`setDraft` 本地 state 保持即时;卸载/外部
  reset 时取消在途 debounce(Requirement 4.3)。两处滑条统一接。

## 5. Decision: A linear remap

两种都能让"一个值对两家都合法",但产品语义与侵入面不同。**需要请求方拍板。**

### 方案 A —— 线性 remap(**推荐**)
- **定义**:百分比 `p∈[0,1]`(前端 = 内部值/2)。真实温度 = `p × 该候选 provider 上限`。
  即 OpenAI/Google:`真实=内部值`(×1,和今天一样);Anthropic:`真实=内部值/2`。
  0%→0,100%→该 provider 上限。
- **未设置**:不发温度,用 provider 原生默认(§3 干净解);删掉路径 Y 的 0.7 伪造。
- **优点**:百分比在两家**线性忠实**(75% → OpenAI 1.5 / Claude 0.75);名副其实"百分比"。
- **代价**:① 动了 0.7 伪造默认 = 跨所有未设置调用的默认行为变化(但更干净可解释);
  ② 既有 Claude 用户授权 0.9 从"发 0.9"变"发 0.45"(数据可弃、且用户正重做该 widget)。
- **落点**:换算函数 `_authored_to_provider_temperature(authored, protocol)` 放 gateway;
  在**每候选最后一公里**应用——路径 X 的三个 `_*_runtime_kwargs` / 路径 Y 的
  `_*_chat` 里,按该候选 protocol 换算(仅非 None 值)。删除 `gateway_chat_model` 的
  0.7 伪造,改为 None 时省略温度。
- **"?" 文案**:「温度按百分比设定,表示相对该模型量程的位置。100% 对应该模型的最高温度
  (OpenAI/Google=2.0,Claude=1.0),50% 即 OpenAI 1.0 / Claude 0.5。留空则用模型默认。」

### 方案 B —— clamp(更轻、更保守)
- **定义**:内部/存储仍是 `0~2` 裸值,只在每候选最后一公里对 **Anthropic** 候选
  `min(temperature, 1.0)`;其余 provider 不动。
- **未设置**:完全不碰(0.7 伪造保留),`0.7 ≤ 1` 不受影响。
- **优点**:`≤1` 的值**零行为变化**、不碰 0.7 默认、gateway 改动最小(仅 anthropic 分支
  各加一个 `min`),风险最低;严格是"修掉今天 >1 发给 Claude 报错"的 bug。
- **代价**:Claude 上滑条**上半段(>50%)全压在 1.0**(75% 与 100% 都发 1.0),
  百分比对 Claude **不再线性忠实**——本质是 clamp、不是"百分比"。
- **落点**:路径 X `_anthropic_runtime_kwargs`(:143)+ 路径 Y `_anthropic_chat`
  (:452 起)各加 clamp;`gateway_chat_model` 的 adaptive-thinking 强制
  `temperature=1.0`(ordinary_chat.py:521)本就 ≤1,保持不动。
- **"?" 文案**:「温度 0~2;OpenAI/Google 用全量程,Claude 上限 1.0(超过按 1.0 处理)。留空用模型默认。」

### 决策对照
| 维度 | A 线性 remap | B clamp |
|---|---|---|
| 百分比对 Claude 忠实? | ✅ 线性 | ❌ 上半段死在 1.0 |
| 碰 `0.7` 伪造默认? | ✅ 要动(改 None→省略) | ❌ 不碰 |
| 既有 Claude 值行为变? | 变(0.9→0.45) | ≤1 不变 |
| gateway 侵入面 | 中(两路径换算 + 删 0.7) | 小(仅 anthropic 加 min) |
| 名副其实"百分比"? | ✅ | ⚠️ 更像 clamp |

**推荐 A**:请求方明确要"百分比的方式",只有 A 让百分比在两家都成立;0.7 本是随手常量,
改成"未设置用 provider 原生默认"是更对的设计。**待请求方确认 A 或 B 后进 tasks.md。**

## 6. 风险 / 待明确

1. **generic / 未知 protocol 的上限**:§2 表暂按 2.0(OpenAI 兼容假设)。实现前用代码
   枚举 `GenericRouteChatModel` 实际承载的 protocol,确认没有 0~1 量程的漏网 provider;
   有则补表。
2. **路径 Y 是否 Studio 实跑路径**:确认 Studio skill run 走工厂(X)还是 ordinary(Y)
   还是都走;两条都要覆盖,但要保证测试覆盖到实际热路径。
3. **engine 不动**:`interception.py` 的 `temperature=0.7`(:37/:166/:262)是
   `_predict_internal` 的 mock/predict 字段,不发真 provider,本特性不改 engine。
   实现时加一条断言/核查确保没有 engine 侧绕过两条网关路径直接发温度的通道。
4. **前端 debounce hook 复用**:先查 `src/hooks/` 是否已有 debounce 封装,避免重复造。

## 8. 2026-07-05 ????

- Frontend: `apps/studio/frontend/src/components/studio/llm-temperature.ts` ??????????????? debounce ??; Role settings ? node Model params ?? slider ??????
- Gateway: `packages/graph-agent-gateway/src/graph_agent_gateway/temperature.py` ??? provider ??????????; factory ? ordinary-chat ???????? provider ??????
- Tests: gateway factory / ordinary-chat / resolver ????? provider ????????; frontend tests ???????? debounce hook?
