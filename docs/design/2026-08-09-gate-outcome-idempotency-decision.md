# 决议：闸门幂等由投影相同性定义，不由事件身份定义（2026-08-09）

状态：已批准（用户 2026-08-09 授权「从第一性原理思考，修好它」，本文件为落盘正本）。
适用范围：Studio 前端闸门状态机（`apps/studio/frontend/src/components/studio/gate-state.ts`
与 `Workspace.tsx` 的闸门接线）、Studio 后端闸门领域事件发出点
（`apps/studio/backend/app/services/gate_events.py` 与 `skills.py`）。
不适用：engine 编译器本身的诊断聚合、gateway 配置真相、run 产物的持久化格式。

本决议修正 `docs/design/2026-08-03-copilot-state-parity-and-tool-surface-decision.md`
的 D4「幂等」条款；修正内容见本文第 5 节。

## 1. 结论

Studio 前端闸门状态机的幂等性，由「事件身份去重」改为「状态迁移」实现。三条规定：

- **状态无条件应用**：一条闸门结果事件到达时，它所指定的状态一律写入状态机。
  任何条件都不得挡在状态写入之前。
- **副作用按投影相同性折叠**：开错误抽屉、关抽屉、切换 Trace 面板、结算 run 这些副作用，
  在本次投影（状态 + 全部副作用及其载荷）与该 skill 上一次已应用的投影完全相同时不产出，
  其余情况一律产出。
- **每一次闸门发生由 `started` 事件定界**：compile 补发 `started`，与 predict、run 对称。
  于是任意两次连续的闸门发生之间必然隔着一次不同的投影。

按事件内容构造去重键的账本（`gateEventKey` 与 `Workspace.tsx` 的 `appliedGateOutcomes`）
整体删除，不保留兼容路径。

## 2. 事实基础

### 2.1 用户实测复现（2026-08-09）

操作序列：在 skill `exp-b-round7` 上按 Compile，编译成功，高亮移到 Predict；
再按一次 Compile；Compile 按钮变为不可点，并永久停留在该状态。
打开文件触发实时 lint 不能解除该状态。

### 2.2 代码链（缺陷位置）

Compile 按钮的禁用条件在整个界面里只有一处，
`apps/studio/frontend/src/components/studio/center-action-bar.tsx:46-56`：

```
if (stage === "idle" || stage === "compiling" || stage === "compile-fail") {
  compileHighlight: true,
  compileDisabled: stage === "compiling",
```

点击处理器先乐观置 `compiling`
（`apps/studio/frontend/src/components/studio/Workspace.tsx:1296`），
随后把 HTTP 响应投影成一条 pass 事件，事件带产物哈希
（同文件 1315-1320 行）。

去重键由事件内容构造，
`apps/studio/frontend/src/components/studio/gate-state.ts:87-88`：

```
const subject = event.runId ?? event.contentHash ?? ""
return `${event.skillId}|${event.gate}|${event.outcome}|${subject}`
```

去重发生在状态写入之前，
`apps/studio/frontend/src/components/studio/Workspace.tsx:685-690`：

```
const key = gateEventKey(event)
if (appliedGateOutcomes.current.includes(key)) return
appliedGateOutcomes.current = [...appliedGateOutcomes.current.slice(-63), key]

const { stage, effects } = projectGateEvent(event)
updateStage(event.skillId, stage)
```

源码未改动时，第二次编译产出同一个产物哈希，第二条 pass 事件与第一条同键，
在第 686 行被丢弃，第 690 行的状态写入不执行。状态机停在第 1296 行写下的
`compiling`，没有任何后续事件能把它推出去。

实时 lint 不能解除该状态，因为 `deriveBuildStage` 中闸门状态优先于 lint 状态
（同文件 2301-2302 行 `if (compileStage) return compileStage`）。

### 2.3 同一缺陷的其他实例

缺陷不限于 compile，凡是"同一主体上可重复发生、且结果相同"的闸门都会撞键：

