# Codex 任务：Studio MVP1 retrofit 后清理 + re-audit double-check

承接已完成的 R4–R8 retrofit（见 `docs/design/studio-mvp1-retrofit-report.md`）。retrofit 结构达标、grounding 扎实，但比 gold 样板 `predict` 胖了 3 处 bloat。本任务：**清理这 3 处 + 清理后重新 audit 一轮 double-check。**

## 铁律（全程）
- **不改任何源代码**（decision-3：drift 只在文档里记）。
- **不碰 gold 样板** `02_capabilities/predict/{baseline.md, mvp1-alignment.md}`。
- **不丢内容**：旧 Coverage/Drift **不直接删** —— 移到临时存档 + 链接，**等对应代码真正实现 + 验证无误后再彻底删**（PM 明确要求，这是迁移期安全网）。
- frontmatter / `units` / 测试锚点 已有的正确内容不动。
- gold 格式参考 = `predict` 那一对。

## 范围
30 个轴②模块的 baseline/alignment 对（`02_capabilities/*` 除 predict、`03_regions/*`、`04_platform/{engine,gateway,llm-copilot-http-api,native-fs,state-engine}`）+ `04_platform/i18n.md`。

## 清理项

### ① 迁移保留附录 → 移临时存档 + 链接（**不删**）
每份 baseline 底部的 `### 原 …（迁移保留）` 附录（retrofit 前的 Current Coverage / Known Drift）：
1. **剪切前先核**：附录里的 coverage/drift 是否都已被新结构（`## baseline / alignment 差异（测试锚点）` 表 + 各 `⚠️` drift 行）覆盖。**有未覆盖的，先补进新结构再剪切** —— 别让临时存档成为某条信息的唯一来源。
2. 把附录内容**剪切**到单一临时存档 `docs/studio/mvp1/_migrated-coverage-drift.md`，按模块分节（`## <module 相对路径>`）。
3. 该临时文档顶部写明：`> 临时存档：retrofit 前各 baseline 的旧 Coverage/Drift。**待对应代码实现 + 验证无误后彻底删除。** 现行真相 = 各 baseline 的新结构（测试锚点 + ⚠️ drift 行）；本档仅迁移期安全网。`
4. baseline 里附录原位**替换成一行链接**：`> 旧 Coverage/Drift 暂存 [\`_migrated-coverage-drift.md\`](../../_migrated-coverage-drift.md#<module-anchor>)（迁移期安全网，代码实现验证后删）。`

### ② API / Data Model/State 段去重
每份 baseline 的 `## API` 与 `## Data Model / State` 段：
- 只保留**真正 distinct 的内容**（真实 API 端点契约 / 数据模型形状）。
- 凡只是把 `## 后端功能` / `## 前端逻辑` 的行**再列一遍**的 → 删。
- 整段无 distinct 内容 → **整段删**（参 gold：`predict` 的 API/Data Model 只在有独立内容时才出现）。
- 判据：删完后，该 baseline 内**不再有同一 `文件:符号名` 跨段重复的行**。

### ③ gateway / llm-copilot-http-api §2 内核瘦身
`04_platform/gateway` + `04_platform/llm-copilot-http-api` 的 `## 2. 数据流 / 机制`：
- ③b **公共内核机制**（provider registry / 6 态标准投影 / materialize 编排 / endpoint 标准化 / fallback / route resolution）**瘦成"引用 `docs/graph-agent-gateway/mvp1/` SSOT + 一句 studio 怎么消费"**，**不在 studio 复述内核实现细节**（四层 NON-GOAL：只引用不复制）。
- **保留** ③a 内容：HTTP 壳 / DTO / studio 消费与渲染 / 易失态 drift。
- Owns 行 / §8 / 测试锚点里已正确的"内核归 ③b"表述保持。

## 清理后：re-audit double-check（重点，PM 要求）
清理完，对全部 31 档（含改过的 + i18n）重审，确认**没清坏、没丢东西**：
1. **结构 R4–R8**：每份仍有完整 frontmatter（`units:` list、**无 `lock:`**）/ `binds_*` / 测试锚点 / §1–§8 / 双向引用。
2. **内容没丢（最关键）**：逐档比对清理前后 —— ① 剪走的 Coverage/Drift 已被新结构覆盖、②③ 删的只是重复/内核复述；**没误删 distinct 信息或 `⚠️` drift**。
3. **binds_code**：文件 + 符号仍全部存在（`文件:符号名`，`missing_count=0`）。
4. **gold 一致**：抽 3–5 档与 `predict` 比对，结构/小节一致、无 bloat 残留。
5. **四层**：gateway/llm-copilot §2 确实瘦成引用、不再复述 ③b 内核。
6. **链接**：`_migrated-coverage-drift.md` 的锚点 ↔ baseline 的链接双向通，无死链。

## 交付
原地编辑 + 新建 `docs/studio/mvp1/_migrated-coverage-drift.md` + re-audit 报告 `docs/design/studio-mvp1-cleanup-report.md`（列：每档清了什么、re-audit 6 项结果、任何"疑似误删 / 未覆盖 / 待人核"的点）。**分批做**（capabilities → regions → platform），每批跑完先报一次。
