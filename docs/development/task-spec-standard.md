---
doc: task-spec-standard
status: drafted（v1;2026-06-06 建立,gateway 实施首用）
applies_to: 所有由 Codex 写测试/审查、由 Gemini 实现的实施任务书
---

# 任务书写作标准(Task-Spec Authoring Standard)v1

> **谁用**:Claude(架构师)写**需求书**的统一格式;实施任务书(kiro `tasks.md`)由 Codex 在契约门后写,**不是** Claude 的产物。
> **两个产物别混**:① **需求书** = Claude 写,流水线**输入**(意图/范围/owns_files/SSOT/测试须覆盖什么),不含实现步骤拆分;② **实施任务书** = Codex 写,契约门过后据**已批准测试**拆实现步骤,并生成给 Gemini 的可复制实施 prompt。
> **流水线**:
> `Claude 写需求书 → Codex 写失败测试 → Claude 审"测试是否忠实编码目标"(契约门) → Codex 据已批准测试写实施任务书(kiro tasks) + 输出 Gemini prompt → Gemini 实现(先读文件再写) → Codex 审到硬退出条件 → 回写 baseline(照真实代码) → Claude 终审`。
> **投递方式**:默认把给 Gemini 的任务内容打印成一个可一键复制的 fenced code block,由用户复制到 Gemini 或由当时可用的人工/自动通道投递;标准本身不依赖任何本地后台会话、桥接器或转发工具。
> **为什么要标准**:统一格式 + 铁律,让每份需求书自带「并发边界 / grounding / 测试契约 / 硬退出 / 回写指令」,杜绝"边设计边审边返工"。

## 〇、第一性原理:Claude 是产品经理,交付契约,不交付实现

这条流水线里 Claude 的身份是**产品经理 / 架构师**,**不是工程师**。这是全文的统领,下面所有铁律都是它的展开。

- **PM 的产物 = 契约**:要什么行为、达成什么效果、测什么、边界在哪、去哪读。
- **怎么实现 = 执行者的工程判断**:Codex 写测试、Gemini 写代码,他们决定解法。**PM 不替工程师做这个判断。**

**把实现细节写进需求书,就是 PM 越权干了工程师的活**,有两重危害:① 执行者没了判断空间,沦为打字员(**手把手**);② 需求书一旦写到代码级(逐行改写 / 字面数组条件 / 函数体 / 锁死行号),Claude 就是在**用 prose 写代码**,绕过了"Claude 不亲自写代码"的铁律——换个文件类型写代码,本质还是写代码。

> **一句话心法**:**PM 定义问题与验收,工程师决定解法。** 需求书写到"契约"为止——再往下一步(告诉执行者"具体改哪行、写成什么样"),就是替别人做事,**停**。
>
> **写每一句前自检**:"这句交给 Gemini,它还需要做工程判断吗?" 不需要 = 你已经替它写完了 = 删掉,回到契约层。

## 一、流水线职责(每份任务书都跑这条)

| 阶段 | 谁 | 干什么 | 产物 |
|---|---|---|---|
| 1 写**需求书** | Claude | 按本标准 §三 写 WS **需求**(意图/范围/owns_files/SSOT 指针/测试须覆盖什么),**不写实现步骤拆分** | `.kiro/specs/{feature}/requirements-wsN.md` |
| 2 写测试(RED) | Codex | 按需求书 §6 写**失败测试**(TDD RED) | 测试文件 |
| 3 **契约门** | **Claude** | 审"测试是否忠实编码 alignment 目标";过了才放行 | 通过/打回 |
| 4 写**实施任务书** | **Codex** | 契约门过后,据**已批准测试**拆实现步骤,写 Gemini 可执行的 kiro 任务文件,并输出可复制 Gemini prompt | `.kiro/specs/{feature}/tasks-wsN.md` + prompt |
| 5 实现 | Gemini | **先读需求书列的文件并确认**,再写代码到测试变绿 | 代码 |
| 6 审查 | Codex | 审到硬退出条件**全满足**(非主观"满意") | 通过/打回 Gemini |
| 7 回写 baseline | Codex | 照**真实代码**改对应 `baseline.md`(此时"目标当现状"物理上不可能) | 更新 baseline |
| 8 终审 | Claude | 查:合不合意图 / baseline 是否诚实 / 测试是否假绿 | 验收/打回 |

