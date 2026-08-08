# 决议:Studio 颜色语言收敛 + Trace 呈现密度重做(2026-08-08)

状态:已批准(PM 2026-08-08 口头批准,原话「开工」)
范围:studio frontend design token + `components/ui/` 共享原语 + Trace 面板 + 画布节点徽章
前置决议:`docs/design/2026-08-08-trace-ui-overhaul-and-predict-stream-decision.md`
**本决议取代**该文件的 **D2**(过滤器改为语义分组 + 单行横向滚动)——见下 §2 D4。

---

## 1. 背景:三个已坐实的缺陷

PM 在真机上看完 Trace 面板后提出六条(颜色太花 / 禁止 indigo 当字色 / filter 占地 /
搜索框被挤没 / 逐元素问必要性 / 节点绿色元素过多)。逐条查证后归并为三个根因,每条都有
实测数或代码坐标。

### B1. `--primary` 当文字色,对比度 1.78:1,低于任何可读门槛

在运行中的桌面 app 里把 token 转成 sRGB 后按 WCAG 2.x 相对亮度公式实测(背景取 `--card`):

| token | 暗色 sRGB | 在 `--card` 上的对比度 |
|---|---|---|
| **`--primary`** | **55, 42, 172** | **1.78 : 1** |
| `--foreground` | 250, 250, 250 | 17.18 : 1 |
| `--muted-foreground` | 161, 161, 161 | 6.94 : 1 |
| `--success` | — | 8.09 : 1 |
| `--warning` | — | 9.39 : 1 |
| `--destructive` | — | 6.21 : 1 |
| `--multimodal-border` | — | 4.77 : 1 |

WCAG AA 正文要求 4.5:1,大字要求 3.0:1。`--primary` 是全套 token 里唯一一个当文字用会
跌破**所有**门槛的——因为它在设计上是**填充色**,配套的是压在它上面的 `--primary-foreground`
(近白)。`--card` 是 `oklch(0.205 0 0)`,`--primary` 是 `oklch(0.398 0.195 277.366)`,
两者亮度只差 0.193,靠色相差撑不出可读性。

全仓 `text-primary`(裸用,不含 `text-primary-foreground`)出现 42 处,其中约 20 处是
"当可读文字用"的误用。误用集中在两个地方:

- **Trace 面板 9 处**:`components/trace/EventTypeBadge.tsx:13`(llm_call 徽章)、
  `components/trace/TraceEventRow.tsx:105`(token chip)/`:176`(Inspect prompt)/`:343`
  (Show full payload)、`components/trace/TraceDocumentPanel.tsx:99`、
  `components/trace/TraceFilter.tsx:52`(`→ <node>` 联动提示)、
  `components/TracePanel.tsx:253`(compare tab 选中态)/`:354`(link 开关)/`:392`(Compare 按钮)。
- **`components/ui/` 共享原语 5 处**:`button.tsx:21` 与 `badge.tsx:25` 的 `variant="link"`、
  `empty.tsx:76` / `field.tsx:137` / `item.tsx:141` 的 `[&>a:hover]:text-primary`。
  这 5 处意味着**全 app 的链接文字**都是这个 1.78 的靛色,而且 hover 之后更不可读。

### B2. 颜色被用来编码"分类",而全 app 其余部分只用颜色编码"严重度"

对照(均为真机观察):

| 界面 | 有颜色的元素 | 颜色在编码什么 |
|---|---|---|
| 画布节点 | 右上角状态胶囊(Idle 中性 / Running 靛 / Success 绿 / Error 红 / Paused 琥珀) | 严重度 |
| Timeline 列表 | 每行一个状态徽章 | 严重度 |
| Settings | 卡片中性,只有 Connected / Test failed 徽章带色 | 严重度 |
| **Trace 面板** | **每一行**的事件类型胶囊 + 左轨圆点 | **事件类型(分类)** |

`components/trace/EventTypeBadge.tsx:5-25` 一个函数里同时用了 `destructive` / `warning` /
`primary` / `success` / `multimodal-border` 五个色族,判据是 `event_type` 字符串。于是一个
40 条事件的正常 run 里,39 条都在抢眼,真正出错的那一条反而不突出——**颜色的信噪比被
稀释到零**。左轨圆点(`TraceEventRow.tsx:72` 的 `eventColor(event.event_type)`)是同一
信息的第二次着色,纯冗余。

