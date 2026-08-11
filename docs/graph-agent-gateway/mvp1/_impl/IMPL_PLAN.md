---
doc: impl-plan
status: drafted（2026-06-06;待 CCB 恢复后开跑）
applies_standard: ../../../development/task-spec-standard.md
binds_design: ../DESIGN_UNITS_INDEX.md · ../README.md
---

# Graph-Agent-Gateway MVP1 实施计划(大模块 + 并发分区)

> **原则**:大模块按**依赖**串,小模块按**文件归属**并发(IR1)。baseline 实施后回写(IR6)。目标机制以各 `alignment` 为唯一真理(IR5),本计划只排**顺序 + 并发 + 文件锁**。
> **投递**:Codex 写好 `task.md` + Gemini prompt 后,把 prompt 打印成可复制 fenced block,由用户复制投递;不依赖本地 CCB 桥接。

## 一、为什么不是"全并发":gateway 核心是耦合的

`call/chat_model.py` 和 `call/clients.py` 是**共享热点文件**(README:50 标「共享」),被模块 07/09/10/11 同时覆盖。`resolver.py` 被 10(工厂实例化)和 01/02(解析纯化)同时碰。所以真正能并发的是**碰不同文件**的工作,核心调用链只能当**一条串行工作流**。

## 二、依赖图

```
WS-1 调用核心(步骤0 产 base_url 共享原语 → 11→10→09→07,串行)─→ WS-5 解析纯化(01/02,碰 resolver.py)
WS-2 base_url 保存侧归一化(import WS-1 的 base_url 原语)──────── 并发
WS-3 6 态/取消 needs_setup ──────────────────────────────────── 并发
WS-4 事件/异常 code 细化 ────────────────────────────────────── 并发,最后
```

- per-protocol `base_url` canonical helper 是 **WS-1 与 WS-2 共享原语**;依赖方向与优先级对齐——**WS-1 步骤 0 先产**(`registry/base_url.py`),WS-2 保存侧 `import` 它。**WS-1 不被 WS-2 阻塞**(原"等 WS-2 给桩"方案废弃:no-op 桩过不了 WS-1 §6 base_url 测试,真桩与 WS-2 重复 = divergence)。
- WS-5 改 `resolver.py`,与 WS-1 的 10 改 `resolver.py` 冲突 → **WS-5 排在 WS-1 之后**。
- WS-2 / WS-3 / WS-4 之间文件不重叠,**可同时跑**,也可与 WS-1 的起步(11)并行。

## 三、工作流分区(按文件归属,IR1)

| WS | 名 | 模块 | owns_files(并发锁) | 依赖 | 并发性 | 优先级 |
|---|---|---|---|---|---|---|
| **WS-1** | 调用核心 | (0)+11→10→09→07 | `registry/base_url.py`(新,步骤0,共享)·`call/profiles.py`(新)·`route_chat_model_factory`(新/或 `models.py`)·`call/chat_model.py`·`call/clients.py`(`_call_*`/dispatch/token-escalation 部分)·`resolver.py`(构造模型那段) | 无(步骤0 自产 base_url 原语) | **内部串行**(见 WS1 任务书) | P0 关键路径 |
| **WS-2** | base_url 保存侧归一化 | 03 | `registry/storage.py`(`_normalize_base_url` 改 import `registry/base_url.py`)·`apps/studio/.../llm_credentials.py`(保存时归一化)·endpoint probe 归一化点 | WS-1 步骤0 的 `registry/base_url.py` | 与 WS-1 起步并行 | P0(保存侧主修复) |
| **WS-3** | 6 态/取消 needs_setup | 08 | `apps/studio/.../llm_state_projection.py`·`llm_role_materializer.py`·router projection helpers + 对应 studio 测试 | 无 | **全并发** | P1 |
| **WS-4** | 事件/异常 code 细化 | 13 | `events.py`·`exceptions.py`·`tracing.py` | 无 | **全并发** | P2(最后) |
| **WS-5** | 解析纯化:route API + skip | 01,02 | `registry/resolver.py`(resolve_role skip+diagnostics)·`resolver.py`(route 级 API)·`protocol.py` | **WS-1**(共享 resolver.py) | 串行,WS-1 后 | P1 |

## 四、WS-1 内部子步骤(关键路径,严格串行)

> 共享 `call/chat_model.py`/`call/clients.py`,不能并行编辑,故内部串行。详见 [`WS1-chatx-core.md`](./WS1-chatx-core.md)。