## 二、8 条铁律(违反即打回)

- **IR1 并发按文件切,不按文档模块切。** 每份任务书在 frontmatter 声明 `owns_files`(本 WS 可创建/修改的文件全集)。**两个并发 WS 的 `owns_files` 不得相交**。共享文件(如 `client_manager.py`/`gateway_chat_model.py`)→ 归同一个 WS 串行,或各自 git worktree 隔离后再合。
- **IR2 grounding 强制(防 Gemini 脑补)。** §3 必须给**完整文件路径** + 对应 alignment §节,并要求执行者"先回读到的关键符号/现状再动手"。
- **IR3 测试 = 契约,Claude 先审;实施任务书在契约门后由 Codex 写。** Codex 写完测试,Claude 先过"测试是否忠实编码了 alignment 目标"(契约门),通过后**由 Codex** 据已批准测试写 kiro 实施任务书,并输出给 Gemini 的可复制 prompt。**禁止**测试没过契约门就写实施任务书或开始实现;**禁止 Claude 代写实施任务书**(实现步骤是 implementation-level,Claude 越线 = "相当于自己写代码")。
- **IR4 硬退出,非主观满意。** §8 验收 = 测试全绿 + 验收清单逐条勾 + 至少一条**真实端到端**(非 fake mock 到绿)。Codex 审查以此为退出条件,不是"看着差不多"。
- **IR5 不重述 SSOT。** 目标机制以 `alignment §x` 为唯一真理,任务书只**指针 + 增量**(测试要求/验收/文件归属/顺序),不复制 alignment 内容(复制 = 双份 SSOT,会 drift)。
- **IR6 baseline 实施后回写。** baseline 永远照**已落地的真实代码**写,不在实现前精修。实现完才回写(顺序见 §一阶段 6)。
- **IR7 范围锁定。** 只动 `owns_files`;发现范围外问题 → 记 `docs/deferred-items.md`,不顺手改。
- **IR8 PM 边界:定契约,不写实现(§〇 的打回触发点)。** 需求书里出现以下任一 = 越权写实现,**打回重写**:① 逐行 `before → after` 代码改写;② 字面代码 / 数组 / 条件表达式 / 函数体;③ 拿精确行号当"改第 X 行"的编辑坐标(行号只能作 grounding,见 §三粒度边界)。给**接口签名**(契约)可以,给**函数体**不行。逐行实现拆分归 Codex 在契约门后写(§一步骤 4),不进需求书。

## 三、需求书模板(Claude 写,逐节强制,缺节即不合规)

> **粒度边界(防"手把手 / 替 Gemini 写代码",违反即打回重写)**:需求书**止于契约**——写「什么行为必须成立 / 什么测试必须覆盖 / 边界与不做 / 去哪读」。**禁止写**:
> - ① 逐行 `before → after` 代码改写(那是实现,归 Gemini);
> - ② 字面代码片段 / 数组 / 条件表达式 / 函数体;
> - ③ 把精确行号当"改第 X 行"的编辑坐标——源文件常 dirty/drift,行号**只能作 grounding**("去这附近读"),不能作编辑指令。
>
> 可以给**接口签名**(`f(x) → T`,这是契约),但**不给函数体**。自检口诀:**"这段交给 Gemini,它还需要做工程判断吗?"** 不需要 = 你已经替它写完了,删掉,留契约。
> 逐行实现拆分(Phase × 步骤)是**实施任务书**的事,Codex 在契约门后写(见 §一步骤 4 / §四 4.2),**不进需求书**。