- **连续两次编译失败**：fail 事件没有产物哈希，`subject` 恒为空串，
  键恒为 `<skillId>|compile|fail|`。第二次失败必被丢弃，
  且失败分支在投影后直接返回（`Workspace.tsx:1304-1312`），
  因此第二次失败既不推动状态机，也不弹出错误抽屉——即使两次的缺陷集完全不同。
- **同一个 run 被暂停两次**：`paused` 事件的 `subject` 是 `run_id`，
  同一个 run 暂停、恢复、再暂停，两条 `paused` 事件同键，第二条必被丢弃。

predict 不受影响：它每次发生都生成新的 `predict_run_id`，主体天然唯一。

### 2.4 缺陷的性质

产物哈希是**产物的身份**，不是**一次发生的身份**。编译是确定性的：同样的输入必然
产出同样的哈希。用产物身份去重，等价于断言"同样的产物只可能来自同一次编译"，
这条断言为假。事件身份被产物身份冒名顶替，是本缺陷的根因。

## 3. 关键设计决定

### D1 状态无条件应用

状态写入不得有任何前置条件。只要一条闸门结果事件到达，它指定的状态一律写入，
与到达次数、到达顺序、到达路径无关。

依据：这条给出「状态机不可能卡在非终态」的构造性保证，是本决议最重要的一条。
本缺陷的严重性正来自把去重挡在了状态写入之前——那让"重复到达"的代价从
"少弹一次抽屉"升级为"界面永久失效"。副作用可以少做一次，状态不可以少写一次：
二者的失败后果不在一个量级，因此必须分开约束，而不是共用一道闸。

### D2 副作用按投影相同性折叠，不按事件身份去重

判断"这次要不要执行副作用"，不查事件历史表，而比较投影：本次投影（状态 +
全部副作用及其载荷）与该 skill 上一次已应用的投影完全相同时不执行，否则执行。
每个 skill 只保留上一次投影，不保留历史。

依据：一次闸门发生经两条传输（HTTP 响应的本地投影、websocket 广播）到达时，
两次描述的是同一件事，投影必然相同——这一点由既有的双路径一致性测试保证。
反过来，两次真实发生若投影完全相同，则它们在界面上要求的结果也完全相同，
副作用执行一次与执行两次得到同一个界面，折叠是安全的。

这里的关键是**用什么定义相同**。原实现用产物哈希定义，而产物哈希是产物的身份，
不是一次发生的身份；投影则直接由"界面要变成什么样"构成，比较它等于比较
"这次要求的界面结果是否与上次一模一样"，不会把两件不同的事认成同一件。
比较状态迁移（新状态是否等于旧状态）曾是候选，但它太粗：同一个 skill 的两个 run
都映射到 `running`，第二个 run 的 `follow-run` 副作用会被误判为重复而丢弃，
Trace 面板会继续跟着上一个 run（`run_manager` 的 `self._runs` 按 run_id 存放，
没有"一个 skill 同时只能有一个 run"的互斥守卫，该情形可达）。投影比较把
`follow-run` 的 run_id 一并纳入比较，因此不存在这个盲区。

### D3 归约器保持「事件 → 投影」的纯函数，不接收当前状态

`projectGateEvent(event) -> { stage, effects }` 的签名不变，保持纯函数：
不读 React 状态、不碰 DOM。"要不要执行副作用"由调用方按 D2 判定，
"上一次投影"由调用方持有。

依据：D2 比较的是投影而不是状态，归约器不需要看见当前状态。让归约器只做
"这条事件意味着什么"，让调用方只做"这次要不要执行"，两个职责各自可单独测试，
也不必为了幂等把状态穿进纯函数。

### D4 每一次闸门发生由 `started` 事件定界

后端 compile 在开始编译前广播一条 `outcome: "started"` 的 `skill_gate` 事件，
与 predict、run 一致。

