# MVP1 三模块接口设计与修改（2026-06-11）

> 状态：独立工作包。用于三模块 PM 分派、Kiro spec 编写、Gemini 实施提示词编写和 Codex 复审。  
> 来源：`temp/productization-mvp1-backwrite-draft-2026-06-11.md`、`temp/productization-mvp1-interface-implementation-plan-2026-06-11.md`、`temp/productization-mvp1-error-enumeration-2026-06-11.md`。  
> 约束：本文档不直接修改 `docs/{engine,graph-agent-gateway,studio}/mvp1/` 下的 FROZEN 权威文档。

## 文件

| 文件 | 用途 |
|---|---|
| `01-design.md` | MVP1 三模块接口设计与错误范围。 |
| `02-implementation-plan.md` | 总实施计划：四步、RED/GREEN、错误族、批次和门禁。 |
| `pm-engine-work-order.md` | Engine PM 作业单和 Gemini 实施提示词模板。 |
| `pm-gateway-work-order.md` | Gateway PM 作业单和 Gemini 实施提示词模板。 |
| `pm-studio-work-order.md` | Studio PM 作业单和 Gemini 实施提示词模板。 |

## 三个 PM 的统一作业流程

每个 PM 必须先建立自己的 worktree 和分支。每一步都按同一流程走，不能跳步：

1. PM 只写/改测试，跑出预期 RED。
2. PM 提交 RED 报告给 Codex 审核。
3. Codex 审核通过后，PM 写 Kiro spec `task.md` 和 Gemini 实施提示词 `gemini-prompt.md`。
4. PM 把 Gemini prompt 交给 Gemini 实施。
5. PM 审核 Gemini 的实现结果，确认无误后提交实施报告给 Codex。
6. Codex 复审通过后，PM 才能进入下一步。

## 四步任务定义

每个模块都分四步实施：

| 步骤 | 名称 | 目标 |
|---|---|---|
| Step 1 | 接口定义 RED | 只写/改接口契约测试，证明当前接口缺失或边界不成立。 |
| Step 2 | 接口定义 GREEN | 写 Kiro spec 和 Gemini prompt，由 Gemini 定义接口并完成 owner-side 最小收口。 |
| Step 3 | 功能收口 RED | 只写/改功能迁移与错误范围测试，证明旧路径仍然存在。 |
| Step 4 | 功能收口 GREEN | 写 Kiro spec 和 Gemini prompt，由 Gemini 把功能收到接口后面并修复本地模拟远端错误。 |

## 不可违反的规则

- 每个 runtime 错误必须有专属 RED 断言和专属 `error_code`。
- GREEN 前必须先 RED；RED 报告未经 Codex 审核不得进入实现。
- `GREEN-2` 不能 fake。唯一例外是 Engine 定义 `LLMProvider` SPI 时允许 contract fake，因为真实实现归 Gateway。
- 只允许硬失败或显式降级，禁止静默降级。
- dev/prod 分层只用于“按 hash 取不到”的完整性场景。
- 本地模拟远端范围现在做：HTTP loopback、多 worker、共用存储。
- 真多机范围现在只留接口位：时钟漂移、真网络分区、跨节点配额。
