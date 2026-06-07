---
module: 09-golden-eval
doc: mvp1-alignment
status: drafted
last_verified: 2026-06-03
aligns_with: ../../../studio/mvp1/02_capabilities/golden-eval.md
decisions_locked: 2026-06-03（Q-G1=A 随技能提交；Q-G2/G3/G4 见 §决策）
---
<!-- 核对进度:已迁 1 块 / 未迁 12 块 / 2026-06-04 -->

~~# 09-golden-eval — MVP1 Alignment(目标设计)~~ → ✅[已迁入](../../02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment.md#1-定义)

> ⚠️ **2026-06-03 决策反转(PM,优先级最高,推翻下文决策 A)**:**golden 不写进 skill**。golden 是**会失效的临时产物**——只辅助优化 skill,不是 skill 本体,**留在 `.workspace/golden/`**(mvp0 `workspace-spec §3.2` 不废)。连带反转:① 决策 A(`phases/<id>/golden.json` 随技能进 git)**作废**;② 不再解冻 `01-physical-layout` 加 golden.json,skill 源码树**不含 golden**;③ golden **失效校验从「编译期硬错误」移到「golden-eval 时」**(compile 读不到 `.workspace`,`[F-v3-golden-stale-fields]` 不再是编译期码)。
> PM 原话:"golden不能写进skill , golden是会失效的临时产物, 他只是辅助优化skill的临时产物,不应该写进skill本体,应该留在.workspace"
> 下文 G1–G5 仍按旧决策 A 行文;**迁移到 `inner/golden-eval` 时按本反转改写**。

MVP1 目标:golden = **每个 agent 节点的「期望输出」,作者/copilot 事先定义,随技能源码版本化**(决策 A)。引擎 predict mock 层已逐节点(见 baseline),故本轮**不是换模型**,而是 5 个收口:① golden 解耦成逐节点常驻文件;② 失效升为编译期硬错误;③ diff 逐节点;④ 空模版生成;⑤ predict 拦截搬进引擎。

<!-- ⚠️ 未迁入（正式 06-golden-eval 已按 2026-06-03 反转改写，旧决策 A 的 G1-G5 正文未被实质承载；需显式退役或按 workspace 方案重写） → 应归入:02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment -->
## 覆盖范围

| 范围 | MVP1 目标 |
|---|---|
| golden 存储 + 物理布局 | `phases/<phase_id>/golden.json`(agent 节点专属、随技能进 git);改 FROZEN `01-physical-layout` |
| 回放 | 从 skill 源码逐节点加载 golden,喂进现有 `resolve_generation` P0(逻辑几乎不动) |
| 失效校验 | 编译期:golden 缺 `io.outputs` 新必填字段 → 编译错误 `[F-v3-golden-stale-fields]` |
| 逐节点 diff | 复用 `_diff_value`/`_score`,换喂入粒度为单节点 output vs 单节点 golden;做成引擎 SDK 能力 |
| 空模版生成 | 按节点 `io.outputs` schema 生成空 golden 模版(复用 stub 遍历骨架) |
| predict 拦截 | 从 gateway `PredictGatewayChatModel` 搬进引擎(接 D2 + create_agent 迁移) |

<!-- ⚠️ 未迁入（正式 06-golden-eval 已按 2026-06-03 反转改写，旧决策 A 的 G1-G5 正文未被实质承载；需显式退役或按 workspace 方案重写） → 应归入:02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment -->
## 目标设计与流程

<!-- ⚠️ 未迁入（正式 06-golden-eval 已按 2026-06-03 反转改写，旧决策 A 的 G1-G5 正文未被实质承载；需显式退役或按 workspace 方案重写） → 应归入:02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment -->
### G1 — golden 解耦为逐节点常驻文件(决策 A:随技能提交)