依据：D2 用投影相同性识别重复，因此两次真实发生之间必须隔着一次不同的投影，
否则第二次发生的副作用会被误判为重复而折叠。人点击时，点击处理器乐观置
`compiling` 提供了这次分隔；copilot 经 MCP 触发时没有点击处理器，若 compile
不发 `started`，连续两次结果相同的编译就会紧邻，第二次的错误抽屉不会弹出。
补 `started` 让两条发起路径的事件序列完全相同，这正是 2026-08-03 决议「状态对等」
原则的要求。前端已经为该事件准备好映射（`gate-state.ts:71` 的
`compile: { started: "compiling", ... }`），后端从未发出——这是实现对设计的偏离，
本决议予以补齐。

需要说明的是，即使没有 `started`，D1 也已经保证按钮不会卡死（状态无条件写入）；
`started` 解决的是副作用层面的完整性，两者各司其职，不可互相替代。

### D5 去重账本整体删除

`gateEventKey` 函数、它的测试、`Workspace.tsx` 中的 `appliedGateOutcomes` ref
与第 686-687 行的去重分支，在同一改动内删除。

依据：项目处于预发布期，不写兼容垫片（AGENTS.md「Development Principles」第一条）。
保留一个已被证明用错身份的去重层，只会让两套幂等机制并存，下一个读代码的人无法
判断哪一套是权威。

## 4. 被放弃的替代方案

### 4.1 由后端为每次闸门发生签发一次性 event_id，前端按 id 去重

做法：`build_skill_gate_event` 生成 uuid，随广播发出，同时经 HTTP 响应契约回传给
点击路径，前端用它替换 `gateEventKey`。这是成熟系统的通行做法（CloudEvents 的
`id` + `source`、Stripe 的 Idempotency-Key、事件溯源的 event id）。

放弃理由：它修的是"键取错了"，没有修"去重被放在状态写入之前"。即使 id 完全正确，
D1 给出的"不可能卡住"的构造性保证仍然缺席——任何一次 id 传递失误都会重新制造
永久卡死，而失误的代价依旧是界面永久失效。它还要改动三个闸门的 HTTP 响应契约
与失败异常，把一个前端状态机缺陷扩散成跨模块契约变更。在 D1 已经消除卡死、
D2 用投影相同性完成折叠之后，事件 id 不再带来额外保证。

若将来出现"两次真实发生的投影完全相同、且必须各自触发一次副作用"的需求，
届时再引入 event_id 是正确的下一步；当前没有这样的需求（KISS/YAGNI）。

### 4.2 只把状态写入提到去重之前，保留账本管副作用

做法：`updateStage` 无条件执行，`if (已见过) return` 只挡副作用。

放弃理由：按钮不再卡死，但 2.3 节的第二条仍在——连续两次内容不同的编译失败，
第二次的错误抽屉依旧不弹，缺陷集也不更新。用错误的身份定义去重，再给受害者
逐个开后门，是补丁而不是修复。

## 5. 对 2026-08-03 决议的修正

`docs/design/2026-08-03-copilot-state-parity-and-tool-surface-decision.md`
第 149-150 行 D4 的第一条实现约束原文为：

> - **幂等**：事件按 `(skill_id, gate, content_hash | run_id)` 去重，
>   重复到达不产生第二次副作用。

该条款作废，替换为：

> - **幂等**：事件到达时状态无条件应用，任何条件都不得挡在状态写入之前；
>   副作用在本次投影与该 skill 上一次已应用的投影完全相同时折叠，其余情况一律产出。
>   不按事件内容构造去重键——产物哈希是产物的身份，不是一次发生的身份
>   （2026-08-09 决议）。

同决议 D3 的事件载荷形状不变。同决议 D4 的另两条实现约束（副作用挂在迁移上、
事件按 skill_id 限定作用域）中，后者不变；前者"副作用挂在迁移上"由本决议 D2
细化为"按投影相同性折叠"——原表述的方向正确，但"迁移"若按状态值理解则过粗，
会漏掉同一状态值下载荷不同的副作用（见 D2 中 run 的 `follow-run` 例）。

