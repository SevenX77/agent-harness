# Tracing 去黑箱:呈现层重构 + 两个契约级缺口(决议)

- 日期:2026-08-13
- 状态:已批准。用户 2026-08-13 逐条给出 8+2 条裁决,本文件为落盘决议;§2 的 D1–D9 与裁决逐条对应。
- 目的(用户原话,2026-08-13):「tracing对于用户的目的是去黑箱,只有完全了解程序每一步执行了些什么,
  才能得到真实反馈,才能有的放矢的优化」。本决议全部取舍以这一句为度量衡。
- 权威设计源:`packages/graph-agent/src/graph_agent/callbacks/events.py`(引擎事件契约)、
  `docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md`、
  `docs/studio/mvp1/01_workflows/04_run-and-verify.md` §C/§D、
  `docs/studio/mvp1/02_capabilities/compile-lint/mvp1-alignment.md`(D9 的 diagnostics-SSOT 依据)、
  `AGENTS.md` 的「Three-Module Architecture」「Development Principles」「Coding Standards」三节
- 前置决议:`docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md`(Trace 信息架构)与
  `docs/design/2026-08-09-streaming-tracing-architecture-decision.md`(流式 tracing 架构)。
  本决议**推翻**前者的 D2(本文 D6)、**修订** `trace-observability/mvp1-alignment.md:158` 的
  折叠机制部分(本文 D3)、**补齐**后者 D1 不变量在 thinking 通道上的洞(本文 D2);
  两份前置决议的其余条目**全部保持有效**,逐项处置见 §5。
- 范围:`packages/graph-agent`(engine)与 `apps/studio/frontend` 两处为主;
  `apps/studio/backend` 沿既有事件通道透传新事件,不新增机制;
  `packages/graph-agent-gateway` 与传输层双通道不在本决议范围(§4)。

---

## 0. 背景定位:底层四层已健全,黑箱剩在哪里

一条 tracing 数据要经过四层:**产生**(引擎/网关发事件)、**记录**(`trace.jsonl` 落盘)、
**传输**(跨进程 + WebSocket 双通道)、**投影**(前端渲染)。经 2026-08-09~11 两份前置决议
及其实施 PR 的改造,这四层的骨架已经健全:步骤帧/增量帧分层、步骤身份配对、
gateway 路由决策进 trace,都已上线(B1)。

以 §0 目的句为度量衡重新验收,剩下的黑箱在两处:

- **两个契约级缺口**:模型的思考(reasoning)在盘上一份副本都没有(B2);
  引擎内部九台执行机器有七台对外零事件,做了影响执行的决定而用户看不见(B3–B5)。
- **呈现层缺陷**:无界正文渲染(B6)、选中与 trace 范围脱钩(B7)、终态后动画不清(B8)、
  Input/Output 伪节点自成一套(B9)、内置工具可被静默删除且边操作无处可看(B10)。

本决议由用户 2026-08-13 的 8+2 条裁决驱动,逐条处置以上全部。

---

## 1. 背景:已核实的事实

以下每条都以代码坐标或一次真实运行的实测坐实,不含推测。行号对应 2026-08-13 的 `main`;
「实测 run」指 `2026-08-10T12-35-19_87d0f2fb`。

### B1. 步骤身份契约已经上线,增量帧确实只流不存

- `prompt_captured` 与 `llm_call` 双帧带 `step_id`,铸造点为
  `packages/graph-agent/src/graph_agent/tracing/steps.py:192`;实测 run 中 21 对全部配对成功。
- `llm_delta`(增量帧)不落盘:`packages/graph-agent/src/graph_agent/callbacks/emit.py:28` 与
  `callbacks/tracing.py:110` 的 persisted 守卫把它挡在 `trace.jsonl` 之外。

这两点说明:D1/D6 需要的配对键已经存在;而「增量帧可丢」的安全性完全押在
「完整文本另有落盘副本」上 —— 这正是 B2 要检验的。