`phases/<phase_id>/golden.json`(只 agent 节点有):
```jsonc
{
  "expected_output": { /* 字段匹配该节点 io.outputs schema */ },
  "source": "manual" | "copilot",   // 永不为 trace（409 守卫天然成立）
  "updated_at": "2026-06-03T..."
}
```
- **路径即身份**:golden 绑 `phase_id`(=目录名),节点重命名 = 目录改名,golden **自动跟着走**,无需单独迁移逻辑(这是 A 比 `.workspace` 更干净的地方)。
- **随技能进 git**:golden 是作者定的质量契约,是技能定义的一部分,跟 `SKILL.md` 一样版本化(决策 A)。
- **不存 `inputs` / `schema_required_fields`**:per-node golden 是该节点"理想输出",不绑特定输入;必填集编译时实时算(Q-G4)。
- **回放接线**:新增「从 skill 源码按 phase_id 加载 golden」的来源,产出等价于现 `expected_traces[phase]` 的结构,喂进 `resolve_generation` P0;`resolve_generation` 的判定逻辑(`runner.py:94-97`)**一行不改**。

<!-- ⚠️ 未迁入（正式 06-golden-eval 已按 2026-06-03 反转改写，旧决策 A 的 G1-G5 正文未被实质承载；需显式退役或按 workspace 方案重写） → 应归入:02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment -->
### G2 — 失效校验:编译期硬错误 + 字段级(最易漏)

规则(PM 原话):改 prompt / agent 内部设置**不**失效;**仅**改 `io.outputs` 致 golden 缺**新必填字段** → 编译错误,补齐才能 predict。

设计:在 `compile_skill` 加 golden 校验 pass——对每个有 `golden.json` 的 agent 节点,取当前 `io.outputs` schema 的 **required 字段集**,检查 `golden.expected_output` 是否覆盖全部当前必填字段;缺 → `[F-v3-golden-stale-fields]`(带缺失字段列表),编译失败。
- **只看 `io.outputs` 必填字段存在性**,绝不碰 `prompt_hash`(这是和现 `_warn_on_stale_golden_hashes_sdk` 整哈希比对的关键区别)。
- 把现版「运行期 warn」退役,改「编译期 error」。

<!-- ⚠️ 未迁入（正式 06-golden-eval 已按 2026-06-03 反转改写，旧决策 A 的 G1-G5 正文未被实质承载；需显式退役或按 workspace 方案重写） → 应归入:02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment -->
### G3 — 逐节点 diff(复用算法)

run 后,每个有 golden 的 agent 节点:该节点实际输出(从 `final_state.json` 取该 phase outputs)vs `golden.json` 的 `expected_output`,喂现成 `_diff_value`/`_score`(`golden_diff.py:130-216`)——**算法不动,只换喂入粒度**;产出每节点一份字段级 diff + 分。

<!-- ⚠️ 未迁入（正式 06-golden-eval 已按 2026-06-03 反转改写，旧决策 A 的 G1-G5 正文未被实质承载；需显式退役或按 workspace 方案重写） → 应归入:02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment -->
### G4 — 空 golden 模版生成

新 helper:`(io.outputs schema) → 符合 schema 的空模版`(每字段填 null/空,按类型),复用 `generate_heuristic_stub` 的 schema 遍历骨架(它已按 schema 生成占位,模版 = 填空值版)。

<!-- ⚠️ 未迁入（正式 06-golden-eval 已按 2026-06-03 反转改写，旧决策 A 的 G1-G5 正文未被实质承载；需显式退役或按 workspace 方案重写） → 应归入:02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment -->
### G5 — predict 拦截搬进引擎(接 D2 + create_agent)

mock **内容**解析(`resolve_generation` 4 级)已在引擎,保留。mock **拦截**从 gateway `PredictGatewayChatModel` 搬进引擎:create_agent 迁移后,predict 模式下 agent 节点的 model **在调真实模型前被短路**——引擎查该节点 golden 状态命中就直接产出。倾向实现:一个引擎侧 predict mock chat model(实现 `BaseChatModel`,`_generate` 调 `resolve_generation`)当 `create_agent(model=...)` 传入,去 gateway 依赖。

<!-- ⚠️ 未迁入（正式 06-golden-eval 已按 2026-06-03 反转改写，旧决策 A 的 G1-G5 正文未被实质承载；需显式退役或按 workspace 方案重写） → 应归入:02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment -->
## 决策(2026-06-03 已锁)

