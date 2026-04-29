# 大厂双审整合 (Task #13, 2026-04-29)

> 主控整合 a1 (codex 工程基线) + a2 (gemini 架构师) 的大厂 1.0.0 出货标准审核. 用户铁律: "**最终 Gemini 和 codex 按照大厂成熟产品审核**".

## 审核背景

阶段 1+2+3 已 ship (8 commits since baseline `5decd0a`):
- `2348a7f` Phase 1 audits + 工程卫生 7 件
- `964aa7b` Phase 2 启动 (A4 + design v2)
- `acf8d97` A1 砍 schema is None + SkillCompileError + validator list 契约
- `61dd53f` A3 code-only dict 静默丢弃修 + reserved key 顺序契约
- `dd6fa6a` A2 phase_executor 切轨新管道 + schema-less LLM legacy fallback (4 轮 iterative)
- `5a1a9a8` mypy strict 全库 0 errors (Task #11)
- `9652627` ruff 0 errors (Task #12)

当前指标:
- pytest 912 passed, 0 failed, 2 skipped (真 LLM smoke skipped-by-design)
- mypy strict src/ → Success: no issues found in 86 source files
- ruff check src/ tests/ → All checks passed!
- 覆盖率 73.25%

## 双审总评

| 视角 | Reviewer | 总评 | 主要硬伤 |
|------|----------|------|---------|
| 工程基线 | a1 (codex GPT-5.5) | **6.7/10** | CI 门禁局部 / License 冲突 / README 过期 / 覆盖率 / 依赖安全 |
| 架构设计 | a2 (gemini 3.1 Pro) | **6.2/10** | phase_executor God Class (1182 行) / 双系统并行 / 真 LLM e2e 缺失 |

**双审一致结论**: 当前**未达大厂 1.0.0 出货标准**, 必须修复 must-fix 后才能 ship.

## a1 工程审 8 维度评分

| 维度 | 评分 | 关键问题 |
|------|------|---------|
| 1. 类型安全 | 8/10 | mypy 0 errors ✓, Any/type:ignore 集中边界可推 v1.1 |
| 2. 错误处理 | 8/10 | 关键路径已 raise/retry/log, 业务错误带上下文 |
| 3. 测试质量 | 6.5/10 | 912 passed 但覆盖率 73.25% < 大厂 80%; 低覆盖模块: factory 17% / parallel_map 13% / synthesize_speech 22% |
| 4. 日志可观测 | 7.5/10 | decision=... 风格日志可追踪, 缺统一 logging.md 标准 |
| 5. 配置管理 | 6.5/10 | **LICENSE Apache-2.0 vs pyproject.toml MIT 冲突** |
| 6. 文档与 API | 5.5/10 | **README 仍写 5.7/10 / 不可生产 / e2e 跑不通**; Public API 边界靠目录约定 |
| 7. 依赖安全 | 5.5/10 | 无 lock/hash/SBOM/CVE audit/Dependabot/CodeQL |
| 8. CI/CD 门禁 | 4/10 | **CI 只 gate 3 文件, coverage 65%** |

## a2 设计审 8 维度评分

| 维度 | 评分 | 关键问题 |
|------|------|---------|
| 1. 接口契约 | 7.5/10 | A1+A2 强类型大幅提升; 中间件间隐式 key 依赖 (_metrics, business_data_md) |
| 2. 模块边界 | **4.0/10** | **phase_executor.py 1182 行 God Class** (LLM 组装 + Code 工具 + Agent 创建 + Middleware 挂载全揉) |
| 3. 拓展性 | 6.5/10 | SKILL.md DSL 友好; 缺 Plugin 机制, 新 phase 类型要改核心引擎 |
| 4. 一致性 / DRY | 6.0/10 | A2 v5 Strategy A 导致 ValidationMiddleware/CognitiveFlow 逻辑重叠 (finish_task 拦截/错误前缀/部分 schema) |
| 5. 可观测性 SRE | 5.5/10 | 缺 OpenTelemetry Span/TraceID; 缺 Metric 暴露 (P99 / 重试率) |
| 6. 测试设计 | 6.5/10 | 912 unit/smoke 好, 真 LLM e2e 缺失严重 (mock 掩盖真实大模型边界) |
| 7. 文档 (架构) | 8.5/10 | docs/v1-reset/ + .kiro/specs/ 极优; 缺最终用户架构图 |
| 8. 双系统清理路径 | 5.0/10 | A2 v5 Strategy A "留给明天", v1.1+ 修 4 SKILL 计划只在文档没代码层 Warning 熔断 |

## 整合 must-fix 列表 (大厂 1.0.0 hard fail, ship 前必修)

### a1 工程基线 must-fix (5 条)

#### M1: CI 门禁全库化 (a1 维度 8 4/10)
- 现状: `.github/workflows/ci.yml:20` 只对 3 个 core 文件跑 ruff/mypy/format
- 修法: CI 全量 `ruff check src/ tests/` + 全量 `mypy src/` + 全量 `pytest` + 合理 coverage gate (≥ 73% 现状或更高)
- 影响: 防回归核心机制

#### M2: License 元数据冲突 (a1 维度 5)
- 现状: `LICENSE` Apache-2.0 vs `pyproject.toml:6` `license = { text = "MIT" }`
- 修法: 统一改 pyproject.toml 为 Apache-2.0 + classifier 同步 + README 表述
- 影响: 发布合规阻塞

#### M3: README 严重过期 (a1 维度 6)
- 现状: `README.md:51` 仍写 "Phase 1 / 0.x / 请勿用于生产 / e2e 跑不通 / 质量 5.7/10"
- 实际: Phase 3 ship 状态, mypy 0, ruff 0, pytest 912, 覆盖率 73.25%
- 修法: 重写 README 反映当前真实状态
- 影响: 1.0.0 对外发布物错误

#### M4: 覆盖率治理 (a1 维度 3)
- 现状: 73.25%, 但低覆盖模块: factory 17% / parallel_map 13% / synthesize_speech 22% / providers 39%
- 修法: 关键路径覆盖至 80%+, 或建立风险分层门禁 (核心模块 90%, 边界模块 50% 等)
- 影响: ship 后线上 incident 风险

#### M5: 依赖安全门禁 (a1 维度 7)
- 现状: 无 lock/hash/SBOM/pip-audit/OSV/Dependabot
- 修法: CI 加 CVE audit step (pip-audit), 加 Dependabot 配置, 出 SBOM, 锁 hash
- 影响: 供应链安全合规

### a2 架构设计 must-fix (3 条)

#### M6: phase_executor God Class 拆解 (a2 维度 2 4/10)
- 现状: `phase_executor.py` 1182 行, LLM 组装 + Code 工具 + Agent 创建 + Middleware 挂载全揉
- 修法: 多态节点架构 (LLMPhaseNode / LogicPhaseNode 等), 依赖解析 / Agent 构建 / 状态合并完全拆分到独立子类
- 影响: 1.0.0 后维护性 / 拓展性 / 测试性

#### M7: 终结 ValidationMiddleware 双系统 (a2 维度 8 5/10)
- 现状: A2 v5 Strategy A 走 legacy ValidationMiddleware fallback (schema-less + dynamic schema)
- 修法: v1.0.0 前完成 4 个 live SKILL (event-extraction aggregate/review, batch-analysis, global-synthesis) 的 raw_output / free_text 类型抽象 + 彻底删旧 VM
- 影响: 不允许带两套互相重叠的数据流引擎发布 1.0.0

#### M8: 真实 LLM e2e CI (a2 维度 6 6.5/10, a1 同方向)
- 现状: test_mvp1_smoke skipped-by-design (无 OPENAI_API_KEY/ANTHROPIC_API_KEY/GEMINI_API_KEY)
- 修法: 真实 API 或拟真高可用 Mock Server (恶劣 JSON 输出模拟), 跑通完整多 Phase SKILL 流程
- 影响: Validator 和 CognitiveFlow 在真 LLM 边界下不可信

## 应改进 (推 v1.1+, 不阻塞 ship)

### a1 推 v1.1+
1. 收敛动态边界 Any / type: ignore (LangChain / LLM provider / dynamic schema), 补 Protocol / TypedDict
2. 退役 dynamic schema fallback (跟 M7 长期方向)
3. 补统一 logging.md (key=value / level / 敏感信息红线)
4. 建立 public/internal API 文档

### a2 推 v1.1+
1. OpenTelemetry Context Propagation 替换 Callback 桥接, 直接对接 Datadog/Jaeger
2. Rust 借用检查器式静态依赖验证 (编译期校验 context_mapping 上下游)
3. Plugin 架构 + IoC 容器化, 真正"引擎-协议-业务"三层解耦

## Task #14 iterative 闭环计划

按用户铁律 (不打补丁, a2 重出 design + 重走流程), 8 条 must-fix 分组处理:

### Group 1: 工程类 fix (a1 主笔)
- M2 License 冲突 (1 行修)
- M3 README 重写
- M1 CI 门禁全库化 (改 .github/workflows/ci.yml)
- M5 依赖安全门禁 (加 Dependabot + pip-audit step)

a1 实施 + 主控 commit. 不需要 a2 design (这是配置 / 文档级 fix, 不动业务架构).

### Group 2: 架构 design fix (a2 design + a3 实施 + a1 review)
- M6 phase_executor God Class 拆解 — 大架构改, **派 a2 出 PHASE3_DESIGN.md** (新建文件)
- M7 终结 ValidationMiddleware 双系统 — 修 4 SKILL + 删 VM, **派 a2 出 design 修 SKILL.md + remove plan**

### Group 3: 测试增强 (a1 + a2 协作)
- M4 覆盖率治理 — a1 加 test 提覆盖率 + a2 review 测试设计合理性
- M8 真实 LLM e2e CI — a2 设计 mock server 或 fixture, a1 实施集成测试

预估总工作量: 5-10 小时 (取决于 M6 God Class 拆的细节).

## 决断 (主控建议)

- **Group 1 + Group 3 大部分可在 v1.0.0 出货前修完** (~3-5 小时)
- **Group 2 (M6 + M7) 是大改, 是否推 v1.0.5 / v1.1.0 由用户决定**
- 否则 v1.0.0 ship 时 must-fix 不全修, 是技术债认领 + 文档 disclaimers 处理

由用户决断 ship 路径:
- **路径 A (彻底 1.0.0)**: 修 8 条全部, 推 1.0.0 出货 1-2 周
- **路径 B (0.9.0 RC)**: 修 Group 1 + Group 3, Group 2 推 1.1.0; 1.0.0 标 RC (release candidate) 或 0.9.0
- **路径 C (现状 ship 含 disclaimers)**: 不改, ship 1.0.0-pre / 0.x.x, README 写明 must-fix 待 v1.1+

主控倾向 **路径 B** (RC 是务实 ship 路径, 大架构改不阻塞短期发布, 长期路标清晰).