0. **base_url 共享原语**(新文件 `registry/base_url.py`)— `canonicalize_base_url(url, protocol)` 幂等纯函数 + 逐 protocol 单测;WS-1 自产、WS-2 import。
1. **11 ProviderProfile**(新文件,加法,最独立)— provider/model→init-kwargs 表;lookup(exact>provider)+ merge(pre_init→init_kwargs→factory→caller-wins);不与 `VerifiedProfile` 合并。
2. **10 RouteChatModelFactory**(新文件,消费 11)— `ResolvedRoute`→`BaseChatModel`;官方 ChatX 优先 / `GenericRouteChatModel` 兜底;base_url 调用时幂等副保险(import WS-2 helper);第 6 步调 11。
3. **09 invocation 接线**(改 `call/chat_model.py`)— `_generate` 第 1/5/7 步换:原始 `BaseMessage` 直接交 ChatX → `.invoke()` → `_build_chat_result` **augment**(非重建)注 route metadata + 从 `usage_metadata` 取 usage + thinking 不拍平;退役 `_call_*` 的「消息转换+provider 调用」两件。
4. **07 编排接线**(改 `call/chat_model.py`/`call/clients.py`)— 保留编排外壳;`_call_with_token_escalation` 从 `_call_*` 搬到编排层包住 ChatX invoke;probe/熔断/usage 归属保留。

## 五、本批不做(范围锁定,避免再发散)

- **06 错误分类**:alignment 明写「mvp1 不变」→ **零代码**(只在 WS-1 测试里断言 ChatX 异常仍被 `classify_exception` 正确分类,不改 06 本体)。
- **predict→engine**:卡 engine designer,跨团队 → **本批不动**(gateway 侧保住 `GatewayChatModel` 类即可,predict 自动不变)。
- **05 model knowledge 下沉**:是 studio→gateway 的**搬迁**(非行为变更),独立低优先级,后续单立 WS。
- **04 registry schema**:`ResolvedRoute` 等已存在,稳定;DTO bridge seam 如需微调,并入相关 WS,不单立。

## 六、执行波次建议

- **Wave 1(并发起步)**:WS-2(base_url helper 先行)、WS-3、WS-1 的步骤 1(ProviderProfile)同时开。
- **Wave 2**:WS-1 步骤 2→3→4(串行,关键路径),WS-4 可挂在旁边并发。
- **Wave 3**:WS-5(WS-1 完成后,resolver.py 才安全)。
- 每个 WS 完成 = 测试绿 + 验收清单 + 回写 baseline + Claude 终审,然后才进下一个依赖它的 WS。

## 七、产物状态(2026-06-06)

- 任务书标准:`docs/development/task-spec-standard.md`
- 本实施计划:本文件
- WS 需求书落点(新):`.kiro/specs/graph-agent-gateway-mvp1/requirements-wsN.md`
- WS kiro task.md 落点:`.kiro/specs/graph-agent-gateway-mvp1/task-wsN.md`

| WS | 需求书/任务书 | 已完成主路径 | 仍 deferred / 尾债 | 状态 |
|---|---|---|---|---|
| WS-1 | `_impl/WS1-chatx-core.md`(旧格式过渡) | 已提交 `12896c9f`;ChatX 调用核心主路径闭合;generic 最小闭环已处理 | `DEF-018`:剩 legacy / profile / thinking 尾债另行处理 | ✅ 主路径闭合 |
| WS-2 | `_impl/WS2-base-url.md`(旧格式过渡) | 已提交 `858dc11b`;base_url 保存侧主路径闭合;`DEF-020` 已完成 | 无已知 WS-2 尾债 | ✅ 闭合 |
| WS-3 | `.kiro/.../tasks-ws3-six-states.md` | 后端 6 态投影/materializer/router 侧主实现已落地并通过聚焦测试;`DEF-021` 已完成 | 无已知 WS-3 尾债 | ✅ 闭合 |
| WS-4 | `.kiro/.../tasks-ws4-fallback-events.md` | fallback event 专属 code 主实现已落地并通过聚焦测试 | 无已知本 WS 尾债 | ✅ 闭合 |
| WS-5 | `.kiro/.../tasks-ws5-resolution-purity.md` | resolution skip/diagnostics/route API 主实现已落地;01/02/04 baseline 均已回写 skipped diagnostics 真实状态 | 无已知本 WS 尾债 | ✅ 闭合 |
