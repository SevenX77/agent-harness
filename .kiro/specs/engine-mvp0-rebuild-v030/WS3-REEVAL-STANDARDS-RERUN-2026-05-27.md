# 引擎工程质量复评 — 标准可追溯重跑 (2026-05-27)

> PM 要求: 再跑一次评分, 并核对之前是否真用了市面通用标准 (ISO/IEC 25010 + CISQ + OpenSSF)。
> 方法: 三方 (a1 工具度量 / a2 ISO 映射 / a3 PM 替身冷审) 重跑, 每个分数强制给「标准追溯链」(对应标准条款 + 合格线 + 引擎实测 + 差距 + 反向验证), 主控亲跑工具复核。
> 对象: packages/graph-agent, stage/engine-v030。引擎代码自上次复评 (2f573fd) **未变** (其间只改文档 + PR-8 废 compat 层仅设计未实施)。

---

## 一、PM 的核对问题: 之前真用了标准吗?

**用了 — 而且这次重跑做了不可反驳的追溯验证。** 三方独立佐证:
- **a1 (工具)**: 追溯到三个标准的**官方文档** (iso25000.com / it-cisq.org / ossf/scorecard checks.md), 每维度点名 ISO 子特性 + CISQ 因子 + OpenSSF check, 并用真实工具 (ruff C90 / mypy --strict / pip-audit) 出数字。
- **a2 (ISO 映射)**: 逐维度核对 ISO 子特性归属 + 砍掉项理由, 并给「标准追溯链框架」本身打 4.5/5, 评价"拒绝了为标准而贴标的坏习惯, file:line+grep 闭环把规范落地成可测试的自动化"。
- **a3 (PM 替身冷审)**: 独立结论 — "三标准确被**实质援引**(ISO 子特性逐维点名、CISQ 圈复杂度实测出具体数字、OpenSSF pip-audit/Dependabot 实跑实查), **非贴标签**; 维度二/三的低分有冷酷工具数字支撑, 未被工程乐观抬高。"

**诚实 caveat (不变)**: 这是把三标准**裁剪适配**成 4 个维度 + 我们自己的「3 合格 / 4 优秀 / 5 world-class」刻度, **不是**逐条跑完整 ISO 25010 八大特性认证。砍掉了对 LLM 引擎不相关的 (ISO 可移植性/兼容性、OpenSSF Fuzzing/签名发布) 并写了理由 (a2 复核: 可移植性"站得住"、兼容性"未来对外 API 时需召回"、Fuzzing"原型期 ROI 过低")。

---

## 二、四维分数 (主控仲裁定稿) + 标准追溯链

| 维度 | 分数 | 上次 | 对应标准 | 合格线 | 引擎实测 |
|---|---|---|---|---|---|
| 一 可靠性与韧性 | **4.0** | 4.0 | ISO Reliability (Fault tolerance / Recoverability) + CISQ 异常/状态恢复 | 无静默失败 + 环检测/超时/重试; 4 分需结构化异常透传 + 外部调用重试降级 | 递归 limit (graph_builder) / max_retries+RetryExhaustedEvent (validation_phase_node) / reference_reader timeout / LLMClient WaveSpeed 3 次退避; 反向验证: 仍有多处 broad except → 不给 5 |
| 二 可维护性 | **3.0** | 3.0 | ISO Maintainability (Analysability/Modifiability/Testability) + CISQ 圈复杂度/死码 | CISQ/ruff C90 圈复杂度 ≤10; F401/F841=0; mypy --strict=0 | ruff 30 个 C901 (最重 execute=44/run=25/_wrap_tool=24); mypy --strict 19 错 (含 module_sandbox 类型不兼容 2 个 PR-5 引入); F401/F841=0; 反向验证: extra="forbid" 等类型骨架健全 → 不低于 3, 但双红 → 不到 4 (踩线地板) |
| 三 安全隔离与供应链 | **3.0** ↓ | 3.5 | ISO Security + CISQ 沙箱 + OpenSSF Vulnerabilities/Dependency-Update/CI | 路径隔离有效; **OpenSSF: 0 已知漏洞 + CI 阻断** | 隔离架构强 (module_sandbox 路径守卫 / read_file allowed_paths / LLMClient lock+close_all); **但真实环境 pip-audit 实测 4 个漏洞** (idna 3.13→3.15 / starlette 1.0.0→1.0.1 / urllib3 2.6.3→2.7.0); 见下 §三 |
| 四 性能效率与可观测 | **3.8** | 3.8 | ISO Performance Efficiency (Time/Resource/Capacity) + CISQ 并发/IO | 异步不卡顿 + 核心 trace 落盘; 4 分需 profiling 证无泄漏 + trace 结构完整 | Trace 双路 JSONL 真落盘 (tracing.py open+write) / 有界并发 (parallel_map ThreadPoolExecutor max_concurrent + asyncio.gather) / LLMClient lock; 缺 profiling/P99/动态背压 → 不到 5 |

**总评 ≈ 3.45 / 5**。引擎"把事情做对"了, 可被信任使用。跟上次唯一实质变化 = 安全 3.5→3.0 (见 §三, 按 OpenSSF 严格化 + 新发现)。

---

## 三、本次重跑额外坐实的真实发现: CI 漏洞扫描器误配置

安全维度三方出现 3.0 (a1) vs 3.5 (a3) 分歧, 根因经主控亲跑两次复核坐实, 是一个**真实的供应链配置缺陷**:

- **a3 / CI 用的命令** `uv tool run pip-audit --skip-editable` → "No known vulnerabilities found" (假 clean)。这正是 CI gate (ci.yml:57) 当前用的命令。
- **a1 / 主控用的环境准确命令** `uv run --with pip-audit pip-audit` → **Found 4 known vulnerabilities** (idna/starlette/urllib3, 均有 fix 版本)。

**根因**: `uv tool run ... --skip-editable` 在隔离工具环境里**重新解析一套全新依赖**来扫, 因此报 clean; 它没有审计项目**实际锁定/安装**的版本。即 **CI 的漏洞门是对着空气扫的, 漏掉了真实环境里的 4 个可修漏洞**。

按 OpenSSF Vulnerabilities check (合格线 = 实际依赖 0 已知漏洞) **严格忠实评分 → 安全 = 3.0**: 既有 4 个未修漏洞, 又有扫描器误配置 (依赖管理实践不达标)。隔离架构本身优秀 (所以不低于 3.0)。

**修复方向 (additive, 低风险)**: ① CI pip-audit 改成审计实际锁定环境 (去掉 `--skip-editable` 或改用 `uv run --with pip-audit`); ② 升 3 个传递依赖 (idna 3.15 / starlette 1.0.1 / urllib3 2.7.0)。

## 四、a3 附带诚实标注 (非本次分数变化, 但记录)

ruff + mypy 在引擎自身锁定工具链 + CI 原命令下当前**均 exit 1 (红)**。任何文档/报告若声称 "CI 三连绿 / ruff·mypy 全绿" 与物理证据冲突。本复评的 3.0 (可维护) / 3.0 (安全) **本就未声称全绿**, 与此一致。