### B2. 思考没有落盘副本 —— 前置决议 D1 的不变量在 thinking 通道上有洞

实测 run 的 `llm_call.response_data` 键集合为
`[content, finish_reason, model_name, model_provider, system_fingerprint, tool_calls, usage]`,
**没有 `reasoning`**。其中一条的 `content` 长度为 0 —— 模型思考后直接调工具,
那一步的全部智力活动只存在于思考里,而思考恰恰哪儿都没存。

根因在读取侧:`_answer_report`(`packages/graph-agent/src/graph_agent/tracing/steps.py:292-304`)
只读 metadata + content + tool_calls + usage;`reasoning_content` 就在
`additional_kwargs` 里 —— Studio adapter(`apps/studio/backend/app/core/adapters/engine.py:420-431`)
已经把它传进来了 —— 但从未被读。

这违反前置决议 `2026-08-09-streaming-tracing-architecture-decision.md` D1 自立的不变量
(增量帧可丢的前提是完整文本各有一份落盘副本,该文 :369-372):
推理增量帧按 B1 只流不存,结束帧又不装推理全文,于是推理全文在盘上**零份** ——
增量帧对这份数据不再是可丢的中间态,而是它唯一的存在形式。

### B3. 九个中间件,七个零事件(grep 实测)

坐标前缀均为 `packages/graph-agent/src/graph_agent/middleware/`:

| 中间件 | 行数 | 事件 | 它在做什么 |
|---|---|---|---|
| `cognitive_flow.py` | 1049 | **0** | `finish_task` / 澄清工具拦截 |
| `protocol_validation.py` | 213 | **0** | 每个 LLM 步边界校验三条状态不变量 |
| `loop_detection.py` | 120 | **0** | 循环检测 |
| `tool_history.py` | 113 | **0** | 保证协议合法工具历史 |
| `tool_error.py` | 64 | **0** | 工具错误处理 |
| `runtime_input.py` | 85 | **0** | 把 AGENT phase 运行时输入送进模型 |
| `exit_control.py` | 180 | 仅 3 处涉事件 | 退出控制 |
| `tracing.py` | — | 发 | 工具调用事件 |
| `execution_control.py` | — | 发 | retry / loop / metrics 的 owner |

在发事件的只有最后两台。前七台每一台都在**做影响执行的决定**
(拦截工具、否决状态、检出循环、注入输入、吞掉错误),而事件流里一个字都没有。

### B4. md2json 静默修数据

`packages/graph-agent/src/graph_agent/cognitive/md2json.py` 的 `Md2JsonResult` 有
`repaired: bool` 字段 —— 解析、schema 校验、修复三件事全程 **0 事件**。
数据被改过,盘上只有一个布尔位,改了什么、为什么改,无处可查。

### B5. validator 事件是骨架

`ValidationFailEvent` 只有 `phase_name` / `errors` / `retry_count`
(`packages/graph-agent/src/graph_agent/callbacks/events.py:151`),
`ValidationPassEvent` 只有 `phase_name`(`events.py:461`)——
两者都不说这次校验**按哪份 schema 检查了什么**。「过了」与「没过」有记录,「检查了什么」是黑箱。

### B6. 呈现层无界正文

`apps/studio/frontend/src/components/trace/TraceStepRow.tsx`:

- `PromptSections`(`:222-247`)把 TEMPLATE / VARIABLES / RENDERED / Response 四段**全量渲染,
  无上限、无折叠**;
- `LiveOutput`(`:273-292`)同样无界;
- 唯一有折叠的是 `GenericPayload`(`:442-467`),其 2KB 阈值来自
  `docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md:158`。

实测单事件最大约 **22KB** —— 一条事件就能把整个面板顶成一屏白纸。

### B7. 点节点过滤 trace,已在 #657 按前置决议 D2 删除

`docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md:106-114`(该文 D2)
裁定「画布聚焦不再过滤 Trace,改为滚动定位」,#657 已实施。当时的理由:link 开关与收窄提示
都被删掉,若保留过滤行为,得到的是「一个看不见、也关不掉的过滤器」。
本文 D6 要推翻这条结论,因此当时的反对理由必须被显式化解,不能装作它不存在。