```markdown
---
ws_id: WS-N-<短名>
modules: [<涉及的设计模块号>]              # 如 [09,10,11,07]
depends_on: [<前置 WS>]                    # 没有写 []
blocks: [<被本 WS 阻塞的 WS>]
owns_files: [<本 WS 可改/建的文件全集>]    # IR1 并发锁,精确到文件
spec_ssot: [<alignment §节 指针>]          # IR5 目标真理在这,不复制
status: drafted
---

# WS-N <名> — 需求书

## 1. 目标(intent + why,一段)
做什么 + 为什么(动机一句)。目标机制细节见 spec_ssot,不在此复制。

## 2. SSOT 指针(grounding,IR2/IR5)
- 目标(怎么做):<alignment 路径 §节>
- 现状(起点):<baseline 路径>
- 范本/参考:<references 路径>
- 必读源码(实现前先读并确认):<file:line 列表>

## 3. 文件归属(并发锁,IR1)
- 本 WS owns(可改/建):<文件列表>
- 禁止触碰(别的 WS 的):<文件列表 + 归属 WS>
- 共享文件协调:<若有,写明串行/worktree 策略>

## 4. 现状锚点(baseline,一句 + 指针)
当前是什么(指 baseline §节),起点。

## 5. 目标行为(可测的契约)
输入 → 输出;关键分支走哪条;错误/边界怎么处理。写**行为**,不写实现细节(让 Gemini 选实现)。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)
从 alignment §测试关键点 抽:必覆盖的行为 / 边界 / 回归用例(含具体回归,如某 provider 某场景);标注哪些必须**真实 e2e**、不许 fake mock。

## 7. 硬依赖约束(若 WS 内组件间有强制先后)
仅写**约束级**先后(如"schema 改完消费方才能编译"),**不细化为实现步骤**(实现序是 task.md 的事,归 Codex/Gemini)。无硬依赖则写"无"。

## 8. 验收标准(硬退出,IR4)
- [ ] 测试全绿
- [ ] <逐条可勾的验收点>
- [ ] 无回归:<点名不能回归的行为>
- [ ] 至少一条真实 e2e 通过

## 9. 不做(范围锁定,IR7)
明确边界:不重构 X;不动共享文件 Y 的 Z 部分;范围外问题记 deferred。

## 10. baseline 回写指令(IR6)
实现落地后,改哪个 `baseline.md` 的哪节,照真实代码写。

## 11. 评审检查点
- 契约门(Claude 审测试):重点查什么
- Codex 审查退出 = §8 全满足
- Claude 终审:意图 / baseline 诚实 / 测试非假绿

## 12. 给 Codex 的交接:按写作规范写 kiro task.md
契约门通过后,Codex 据**已批准测试**写 kiro `task.md`(落点 `.kiro/specs/{feature}/task-wsN.md`),遵守:
- **来源 = 已批准测试**(测试是契约),不凭空设计实现步骤;
- **格式** = Phase 分段 + `- [ ]` 勾选项 + 每条挂 `_Requirements: <模块.功能>` + 验证命令;
- frontmatter 指回 alignment(design SSOT)+ 本需求书;**不重写设计**;
- 嵌入编排注解:`owns_files` / 实现者 = Gemini / §8 硬退出;
- **行号 Codex 落地时自己重新核**(源文件会 drift),不照抄本需求书里的行号;
- **不跑 `/kiro:spec-tasks`**(会 clobber),人工按规范写。
- 完整规范见 `task-spec-standard.md` §四 4.2。
```

## 四、两个产物的落点(需求书 vs 实施任务书)

按项目规则「实施归 kiro」(`design-doc-standards/01-writing-standard.md §8` / `02-audit-standard.md Q4` / 上层 `spec-driven.md`),流水线有**两个不同产物,作者和落点都不同**,不得混为一谈:

