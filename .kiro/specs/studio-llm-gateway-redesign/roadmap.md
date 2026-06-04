---
status: Proposed (待用户拍板)
created: 2026-06-02
owner: Studio + Engine (架构/排序 = Claude；实现 = codex/gemini)
relates:
  - ./architecture-direction.md        # 上位 ADR：LLM 全栈远端服务化
  - ./client-layer-decision-record.md  # A' client 层决策 (D1-D3)
  - ./design.md / ./tasks.md           # W0 回归修复 (Req1-4, tasks 1-10)
  - ../../../docs/graph-agent-gateway/mvp1/   # 14 模块 MVP1 文档
---

# LLM Gateway 重设计 — 工作流排序 / Phasing 路线图

> 本文是 **#4 工作流排序**的产出：把所有工作流按依赖排成 Phase A–E，给出每阶段的范围 / 归属文档 / owner / 进入闸 / 交付物。
> 决策与理由（A'、编排/调用分离、base_url、错误分类、D3 边界）见各归属文档；本文只管**先后与依赖**。
> **纪律**：本文是设计/排序产物，不是执行任务。每阶段的细化 tasks 在进入该阶段时再写。

---

## 0. 一句话

五条工作流按依赖排：**#1 边界设计（纯设计）先行** → **W0 回归（已就绪，可并行先落地）** → **W1 A' client 层迁移** → **W2 聚合层（已收敛为轻量）** → **W3 后端迁入 gateway 包（最大，桥接远期远端化 spec）**。`#1` 是 lynchpin：它解 D3 文档缺口、定后续所有边界。

---

## 1. 工作流清单（范围 + 归属 + owner）

| 代号 | 工作流 | 范围（一句话） | 归属文档 | 性质 | owner |
|---|---|---|---|---|---|
| **#1** | 服务边界 + 对外 API 设计 | 定 core vs studio-adapter；定 `packages/graph-agent-gateway` **包级 Python API**（level①）；14 模块打标；写清 API 输入/输出契约 | 本 roadmap + 决策记录 D3 + mvp1 docs | **纯设计** | Claude（架构）→ codex plan-review |
| **W0** | 回归修复 (Req1-4) | save 解耦 / resolver 优雅跳过 / 测试 SSOT 回写 / 远端形状 | design.md + tasks.md（Phase1-3, tasks 1-10，**已就绪未排期**） | 实现 (TDD) | 后端 codex / 前端 gemini |
| **W1** | A' client 层迁移 | 调用层换原生 ChatX（09 改写 + 10 factory 新建 + 11 profiles 新建）；编排外壳**不动** | client-layer-decision-record + mvp1 09/10/11 | 实现 | 后端 codex |
| **W2** | provider 聚合层（**已收敛**） | card = studio **视觉分组投影**；扁平 endpoint 模型不动；至多一个可选展示键 | 待写（studio-adapter 侧） | 实现（轻） | 前端 gemini（+ 可选键 codex） |
| **W3** | LLM 后端迁入 gateway 包 | `apps/studio/.../services/llm_*` → `packages/graph-agent-gateway`；studio 只留 HTTP adapter + 前端 | 待写（#1 产出后） | 实现（大） | 后端 codex |

> **W2 为何收敛**：用户拍板「一张 card 的多 URL = 各自独立 route，角色分别指定，card 只是视觉归类」。现状 registry 已支持（`RoleEntry.fallback_chain` 按 `route_id` 逐个指定，endpoints 已扁平在 `provider_endpoints`）→ 无需 `Provider` 一等实体、无需「resolve 在卡内选择」、无 registry schema 迁移。聚合降级为 studio-adapter 的分组投影。**这取代了 handover #2 早期「resolve 如何在其中选」的框架。**

---

## 2. 依赖关系（为什么这么排）