### B8. run 到终态后,动画不清

- 画布节点状态:`apps/studio/frontend/src/components/studio/node-status.ts:106-110`
  (`phase_start`→running / `phase_end`→success,最后一条赢);
- trace 步骤行:`buildTraceSteps`(`apps/studio/frontend/src/utils/trace-steps.ts`),
  无结束帧即永远 running。

两处都**只从事件流推导**;被取消/失败的 run 不补发 `phase_end` / `llm_call` 结束帧,
于是转圈永生。前置决议 `2026-08-09-trace-ia-and-streaming-overhaul-decision.md` D7
(该文 :154-163)已记录此缺陷,并立下「未在真窗口复现定位到具体控件前不得声称已修」的纪律。

### B9. Input/Output 伪节点特判

- `apps/studio/frontend/src/components/nodes/GlobalInputOutputNode.tsx` 的裸卡片样式自成一套,
  不与 phase 节点共享任何样式定义;
- `apps/studio/frontend/src/components/GraphCanvas/GraphCanvas.tsx:2464-2495`
  对 Input/Output 节点**单击与双击都特判**跳 Input 面板 —— 单击别的节点是「选中」,
  单击 Input/Output 却是「跳面板」,同一动作两种语义。

### B10. 内置工具可被静默删除;边操作事件已在流中,而 EdgeContextView 是固定版式

- 引擎 `packages/graph-agent/src/graph_agent/core/loader.py:1246` 把四个内置工具放进可用集合,
  skill 文件里**声明内置名静默通过,无任何诊断**;
- 前端 `apps/studio/frontend/src/components/studio/panels/PropertiesPanel.tsx:3913` 的
  `RESERVED_TOOL_NAMES` 只拦「新增」路径,`:3950-3966` 对文件里已声明的**任何**名字都渲染删除按钮 ——
  `finish_task` 就这样可以被用户删掉,而删掉它的 skill 编译照样通过;
- `apps/studio/frontend/src/components/studio/panels/EdgeContextView.tsx` 是固定版式面板,
  而边操作事件族(`blackboard_reduce` / `input_dispatch` / `input_file_injected` /
  `artifact_saved`,OB4)**已经在事件流中** —— 数据有了,呈现还停在另一套形态里。

---

## 2. 决策(用户 2026-08-13 裁决,逐条)

### D1 · 装载 prompt 是流里的一步:LLM 步骤展开态按执行顺序渲染子条目

展开的 LLM 步骤不再分「TEMPLATE / VARIABLES / RENDERED / Response」四个特殊容器,
而是按**执行顺序**渲染子条目:

> 装载 prompt(`template_source`)→ 渲染后 prompt → 思考 → 回答 / 工具 → 设置 / 路由判定

**废除 TEMPLATE / VARIABLES 特殊容器**。agent phase 内按 **Iteration 分层**:
数据源为 `agent_loop_iteration` 事件 + `prompt_captured.loop_index`,**纯前端投影**,不新增事件。

**依据。** §0 度量衡:去黑箱要求呈现顺序即执行顺序 —— 装载模板确实是程序执行的第一步,
它就该是流里的第一个子条目,而不是被抽出来放进一个与时间无关的容器。
B6 证明特殊容器的另一宗罪:它们各自无界渲染,长内容问题因此散落在四处而不是收敛在一处(由 D3 统一解决)。

### D2 · 思考必须落盘(契约级)

`_answer_report`(`tracing/steps.py:292-304`)补 `reasoning` 键,
读 `additional_kwargs.reasoning_content`(Studio adapter 已在
`engine.py:420-431` 传入,只差读取)。

**这补的是前置决议 D1 不变量的洞**(B2):推理全文从「盘上零份」变为「盘上恰好一份」,
推理增量帧才重新成为可丢的中间态。**代价被明示并被接受**:`trace.jsonl` 会变大 ——
理由是去黑箱是 tracing 的目的本身,为了文件小而让一整个思考通道在盘上消失,是本末倒置。

