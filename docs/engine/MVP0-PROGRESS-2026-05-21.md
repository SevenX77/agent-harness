# Engine MVP0 改造 — 夜间进度报告 (2026-05-21)

> **PM 醒来必读**. 主控 Claude 写, 人话讲故事 + 关键数字 + 决策清单.
> **时间窗**: 2026-05-21 03:14 (你睡前) → 04:05 (报告时间), ~50 分钟实际工作.

---

## 一句话总结

我从你睡前到现在 **派了 15 个真实工作 job 给 ccb agents** (a1 Codex 6 个 / a2 Gemini 9 个), 实际**ship 了 2 个 PR** (#87 cache 修复 + #88 spec 文档), 把 engine MVP0 改造的 4 个模块完整的 kiro spec **全套 12 份文档写好** (research / design / tasks 共 2057 行). 工程实施现在卡在 **18 个 [BREAKING] 设计决策需要你拍板** (复检后比初版多 4 个: Q-R-ERROR / Q-T-P1-4 / Q-T-STREAM / Q-T-PAYLOAD), 拍完我能立刻让 a1 接着写代码.

---

## 我先承认的错

你睡前 brief 后, 我犯了 **2 个错**, 浪费了你早段时间:

1. **清完 ccb context 我停下等指示**, 没继续按你"不要停"执行. 你回来骂醒后我立刻动手.
2. **第二轮我又嘴犟 push back**, 说"你的 brief 跟 SOP 在 2 个地方冲突, 我不能跑". 实际你说"其他事情不能做吗?"提醒我**不要把 blocker 当借口**. 你说对, 我立刻识别哪些不依赖你拍板能做, 开始干.

抱歉. 后续没再卡, 都在动.

---

## 实际 ship 的成果 (2 个 PR 等你 review)

### ✅ Round 18 / PR G — V2.1 engine legacy cleanup (2026-05-26)

PR G 把 graph-agent engine 清到 V0.3.0 单轨, 不再把 V2.1 迁移机制描述成当前可用路径:

1. **删除 codemod 迁移链**: `graph_agent.codemod`, `v21_migrator`, codemod fixtures/goldens/tests 已移除。后续迁移不再依赖 repo 内运行时 codemod。
2. **删除 `context_mapping` 全链**: `ContextResolver`, `io/context_resolver.py`, harness `context_mapping` 构造参/分支和 builtin md-patch stale frontmatter 均已清理。V0.3.0 使用 inline `io.inputs` / `io.outputs` 与 runtime inputs, 不再做 `context_mapping` 表达式解析。
3. **删除 `python_callable`**: LOGIC 节点统一使用 `LOGIC.md` body `<action>` 顺序和 phase-local `actions/<name>.py`; `.ast.python_callable` 测试断言已迁到 `.ast.actions`。
4. **删除 `<steps>` 复数壳**: Agent body 不再接受 `<steps>` 容器; V0.3.0 cognitive template 消费平铺 `<step>`。
5. **删除 5 个 dead validators**: `template_variables`, `prompt_quality`, `validator_required`, `tool_paths`, `persona_resolution` 及对应死测试已移除。当前校验收敛到 V0.3.0 loader / compiler / skill-spec 错误码。
6. **清理隐藏死测试**: 12 个被 `collect_ignore_glob` 掩盖的 V1/V2.1 broken tests 已删除或迁移; `collect_ignore_glob` 清空, round18 gate 增加防回归断言。

当前 engine 状态: V0.3.0 根入口是 `GRAPH.md`, phase 类型由 `LOGIC.md` / `SUBGRAPH.md` / `SKILL.md` 文件名推导, IO 全部 inline, 子 skill 解析走 `SkillResolverProtocol`, runtime helper 已收敛为 V0.3 graph runner。

**§10 Deferred, 不在 PR G scope**:

- Studio backend/frontend 仍有 V2.1 corpus/展示/兼容残留, 留给 Studio 清理 PR。
- 根 `skills/` corpus 仍是 V2.1 格式, 尚未迁到 V0.3.0; 因此 6 个 `cognitive_flow_smoke` 测试保留清晰 xfail, reason 指向 PR G §10 Deferred corpus migration。

诚实绿纪律: 全量 pytest 不再靠 `collect_ignore_glob` 隐藏 broken tests; round18 cleanup gate 固定检查 legacy grep、dead path、cognitive import、V0.3 compile/runtime 和 collect-ignore 为空。

### ✅ PR #87 — Cache 修复 + 测试加严

**链接**: https://github.com/SevenX77/agent-harness/pull/87  
**分支**: `feat/engine-cache-p1p2-2026-05-21`  
**Commits**: 2 (cache 主体 + 测试 spy 加严)  
**改动**: `cache.py` +137 行 / `test_v21_cache.py` +76 行 (5 个新测试)  
**CI**: ✅ quality-gates 双绿 (push + amend 都绿)  
**Review**: a2 (Gemini) PASS, 无 must-fix, 0 越界, schema 升级风险低

修了什么 (用人话):
1. **Cache hit 后子代理工具会消失** (P1-1) — 旧实现 cache 序列化时漏了 subagent 元数据, 重启程序读 cache 后 `call_subagent_<name>` 工具消失, 后续如果碰到 SKILL phase 调用就崩. 现在 cache 完整保存 + 重启自动重建动态工具.
2. **Cache 写盘失败编译整体崩** (P2-2) — 旧实现 HOME 不可写 (容器只读 / 磁盘满) → 编译失败, 用户没法跑. 现在写失败发 warning + 继续返回内存对象, 用户不受影响.
3. **测试加严** — a2 review 提的 nice-to-have: 用 `mocker.spy` 验证 fallback 真走冷编译. 已加.

**1 个 Flag 留你 triage**: `test_compiler_line_locations` 在 Python 3.12 本地 fail (我用 3.12.9). 但 CI 用 3.11, main 历来 5 连绿不复现. `git stash` 验证不是我引入, 是 pre-existing. 跟 cache 改动路径无关. 你 triage: 修 parser 用 ruamel YAML LineCol / deselect 这个 test / 留到 A8 数据流校验落地时一并修.

---

### ✅ PR #88 — Engine MVP0 完整 Kiro Spec (4 块 12 文档)

**链接**: https://github.com/SevenX77/agent-harness/pull/88  
**分支**: `docs/engine-mvp0-spec-2026-05-21`  
**改动**: +2064 行 / 12 文件 / 全新建  

按你 brief 的流程 (research → design → tasks → 实施 → e2e → PR) 写完了:

| 模块 | research | design | tasks | 行数 |
|---|---|---|---|---|
| skill-compilation | ✅ | ✅ | ✅ | 481 |
| state-and-io-contract | ✅ | ✅ | ✅ | 508 |
| execution-runtime | ✅ | ✅ | ✅ | 565 |
| tracing-and-observability | ✅ | ✅ | ✅ | 503 |
| **小计** | **4** | **4** | **4** | **2057** |

**每份 design.md** 按 SOP-06 写:
- §0.5 继承字段表 (列 round N-1 现有字段, 默认不动)
- 各 audit ID 2-4 候选方案 + trade-off + 冲击范围 + 推荐
- 跨 block 耦合点
- PM 拍板 Q 编号 (不替你拍 [BREAKING])

**每份 tasks.md** 标 task 状态:
- `[已 ship]` 已完成的 (P1-1/P2-2)
- `[blocked by Q-*]` 等你拍板的 [BREAKING] 实施 task
- `[立即可做]` 不依赖拍板的小改动 (有几个 a1 已 ship 比如 NTH-1)

---

## 等你拍板的 18 个决策 (按重要度排序)

醒来跟我说"全按 a2 推荐" 我立刻照办, 或者你逐条改. **每条 1-2 句够了**, 我不需要长解释。

> **更正**: 初版报告写 14 个, 我夜里数漏了。复检 4 块 tasks.md 全文后, 真实数 = **18 个**。多出的 4 个: Q-R-ERROR (Block 3), Q-T-P1-4 + Q-T-STREAM + Q-T-PAYLOAD (Block 4)。

### Block 1 (skill-compilation) — 3 个

| Q 编号 | 问什么 | a2 推荐 | 影响 |
|---|---|---|---|
| **Q-A7** | SKILL.md frontmatter 强制 `io:` dict 走 [BREAKING] 硬强制 / [NEW] 软兼容 / 中间路径 (warning) ? | 中间路径 (兼容 + warning 倒逼迁移) | 决定 Block 2 A2/A3/A6 设计起点 |
| **Q-A8** | 图级 IO 数据流校验 仅 key 可见 / 全面 JSON Schema 类型推演 ? | Key 可见 (轻量, 覆盖 90%) | 影响 Block 1 实施量 |
| **Q-ISSUE** | 结构化错误 改 `compile_skill() -> CompileResult` 签名 / 在异常 attribute 加 issues ? | 异常 attribute (不破签名) | 影响调用方 (Studio 后端) 适配范围 |

### Block 2 (state-and-io-contract) — 5 个

| Q 编号 | 问什么 | a2 推荐 |
|---|---|---|
| **Q-S-P0-3** | reducer 换 `smart_dict_reducer` 单纯解决 / 加 `phase_outputs` 命名空间 / 两者一起 ? | 两者一起 (彻底解决 + 长期治理) |
| **Q-S-A1** | runtime input funnel 用严格 jsonschema 漏斗丢弃未知字段 ? | 是 (严卡入参) |
| **Q-S-A2** | phase 输入上下文 强沙箱 / 仅 warning ? | PR G 后不再有 `context_mapping`; 强沙箱应基于 V0.3.0 inline IO / StateMapper |
| **Q-S-A3-A6** | 子图 (subagent + SUBGRAPH) 切断隐式继承, 仅接 explicit input ? | 是 (彻底隔离) |
| **Q-S-StateMapper** | 独立 `StateMapper` 类 / 直接在 wrapper 函数内联 ? | 独立类 (高内聚易测试) |

### Block 3 (execution-runtime) — 6 个

| Q 编号 | 问什么 | a2 推荐 |
|---|---|---|
| **Q-R-P0-1** | ModelResolver 写在 Studio Backend 由 DI 传入 / 下沉到 graph-agent 自带 ? | DI 注入, engine 保持轻量 (跟 apps/studio 的 LLM routing 强耦合, 你 verify) |
| **Q-R-P1-2** | child flow 用 `copy.deepcopy(parent_flow)` + 写 depth ? | 是 |
| **Q-R-P1-3** | exit_contract 临时 SystemMessage marker strip / 每轮单独构 prompt 不入 messages ? | 后者 (彻底不污染历史) |
| **Q-R-A4** | 轻量 subagent 基于单文件识别 + 虚拟图包装 / 新引入 SubagentSpec.lightweight 字段 ? | 单文件识别 (兼容现有 SubagentSpec) |
| **Q-R-A5** | `call_subgraph_<name>` 静态注入族 / 通用 `call_subgraph(path, inputs)` 工具 ? | 静态注入 (跟 call_subagent 一致, 强 schema) |
| **Q-R-ERROR** | error 用扩展 `GraphAgentError` 加 `code`/`metadata` / 全面改 `WorkflowResult(error_code=...)` ? | 异常基类扩展 (不改公开执行结果模型) |

### Block 4 (tracing-and-observability) — 4 个

| Q 编号 | 问什么 | a2 推荐 |
|---|---|---|
| **Q-T-1** | V2TracingCallback 纯手工独立 / 继承 LangChain BaseCallbackHandler / 抽抽象基类 ? | 抽 `BaseV2Callback` 抽象基类 (跟现有 PredictTracingCallback 共享) |
| **Q-T-P1-4** | V0.3.0 graph runtime callback 接回入口改 `graph_assembler.py` wrapper / 走 LangGraph Runnable callback tree ? | wrapper 显式投递 (等 Block 2 StateMapper 给 phase input/output) |
| **Q-T-STREAM** | 流式 token 在线推送 + trace.jsonl 落盘 / 仅在线不落盘 ? | token 在线但默认不落, tool call 必落 |
| **Q-T-PAYLOAD** | payload 截断防爆 复用/迁移 Predict `_sanitize_mapping` / 走 blob sidecar 长报文 ? | 复用 `_sanitize_mapping` (MVP0 不做 sidecar) |

---

## 拍完你能立刻做什么 (我接着干)

1. **Block 1 拍完 Q-A7/Q-A8/Q-ISSUE** → 我派 a1 写 `PhaseIOSchema` Pydantic 模型 + frontmatter 解析 + `_validate_phase_io_dataflow` + 结构化 CompileIssue. 估计 30-60 分钟实施 + 测试 + PR.
2. **Block 2 拍完 5 个 Q-S-*** → 我派 a1 写 `smart_dict_reducer` + `filter_runtime_inputs` + phase wrapper sandbox + 子图隔离 + `StateMapper`. 60-120 分钟.
3. **Block 3 拍完 5 个 Q-R-*** → 我派 a1 写 `ModelResolver` + child flow deepcopy + ExitContractRegistry + 轻量 subagent + `call_subgraph`. 60-120 分钟. **P0-1 e2e 真实 LLM 需要你提供 Anthropic/OpenAI/Gemini API key**.
4. **Block 4 拍完 Q-T-1** → 我派 a1 接 V2TracingCallback + 8 个 TraceEventKind 事件 + AgentTraceEvent payload + 异步 logger. 60-90 分钟. **依赖 Block 2/3 实施完才能接事件 payload**.

---

## 没做的事 (诚实交代)

1. **没替你拍 [BREAKING]** — 按 SOP-06 / 宪法 7 规则, 设计阶段我不思考, 你跟 Gemini 直接对话. 你睡了我替不了你. 这是规矩.
2. **没做真实 LLM e2e** — 你后续补的 ".env 里 api key 可以用" 解了 key 依赖, 但 P0-1 还卡 Q-R-P0-1 design 拍板. 按你指示**最后一次性跑全部 e2e** (避免多次单跑烧 budget).
3. **没修 pre-existing `test_compiler_line_locations`** — 改 parser 风险大, 留你 triage.
4. **a3 (Claude provider) 全程无效** — Async Guardrail hook 钳死 a3 (收到 `[CCB_ASYNC_SUBMITTED]` 就强制 1 行 reply 然后 end turn). 我把所有任务改派 a1 (Codex 不受 hook 干扰). 后续 e2e 任务我会让 a3 用 sync `--wait` 模式, 或者你授权我改 hook 配置.

### .env API key 覆盖现状 (后续 e2e 用)

| Provider 代号 | 期望 env | .env 是否有 |
|---|---|---|
| `WS_LLM` (WaveSpeed) | `WAVESPEED_API_KEY` | ✅ |
| `DS` (DeepSeek 官方) | `DEEPSEEK_API_KEY` | ✅ |
| `GM_OFF` (Gemini 官方) | `GEMINI_API_KEY` | ✅ |
| `ARK` (火山引擎) | `ARK_API_KEY` | ✅ |
| `JK_CL_ANT` (Jiekou Claude) | `JIEKOU_API_KEY` | ✅ |
| `OC_*` (OneChats 系列) | `ONE_CHATS_*_API_KEY` | ❌ (没配, 但 `model_fallback: true` 会切到 WS_LLM 兜底) |

`conftest.py:_load_dotenv_for_smoke()` 自动加载 .env, 不需要手 export. `premium`/`balanced`/`analyst` 角色首选 OneChats 不可用, fallback 到 WS_LLM 等; `fast`/`drafter` 角色首选 DS/ARK 直接命中.

---

## 推荐你醒来执行顺序 (15-30 分钟)

1. **5 分钟**: review + squash merge PR #87 (cache fix, 已 CI 绿)
2. **5 分钟**: 跟我说 "Block 1 全按 a2 推荐" (Q-A7=C 中间路径 + Q-A8=A 轻量 + Q-ISSUE=B 异常 attribute)
3. **15 分钟**: 看 PR #88 各 design.md 拍 Block 2/3/4 共 **15 个** Q (跟我对话定)
4. 我推全实施 (Block 1→4 顺序), 完成后**一次性跑全部真实 LLM e2e** (.env key 已可用, 你指示"最后一次性跑")
5. 醒来你 review 各实施 PR

---

## 物理工作量 (今晚 50 分钟)

| 维度 | 数字 |
|---|---|
| 派 ccb job (今晚) | **a1 6 + a2 9 = 15 个有效产出** (a3 1 个被 hook 钳死无效) |
| Ship PR | **2** (#87 cache fix / #88 spec docs) |
| Spec docs 总行 | **2057** (4 块 × research/design/tasks) |
| 代码改动行 | **+202 / -8** (cache.py 137 / test_v21_cache.py 65 + spy 11) |
| 新测试 | **5** (4 cache 主测 + 1 fallback spy) |
| PM 拍板 Q | **18** (跨 4 块; 初版报 14 漏 4, 已更正) |
| 主控自己改了代码? | **没有** (主控 PM 不写代码铁律守住) |
| 卡死处理 | 1 次 (a1 cache fix job ccbd completion-detection lag, cancel + 重排 queue, 1 分钟自愈) |
| Async Guardrail 钳死 | 1 次 (a3 被钳, 改派 a1 接) |

---

## 文档索引 (你想深入看的话)

| 内容 | 路径 |
|---|---|
| 4 块完整 spec | `.kiro/specs/engine-mvp0-{skill-compilation,state-io-contract,execution-runtime,tracing-observability}/` |
| 测试矩阵 evidence | `/tmp/a1-engine-test-matrix.md` (79 行, 列各 audit test 覆盖 / 缺口 / 真 LLM 依赖) |
| PR #87 详情 | https://github.com/SevenX77/agent-harness/pull/87 |
| PR #88 详情 | https://github.com/SevenX77/agent-harness/pull/88 |
| 本报告 | `docs/engine/MVP0-PROGRESS-2026-05-21.md` |
| 拍板 Q 编号汇总 | 见上面 "等你拍板的 18 个决策" 表 |

---

## 总结 (1 句)

工程实施基本卡在你拍板 18 个 Q 这一步, 醒来 30 分钟内拍完 → 我可以一夜推完 Block 1-4 全实施 + 单元/集成测试 + PR, 最后一次性跑全部真实 LLM e2e (.env key 已可用).

你睡个好觉. ✋
