# Design: Subagent Integration

> Spec owner: a2 Gemini (designer)
> 配套: [requirements.md](./requirements.md) | [research.md](./research.md)

## 1. 架构概览

Subagent 的运行时链路不再是手写胶水代码, 而是标准的工具回调链路:

```
[ Agent Loop (LLM in mode=skill phase) ]
       │ (1) 决定调用 call_subagent_beat_extractor(inputs=[arg1, arg2, arg3])
       ▼
[ Engine Tool Wrapper ]
   ├─ (2a) Schema Validation (Pydantic 对照 sub-skill input schema)
   ├─ (2b) Informed Retry on schema mismatch (max=10)
   ├─ (2c) Max Depth check (≥1 时报错, 原型期硬限制)
       │ (3) Validation passed
       ▼
[ Concurrency Limiter (semaphore=3, NFR-1) ]
       │ (4) 通过 LangGraph Send API spawn 并发分支
       ▼
   ┌───┼───┐ (5) 并发 invoke 独立的 sub_assembled.graph
   ▼   ▼   ▼
[ Subgraph Node × 3 ]  ←─ 各自独立的 messages=[], 干净 context
       │ (6) 各自跑完返回 data delta
       ▼
[ Engine Aggregator ]
       │ (7) 聚合 N 个 results 成 list 返回给 parent agent
       ▼
[ Agent Loop continues ]  ←─ LLM 看到结果, 决定下一轮再发 3 个 / 还是其他动作
```

## 2. SKILL.md Schema 扩展

为保证对原有体系的非侵入性, **复用 `mode: skill`**, 在 `phase_config` 中追加 `subagents:` 字段:

```yaml
# phases/<phase_id>/SKILL.md 顶层 frontmatter (示例)
---
mode: skill
phase_config:
  tools: [read_file, search_text]
  subagents:
    - name: beat_extractor
      path: subskills/beat_extractor
      description: "Given a raw scene, extracts narrative beats."
    - name: producer_strategy
      path: subskills/producer_strategy
      description: "Score audience pull of a beat sequence."
---
```

Loader 解析后, 会自动动态生成两个具备 Pydantic 校验的 tool: `call_subagent_beat_extractor` 和 `call_subagent_producer_strategy`, 注入当前 phase 的运行时 tools 列表。

**不加 4th mode** — 复用 `mode: skill` 语义。subagent 在 user 视角是 "phase 的随身能力", 不是新概念。

## 3. Dispatcher 模式与 Schema 校验

**强制引擎接管 dispatcher**。PM 无需介入 (FR-1, 拒绝 V1 adaptation 的 beat_dispatcher.py 模式)。

引擎动态生成的 tool 签名 (伪代码):

```python
def call_subagent_beat_extractor(inputs: list[BeatExtractorInput]) -> list[SubagentResult]:
    """
    Args:
        inputs: 批量 input, 每个 input 符合 beat_extractor 的 SKILL.md 声明的 io.inputs schema
                (Pydantic 校验, 错了 informed retry)
                最佳实践: 一次 ≤ 3 个 (engine 限并发, agent loop 自己循环送下一批)
    Returns:
        list of SubagentResult: 每个含子 skill 跑完的 data delta + 状态
    """
    # 1. Depth check (FR-5)
    if RunContext.current.subagent_depth >= 1:
        raise FatalError("Max Depth 1 exceeded: subagent cannot call another subagent")
    # 2. Pydantic Schema validation auto-handled by tool wrapper
    # 3. Concurrency limiter (NFR-1)
    semaphore = asyncio.Semaphore(3)
    # 4. LangGraph Send fan-out, 各自独立 context
    # 5. Aggregate + return
```

如果大模型传了乱七八糟的字段, 引擎底层的 agent executor 拦截并走 informed retry 流程, 上限默认 10 次 (FR-4)。

## 4. 并发限流与 Batch 策略

遵循 user 5/18 原话:
> "默认上限 3 个并发, 一次性发 3 个一组, 3 个一组, agent loop 自己循环做完所有的"

实施:
- engine 设置并发最大窗口值 = 3 (semaphore)
- engine tool 收到的数组长度如果超过 3, 同时启动并在外侧用 semaphore 节流 (FIFO)
- **不做跨轮 batch 自动切割** — agent loop 自己控制 batch 序列 (例: 100 个 input 自己拆 33 轮 + 1 轮零头)
- 引导 LLM 通过 tool description 明确 hint: "inputs 一次不要超过 3 个"

## 5. Studio Frontend 视觉规范

跨给 apps master 实施 (frontend scope), small change ~0.5 天:

### Canvas 节点
- 声明了 subagent 的 `mode: skill` phase 节点: 顶部 metadata 区域加一枚 **"Toolbox" 小 badge** (区别于无 subagent 的普通 skill phase)
- 不影响节点主样式 / 不影响双击行为 (双击仍 nav 到当前 phase 的 SKILL.md)

### Properties Tab (sidebar 右侧)
- 选中带 subagent 的 phase 节点时, 现有 Properties 渲染基础上, 在 `Tools` 列表下方新增一栏 `Subagents`
- 每条 subagent 显示 `name | description`, 各项可 click → trigger `canvas:open-phase-file` event nav 到 sub-skill 的 SKILL.md (复用现有 R3 的 sidebar tab routing)

### AssetsPanel
- 不变 — AssetsPanel 只展示物理目录, 不展示动态 subagent 关系

## 6. 实施 Phase 划分 (high-level, tasks.md 细节由 a1 写)

| Phase | 范畴 | Owner | 工作量 |
|---|---|---|---|
| Phase 1 — Engine Core | SKILL.md parser 扩展 `subagents:` 字段 + Pydantic Schema validation 框架 + `call_subagent` 动态构造 | a1 (backend) | ~1 day |
| Phase 2 — Executor | LangGraph Send fan-out + Concurrency Limiter (semaphore=3) + Max Depth check + 复用 `_subgraph_node` 底层 | a1 (backend) | ~1 day |
| Phase 3 — Frontend Badge & Properties | Canvas Toolbox badge + Properties Tab Subagents 列表 + click nav | apps master (frontend) | ~0.5 day |
| Phase 4 — Validation | PM (user) 用 adaptation_v1_sandbox 重新调成 V2.1 layout, 作 subagent 标杆 fixture | user | TBD |

总 engine + frontend: ~2.5 day. user phase 4 调 fixture 长度由 user 自定。

## 7. 风险与已知 Trade-off

| 风险 | 影响 | 缓解 |
|---|---|---|
| **Max Depth = 1 限制** | 未来真实业务可能需要更深嵌套 (如长篇写作场景层层拆分) | 原型期硬锁, 解锁需配套严格 token 预警体系, 留 Phase ≥ 2 spec 议题 |
| **`parallel_map` 语法糖纠结** | user 觉得业务与调用无关, 引擎内置即可 | **默认只提供 `call_subagent`** (具名 + 描述清晰, LLM 调用冲动强). 不提供裸 `parallel_map` 避免歧义 |
| **informed retry max=10 仍 stuck** | LLM 反复传错对不上, 10 次都失败 | task fail, log 完整 LLM/engine 交互供 user 诊断 (NFR-3 trace ID 关联) |
| **Pydantic schema 推导失败** | sub-skill SKILL.md 的 io.inputs 没写或写错, engine 拿不到 schema | loader 编译期 fatal error, 阻止 skill load (skill 必须声明完整 input schema 才可作 subagent target) |
| **并发数 3 不够 / 太多** | 实战可能需要调整 | 留 config 字段 (NFR-1 默认值, 可在 graph_agent 配置 override) |