### D3 · 折叠属于文本自己:5 行 / 20 行 / Monaco 全文(取代 ~2KB 字节阈值机制)

长文本折叠不属于某个容器,而属于**文本自己**,三态统一:

- **收起**:5 行 —— 一眼识别这段是什么;
- **展开**:20 行;
- **看全文**:点链接进 Monaco 只读视图。

提炼为 `components/ui/folded-text` 共享原语,**禁止特殊容器** ——
任何 trace 表面的长文本都消费同一个原语,不允许再出现「这一段自己决定怎么折」的局部实现。

**取代关系。** `trace-observability/mvp1-alignment.md:158` 的「自动展开 payload 上限 ~2KB」
是按**字节**决定折叠的机制,本条以按**行**的三态取代其机制部分;
该行「长 trace 默认折叠大块」的**原则不变**。字节阈值的缺陷由 B6 坐实:
它只被 `GenericPayload` 一处实现,四段容器与 LiveOutput 都在它管辖之外,
「机制绑在容器上」正是无界渲染能存在的原因。

### D4 · 内部机器自述:发「决定」不发「路过」(E3)

每个「做了**影响执行的决定**」的内部步骤发语义事件,带**完整句子**的 `message` ——
像程序 print 一样把自己做了什么说出来。

**防噪音原则**:发「决定」不发「路过」—— 修了数据、拦了循环、注了输入、吞了错误、
下了校验结论才发;纯透传不发。这条原则是 D4 不退化成日志洪水的边界。

逐机器清单(对应 B3/B4/B5 的缺口):

| 机器 | 要自述什么 |
|---|---|
| `md2json`(**优先级最高**,B4) | 解析结论 + schema 校验结果 + `repaired` 时修了什么 |
| `protocol_validation` | 检查了哪条不变量、结论 |
| `loop_detection` | 检出重复时报告 |
| `tool_error` / `tool_history` / `runtime_input` / `exit_control` / `cognitive_flow` | 逐个盘点补报(各自「做决定」的时刻) |
| validator 事件(B5) | 补「按哪份 schema 检查了什么」 |

### D5 · 边点 = 边的步骤

点 edge 中点,显示**上一 `phase_end` 到下一 `phase_start` 之间的边操作事件**
(B10 列出的事件族已在流中),以与节点 tracing **相同的步骤行样式**呈现。

`EdgeContextView` 固定版式中的语义展示部分**退役进 tracing 行**;
`EdgeTamperEditor`(改黑板 resume)是操作件不是展示件,**留在面板**。

**依据。** B10:数据早已在事件流里,固定版式面板是同一信息的第二套呈现形态;
边上发生的事与节点上发生的事同属一条执行流,理应用同一种步骤行读法。

### D6 · 选中即范围(推翻前置决议 D2 / #657)

**画布选中态 = trace 显示范围**:选中节点 / 边 / Input / Output 各显示对应范围,
**点空白 = 全量**。

**两次裁决都记全。** 前置决议 D2(B7)删除过滤的理由是:link 开关与收窄提示已删,
留过滤即「不可见、不可关的过滤器」。本条推翻它,且反对理由被正面化解而非绕开:

- **不可见** → 过滤严格绑定**可见的选中环**(画布上选中态本身就是过滤器的开关指示),
  且 trace 面板头部**显示当前范围**;
- **不可关** → 面板头部范围提示**可一键清除**,点画布空白也回到全量。

前提变了,结论跟着变:当时被删的是一个没有任何可见锚点的过滤行为,
现在立的是一个锚点即选中态、状态可见、一键可退的范围机制。

### D7 · 状态投影 SSOT:run-status-projection(M3)

新建前端模块 **run-status-projection**,统一从 `(事件流, run 终态)` 推导一切派生状态,
取代 B8 那两处各自为政的推导。

