---
module: 02-mechanism/05-run-inner/03-cognitive
doc: mvp1-alignment
status: drafted（机制·运行内层;A §2 finish_task/三态/输出/prompt 成段;W 工程决策(§4 已披露);rich 三态接 live=impl 归 kiro）
aligns_with: ../../../00-architecture-overview.md（§3 机制层 B·运行内层）
---

# 03-cognitive — 机制 B · 认知接缝(运行内层)

> **Tier**: 机制层 B · 运行·内层 | **Owns**: system prompt 喂入 · finish_task 显式提交 · 输出解析/patch(md2json + patcher) | **现状**: A 主体迁入;W 原话需补链;rich 三态未接 live | **Related**: `02-middleware`(CognitiveFlow 槽,双向)· `05-exit-control`(退出闸)· `skill-syntax`(模板语法)· `03-assemble`(模板渲染)

## 1. 定义
cognitive = 内层 agent 的**"认知"接缝**:消费 system prompt、`finish_task` 显式提交工具、输出解析(md2json)与修补(patcher)。CognitiveFlow 中间件**实现**在 `02-middleware` 的槽 2,但**逻辑归本域**(双向引用)。

## 2. 数据流 / 机制
- **finish_task = 显式提交工具**(markdown 入参):模型用 tool call 把最终交付物作参数提交,系统再解析+校验,**不降级为 loop 后从末条消息抽取**(交付物边界会歧义)。CognitiveFlow 在 `wrap_tool_call` 截 finish_task / ask_clarification。
- **校验三态分流**(接回 rich `tools/md_to_json.py`,退役简化版 `cognitive/md2json.py`):全合格 → 返回 validated 模型;**结构错** → surgical md-patch(只抽失败的 `##` block 修,patcher 仍受 Pydantic 兜底、不信纯文本);**语义错** → 抛 `SemanticValidationError` 打回主 agent 按业务上下文重生成(**绝不交 patcher 猜值**)。业务规则错由 `CognitiveFlow._run_business_validator`(Pydantic 通过后跑 phase validator)处理,失败返 `[Business]` 前缀。
- **输出格式**:主路径 `md → md2json → schema → patcher`(provider-agnostic 弱模型兜底);provider structured-output 仅作每模型待测优化(必先测弱模型、不过不替换);**yaml 否决**(缩进/标量歧义只是换一种脆弱)。
- **prompt 减负**:exit gate(`05-exit-control`)兜底"必须 finish_task"后,prompt 不再重复恐吓式提醒、只定义一次提交方式,减 token 噪音;frozen V0.3.0 spec 本轮不改,标 V4 解冻待办。

## 3. 接口契约
finish_task 签名 + 校验路由(结构错→REFORMAT / 语义错→…);**成功 finish_task 写 accepted marker,不 `goto=END`**(交 `05-exit-control` 的 after_agent 闸放行,否则绕过退出闸);md2json 输出 = validated business_data。

## 4. 设计决策基础(决策依据)
本模块是**认知接缝机制收口**(finish_task/校验/输出/prompt 四源合并),决策为工程判断:
- **CG1**(显式提交 vs 末条消息抽取):提交工具让交付物边界成模型的显式信号;自由文本抽取无法可靠区分解释/思考/真正 BusinessData。
- **CG2**(成功 finish_task 不 `goto=END`,交 exit gate):04 实证 `goto=END` 会绕过 after_agent 退出闸。
- **CG3**(留 md2json+patcher、structured-output 仅弱模型待测、yaml 否决):md2json 是 provider-agnostic 弱模型兜底,强模型 typed-JSON 能力不能覆盖弱模型实证风险。
> ⚠️ 该 cluster 迁移源(02/03/07/08,2026-06-02)未捕获用户原话;审计标注见 `01-agent-loop` §4。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| CG1 | finish_task 保持显式提交工具 | 提交语义明确可校验,不靠自由文本抽取 |
| CG2 | 成功 finish_task **不 `goto=END`**,写 marker 交 `05-exit-control` | 04 实证 goto=END 绕过退出闸 |
| CG3 | 保留 md2json+patcher;structured-output 仅弱模型待测;yaml 否决 | 现路径稳;弱模型优化不动主路径 |

## 6. 测试关键点
1. 结构错(缺字段)触发 REFORMAT;语义错走对应分流。
2. 成功 finish_task 经 `05-exit-control` after_agent 闸,不静默吐空(D-test)。

## 7. 涉及 region / platform
engine 全权。

## 8. gaps / 待设计
1. 退役 `cognitive/md2json` 与 `tools/md_to_json` 重复(kiro 消重)。
2. structured-output 弱模型路径待测。

## 交叉引用(链接, 不复制)
00-architecture-overview §3 · `02-middleware`(CognitiveFlow 槽,双向)· `05-exit-control`(退出闸,双向)· `01-contract/02-skill-syntax`(模板语法)· `03-assemble`(模板渲染)· 代码现状 `tools/md_to_json.py:515-604`(rich 三态分流)/`middleware/cognitive_flow.py:348-390`(wrap_tool_call 截获)