| # | 决策 | 结论 |
|---|---|---|
| Q-G1 | golden 存哪 | **A:随技能提交 `phases/<phase_id>/golden.json`**(进 git,算技能定义);**不**放 `.workspace` |
| Q-G2 | 失效严格度 | v1 **只 block「缺必填字段」**(PM 原话);多余字段/类型不符 = warning,不挡 predict |
| Q-G3 | diff 归属 | **引擎 SDK**(`evaluate_golden_baseline` 逐节点版,纯函数);Studio 只渲染 |
| Q-G4 | 必填集来源 | **编译时实时算当前 `io.outputs` 必填集**;golden 文件**不**冗余存 `schema_required_fields`(避免两份漂移) |

<!-- ⚠️ 未迁入（正式 06-golden-eval 已按 2026-06-03 反转改写，旧决策 A 的 G1-G5 正文未被实质承载；需显式退役或按 workspace 方案重写） → 应归入:02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment -->
## FROZEN 解冻清单(本轮触发)

1. **`01-physical-layout.md`**:`phases/<id>/` 目录树 + 字段表加 `golden.json`(可选,仅 agent/SKILL.md 节点;holds 该节点期望输出)。precedent = 同目录已有可选 `validator.py`/`actions/`。
2. **`workspace-spec/baseline.md` §3.2**:golden **不再是 workspace artifact**——删 `golden/<baseline_id>/` 整次结构 + 「固化 predict RunResult 为 baseline」叙述;golden 改在 skill 源码 `phases/<id>/golden.json`。
3. **`11-error-code-spec.md`**:新增 `[F-v3-golden-stale-fields]`(golden 缺必填字段,编译期 FATAL)。
4. **`12-compile-runtime-flow-spec.md`**:编译期校验流加 golden 字段校验 pass。

<!-- ⚠️ 未迁入（正式 06-golden-eval 已按 2026-06-03 反转改写，旧决策 A 的 G1-G5 正文未被实质承载；需显式退役或按 workspace 方案重写） → 应归入:02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment -->
## 已实现 / 与 baseline 差异

- 已实现:逐节点回放(`resolve_generation` P0)、字段级 diff 算法、409 守卫、schema 漂移检测骨架——**复用,不重写**。
- 未实现:逐节点常驻 golden 加载(G1)、编译期失效硬错误(G2)、逐节点 diff 喂入(G3)、空模版生成(G4)、拦截搬引擎(G5)、FROZEN 物理布局/workspace-spec 改动。

<!-- ⚠️ 未迁入（正式 06-golden-eval 已按 2026-06-03 反转改写，旧决策 A 的 G1-G5 正文未被实质承载；需显式退役或按 workspace 方案重写） → 应归入:02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment -->
## 代码索引(clues)

- `runner.py:84-124`:回放接入点(P0 不改)。
- `runner.py:127-160`:旧 warn 检测(退役,改编译期 G2)。
- `_predict_internal/strategy.py:103-173`:golden 策略族 + from_param(加「从 skill 源码加载」来源)。
- `golden_diff.py:130-216`:diff 算法(G3 复用,换喂入)。
- `_predict_internal/stub.py:generate_heuristic_stub`:G4 模版生成复用骨架。
- `01-physical-layout.md:14-28` / `workspace-spec §3.2`:FROZEN 解冻落点。

<!-- ⚠️ 未迁入（正式 06-golden-eval 已按 2026-06-03 反转改写，旧决策 A 的 G1-G5 正文未被实质承载；需显式退役或按 workspace 方案重写） → 应归入:02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment -->
## 待办/疑点

1. 待办(TDD 失败测试先行,委派 Codex):G1 逐节点加载 + G2 编译期校验 + G3 逐节点 diff + G4 模版 + G5 拦截搬引擎。
2. 待办:FROZEN 解冻 4 项(物理布局/workspace-spec/错误码/编译流)需走解冻决策(决策 A 已隐含批准物理布局加 golden.json)。
3. 疑点:golden 的「该节点实际输出」从 `final_state.json` 取还是从 trace 的 finish_task 产物取——实现期对齐(两者都应是 validated business_data)。