- **铁律:run 到终态 ⇒ 任何派生状态不得为 running。** 缺结束帧不再是「永远转圈」的理由 ——
  终态本身就是最后的裁决输入。
- 每个消费组件登记「**状态 → 显示效果**」对照表,并用测试锁住。
- 承接前置决议 D7 的纪律:**未在真窗口复现并定位到具体控件之前,不得声称已修**。

### D8 · Input/Output 一致性 + 样式模块化通则(M4)

- 节点卡片基础样式 / 状态胶囊 / 连线样式提炼为**共享模块,一处定义**;
  phase 节点与 Input/Output 都是**调用方**(消灭 B9 的裸卡片副本)。
- 交互统一:**单击 = 选中**(与其他节点同义,并接入 D6 的选中即范围);
  跳 I/O 面板挪到**双击**(删除 `GraphCanvas.tsx:2464-2495` 的单击特判)。
- **通则**:凡「使 X 与 Y 一致」的改动,一律**先提共享模块再消费**,禁止复制样式副本 ——
  复制出来的一致性在下一次改动时就会漂移,那不是一致,是巧合。

### D9 · 声明内置工具 = 编译诊断(引擎,diagnostics-SSOT)(E2)

- 引擎 loader 新增诊断码 **`[F-v3-agent-tool-reserved]`**:skill 文件声明内置工具名
  (B10:`loader.py:1246` 的四个内置名)即产出编译诊断,不再静默通过。
- UI 对被诊断的行**挂错误标记**;此时删除按钮的语义从「能删掉 finish_task 的漏洞」
  翻转为「修复诊断的手段」—— 前端不需要再靠 `RESERVED_TOOL_NAMES` 自造拦截规则,
  这正是 `AGENTS.md`「Compile/lint 单出口 + 同一份诊断(diagnostics SSOT)」的落法:
  引擎能拥有的规则,Studio 不自造。
- 顺带修复 `PropertiesPanel.tsx` 同文件的 cp936 乱码字符串(「鈥?」)。

---

## 3. 验收判据

因果验证:每条都要有动作**之后**的可观察结果作证据;命令跑过、测试通过、
实施者自报「已完成」,都不单独构成证据。两条全局纪律:

- **真机点验截图为准**:每个工作项的 UI 判据以真实桌面 app 的点验截图为证;
- **动画类缺陷**(B8 一族)**必须先在真窗口复现并定位到具体控件**,再修、再验;
  未定位前不得声称已修(承接前置决议 D7)。

**E1(D2 思考落盘)**

1. 跑完一次**包含模型思考**的真实运行后,`trace.jsonl` 中对应 `llm_call` 的
   `response_data` 含非空 `reasoning` 键。证据形式为**该文件的实际内容**,
   不接受「代码里读了参数」这类上游断言(与前置决议判据 6 同一口径:只认盘上成品)。
2. B2 那种「`content` 长度 0、模型思考后直接调工具」的调用,其思考全文可**仅从 `trace.jsonl`** 读出。

**E3(D4 机器自述)**

3. D4 清单中的每一台机器,构造出它「做了影响执行的决定」的情形后,
   事件流中出现对应语义事件,`message` 是完整句子;
   `md2json` 的事件写明解析结论、schema 校验结果、`repaired` 时修了什么。
4. **防噪音反向判据**:一次纯透传的运行(无修复、无拦截、无注入、无吞错)
   不因本决议新增任何事件。
5. `ValidationFailEvent` / `ValidationPassEvent` 带「按哪份 schema 检查了什么」。
6. 三条引擎门禁全绿:`uv run ruff check packages/graph-agent` ·
   `uv run mypy --strict packages/graph-agent/src` · `uv run pytest packages/graph-agent/tests`。

**M1+M2(D3 折叠原语 + D1 子条目)**

7. `components/ui/folded-text` 存在且为唯一折叠实现;
   `TraceStepRow.tsx` 的 `PromptSections` 四段容器与 `LiveOutput` 无界渲染 grep 为 0 命中;
   长文本三态(收起 5 行 / 展开 20 行 / Monaco 全文)真机点验各截一图。