画布节点上同样有一处分类着色:`components/nodes/SkillNode.tsx:136` 的绿色 `ShieldCheck`
(golden captured)和 `:148` 的琥珀 `ShieldHalf`(logic-ok)。"有没有基准"是节点的**属性**,
不是"事情好不好",却借用了 success / warning 两个严重度色。结果是一个跑成功的节点上有
两处绿(状态胶囊 + 盾牌),读者无法判断哪一处在说结果。

### B3. 面板顶部 chrome 占 18.8%,搜索框被挤到不可用

真机实测(窗口 1400×900,面板宽 383px):

- 面板总高 **831px**;
- 身份条 **41px** + 搜索/动作/筛选块 **115px** = **156px chrome(18.8%)**;
- 事件列表只拿到 675px。

115px 里的构成与必要性:

- 搜索框与 link 开关、`Resume`、`Compare`、`Golden` 四个按钮**共享一行**。
  Resume/Compare/Golden 是 **run 级动作**,不是列表工具,且多数时候 `disabled`;它们把
  搜索框压到只剩 `Sear` 可见(真机截图 `v8-final-run-trace.png`)。
- 筛选常驻**两行**:4 个语义桶 + `Clear`,再加一行按节点名的 chip。节点 chip 与
  "点画布节点联动"(link 开关 + `→ <node>` 提示)是**同一能力的第二个入口**。
- `Clear` 在无筛选时 `disabled` 常驻,零价值。

另有一处与现有规范直接冲突:每条事件是一个 `rounded-md border` 卡片盒
(`TraceEventRow.tsx:86`),而 `docs/development/FRONTEND_UI_SPEC.md` §2.5 已明写
「面板里的列表行统一复用 `_shared/FileRow` 那套**无边框 ghost 行**…不要给每行套 `border` 盒子」。

事件行还有一处纯重复:第二行渲染 `<NODE> · <message>`,而对 `run_started` /
`input_dispatch` / `agent_loop_iteration` 这类事件,`eventMessage()` 返回的就是
`event_type` 本身,于是第二行与胶囊**逐字相同**(真机可见:胶囊 `input_dispatch`,
下一行 `SETUP · input_dispatch`)。

---

## 2. 决策

### D1. `--primary` 只做填充与描边,永不做文字色

- **规则**:`text-primary`(裸用)在 `apps/studio/frontend/src` 中禁止出现。需要"这里是主色"
  时用**填充**承载:`bg-primary text-primary-foreground`(实心)或 `bg-primary/15 text-foreground`
  (淡底)。`text-primary-foreground` 压在 `bg-primary` 上不受影响,仍是正确用法。
- **例外只有一个**:真正的**可交互文字**(`Button variant="link"`、`Badge variant="link"`、
  行内动作链接、链接 hover)需要一个能读的品牌色 → 新增 token `--link`,
  暴露为 `text-link`。
- `--link` 取与 `--primary` 同色相(277.4)、提亮到在 `--card` 上 **≥4.5:1** 的值,
  保住品牌识别的同时可读。亮色模式取同色相的加深值,同样 ≥4.5:1。
- **理由**:这不是审美取舍,是 B1 的实测数。1.78:1 连大字门槛(3.0)都过不去。

### D2. 颜色只表达严重度,不表达分类

- **规则**:Studio 前端里,颜色(success / warning / destructive / primary)只允许编码
  **事情的好坏程度**;"这是哪一类东西"一律用**文字与排版**表达(等宽字体、字重、分组标题、图标形状)。
- 落到 Trace:
  - 事件类型胶囊 → **中性等宽文字**,不再按 `event_type` 上色;
  - 左轨圆点 → **中性小点**,只有 `internal_error` / `validation_fail`(destructive)和
    `llm_fallback` / 重试(warning)着色;
  - tool 相关的绿(工具图标、`Expand` 按钮、subtree 块边框)→ **中性**;
  - 保留着色的只剩两类:**错误**(destructive)与**降级/重试**(warning)。
- 落到画布节点:`golden captured` 与 `logic-ok` 两个盾牌改为**中性徽章**(形状+tooltip 区分),
  状态胶囊(Idle/Running/Success/Error/Paused)保持现有颜色不动——那才是严重度。
- **理由**:B2。让颜色重新具备信噪比;顺带使 Trace 与画布/Timeline/Settings 说同一种语言。

