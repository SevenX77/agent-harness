# Trace 长文本呈现改判:固定高度文本井(2026-08-14)

状态:已批准(用户 2026-08-14 裁决原话,见 §1)。本文取代
`docs/design/2026-08-13-trace-goes-glass-box-decision.md` 的 **D3**(5 行/20 行/Monaco
三态折叠)关于长文本呈现机制的全部内容;该文其余决议(D1/D2/D4-D8)不受影响。

## 1. 用户裁决(原话)

> tracing里面长文结果的折叠展开还是很奇怪。首先不要套那么多层容器,第二改成和copilot的
> thinking一样,一个固定高度的scrollarea,把我之前说的5行20行覆盖掉,第三,弹编辑器为什么
> 要自创一个modal?编辑器该怎么出现还是怎么出现啊。

拆成三条:

1. **剥容器**:长文本周围不许套多层视觉容器。
2. **固定高度滚动井**:呈现机制改为与 copilot thinking 同款的固定高度 scrollarea,
   **覆盖(推翻)** 2026-08-13 D3 的「收起 5 行 → 展开 20 行 → Monaco 全文」三态。
3. **全文走正常编辑器**:看全文不许自创 modal;编辑器按它在 app 里平常的方式出现。

## 2. 被推翻的旧裁决(显式记录)

| 旧裁决 | 内容 | 本次处置 |
|---|---|---|
| 2026-08-13 D3 | 长文本按行三态:收起 5 行 / 展开 20 行 / 点链接进 Monaco 只读 **modal** | **整体推翻**:行数档位、按显示行折算(160 列)、Expand/Collapse 控件、自造 Dialog+Monaco 全部删除 |
| 2026-08-09(F9 内)「tracing里面的中间结果不要用一个固定高度的框框住,本来panel就有scroll」 | 中间结果不设固定高度内层滚动 | **就长文本范围推翻**:固定高度滚动井正是新机制。该裁决当时针对的「工具输入 `max-h-32` / payload `max-h-40` 塞在盒中盒里」的形态,其反对的实质(容器嵌套)由本次第 1 条承接 |

「默认折叠大块」的原则(2026-08-09)不变——固定高度井本身就是"折叠":超出井高的部分
不占面板高度,靠井内滚动与编辑器全文入口触达。

## 3. 机制设计

### 3.1 共享原语 `components/ui/text-well.tsx`(TextWell)

- **一个固定高度、溢出即滚的文本井**,样式与 copilot ThinkingBlock 的滚动框同款:
  `max-h-40 overflow-auto whitespace-pre-wrap rounded-sm bg-muted/30 p-2`。
  短文本自然矮于井高,不产生滚动;无任何行数计算、无展开/收起状态。
- `autoFollow`:流式期间自动滚到最底(copilot「thinking 自动往下滚」既有行为,
  `copilot-panel.tsx` ThinkingBlock 的 `scrollTop = scrollHeight` 逻辑收编进原语)。
- 溢出检测(`scrollHeight > clientHeight`)时在井下渲染调用方给的 `overflowAction`
  (trace 用它放「View full text」;copilot 不传)。
- 文本可选中复制(复用 `allowTextSelectionProps`)。
- **双消费**(FRONTEND_UI_SPEC §2.12 共享样式规则:先提共享模块再消费):
  trace 全部长文本 + copilot ThinkingBlock 的滚动框。两处样式今后同源联动。

### 3.2 剥容器

现状是盒中盒:`LLMFlow` 外层 `rounded-md border bg-muted/30 p-2` 卡片盒内,每段
FoldedText 又画一个 `bg-background/80 p-2` 盒。改为**一段文本恰好一个视觉容器**:

- `LLMFlow` / `ToolArguments` / 工具摘要 / `GenericPayload` 的外层卡片盒撤掉,
  只留间距(`space-y-*`);标签(FlowEntry 标题)+ 文本井直接落在步骤行内。
- 井(`TextWell` 的 `pre`)是唯一画背景/圆角的层。

### 3.3 全文入口 = 虚拟只读文档走正常编辑器通路

- `folded-text.tsx` 的自造 Dialog+Monaco modal **删除**。
- 「View full text」调 `onFileOpen({ path, content, title, language, saveEnabled: false })`:
  `Workspace.tsx` `toOpenFile`(:1057)对带 `content` 的请求直接用内容、不读磁盘;
  `saveEnabled: false` 使 `LazyMonacoPanel` 只读、不 lint、不 autosave。
  **这条虚拟只读文档通路已存在并在用**——保存冲突的 View diff(`Workspace.tsx:2052-2071`)
  就是这样打开 remote 版本的。编辑器 overlay 按它平常的方式出现,零新增呈现面。
- 无 workspace 上下文的场合(单元测试渲染)不渲染该入口。

### 3.4 删除清单(no-backward-compat,同一改动内删干净)

- `components/ui/folded-text.tsx` + `folded-text.test.tsx`(foldPlan、
  FOLDED_TEXT_COLLAPSED_LINES/EXPANDED_LINES/WRAP_COLUMNS、Expand/Collapse 控件、
  Dialog+Monaco 全文视图)。
- `TraceStepRow.tsx` 全部 `FoldedText` 引用与相关注释;引用旧原语的测试断言改写。

## 4. 验收判据

1. trace 任一长文本(Rendered prompt / Thinking / Answer / Tool input / 工具结果 /
   Event payload)呈现为一个固定高度滚动井;井内可滚,面板不因它变长;无 Expand/Collapse。
2. 长文本井下出现「View full text」,点击后**编辑器 overlay**(与打开 skill 文件同一面)
   打开只读全文,标题为该段落语义名;无自造 modal。
3. LLM 步骤展开体内无盒中盒:每段文本恰好一层视觉容器。
4. copilot 的 Thought 滚动框与 trace 文本井由同一 `TextWell` 渲染(代码级同源),
   流式时仍自动跟底。
5. `components/ui/folded-text.tsx` 不存在;仓内无 `FoldedText`/`foldPlan` 残留引用。
