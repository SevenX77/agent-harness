# 决议:Trace 呈现层重做 + predict 事件流补齐(2026-08-08)

状态:已批准(PM 2026-08-08 口头批准第 1 项方案并要求第 2/3 项重做)
范围:studio backend `run_manager` 流式契约 + studio frontend Trace/Full Trace 呈现层
前置决议:`docs/design/2026-08-07-timeline-viewed-run-and-trace-ui-decision.md`(viewed-run 模型)

---

## 1. 背景:五个已坐实的缺陷

前一轮(PR #636)把"看哪一次 run"变成显式状态后,点验暴露出五个缺陷。每一条都有实测或代码坐标,不是推断。

### B1. predict 的实时事件流永远为空

predict 的实时事件只存在于一条**临时内存 record** 里:
`app/services/predictor.py:104-111` 建(`register_transient_predict_run`),
`app/services/predictor.py:130-132` 的 `finally` 拆(`_finish_predict_event_stream`),
拆的动作是直接删——`app/services/run_manager.py:1119-1121` `self._runs.pop(run_id, None)`。

record 没了,订阅就报错:`stream_run` 开头 `record = self._runs.get(run_id)`,为 None 时
`raise standard_http_exception("RESUME_CHECKPOINT_NOT_FOUND", ...)`。

实测 A(record 活多久):对真实 sidecar 打一次 predict,`PREDICT done http=200 total=0.320267s`;
同期每秒探一次 `GET /runs` 全部 6ms 正常返回——事件循环没被阻塞,是 predict 本身只有 0.32 秒。

实测 B(迟到的订阅会怎样):predict 结束后对同一 `run_id` 开 WebSocket,得到
`OPEN → ERROR → CLOSE code=1006`,零事件。

因果:临时 record 寿命 ≈ 0.3 秒,而前端必须先收到 gate `started` 事件 → 渲染 TracePanel →
再握手 WebSocket,必然晚于这 0.3 秒。等它连上,record 已被 pop。

同源现象:一次早已完成的**真实 run**(`2026-08-07T11-39-40_a20015ec`)开 WebSocket 同样
`1006`——内存 record 只活在跑它的那个进程里,进程重启后磁盘上躺着完整 trace,WebSocket 侧
却读不到。

### B2. Trace 过滤器占据面板顶部过大面积

`hooks/useTraceFilter.ts:73-80` 把标签定义为"本次 run 里出现过的全部原始枚举值":

```ts
const eventTypes = useMemo(
  () => Array.from(new Set(events.map((event) => event.event_type))).sort(), [events])
const phases = useMemo(
  () => Array.from(new Set(events.map((event) => eventPhase(event)))).sort(), [events])
```

`components/trace/TraceFilter.tsx` 再把它们两行 `flex-wrap` 平铺。17 条事件的小 run 就产出
8 个类型标签 + 4 个 phase 标签 + 标题行 + Clear 行,竖向吃掉四行高度;真实 run 只会更多。

### B3. 事件块之间空隙过大

`components/trace/TraceEventRow.tsx:35` `TRACE_EVENT_ROW_HEIGHT = 128` 是虚拟化用的固定行高,
每个包装 div 又写死 `minHeight: TRACE_EVENT_ROW_HEIGHT`;
`components/trace/VirtualTraceList.tsx` 的行容器**在此之上**再叠一层 `space-y-5`(20px)。
一条普通事件卡片(徽章行 + phase 行 + 消息行 + `p-3`)的自然高度远小于 128px,于是每行凭空
多出几十像素空白,再加 20px 间隙。

### B4. 滚动区域高度算错,末尾内容滚不到

同一处叠加是个确凿的越界 bug,不只是观感问题:

- 滚动容器的高度写死为 `totalHeight: events.length * TRACE_EVENT_ROW_HEIGHT`;
- 实际渲染的行容器是 `absolute` 定位 + `space-y-5`,真实内容高度是
  `n * 128 + (n-1) * 20`,恒大于 `totalHeight`;
- 绝对定位不撑开父级,父级高度被 `style.height` 定死 → **超出的部分落在可滚动范围之外**。

任何一行被展开(`ExpandedPayload`)时行高超过 128px,溢出量进一步放大。

### B5. Full Trace 文档:编辑器外观 + 内容被硬截断

- 外观:`components/MonacoPanel.tsx:73-95` 用 Monaco 编辑器渲染文档,面板里出现行号、代码
  编辑器配色与滚动条,与其余 panel 的呈现语言不一致。
- 内容:`utils/trace-document.ts:30` `const DETAIL_CHAR_BUDGET = 1200`,:50-52 把超出的部分
  换成 `… (N chars total, truncated)` 字符串。截断后**没有任何入口能取回全文**,所以"完整
  trace"名不副实。

---

## 2. 决策

### D1. 完成的 run 从磁盘回放(修 B1)

`RunManager.stream_run` 在内存 record 缺失时,不再直接抛 `RESUME_CHECKPOINT_NOT_FOUND`,
而是查磁盘:`run_metadata.json` 存在即认为这是一次**已完成**的运行,读同目录 `trace.jsonl`
按序推入队列,然后推 `None` 结束。两者都不存在时才抛原来的错误。

依据:磁盘上的账本来就齐了——`record_predict_outcome` 的 docstring 已经写明
"the trace sits unread in the very same directory",说明这个矛盾早被意识到,当时只补了 REST
侧、没补 WebSocket 侧。一处改动同时修好 predict 和"进程重启后老 run 读不到"这两个同源问题。

被否掉的替代方案:延长临时 record 的驻留时间。那是拿超时赌前端握手速度,赌赢也只是把竞态
窗口挪大一点,还要额外引入淘汰策略,属于补丁思维。

### D2. 过滤器改为语义分组 + 单行横向滚动(修 B2)

**类型维度**不再罗列原始枚举,改为固定的 4 个语义桶,由一个权威分类函数
`traceEventCategory(eventType)` 定义:

| 桶 | 含义 | 覆盖的 event_type |
|---|---|---|
| `errors` | 失败 | `internal_error`, `validation_fail` |
| `llm` | 模型交互 | `llm_call`, `prompt_captured`, `llm_fallback` |
| `tools` | 工具执行 | 任何含 `tool` 的类型 |
| `flow` | 流程骨架 | 其余全部(`run_started`/`run_ended`/`phase_start`/`phase_end`/`input_dispatch`/`agent_loop_iteration`/`predict_chain_start` …) |

四个桶**全覆盖且互斥**:任意 event_type 恰好落进一个桶,新增类型自动落入 `flow`,不会漏掉
事件。桶始终全部显示(不随 run 内容增减),用户看到的是稳定的四个开关,而不是随机长度的枚举。

**节点维度**保留真实节点名(那是用户自己画的图,必须逐个可选),但改为**单行横向滚动**,
与 copilot 聊天标签同一手法:不换行、不撑高面板,溢出时横向滑动。

标题行与 Clear 按钮合并进这一行,过滤器整体从四行降到两行。

### D3. 去掉固定行高虚拟化,行高由内容决定(修 B3 + B4)

固定行高虚拟化是 B3 和 B4 的**同一个**成因:它要求"每行多高"这件事被预先猜死,而卡片的真实
高度取决于内容(有没有 token、有没有 model、有没有错误块、有没有展开)。猜高了就到处是空白,
猜低了内容就溢出容器。再叠一层 `space-y-5` 只是让这两种偏差同时发生。

决定:**删除虚拟化,列表按自然流渲染全部事件**。

- 行高由内容决定,不再有 `TRACE_EVENT_ROW_HEIGHT`;行间距只在列表上声明一次(`space-y-1.5`)。
- 滚动容器的高度由内容自然撑开,因此"容器高度 == 内容高度"是构造上成立的,不需要再算。
- 键盘导航与选中滚动改用 `scrollIntoView({ block: 'nearest' })`,不再用 `index × 行高` 估算位置。
- 组件相应更名 `VirtualTraceList` → `TraceEventList`(名字不能继续声称一件它不做的事)。

为什么可以不要虚拟化:MVP1 的 trace 量级是几十到几百条事件,渲染成本可以忽略;单条事件的
体积已经由既有的 payload 预览上限(`TRACE_PAYLOAD_AUTO_EXPAND_BYTES`)挡住。设计源没有对
虚拟化提出任何要求——它是实现手段,不是约束。等真出现万级 trace 再引入按真实高度测量的
虚拟化(那时才有依据选型),现在为它预留复杂度属于 YAGNI。

### D4. Full Trace 改为排版文档,长内容折叠而非截断(修 B5)

- 去掉 Monaco。Full Trace 用与其它 panel 一致的排版视图渲染:节点分组标题 + 逐条状态,
  长 JSON 块用等宽字体呈现在卡片内,但不带行号/编辑器配色/编辑器滚动条。
- 保留设计原意"人能读、轻度格式化(非原始 jsonl)"
  (`docs/studio/mvp1/01_workflows/04_run-and-verify.md:105`),放弃"只读编辑器"这一实现载体
  (同文件 :82)——PM 2026-08-08 明确要求 panel 内不使用编辑器样式。
- 删除 `DETAIL_CHAR_BUDGET` 硬截断。长内容默认折叠到固定高度并显示尺寸,用户点开即得全文;
  "完整 trace"必须真的完整。
- 保留按节点分组与 focus 跳转能力(atom #17):focus 某节点时文档滚动到该节点区块。

### D5. 两个 Trace 面的分工写进 UI(消歧)

设计源已定义两者(`04_run-and-verify.md:82`),但界面上没说清,所以用户会问"有什么区别"。
定义如下,并在 Full Trace 顶部以一句话点明:

- **Trace(Timeline 区域内的视图)**= 交互式事件时间线。可过滤、可搜索、可展开单条、可与画布
  节点联动(link),粒度随 focus 变。用途:**定位**——在几十上百条事件里找到出问题的那一条。
- **Full Trace(独立文档)**= 同一次 run 的**全文**。不过滤、不虚拟化、按节点分组顺序通读,
  长内容可展开到底。用途:**通读与取证**——完整看一遍、复制、翻查任意细节。

两者共读同一份事件缓存(viewed-run 决议),永远描述同一次运行。

---

## 3. 验收判据

1. 桌面 app 点 Predict,Trace 面板在 predict 结束后能显示该次 predict 的全部事件(不再停在
   "Waiting for run events")。
2. 对一次早已完成的 run 开 WebSocket,收到完整事件序列后正常关闭,不再是 `1006`。
3. Trace 过滤器占用不超过两行;类型标签恒为 4 个语义桶;节点标签单行横向滚动不换行。
4. 四个语义桶对任意 event_type 全覆盖且互斥(测试锁住)。
5. 列表渲染出的行数 == 事件数(测试锁住),最后一条事件可以滚到并完整可见;展开任意一行后
   仍可滚到列表底部;行上不存在固定高度。
6. Full Trace 面板内不出现 Monaco 编辑器;长内容可展开到全文,不存在不可恢复的截断。
7. CI 全绿(ruff / mypy×3 / pytest×3 / 前端 lint+typecheck+test+build / pip-audit)。
8. 真机点验:上述每一条都有第一手 DOM 证据或截图。

## 4. 明确不做

- 不做 run_id 概要中间层(仍是 target-design)。
- 不改事件本身的语义、颜色映射与徽章文案——本次只动过滤分桶与排版。
- 不为 `stream_run` 的磁盘回放引入分页/游标续传;一次性读完即可,trace 文件的量级由
  `trace.jsonl` 自身决定。
- 不保留任何旧路径:Monaco 版 Full Trace 与 `DETAIL_CHAR_BUDGET` 直接删除,不留开关。