## 6. 实施顺序

| 序 | 内容 | 依赖 |
|---|---|---|
| 1 | 前端：新增投影折叠单元（判定"本次投影是否与该 skill 上一次已应用的投影相同"），`projectGateEvent` 签名保持不变 | — |
| 2 | 前端：`Workspace.tsx` 无条件写状态，副作用按序 1 的判定执行；删除 `gateEventKey` 与 `appliedGateOutcomes` | 序 1 |
| 3 | 后端：`compile_skill_for_studio` 在编译前广播 `started` | — |
| 4 | 修正 2026-08-03 决议 D4 幂等条款 | — |

四项落在同一个 PR：删除旧幂等机制与建立新幂等机制必须同时发生，
否则中间态既没有去重也没有折叠约束。

## 7. 验收判据

判据以自动化测试表达，全部为新增或改写的失败测试先行（TDD）。

**前端（投影折叠单元的单测）**

1. 同一 skill、同一产物哈希的两条 compile pass 事件，中间隔一条 `started`：
   两次都判定为"应执行副作用"。
2. 同一条 compile pass 事件连续到达两次（模拟 HTTP 投影与 websocket 广播描述
   同一次发生）：第二次判定为"应折叠"。
3. 两条 compile fail 事件携带不同的缺陷集且紧邻到达：第二次仍判定为"应执行"，
   因为投影的 `open-drawer` 载荷不同。
4. 同一 skill 的两条 run `started` 事件携带不同 run_id 且紧邻到达：
   第二次仍判定为"应执行"，因为 `follow-run` 的 run_id 不同——这一条锁住 D2
   中说明的、按状态迁移判定会漏掉的盲区。
5. 折叠判定按 skill 隔离：skill A 的投影不影响 skill B 的判定。

**前端（`Workspace` 集成）**

6. 连按两次 Compile（后端两次都返回同一产物哈希），动作栏在第二次之后停在
   `compile-pass`：Compile 可点、Predict 高亮。这是用户 2.1 节复现路径的回归测试，
   且必须在"第二次投影与第一次完全相同"的最坏情况下通过——即不依赖 `started`
   到达，单靠 D1 的状态无条件写入就成立。

**后端（`apps/studio/backend/tests`）**

7. `compile_skill_for_studio` 成功路径广播两条事件，顺序为
   `started` 后接 `pass`；失败路径广播 `started` 后接 `fail`。

**门禁**

8. AGENTS.md「CI Gates」全部本地通过：前端 lint / typecheck / test / build，
   后端 ruff / mypy（SDK `--strict`）/ pytest ×3，pip-audit 零 CVE。

**真机点验**

9. 合并后在主仓 app 上复现 2.1 节操作序列：连按两次 Compile，第二次之后
   Compile 仍可点。以真窗口截图为证。

## 8. 术语

- **闸门（gate）**：compile、predict、run 三个必须按顺序通过的关卡。
- **一次闸门发生（gate occurrence）**：一次具体的编译/预测/运行动作，
  从 `started` 开始，到终态事件结束。两次发生即使产出完全相同的产物，
  也是两次不同的发生。
- **闸门结果事件（`skill_gate` event）**：后端在 service 层广播的领域事件，
  载荷形状见 2026-08-03 决议 D3。
- **投影（projection）**：一条闸门结果事件被翻译成的界面结果，由"状态"与
  "全部副作用及其载荷"两部分构成。两个投影相同，指这两部分逐项相同。
- **折叠（fold）**：本次投影与该 skill 上一次已应用的投影相同时，不执行本次副作用。
  折叠只作用于副作用，永不作用于状态。
- **副作用（effect）**：状态之外的界面动作——开关错误抽屉、切换 Trace 面板、
  结算 run。
