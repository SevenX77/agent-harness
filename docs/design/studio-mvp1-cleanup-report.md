# Studio MVP1 Cleanup Report

> 生成日期: 2026-06-05
> 范围: 30个非predict模块baseline/alignment对 + `04_platform/i18n.md`。`02_capabilities/predict/{baseline.md,mvp1-alignment.md}` 仅作gold参考，未修改。

## 清理摘要

- 新建 `docs/studio/mvp1/_migrated-coverage-drift.md`，集中保存旧Coverage/Drift迁移附录。
- 30份baseline的旧迁移附录已移入archive，原位替换为archive锚点链接。
- 30份baseline中仅复述UI/前端/后端表格的 `## API` 与 `## Data Model / State` 已删空移除。
- `04_platform/gateway` 与 `04_platform/llm-copilot-http-api` 的alignment §2已瘦身为gateway SSOT链接 + Studio消费/HTTP壳说明。
- 额外发现并迁移2个alignment旧gaps附录: `02_capabilities/copilot-assist` 与 `04_platform/llm-copilot-http-api`。

## Re-audit 证据

| 项 | 结果 | 证据 |
|---|---|---|
| 1. 结构R4-R8 | PASS | 30对baseline/alignment + i18n检查，frontmatter/units/无lock/binds/§1-§8/测试锚点/交叉引用 fail_count=0 |
| 2. 内容没丢 | PASS | 清理前快照比对: 除计划内迁移、去重、§2瘦身和2个alignment附录迁移外，non_target_diff_fail_count=0 |
| 3. binds_code | PASS | 31份含binds_code文档，145个 `文件:符号`，missing_count=0 |
| 4. gold一致 | PASS | 抽样 `compile-lint`、`canvas`、`settings`、`gateway`、`llm-copilot-http-api` 对比 `predict`，结构一致且无API/Data重复残留；predict diff确认未改 |
| 5. 四层边界 | PASS | `gateway`/`llm-copilot-http-api` §2仅保留SSOT链接和Studio消费/HTTP壳内容，section2_boundary_fail_count=0 |
| 6. 链接 | PASS | archive anchors=30，30个baseline前向链接和archive回链全通；2个alignment附录链接也通 |

## 逐档结果

| 档 | 清理了什么 | 1结构 | 2内容 | 3 binds_code | 4 gold | 5 四层 | 6链接 | 疑点/待人核 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 02_capabilities/compile-lint | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 02_capabilities/conflict-overwrite | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 02_capabilities/copilot-assist | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model；alignment旧gaps迁到archive并留链 | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 02_capabilities/debug-resume | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 02_capabilities/file-editing | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 02_capabilities/golden-eval | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 02_capabilities/graph-authoring | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 02_capabilities/phase-editing | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 02_capabilities/publish | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 02_capabilities/run-execution | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 02_capabilities/skill-workspace | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 02_capabilities/studio-settings | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 02_capabilities/trace-observability | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 03_regions/assets | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 03_regions/canvas | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 03_regions/center-action-bar | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 03_regions/copilot | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 03_regions/editor | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 03_regions/input | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 03_regions/local-history | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 03_regions/properties | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 03_regions/settings | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 03_regions/shell-layout | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 03_regions/timeline | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 03_regions/welcome | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 04_platform/engine | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 04_platform/gateway | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model；alignment §2瘦成gateway SSOT引用+Studio消费说明 | PASS | PASS | PASS | PASS | PASS | PASS | 无 |
| 04_platform/llm-copilot-http-api | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model；alignment §2瘦成gateway SSOT引用+HTTP壳说明；alignment旧gaps迁到archive并留链 | PASS | PASS | PASS | PASS | PASS | PASS | 无 |
| 04_platform/native-fs | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 04_platform/state-engine | baseline旧Coverage/Drift迁到archive并原位留链；删空重复API/Data Model | PASS | PASS | PASS | PASS | N/A | PASS | 无 |
| 04_platform/i18n.md | 未改文档，仅纳入31档re-audit | PASS(单文档platform-note) | PASS(快照确认未改) | PASS | PASS(结构特例) | N/A | PASS | 无 |

## 结论

- 未修改任何源码。
- 未修改 `predict` gold样板。
- 未发现疑似误删、未覆盖或需要人工裁决的点。
- 临时archive仍是迁移期安全网，按prompt约定待对应代码实现并验证无误后再删除。
