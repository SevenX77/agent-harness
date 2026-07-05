# Requirements Document — Studio LLM 温度百分比化 + 跨 provider 兼容

## Introduction

Studio 里 LLM 温度(temperature)在两处以滑条编辑:**节点 Model 参数覆盖**
(`PropertiesPanel.tsx` 的 `LlmNodeParamsField`)与 **LLM Role 设置**
(`RoleSettingsDialog.tsx` 的 `RoleSettingsFields`)。当前两处滑条都取 `min=0 max=2`
的**裸温度值**,原样透传给 provider。这带来两个问题:

1. **跨 provider 不兼容**。不同 provider 的温度量程不同:OpenAI / Google 是 `0~2`,
   Anthropic(Claude)是 `0~1`。一个 role 会 fan-out 到多条候选、可能命中不同
   provider(fallback 的意义),但温度是**单个裸值原样发给每条候选**。因此把滑条拖到
   `1.5` 后,一旦某条候选命中 Claude,`1.5` 会原样发出 → 超出 Claude 上限、报错。
   这是**当前真实缺陷**(见 design.md §1 证据)。

2. **滑条拖动卡顿**。两处滑条的 `onValueChange` 每一跳都立即落库(role 走
   `onSubmit`,node 走 `persist`),拖动过程中高频触发网络写,体感卡。

3. **缺可解释性**。用户看到一个 `0~2` 的裸数字(或将来的百分比),不理解它在两家
   provider 上分别意味着什么。

本 spec 把温度编辑统一成**百分比语义**(相对该模型量程的位置),在网关侧按候选
provider 的量程把百分比换算成合法真实温度,给滑条加 **"?" 说明**,并给两处滑条的
**落库**套 debounce(拖动只更本地 state,网络写延迟合并)。

**权威来源约束(evidence-first 铁律)。** 温度真实发送逻辑在 gateway
(`packages/graph-agent-gateway`),不在前端;前端只做"百分比 ↔ 内部值"的展示换算,
绝不自己决定发给 provider 的真实温度。跨 provider 的量程映射属于 gateway 的
role 物化 / 运行时路径职责,按 AGENTS.md「Development Principles 第 3 条」应改在
gateway,并对齐 gateway MVP1 设计源(`docs/graph-agent-gateway/mvp1/`)后写回该设计源。

**开放决策(见 design.md §5)。** "百分比 → 真实温度"有两种对两家都成立的做法:
**(A) 线性 remap**(0%→0,100%→该 provider 上限;百分比在两家线性忠实)与
**(B) clamp**(存 0~2、仅对 Claude 把 >1 夹到 1;≤1 值零变化)。二者行为可见地不同
(见 design.md §5 对比),且决定 gateway 改动的侵入面。requirements 在意图层陈述,
design.md 用证据 + 产品取舍把 A/B 定死后再进实现。**当前默认推荐 A。**

## Requirements

### Requirement 1:温度以百分比语义编辑(前端展示)

**Objective:** 作为 skill 作者,我要温度滑条以百分比呈现(相对该模型量程的位置),
这样一个滑条对 OpenAI 与 Claude 都讲得通,不用记两套量程。

#### Acceptance Criteria
1. When 用户打开节点 Model 参数或 LLM Role 设置的温度栏, the Studio 前端 shall
   以**百分比**(0%~100%)展示当前温度读数,而非裸的 `0~2` 数值。
2. When 用户拖动温度滑条, the Studio 前端 shall 实时更新百分比读数,拖动过程**不卡顿**
   (本地 state 即时响应,落库另行 debounce,见 Requirement 4)。
3. Where 温度处于"未设置"(继承默认)状态, the Studio 前端 shall 显示占位符(如 `—`)
   而非某个具体百分比,表达"未覆盖、用默认"。
4. The 前端 shall 复用现有 `@/components/ui/slider`(shadcn/Radix 默认封装),
   不新造滑条组件;读数字体/颜色沿用 PR #365 定的正常字体、正常前景色。

### Requirement 2:跨 provider 兼容——百分比按候选量程换算为合法真实温度

**Objective:** 作为 skill 作者,我要同一个温度设置在任何命中的 provider 上都发出**合法**
的真实温度,这样 role 兜底到 Claude 时不会因为温度超 1 而报错。