### D3. 事件行改为无边框 ghost 行,删掉重复信息

- 去掉每行的 `border` 盒,改 `rounded-md border-0 hover:bg-accent`(对齐 UI_SPEC §2.5)。
- 第二行文案与事件类型胶囊**逐字相同时不渲染**(判据:`eventMessage(event) === event.event_type`)。
- 节点名从"每行重复"改为**分组头**:相邻事件属于同一节点时,只在该组第一行上方标一次节点名。
- **理由**:B3 的重复项;行高与视觉噪音同时下降,不牺牲任何信息。

### D4. 顶部重排:搜索独占一行,run 级动作归位,筛选按需出现(取代前决议 D2)

- **搜索框独占整行**,不与任何按钮共享横向空间。
- `Resume` / `Compare(golden)` / `Golden(promote)` / **Open run report** 收进身份条右侧的
  一个 `⋮` 溢出菜单(本地 `DropdownMenu`)。它们是 run 级动作,归属 run 身份而非事件列表。
- 筛选从"常驻两行"改为**按需**:一个 `Filter` 按钮(本地 `Popover`)承载 4 个语义桶 + 节点多选;
  已选条件在按钮旁以 chip 回显,并提供就地清除。**无筛选时该区域高度为 0**。
- `→ <node>` 联动提示并入身份条,改用 `text-muted-foreground`。
- **前决议 D2 作废**:它把节点 chip 从 `flex-wrap` 改成单行横向滚动,解决了"高度随数据增长",
  但没解决"常驻两行本身就是常驻成本"。按不向后兼容原则,直接换掉,不保留旧形态。

### D5. `report.md` 的用户入口

`report.md`(RUN_EXECUTION F6)此前只落在 run 目录里,前端无任何引用。本决议给它一个入口:
身份条 `⋮` 菜单中的 **Open run report**,调用现有 Rust native-fs 的打开能力在系统默认程序里
打开该 run 目录下的 `report.md`。报告本身仍是纯投影,不因为有了入口而变成第四份真相。

---

## 3. 验收判据

因果验证,逐条要有可复核证据:

1. **`text-primary` 裸用在 `apps/studio/frontend/src` 中为 0 处**——由一条 vitest 守卫测试
   扫描源码断言,而不是靠人自觉。
2. **`--link` 在暗色 `--card` 上实测 ≥4.5:1**——由一条 vitest 解析 `index.css` 的 token、
   按 oklch→linear-sRGB→WCAG 相对亮度计算并断言;同一测试同时锁住所有"允许当文字用"的
   token 都 ≥4.5:1。
3. **Trace 一屏内的着色元素只剩错误与降级两类**——真机截图为证:一次全成功的 run,
   事件列表中无绿色、无靛色、无蓝色胶囊。
4. **面板 chrome 高度显著下降**——真机量 `[role=log][aria-label=Trace]` 的子元素高度,
   无筛选状态下 chrome 从 156px 降到 ≤90px。
5. **搜索框独占一行,任何窗口宽度下 placeholder 完整可见**——真机量输入框宽度 + 截图。
6. **画布上一个跑成功且有 golden 的节点,只有一处绿**(状态胶囊)——真机截图。
7. **`⋮` 菜单能打开当前 run 的 `report.md`**——真机点击 + 截图。
8. 前端四道门禁全绿:`npm run lint` / `typecheck` / `test` / `build`。

## 4. 明确不做

- 不动画布本身的配色:靛色流程边、`Compile` 实心主按钮是全局品牌锚点,是正确用法(填充色做填充)。
- 不动 Copilot 面板、Settings 页的信息架构。
- 不引入第二套灰阶或第二个品牌色;`--link` 是 `--primary` 的同色相派生,不是新色族。
- 不为兼容旧样式保留任何开关/变体——按不向后兼容原则,旧路径同轮删干净。

## 5. 交付切分

共享基础设施(design token + `components/ui/` 原语)与局部面板改动分成两个 PR **串行**交付,
避免 UI_SPEC 要求排队的共享文件与局部改动挤在一起:

- **PR-1**:`--link` token + 清理全部 `text-primary` 裸用 + 两条守卫测试 + 规则写回
  `FRONTEND_UI_SPEC.md` §2.2。
- **PR-2**:Trace 面板(D2 事件行着色 / D3 行密度 / D4 顶部重排 / D5 报告入口)+
  画布节点徽章中性化。