8. 展开的 LLM 步骤子条目顺序为「装载 prompt → 渲染后 prompt → 思考 → 回答 / 工具 →
   设置 / 路由判定」,与该步骤的执行顺序一致;agent phase 内按 Iteration 分层;真机截图为证。

**M3(D7 状态投影 SSOT)**

9. 取消一次、跑失败一次真实 run:终态之后画布节点、trace 步骤行、顶条徽章
   **无任何 running 残留**,真机截图为证;修复报告写明它原本坏在哪一层(先复现定位,后修)。
10. 每个消费组件的「状态 → 显示效果」对照表在册,且有测试锁住;
    B8 的两处旧推导(`node-status.ts` 独立分支、`buildTraceSteps` 独立分支)收编进
    run-status-projection,不残留第二份推导逻辑。

**M4(D5 边步骤 + D6 选中即范围 + D8 一致性)**

11. 点 edge 中点:显示上一 `phase_end` 到下一 `phase_start` 之间的边操作事件
    (`blackboard_reduce` / `input_dispatch` / `input_file_injected` / `artifact_saved`),
    样式与节点步骤行一致;`EdgeContextView` 的语义展示部分退役,`EdgeTamperEditor` 仍可用。
12. 依次选中节点、边、Input、Output、空白:trace 范围随选中收窄,
    面板头部显示当前范围并可一键清除,点空白回到全量;真机点验各态。
13. Input/Output 与 phase 节点消费同一共享样式模块(基础卡片 / 状态胶囊 / 连线);
    `GlobalInputOutputNode` 的裸卡片副本 0 命中;单击 = 选中、双击才进 I/O 面板
    (`GraphCanvas.tsx:2464-2495` 的单击特判删除)。

**E2(D9 内置工具诊断)**

14. skill 文件声明四个内置名之一 → `compile_skill` 产出 `[F-v3-agent-tool-reserved]` 诊断;
    UI 对被诊断的行挂错误标记;`PropertiesPanel.tsx` 中「鈥?」grep 为 0 命中;三条引擎门禁全绿。

**全局**

15. 每个引擎 PR(E1 / E3 / E2)合并后重建 vendor 快照 + `compileall` 预热 + 重启桌面 app
    (`AGENTS.md`「Workflow Pipeline」第 7 条),**然后**才做该项真机点验 ——
    不重建则点验点到的是冻结快照里的旧引擎,报告即失实。

---

## 4. 明确不做

- **不做列表虚拟化。** 实测单 run 最大 137 行,量级构不成虚拟化的理由;
  且窗口化曾因「末尾事件够不着」被删并留有锁定测试,重新引入等于与那条测试对赌。
- **不做主从双栏详情面板。** 与本文 D1/D3 确立的「子条目内联 + 折叠」路线直接冲突 ——
  同一段内容会同时出现在行内与详情栏两处。
- **不动传输层双通道。** 步骤帧/增量帧分道是前置决议的产物且运转正常;
  本决议的全部改动落在契约(落盘什么)与投影(怎么呈现)两层,传输层行为不变。
- **不给手工同步的两份事件形状加漂移门禁。**
  `docs/graph-agent-gateway/mvp1/13-x-tracing-events-exceptions/mvp1-alignment.md:130`
  已把「网关侧 dataclass 与引擎侧 Pydantic 变体人工保持同步、无门禁报警」记录为
  **被决议接受的代价,不是遗漏**;要不要加形状比对门禁属三模块架构范围,本决议不重开。

---

## 5. 本决议取代/修订的既有记录