### 4.1 需求书(Claude 写,步骤 1)— 即你口中的"任务书"
- **作者**:Claude(产品经理 / 架构师)。**落点**:`.kiro/specs/{feature}/requirements-wsN.md`(kiro,和 Codex 的 `task-wsN.md` 同目录;需求书 ≈ kiro requirements,task.md ≈ kiro tasks)。
- **内容**:本标准 §三 模板——意图 / 范围 / owns_files / SSOT 指针 / 行为契约 / 测试须覆盖什么 / 验收 / 不做 / **给 Codex 写 task.md 的交接(§三 第 12 节)**。**不含实现步骤拆分、不含字面代码、不锁行号**(§〇 / IR8)。
- **作用**:它是 Codex 写测试、契约门审查、以及 Codex 后续写 `task.md` 的**输入**。
- **完整范例**:见文末 **§六 样版**(自包含,不依赖其他文件)。

### 4.2 实施任务书 = kiro `task.md`(**Codex 写**,步骤 4,契约门后)
- **作者**:**Codex**,在契约门通过后,据**已批准的测试**拆实现步骤。**Claude 不写**(实现步骤是 implementation-level,Claude 代写 = 用 prose 写代码,违反 §〇 / IR3 / IR8)。
- **落点**:`.kiro/specs/{feature}/`(如 `graph-agent-gateway-mvp1`)。**并发多 WS 时每个 WS 写自己的文件**(如 `task-ws4.md`),**不并发改同一个文件**(撞文件)。
- **Codex 写 `task.md` 的写作规范**(Claude 在需求书 §12 把这份规范交给 Codex,Codex 落地时遵守):
  - **来源 = 已批准测试**:每个 Phase / 步骤都从已通过契约门的测试反推,**不凭空设计**(测试是契约)。
  - **格式 = kiro 任务格式**:Phase 分段 + `- [ ]` 勾选项 + 每条挂 `_Requirements: <模块.功能>` + 每条带**验证命令**。
  - **frontmatter** 指回该 WS 的 alignment(design SSOT,**不重写设计**)+ 涉及模块 + 对应需求书路径。
  - **嵌入多-AI 编排注解**:`owns_files` / 实现者 = Gemini / 硬退出条件(kiro 原生没这层)。
  - **行号自核**:行号只能作 grounding;源文件会 drift,Codex 落地时**自己重新核行号**,不照抄需求书里的旧行号。
  - **`requirements.md`/`design.md` 不重写设计**,指回三轴 alignment,避免双份 SSOT。
  - **不跑 `/kiro:spec-tasks` 自动生成**(会 clobber),人工按本规范写,只借 kiro 目录结构。
  - **同步输出 Gemini prompt**:契约门通过、`task.md` 写好后,Codex 必须把给 Gemini 的完整任务 prompt 以 fenced code block 打印出来,让用户能一键复制。prompt 必须包含:工作区路径、必读文件、RED 测试结果、owns_files/禁止触碰、目标行为、验证命令、回报格式。投递渠道由当时环境决定,不得把某个本地转发机制写成硬依赖。

## 四·五、先于需求书:实施计划(IMPL_PLAN)怎么写

> 每个 feature 在写第一份需求书之前,Claude 应先产出**实施计划**(`_impl/IMPL_PLAN.md` 或同级位置),确定 WS 切分、依赖、并发性。**计划是所有需求书的前置输入**;没有计划就写需求书 = 不知道文件锁冲不冲突。

### 为什么要先切 WS

多个 WS 并发执行时,**并发安全的单元 = 文件不重叠**。"模块"是设计维度,不等于"可以并发"——一个文件被两个模块共享,两条 WS 同时动它就会打架。实施计划的核心工作就是**把文件归属锁清楚**,让并发安全。

### IMPL_PLAN 的结构(逐节)