1. **#1 是 lynchpin（先行，纯设计零落地风险）**：它定义 core/adapter 线 → 决定 W3 迁移边界、W1 的 factory/invocation 公共 API、W2 可选展示键的归属、甚至 W0-Phase3 的 SSOT seam；同时是 **D3 文档缺口**（14 模块缺 core/adapter 标 + API 契约，见校验报告）的**统一解药**——所以 D3 标注随 #1 一起落，不零散补 doc。
2. **#1 与 architecture-direction 对齐**：只设计 **level① 包级 Python API**（D3 明确）；**level② 远端服务 API（REST/gRPC）属远期独立 spec**。但 level① 形状要「可演进为远端服务」，不引反远端债（沿用 ADR §4 决策）。
3. **W0 与 A' 正交**（touch 不同代码）：W0 改 `resolve_role`（编排-role 解析）+ save 路径 + 前端；A' 改 `gateway_chat_model` 的**调用步骤**。低冲突。W0 已有 TDD tasks、修**真实回归**（保存死锁 + 运行期崩溃）、低风险 → 可与 #1 设计**并行先落地**。
4. **W1 A' 依赖 #1** 的调用层 API 边界（09/10/11 公共契约）；进 W1 前先过 **handover §5 去风险闸**。
5. **W2（收敛后）几乎无依赖**：纯 studio-adapter；若需可选展示键，按 #1 的 core/adapter 归属落。轻量、低优先。
6. **W3 完全依赖 #1** 的 core/adapter 线；blast radius 最大；宜最后；是通往**远期远端化 spec** 的桥。

### 关键 seam（同一处代码，避免重复改）
- **save 路径**：W0-task2 改 `_save_roles_with_active_routes`（`routers/llm.py:4726`）↔ **base_url 保存时归一化（F1/模块03）的天然挂载点** → 二者相邻/合并，一次性改 save 路径。
- **测试 SSOT**：W0-Phase3（tasks 6-9）↔ 模块 08 ↔ **核心目标闭环（#5）的地基** → 落点（core 还是 adapter）需 #1/#5 先表态，故 W0-Phase3 宜在该结论后。
- **编排 vs 调用**：W0 改 `resolve_role`；A' 改 `gateway_chat_model` 调用步骤 → 不同处，低冲突。

---

## 3. Phasing（建议）

### Phase A — 边界设计 + 文档收口（纯设计 / 文档，NOW）
- **A1（#1）服务边界 + 包级 API 设计**：core vs studio-adapter（用校验报告已产出的每模块归属）；`packages/graph-agent-gateway` public API 清单（编排 `resolve→route`；调用 `factory + invoke`；registry/credentials 读写）；14 模块打标；写清每个 API 的输入/输出契约。形状对齐 ADR（可演进为远端服务，不引反远端债）。
- **A2（#5）核心目标闭环设计**：确认「探测 → 持久化 → **复用来修正真实调用参数**」完整路径（跨 02 `materialize`→`runtime_settings` 与 08 SSOT）；把模块 08 mvp1 doc 的 **PARTIAL** 缺口补成 COVERED；定义闭环落在 core 还是 adapter（影响 W0-task7 与 W3）。
- **A3（#6）predict 边界**：等 engine 设计师回复后，定 gateway 侧只暴露 `role→route` 的 API（占位，不阻塞 A1/A2）。
- **A4（并行机械修复，文档非代码，Claude 做）**：校验报告里**与 #1 无关**的部分 —— decision-record 引用全体重锚（统一 +18 偏移）；补模块 09 的 F2/F1 覆盖缺口 + bug 根源（空 content→400）描述；修 09/14 源码行号小漂移。（D3 core/adapter 标注随 A1 落，不零散补。）
- **闸**：Phase A 完成 → 发 codex plan-review（CCB）→ 用户拍板 → 进 Phase B。

### Phase B — W0 回归修复（实现，可与 Phase A 末尾并行）
- **B1** W0-Phase1/2（save 解耦 + resolver 优雅跳过）：后端 codex，TDD。可不等 #1。**base_url 保存时归一化在此 seam 一并设计落地**。
- **B2** W0-Phase3（测试 SSOT 回写 + 远端形状）：后端 codex + 前端 gemini；SSOT 落点用 A2 结论。
- **交付**：真实回归（死锁 + 崩溃）修复 + 测试状态后端 SSOT（= 核心目标闭环地基）。

### Phase C — W1 A' client 层迁移（实现）
- **进入闸（handover §5 去风险）**：`classify_exception` 真机验证（401/400/网络错，状态码可分类；ChatX 瞬时重试耗尽后仍可分类）；base_url 每 protocol 规则真机再巩固。
- **C1** 模块10 `RouteChatModelFactory`（新建）+ 模块11 provider-profiles（新建）→ **C2** 模块09 调用层换原生 ChatX（编排外壳不动）。后端 codex。
- **验收**：决策记录 §5 的 7 项确定性单测 + `temp/probe_chatx.py` 5/5（人工冒烟，非 CI 闸）。

### Phase D — W2 聚合层（轻，实现）
- studio-adapter 卡片分组投影；若需可选展示键，按 A1 的 core/adapter 归属落。前端 gemini（+ 可选键 codex）。