#### Acceptance Criteria
1. When 一条候选路由命中 OpenAI / Google / OpenAI 兼容协议, the gateway shall
   使该候选发出的真实温度落在 `0~2`。
2. When 一条候选路由命中 Anthropic(Claude), the gateway shall 使该候选发出的
   真实温度落在 `0~1`,**绝不发出 >1 的温度**。
3. While 一个 role fan-out 到多条不同 provider 的候选, the gateway shall
   **按每条候选各自的 provider 量程**换算,同一个百分比设置在不同候选上换算成各自
   合法的真实温度(换算按候选 protocol,不按 role 层一次性算定)。
4. Where 温度为"未设置"(None), the gateway shall 不因本特性改变"未设置"的既有行为
   语义 —— 具体"未设置"映射为 provider 原生默认(方案 A)还是保持既有 `0.7`(方案 B),
   由 design.md §5 的 A/B 决策锁定,并在实现中一致落地。
5. The 换算 shall 只发生在授权值进入运行时的边界点(role 物化生效值 + node 覆盖入口),
   下游 provider 请求构造处拿到的即为真实温度,不重复换算、不遗漏路径(两条运行时路径
   见 design.md §1)。

### Requirement 3:温度栏"?"说明

**Objective:** 作为 skill 作者,我要温度栏旁有个"?"能看懂百分比在两家的含义,
这样我知道拖到某个百分比对 OpenAI / Claude 各意味着什么。

#### Acceptance Criteria
1. When 用户 hover 温度栏的"?"图标, the Studio 前端 shall 弹出说明,讲清"百分比 =
   相对该模型温度量程的位置",并给出两家的具体换算示例(文案随 A/B 决策定稿)。
2. The "?" shall 复用现有 `HelpTooltip` 封装(与同面板 thinking 等栏一致),
   不新造 tooltip。
3. The "?" shall 同时出现在节点 Model 参数与 LLM Role 设置两处温度栏。

### Requirement 4:两处滑条落库 debounce

**Objective:** 作为 skill 作者,我拖动温度(及其它滑条参数)时要顺滑不卡,
这样连续拖动不会每一跳都打一次网络写。

#### Acceptance Criteria
1. When 用户连续拖动温度滑条, the Studio 前端 shall 即时更新本地 UI state,
   并将**落库/提交**(node 的 `persist` / role 的 `onSubmit`)以 debounce 合并,
   连续拖动期间不逐跳落库。
2. When 用户停止拖动超过 debounce 窗口(或松手 commit), the Studio 前端 shall
   落库最终值,保证最终一致(不丢最后一次值)。
3. Where 组件在 debounce 窗口未触发前卸载或 draft 被外部重置, the Studio 前端 shall
   不落一个过期值、不覆盖更新后的 draft(取消在途的 debounce)。
4. The debounce shall 覆盖两处滑条(node Model 参数 + LLM Role 设置),行为一致。

### Requirement 5:TDD、门禁与设计源同步

**Objective:** 作为维护者,我要这次改动 test-first、门禁全绿、并把新语义写回设计源,
这样 `main` 不变红、设计与代码不漂移。

#### Acceptance Criteria
1. The gateway 换算逻辑 shall test-first:先加**失败测试**——同一百分比/授权值在
   Anthropic 候选上换算出的真实温度 ≤1、在 OpenAI 候选上落在 0~2、未设置行为符合
   A/B 决策 —— 再写生产代码。
2. The 前端 debounce 与百分比换算 shall 有对应单测(vitest):拖动只更本地不逐跳落库、
   停止后落最终值、百分比 ↔ 内部值换算正确。
3. The 改动 shall 保持全部门禁绿:gateway `uv run ruff check` /
   `uv run mypy --strict packages/graph-agent-gateway/src` /
   `uv run pytest packages/graph-agent-gateway/tests`;studio backend
   `uv run pytest apps/studio/backend/tests`;前端
   `npm run lint && npm run typecheck && npm test && npm run build`。
4. The 新的温度百分比 + 跨 provider 换算语义 shall 写回 gateway MVP1 设计源
   (`docs/graph-agent-gateway/mvp1/`),使设计成为真相(不是只改代码)。
5. The 改动 shall 遵循「无向后兼容」:温度字段语义直接切换到新定义,不写迁移垫片/
   双读;既有 skill 里的裸温度值按新语义重解释(数据可弃)。
