---
spec: engine-mvp0-rebuild-v030/round-11-PR-beta-middleware
phase: PR beta PM report
branch: feat/pr-beta-middleware
owner: a1 主笔 / a2 spec audit / a3 PM-proxy audit
---

# PR beta Report

## 设计

PR beta 接在 PR gamma0 后面, 把上一轮固定好的规则真正接进运行流程。之前装配层里散着判断任务是否完成的逻辑, 容易让“装配负责接线”和“运行时负责判断”混在一起。这次改成中间件(任务处理流水线上的一道道工序)统一接管关键判断, 也就是做责任剥离(把判断权从装配层移到专门的运行层)。核心设计是: 模型提交结果后, 先走 schema gate(检查输出结构是否符合声明的关卡), 再进入 validator(业务校验开关)契约; 没声明输出结构的非终结 phase(还不是最终产出的一段任务)继续兼容放行, 避免旧版 V2.1 流程被打断。

## 实现

本 PR 按 tests-first 推进: 先写红灯测试, 再补中间件工厂和 6 层骨架, 然后实现输出结构检查、业务校验契约、装配层接入、提问拦截, 最后把在线路径接到认知流程中间件。当前诚实状态是: 6 层顺序已经固定, 但在线路径只接入认知流程这一层; 其余 5 层已经有占位, 后续再正式接入。a2 做了 spec 对齐验证; a3 抓到旧版兼容回归、空结构兜底和 dormant 路径等问题, a1 已修。文档同步阶段, a2 初稿偏向最终目标态, a1 已重写成当前实现的字段级翻译。

## 验收

现在一个 LLM 阶段完成任务后, 系统先看它有没有声明输出结构。没有声明时直接接受写回, 保持旧版兼容; 有声明时先检查结构, 不合格就把可见错误反馈给模型重试。结构合格后, 已准备好的业务校验契约可以把“通过”或“问题说明”统一回传, 但从 `validator: true` 到具体校验器实例的自动解析留给后续 PR。模型向用户提问时, 有人值守会走人工确认, 无人值守会返回保守降级回复; 普通业务工具不被拦截。验收结果: graph-agent 全套 971 个测试通过、0 失败, 代码风格检查和类型检查均通过。

## 开发者参考

Commits:

- `84957f1` feat(v030): PR β — middleware refactor + CognitiveFlow 接管 finish_task / ask_clarification
- `671f97a` feat(v030): PR γ — Agent AST/loader exit_contract removal + validator + middleware order 契约补丁 (#92)
- `206103f` feat(v030): PR α — Gateway 抽独立 package + LLM Roles Phase 1 data 层 (#91)

Key paths:

- `.kiro/specs/engine-mvp0-rebuild-v030/round-11-PR-beta-middleware/`
- `packages/graph-agent/src/graph_agent/middleware/`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `packages/graph-agent/src/graph_agent/runtime/state_mapper.py`
- `packages/graph-agent/tests/middleware/`
- `docs/engine/mvp0/execution-runtime/logic-explained.md`
- `docs/engine/mvp0/state-and-io-contract/logic-explained.md`