### Phase E — W3 LLM 后端迁入 gateway 包（大，实现）
- 按 A1 的 core/adapter 线把 `services/llm_*` 迁入 `packages/graph-agent-gateway`；studio 只留 HTTP adapter + 前端。后端 codex。是通往**远期「远端 LLM 服务」独立 spec** 的桥。

---

## 4. 开放 / 待确认（不阻塞 Phase A 启动）
- **#6 predict**：等 engine 回复（A3）。
- **ADR §6**：roles 是否归「远端 LLM 服务域」（暂按「是」）；近期范围 = ①②③（暂按「是」）。
- **#7 小项**：编排/调用是否抽独立 `RouteInvoker` 类（A' 至少做到 factory；更彻底分离可在 Phase C 内决定）；`mvp0/` 是否也按模块拆（低优先）。

---

## 5. owner / CCB
- 设计 / 排序 / 边界 = Claude（架构/PM）。后端实现 = codex。前端实现 = gemini。
- 每阶段**设计完发 codex plan-review**；实现完 code-review；Git 由 Claude 管。

---

## 6. Gemini 独立审计的建设性输入（2026-06-02，已核实关键项）

> Gemini 对同一批 mvp1 文档做了独立审计（`~/.gemini/antigravity-ide/brain/3d7cea82-.../audit_report.md`）。
> **与我方 14-agent 审计的关系（互补，非冲突）**：双方都确认**文档↔源码保真度高**（路径/类名/函数/源码行号准确，无捏造）。差异处：
> - Gemini「行号完全吻合」是**仅指源码**；它未核对**决策记录交叉引用行号**，故漏了 +18 行系统漂移（D3 本轮插入 ~18 行所致，机械可修）。
> - 我方早先「09/14 FAIL」经复核**判重了**：09 实为 PASS+待补（retry 是 07/09 共享题，07 已覆盖，09 交叉引用即可）；14 实为 PASS+待 D3（已路由到 #1）。**两批文档无硬性内容错误。**

**已亲自核实为真的两项关键发现：**
1. **健康/熔断状态双源、互不连通**（route 可用性 SSOT 问题，喂 #1/#5）：gateway 运行期熔断 = `client_manager._provider_down_cache`（进程内 ClassVar + `monotonic` TTL，重启即失，`client_manager.py:51,340-368`），**从不读写** SQLite；持久层 `SqliteLlmHealthStore`（`llm_health.sqlite`，`llm_health_store.py:26`）只被 studio 的 `materialize_role`/`project_provider_model_state` 消费来门控「哪些 route 进链」。→ 运行期 fallback 用的是另一套进程内 cache。**决策点**：熔断/健康 SSOT 落 core 还是 adapter、两套要不要统一（#1）。注意：这与「能力→runtime_settings 参数修正链」是两条轴。
2. **`probe_import_draft` 是占位桩**（喂 #5）：`routers/llm.py:872-876`，docstring 自陈「real agent probing is handled by a later worker」，仅把 status 改 `probed` 回存，无真实探测。→ 探测→持久化→复用闭环缺真实 probe worker。

**其余建设性项 → Phase A（#1/#5）设计输入：**
- `ModelResolverProtocol.resolve()` 返回 `BaseChatModel`，route-first API 该新增 `resolve_routes()` 还是加包装器（#1/A1 公共 API 形状）。
- `ResolvedRole` 加 `skipped`/`skipped_diagnostics` 诊断字段，让 studio 能追溯哪些 route 被跳过及原因（W0-Phase2 + 可观测性）。
- `snapshot_version` 写入责任未定（`ResolvedRoute` 有字段、resolver 未赋值）（#1/W0，我方审计亦发现）。
- 新 `ProviderProfile`（模块11）vs registry `VerifiedProfile`（已测调用法）命名/职责边界须澄清防混淆（#1/W1，我方审计亦发现）。
- **Ark 运行期 → 原生 ChatX 映射未明**（Volcengine Ark 可能无干净 native ChatX）→ 加入 **Phase C 去风险闸**。
- lint 用 raw vs effective（合并 verified profile）capabilities（#5/#1 设计题，我方审计亦发现）。
- `notable_model_ids` 强依赖 Markdown 三级标题精确匹配 `## 4. Notable Model IDs` → 标题微调静默失效（加守卫，对齐无静默失败铁律）。

**仅佐证我方已有项（无新动作，提升信心）**：base_url 保存归一化挂 `upsert_endpoints`、token-escalation 搬编排层、ChatX 异常分类确定性测试、Copilot 假测试重写、predict 待 engine 后删、拆巨型 `llm.py` + role-save 分流下沉 service。