```markdown
# {Feature} 实施计划(大模块 + 并发分区)

> 原则一句话(串 vs 并的判据)。
> 投递方式一句话(prompt 复制 / 其他)。

## 一、为什么不是"全并发"(热点文件分析)
点名哪些文件是"热点"(被多个模块同时改)→ 它们是串行的根因。
没有热点 = 可全并发,也要说清楚。

## 二、依赖图(ASCII,一眼看懂)
WS-X → WS-Y 表示 Y 必须等 X 完成。
同行 = 可并发。
格式:简单 ASCII,不要复杂图表。

## 三、工作流分区表(IR1 文件锁的权威来源)
| WS | 名 | 模块 | owns_files(并发锁) | 依赖 | 并发性 | 优先级 |

owns_files 是最重要的列:精确到文件名,两行 owns 不能有交集。
优先级 P0/P1/P2 = 上线紧迫度,不是执行顺序(执行顺序由依赖图决定)。

## 四、WS 内部串行约束(仅有内部热点时才写)
只写有内部串行的 WS(如 WS-1 内部 11→10→09→07,因为都碰同一个热点文件)。
没有内部串行的 WS 不写这节。

## 五、本批不做(范围锁定)
明确列出哪些模块/功能本次不碰,以及为什么(等依赖/优先级低/独立任务)。
写了"不做"才能防止 WS 执行时顺手扩散。

## 六、执行波次建议(可选,有并发时才有价值)
Wave 1 / Wave 2 / Wave 3:每波可以同时跑哪些 WS。
每个 WS 完成的定义 = 测试绿 + 验收清单 + 回写 baseline + Claude 终审。

## 七、产物状态(动态维护)
| WS | 需求书 | 实现 | 状态(⏳/🔄/✅) |
随实施进度更新,不要让它变成"永远是 draft"的死文件。
```

### 写计划的三条原则

1. **先找热点文件,再决定并发**。看 `owns_files` 是否重叠,重叠的强制串行或 worktree 隔离。模块数量多 ≠ 需要串行。
2. **计划只排顺序 + 文件锁,不写实现细节**。机制细节在各模块 alignment,不在计划里重述(IR5)。计划写完看这个问题:"我能从计划里知道谁能先跑、谁要等谁、谁不能同时动哪个文件"——能 = 计划到位了。
3. **§七产物状态要活**。每个 WS 闭合就更新状态,让计划成为全局进度面板,不然每次只能靠记忆判断"现在跑到哪了"。

### 完整范例
`docs/graph-agent-gateway/mvp1/_impl/IMPL_PLAN.md`(gateway 实例,自包含可参考)。

---

## 五、本标准自身的边界

- 本标准管**需求书怎么写**(Claude 产物)+ **`task.md` 的写作规范**(Codex 产物),不管设计文档(那是 `docs/development/design-doc-standards/`)。
- 实施后回写的 baseline 仍受 design-doc-standards R2(对齐真实代码)约束。
- 锁/FROZEN 留到实施后、baseline 稳定再上(见 `graph-agent-gateway/mvp1/AUDIT_REMEDIATION_PLAN.md` 战略转向)。

## 六、样版:一份合规需求书(自包含示例,Claude 写)

> 按本标准写的**需求书**完整样版。**纯演示**——文件路径 / 模块号 / alignment 章节均为虚构,只为展示格式与「契约 vs 实现」的边界,**不指向真实文件**。读的时候盯住:**写了什么(契约)、刻意没写什么(实现细节留给执行者)**。

