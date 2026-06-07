# Codex 任务:Studio MVP1 全量语义审计(FROZEN 前终审 · 逐字读 ×2)

承接:机械硬规则(R2 binds_code grounding / R4 结构+测试锚点 / R5 双向+链接 / R6 / R7 状态 / R8 INDEX 去重)Claude 已脚本 **100% 全量** 验过、全 PASS;`_reorg→workflow` 决策固化已完成(mvp1 零引用 _reorg,决策原话就近 inline 在主场)。

**本任务 = 你逐字读全部 62 档模块文档(每档至少读 2 遍),审 Claude 只能抽样的语义层。** 目标:为逐档 FROZEN 提供不依赖抽样的语义底。

## 规范
审计判据 = `docs/development/design-doc-standards/02-audit-standard.md`(R0–R8 硬规则 / Q1–Q5 质量 / 双轨 / 输出格式 / 铁律)。先读它。

## 范围
`docs/studio/mvp1/` 下 31 个模块的 `baseline.md` + `mvp1-alignment.md` 对(`02_capabilities/*` 含 predict、`03_regions/*`、`04_platform/{engine,gateway,llm-copilot-http-api,native-fs,state-engine}`)+ `04_platform/i18n.md`。共 62+1 档。**每档逐字读 2 遍**(第 2 遍专找第 1 遍漏的)。

## 重点审(语义,不可脚本化)
1. **R0 内容正确**:文档内有无自相矛盾 / 逻辑漏洞 / not-make-sense;跨文档对同一事实有无冲突。
2. **R1 唯一真理**:有无把弃用文档当 SSOT(尤其 `.kiro`、mvp0、已 superseded 的 `_reorg/alignment-notes`);缺的该 🚨 真空,不靠链旧文档充数。
3. **R3 alignment 反映最新决策**:alignment 的「目标」是不是最新拍板决策?有无 stale / 被推翻的旧目标?
   - 比对 SSOT(冲突时):PM 原话/🔒 > 领域 canonical(`01_workflows/00_settings-ux-spec.md` 管 provider 状态机/分层;`docs/engine/mvp1/` 管引擎契约;`docs/graph-agent-gateway/mvp1/` 管 gateway 内核)> workflow 节点文档(决策 SSOT)> 派生/摘要。**workflow 不靠"新"自动赢——若 alignment 有 PM 原话且 workflow 是 AI 派生无明确覆盖,以 PM 原话为准。**
   - **特别核 finality 热点**:`03_compile`/`04_run-and-verify`/`05_debugging`/`06_eval` 4 个 workflow 节点的决策正文——`alignment-notes:300` 记它们截至 2026-06-02 未过 PM(后续 INDEX 记"全 7 节点走查完成"补签)。逐条确认这 4 节点引用到的决策是真 PM 签批,不是 AI 派生未签。
4. **Q1 颗粒度**(对照 gold `02_capabilities/predict`)· **Q2 决策原话**(§4 就近留底)· **Q3 跨模块一致**(顺 `DESIGN_UNITS_INDEX` 的 spans 逐处查)· **Q4 gap/边界**(🚨 真空;实施细节不混进设计)· **Q5 scope**(对 `README.md` 四层 non-goals)。

## 方法(两遍 + loop-until-dry)
- **Pass 1**:逐档读全文 → 列 R0/R1/R3 + Q 的具体发现(每条挂 `文件:符号名`/引用证据)。
- **Pass 2**:重读一遍,专找 Pass 1 漏的(尤其跨文档矛盾、stale 目标);再扫一轮直到一轮零新发现。
- 拿不准"现状是否被新决策推翻" → 核最新决策(`FROZEN` 也可能已废)。

## 铁律
- **不改代码、不改文档**:只产出"审计标注 + 🚨 + 证据";发现的代码债如实记进报告(归 refactor-target),不顺手改。
- **宁可误报、不可漏报**;每条结论必有 `文件:符号名`/引用,不凭印象。
- predict 是 gold 样板:审它但不改。

## 交付
`docs/design/studio-mvp1-semantic-audit-report.md`:逐档(R0/R1/R3 + Q1–Q5 verdict + 🚨 + 修复建议)+ 全局汇总(① FAIL 总清单按优先级 ② 🚨 真空债 ③ 跨模块 drift ④ 锁状态:各档可否进 FROZEN ⑤ finality 热点 03–06 结论)。**分批报**(capabilities → regions → platform),每批先报一次。
