---
spec: engine-mvp0-rebuild-v030/round-10-PR-gamma0-contract-patch
phase: PR gamma0 PM report
branch: feat/pr-gamma0-contract-patch
owner: a1 主笔 / a2 honesty audit / a3 PM-proxy audit
---

# PR gamma0 Report

## 设计

PR gamma0 是 PR alpha 之后、PR beta 之前的一次契约补丁。它解决的不是单个 bug, 而是把后续中间件(任务处理流水线上的一道道工序)改造必须依赖的几条规则先固定住: Agent 不再让作者手写退出契约(就是"什么时候算做完、输出要长什么样"的规则), 输出要求由系统统一注入; validator(业务校验开关)不再表示一段可变的用户代码, 只表示是否启用校验; 中间件顺序不再靠各处约定, 而是提前钉成一份统一顺序表。这样做的目的很直接: 后续实现只需要按同一份规则接线, 不再边实现边猜旧字段还算不算有效。

## 实现

本 PR 已按设计完成。旧的 Agent 退出契约入口被移除, 但旧 Skill 路径没有被顺手大拆, 避免把 gamma0 扩成 legacy cleanup。validator 的含义已收窄成布尔开关, 并补上非布尔输入的失败测试。中间件顺序被固定为后续 beta 要接入的目标顺序, 当前已实现的部分也保持为这个顺序的前缀。a2 审计先抓到一处藏在代码里的写死默认值, 以及 validator 含义不清, 修后 PASS。a3 复审又抓到文档没同步干净、缺一个测试、报告写法问题, 均已修完。

## 验收

现在一个 LLM 阶段收到任务后, 系统不再从作者文本里找退出规则, 而是把统一规则和输出结构放进提示里。模型完成工作时, 后续中间件会按固定顺序处理协议、认知流程、执行控制、追踪、工具错误和循环检测(这六步顺序后续不会乱)。若声明了输出结构, 校验链路按这份结构判断结果; 若启用了业务 validator, 它只按统一的固定方式返回"通过"或"问题说明"。测试方面, gamma0 专项 TDD、graph-agent 全量测试、代码风格检查、类型检查均通过; 两个原本依赖线上配置文件、容易误判的测试, 已改成用独立的测试数据。

## 开发者参考

Commits:

- `c7af5fc` docs(gamma0): kiro spec 4 件套
- `6042fc1` test(gamma0): TDD tests for 5 项必修
- `8145600` feat(gamma0): impl 5 项必修
- `3c48931` fix(gamma0): remove private exit_contract fallback
- `f67f1cf` docs(gamma0): sync skill-spec docs + add validator non-bool test
- `8541f9a` docs(gamma0): fix F8/F9 doc drifts
- `d2aae7e` docs(gamma0): polish PR-REPORT.md per a3 audit
- `4708382` fix(gamma0): decouple 2 yaml tests from production config

Key paths:

- `.kiro/specs/engine-mvp0-rebuild-v030/round-10-PR-gamma0-contract-patch/`
- `packages/graph-agent/src/graph_agent/core/`
- `packages/graph-agent/src/graph_agent/cognitive/`
- `packages/graph-agent/src/graph_agent/middleware/`
- `packages/graph-agent/tests/core/`
- `packages/graph-agent/tests/cognitive/`
- `packages/graph-agent/tests/models/`
- `docs/engine/skill-spec/`
- `docs/engine/execution-runtime/`