```markdown
---
ws_id: WS-7-probe-timeout
modules: [12]
depends_on: []
blocks: []
owns_files:
  - src/gateway/probe.py            # 健康探测主逻辑
  - tests/gateway/test_probe.py     # 探测单测
spec_ssot:
  - docs/.../12-probe/alignment.md §F1(超时语义) / §F2(重试语义)
status: drafted
---

# WS-7 endpoint 健康探测加超时 + 单次重试 — 需求书

## 1. 目标(intent + why)
给 endpoint 健康探测加**超时**与**失败单次重试**。现状探测无超时,慢 endpoint 把整条探测链卡死;一次抖动就判不可用,过于敏感。目标:探测在超时内返回,瞬时失败给一次重试机会。机制细节以 spec_ssot 为唯一真理。

## 2. SSOT 指针(grounding,IR2/IR5)
- 目标(怎么做,唯一真理):docs/.../12-probe/alignment.md §F1/§F2
- 现状(起点):docs/.../12-probe/baseline.md §2
- 必读源码(实现前先读并回述现状 —— 这是"去哪读",**不是**"改第几行"):
  - `src/gateway/probe.py` 的 `probe_endpoint`(当前无超时、无重试的探测入口)

## 3. 文件归属(并发锁,IR1)
- 本 WS owns:见 frontmatter。
- 禁止触碰:endpoint 配置加载相关代码(别的 WS owns)。

## 4. 现状锚点(baseline)
现状 `probe_endpoint`(探测单个 endpoint 是否健康)同步发一次请求、无超时、无重试,失败即判不健康。详见 baseline §2。

## 5. 目标行为(可测的契约 —— 描述行为,不写代码)
- 探测必须在**可配置超时**内返回;超时 = 一次失败。
- 探测失败(含超时)→ **重试一次**;两次都失败才判不健康。
- 成功(首次或重试)→ 判健康,返回探测耗时。
- 注:重试退避策略、用什么超时原语、异常怎么捕获 —— **由实现者(Gemini)决定**;契约只要求"超时内返回 + 失败重试一次"。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)
- 超时内成功 → 健康。
- 探测超时 → 记一次失败 → 触发重试。
- 首次失败、重试成功 → 最终健康。
- 两次都失败 → 不健康。
- ★ 至少一条真实 e2e:用本地慢响应 stub 触发超时路径,**非纯 mock 计时器**。

## 7. 硬依赖约束
无(本 WS 自包含,不依赖其他 WS 先落地)。

## 8. 验收标准(硬退出,IR4)
- [ ] `test_probe.py` 全绿
- [ ] 超时内返回 / 失败重试一次 / 两败才不健康 —— 各有测试
- [ ] 无回归:已健康 endpoint 的探测结果不变
- [ ] 至少一条真实 e2e(超时路径)

## 9. 不做(范围锁定,IR7)
- 不改探测的调用方 / 调度频率(别的 WS)。
- 不加多次重试 / 熔断(本轮只"单次重试");需要的记 deferred。

## 10. baseline 回写指令(IR6,Codex 落地后)
实现 + 测试绿后,Codex 照真实代码改 baseline §2:`probe_endpoint` 已加超时 + 单次重试;诚实标注未做的(多次重试 / 熔断)为待办,不得"目标当现状"。

## 11. 评审检查点
- 契约门(Claude 审测试):超时 / 重试 / 两败三条路径是否都被测;e2e 是否真触发超时而非 mock 计时器。
- Codex 审查退出 = §8 全满足。
- Claude 终审:合不合 §F1/§F2 意图 / baseline 诚实 / 测试非假绿。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md
契约门通过后,你(Codex)据**已批准测试**写 kiro `task.md`(落点 `.kiro/specs/{feature}/task-ws7.md`):
- 来源 = 上面已批准的测试(测试是契约),不凭空设计实现步骤;
- 格式 = Phase 分段 + `- [ ]` + 每条挂 `_Requirements: 12.F1/12.F2` + 验证命令;
- frontmatter 指回 alignment §F1/§F2 + 本需求书;不重写设计;
- 嵌 owns_files / 实现者 = Gemini / §8 硬退出;
- 行号你落地时自己核(源文件会 drift),不照抄本需求书;
- 不跑 `/kiro:spec-tasks`。
- 完整规范见 `task-spec-standard.md` §四 4.2。
```

> **这份样版示范了边界**:
> - §5 只说"超时内返回 + 失败重试一次"(**行为契约**),**没说** "用 `asyncio.wait_for`、退避 200ms、`except TimeoutError`"(那是实现,留给 Gemini);
> - §2 给的是"去读 `probe_endpoint`"(**grounding**),**不是** "改第 42 行"(编辑坐标);
> - §6 给测试**要覆盖什么行为**(契约),不替 Codex 写测试代码。
>
> 这就是 §〇 的 PM 边界:**定义问题与验收,不交付解法**。对照之前那种"把数组旧值→新值、把条件表达式、把精确行号全写死"的写法,差别一眼可见。
