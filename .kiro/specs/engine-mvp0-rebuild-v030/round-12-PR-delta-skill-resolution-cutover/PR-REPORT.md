---
spec: engine-mvp0-rebuild-v030/round-12-PR-delta-skill-resolution-cutover
phase: PR delta PM report
branch: main working tree
owner: a1 主笔 / a2 spec audit / a3 PM-proxy audit
---

# PR delta Report

## 设计

PR delta 是技能查找系统的硬切换(cutover, 一次性删旧路径并同步测试)。以前引擎同时支持“按技能名查找”和“按相对文件夹查找”, 后续状态隔离、子图调用、Studio 导入都会撞到双轨问题。本轮统一交给技能解析器(skill_resolver, 引擎按技能名找代码路径的查找器): 入口必须传, 子图节点(SUBGRAPH, 一个 skill 嵌套调用另一个 skill)只认技能名, Studio 后端同步迁移。状态隔离留给 gamma2。

## 实现

本轮按 tests-first 推进: 先补 5 组红灯测试, 再完成 5 组源码切换, 同步迁移 Studio 后端 4 个调用点, 并补子图最小验证。a2+a3 复审红灯时抓到 1 个错误码遗漏, a1 补齐后实施; cutover cleanup 又迁移 122 个旧测试。随后完成源码审、docs sync 和 docs 审。δ.1 到 δ.12 已全部完成, 实耗约 1.5 小时。

## 验收

现在引擎所有入口都强制注入技能解析器, 缺失时直接失败, 不再回到旧路径。子 skill、子图、Studio 后端 4 个调用点都走同一套解析器。5 个 resolver 错误码对齐规范, 其中 1 个是当前无主动触发点的保留项。验收结果: graph-agent 984 个通过、Studio backend 350 个通过; 风格检查、类型检查通过; 旧残留扫描 0 命中。

## 开发者参考

Commits:

- 当前 PR delta 变更仍在工作树, 尚待主控统一 commit。
- `cb060fe` feat(v030): PR β — middleware refactor + CognitiveFlow 接管 finish_task / ask_clarification (#93)
- `671f97a` feat(v030): PR γ — Agent AST/loader exit_contract removal + validator + middleware order 契约补丁 (#92)
- `206103f` feat(v030): PR α — Gateway 抽独立 package + LLM Roles Phase 1 data 层 (#91)

Key paths:

- `.kiro/specs/engine-mvp0-rebuild-v030/round-12-PR-delta-skill-resolution-cutover/`
- `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py`
- `packages/graph-agent/src/graph_agent/core/compiler.py`
- `packages/graph-agent/src/graph_agent/core/loader.py`
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`
- `packages/graph-agent/src/graph_agent/core/runner.py`
- `apps/studio/backend/app/services/skill_resolver.py`
- `apps/studio/backend/tests/test_delta_skill_resolver_injection.py`
- `packages/graph-agent/tests/fixtures/v030_skill_registry/`
- `docs/engine/mvp0/skill-resolution/logic-explained.md`
- `docs/engine/mvp0/skill-resolution/mvp0-alignment.md`
- `docs/engine/mvp0/skill-resolution/baseline.md`
