---
module: 01-contract/01-physical-layout
doc: baseline
status: ♻️ mvp0 FROZEN（本域汇总,字段权威在 mvp0）
---

# 01-physical-layout — Baseline(现状 = mvp0 FROZEN)

> 现状 = mvp0 FROZEN 契约,本域不复制、只链接:
> - skill 源码树 + 文件命名 + 文件名→类型推导 → `docs/engine/mvp0/skill-spec/01-physical-layout.md`(FROZEN)
> - `.workspace` 运行时户型 → `docs/engine/mvp0/workspace-spec/baseline.md`
> - 校验入口实证:`packages/graph-agent/src/graph_agent/core/loader.py`(从根向下校验物理结构)、`core/runner.py`(workspace_dir 校验)

mvp1 唯一实质变化(见 mvp1-alignment §5 PL2):golden 落点从"曾拟进 skill 源码"反转回 `.workspace/golden/`。