| 既有记录 | 处置 |
|---|---|
| `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` D2「画布聚焦不再过滤 Trace,改为滚动定位」(#657 已实施) | **推翻**,本文 D6 取代。前决议的反对理由(不可见、不可关的过滤器)由「过滤绑定可见选中环 + 面板头部显示范围并一键清除」化解;两次裁决及各自前提均在册(B7 + D6) |
| `docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md:158`「自动展开 payload 上限 ~2KB」 | **修订机制部分**,本文 D3 的 5/20 行三态折叠取代字节阈值;同行「默认折叠大块」的**原则不变** |
| `docs/design/2026-08-09-streaming-tracing-architecture-decision.md` D1 不变量(:369-372)在 thinking 通道上的洞 | **补齐**,本文 D2。这不是对 D1 的推翻 —— D1 不变量本身照旧,本文让它在 thinking 通道上第一次成立 |

两份前置决议的其余全部条目 —— 信息架构决议的 D1、D3–D14,流式架构决议的 D1–D10 ——
**保持有效,不受本决议影响**。

`docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md` **不在**哈希锁清单内
(实测 2026-08-13:`docs/studio/mvp1/_audited-ready-hashes.json` 与 engine 侧清单均无
trace/observability 条目),D3 的修订 PR 直接改,无需重钉哈希。

---

## 6. 实施切分

一个 PR 一件事,顺序即 **E1 → E3 → M1+M2 → M3 → M4 → E2**。
顺序由数据依赖决定,不由工期决定:E1 不先行,则每一次带思考的真实运行都在继续**永久丢失**
推理全文(落盘缺的数据无法事后补救,与前置决议 D1 的先后逻辑同源);
E3 先于前端,因为 M1+M2 要渲染的「思考」子条目与机器自述行,数据源正是 E1/E3 的产出 ——
先做前端只能渲染空段。

| PR | 决策 | 内容 | 落点模块 | 必须同步更新的设计源 |
|---|---|---|---|---|
| **E1** | D2 | `_answer_report` 补 `reasoning` 键(先行,改动小,止住正在发生的数据丢失) | engine | `docs/engine/mvp1/` 对应机制档(tracing 落盘契约) |
| **E3** | D4 | 内部机器自述:逐机器语义事件 + validator 事件补 schema 信息(引擎主体) | engine | `docs/engine/mvp1/` 对应机制档(中间件 + 事件契约) |
| **M1+M2** | D3 + D1 | `components/ui/folded-text` 共享原语;LLM 步骤子条目按执行顺序渲染,废四段容器;Iteration 分层 | studio frontend | `02_capabilities/trace-observability/mvp1-alignment.md`(**重钉哈希**) |
| **M3** | D7 | run-status-projection 模块 + 消费组件对照表 + 锁定测试 | studio frontend | `02_capabilities/trace-observability/mvp1-alignment.md`(如改动则重钉哈希) |
| **M4** | D5 + D6 + D8 | 边点 = 边步骤、EdgeContextView 语义部分退役;选中即范围 + 面板头部范围提示;共享样式模块 + 单击/双击语义统一 | studio frontend | `docs/development/FRONTEND_UI_SPEC.md`(D8 通则入规)+ timeline / trace-observability 对应段(如改动则重钉哈希) |
| **E2** | D9 | 诊断码 `[F-v3-agent-tool-reserved]` + UI 错误标记 + 乱码修复 | engine + studio frontend | `docs/engine/mvp1/` 对应机制档(loader 诊断)+ `02_capabilities/compile-lint/mvp1-alignment.md`(如改动则重钉哈希) |

**E1、E3、E2 合并后必须重建 vendor 快照。** 三者都改动 `packages/graph-agent` 源码,
而桌面 app 的 Python sidecar 无论是否 dev 构建,都从冻结的
`apps/studio/tauri/vendor/site-packages` 快照 import `graph_agent`;
不重建则运行中的 app 仍跑旧引擎,新字段被 `extra_forbidden` 拒绝、新事件永不出现。
操作步骤:先关闭运行中的桌面 app(Windows 会锁住 vendor 的 `.pyd`/`.dll`),
再从仓根执行 `uv run python apps/studio/backend/scripts/build_vendor.py` 与 `compileall` 预热,
最后用标准启动器重启。完整规程见 `AGENTS.md`「Workflow Pipeline」第 7 条。
