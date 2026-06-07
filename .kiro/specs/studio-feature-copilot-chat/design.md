# Design — Studio Copilot Chat

> **阶段**: PM 已解锁 implementation。本 design **仅覆盖 MVP0**(最低限度可用 + 领域感知脑子)。
> **关系**: 本文为 MVP0 取代 `requirement.md` 的 chat-shell 取向(见 §0 重构);brain 场景 → MVP1。
> **日期**: 2026-06-01
> **配套**: 评审发现见 [pm-pending-questions.md](./pm-pending-questions.md)。

---

## 0. 重大重构 (Reframe)

原 `requirement.md` 聚焦 chat-shell(@mention picker、UI pill、safe-write、diff 气泡)。结论:**这些是 commodity**,vscode/cursor/antigravity 已解决,抄即可,不是 Copilot 的差异化价值。

**真正的价值 = Copilot 的领域脑子**:理解用户搭 skill 时的真实场景(搭 graph topology、写 action/tool/agent prompt、compile bug 修复、领域诊断),并按需渐进式披露 engine 知识。

**证据(为何重构)**:
- Copilot 今天的全部"大脑" = 3 行通用 prompt + 一坨 view-context JSON,见 [copilot.py:70-74](../../../apps/studio/backend/app/services/copilot.py) + `build_system_prompt` [:183-198](../../../apps/studio/backend/app/services/copilot.py)。它不知道 skill 是什么、怎么搭、怎么写 prompt、怎么读编译错误。
- 而 engine 知识早已备好却闲置:`docs/engine/mvp0/skill-spec/00-12`(13 份规范)+ `docs/public/SKILL_AUTHORING_PLAYBOOKS.md`(已含场景路由)+ 结构化错误码 `F-v3-*` + 编译 AST。

**优先级**:usable-fast(可抄但是门槛)→ **brain(重点)** → chat-shell(commodity,最后)。

---

## 1. 范围 (Scope)

| 层级 | 内容 | 归属 |
|---|---|---|
| **MVP0(本 design)** | 最低限度可用 + 领域感知知识配置:常驻薄层 + 按需渐进式披露 + SDK 正确配置 | 本 spec |
| **MVP1** | brain 场景细化:场景路由判定、每场景 system prompt 设计、错误码驱动的 bug 修复流程、AST 感知诊断 | 本 spec(后续) |
| **Deferred(抄成熟产品)** | chat-shell:@mention picker、UI pill、safe-write 拦截、diff 气泡 | 本 spec(降级) |
| **他属(不在本 spec)** | 连接 / 路由测试 / 选模型 / 状态持久化 | `studio-llm-gateway-redesign` + `studio-llm-copilot-reconciliation`(已 design+tasks) |
| **独立 P0** | `permission_mode` 安全写(Write/Edit 拦截 + Bash 旁路) | 见 pm-pending-questions §P0-B,本切片不动 |

**保留自原 spec 的部分**:context-resolver 管道(原 REQ-4/5:展开 phase AST / edge / 编译错误)**保留** —— 它是 brain 获取"当前 skill 事实"的输入管道,MVP1 用。

---

## 2. MVP0 需求 (取代 requirement.md 的 chat-shell 取向)

- **R1**:Copilot 拥有 skill 创作领域知识 —— 常驻薄层(总是在)+ 按需全量(用时读)。
- **R2**:知识源**唯一真相** = `docs/engine/mvp0/skill-spec/*` + `SKILL_AUTHORING_PLAYBOOKS.md`,**不复制**到别处(防漂移)。
- **R3**:渐进式披露 —— 按需读取,不把全部规范塞进每轮上下文。
- **R4**:正确使用 SDK `system_prompt`(不再把指令拼进用户消息)。
- **R5(MVP0 收尾,可选)**:in-chat 残差 —— 面板头部显示当前生效模型(原 REQ-9);连接失败给可操作错误卡而非 raw traceback(原 REQ-10);new-chat 重置会话。

---

## 3. 架构:知识三层 + 注入机制

### 3.1 知识分层

| 层 | 内容 | 载体 |
|---|---|---|
| **常驻薄层**(~1 页) | ① `00-FORMAT-GROUND-TRUTH` 浓缩:skill = `GRAPH.md` + `phases/<id>/{LOGIC,SUBGRAPH,SKILL}.md`;双轨制(frontmatter=结构 / body=内容);文件名定类型。② **场景→文档映射表**(抄 `SKILL_AUTHORING_PLAYBOOKS.md` 的 scenario→required_docs)。③ `F-v3-*` 错误码 → 读 `11-error-code-spec` 的指针。 | SDK `system_prompt` 的 `append` |
| **按需层**(全量) | 13 份 `skill-spec/*` + `PLAYBOOKS` 全文。`02` 搭 topology、`05` 写 agent、`11`/`12` compile 规则、`07` @mention…… | 留在磁盘,`Read` on demand |

> **常驻层只放"是什么 + 去哪查"**,不放 compile 规则细则 / 错误码全表 / 文件树细则 —— 否则 token 每轮爆。
> **漂移控制**:常驻薄层是 `00` + PLAYBOOKS 的**浓缩**,存在与源文档漂移的风险 → 薄层尽量短、只写稳定的骨架,细节一律指向 canonical 文档让模型按需读。

### 3.2 注入与发现机制(三件套)

1. **薄层** → SDK `system_prompt = preset(claude_code) + append(薄层)`。继承 Claude Code 的文件编辑/工具调用本能,叠加领域知识(决策 D2)。
2. **全量规范按需加载** → 打包成 **`engine-authoring` 本地 plugin**(SDK `plugins=`),`skills=["engine-authoring"]` 启用。SDK `skills=` 是**上下文过滤器**(只让该 skill 的 name+description 常驻,正文模型判定相关才加载),不是发现机制;发现靠 `plugins=`,**与 cwd 无关**(cwd 是用户 workspace,没有 engine skill)。
3. **规范源文件可达** → `add_dirs=[<docs/engine/mvp0/skill-spec 绝对路径>, <PLAYBOOKS 绝对路径>]`,让 `Read` 够得着**唯一真相源**。`engine-authoring` 的 SKILL.md body 只做"路由",指向这些路径,不复制规范正文。

---

## 4. SDK 配置 (build_options diff)

现状 [build_options:112-132](../../../apps/studio/backend/app/services/copilot.py) 只设 `cwd / permission_mode / allowed_tools / env`,**未设 `system_prompt`**;指令被拼进用户消息 [:361](../../../apps/studio/backend/app/services/copilot.py)。

```python
ClaudeAgentOptions(
    cwd=workspace_dir,
    permission_mode="acceptEdits",            # 安全写是独立 P0,本切片不动
    allowed_tools=_ALLOWED_TOOLS.copy(),
    env=env,
    # —— MVP0 新增 ——
    system_prompt={                            # 用预设+append,替代"拼进用户消息"
        "type": "preset", "preset": "claude_code",
        "append": ENGINE_GUIDE_DIGEST,         # §3.1 常驻薄层
    },
    add_dirs=[str(ENGINE_SPEC_DIR), str(PLAYBOOKS_PATH)],   # 绝对路径,唯一真相源
    skills=["engine-authoring"],               # 上下文过滤:启用该 skill
    plugins=[engine_authoring_plugin],         # cwd 无关地注入 skill(发现机制)
    setting_sources=[],                        # 隔离意图:不误读用户 workspace 的 .claude
                                               #   ⚠ skills= 会自管 setting_sources;两者+plugins= 的交互须 PoC 确认
)
```

**必须同时修(否则 system_prompt 是死的)**:删掉 [:361](../../../apps/studio/backend/app/services/copilot.py) 把 `build_system_prompt` 拼进用户消息的写法 → 改用上面的 `system_prompt`(可缓存、不每轮重发)。`build_system_prompt` 现注入的 view-context JSON 仍可保留为每轮的 situational context(进用户消息或 append),但**领域知识**走 system_prompt。

---

## 5. engine-authoring plugin / skill 打包

- **形态**:随 backend 打包的本地 plugin,含 `skills/engine-authoring/SKILL.md`。
- **SKILL.md**:frontmatter `name: engine-authoring` + `description`(触发条件:用户在搭/改/调 skill — topology、prompt、compile bug);body = §3.1 的场景→文档路由 + 指向 `add_dirs` 下规范的相对/绝对路径。
- **规范正文不进 plugin**:通过 `add_dirs` 指向 `docs/engine/mvp0/skill-spec`(monorepo 单一真相源,无复制无漂移)。
- **部署形态待定**(见 §8 风险):monorepo 内 backend 与 docs 同发 → `add_dirs` 直接指 repo docs;若 backend 独立部署 → 需把规范随 plugin bundle。
- **精确 `SdkPluginConfig` 字段** = 实现阶段细节。

---

## 6. 数据流示例(渐进式披露在跑)

PM:"帮我加一个 summarize phase"
→ `engine-authoring` description 触发(skill listing 命中)
→ 模型按需 `Read` `02-graph-md-spec`(GRAPH.md 拓扑)+ `05-agent-md-spec`(SKILL.md 写法)
→ 编辑 `GRAPH.md` + 新建 `phases/summarize/SKILL.md`
→ `POST /skills/{id}/compile`([skills.py:109](../../../apps/studio/backend/app/routers/skills.py))
→ 若返回 `F-v3-*` 错误,按薄层指针 `Read` `11-error-code-spec` → 定位 `phase_id/field_path` → 给修复
→(改文件落盘的"唯一写入权威"问题见 pm-pending §P0-A,属 chat-shell/safe-write 切片)

---

## 7. 决策记录 (Decisions)

| ID | 决策 | 备选 | 理由 |
|---|---|---|---|
| **D1** | 知识注入 = A(薄层 system_prompt)+ Skill 机制(plugin 渐进式披露) | 全量塞 system_prompt(token 重、不 scale) | 既最低限度可用,又原生按需加载、可扩展 |
| **D2** | `system_prompt` = preset(claude_code)+append,**MVP0 用,跑通后再评估切纯自定义 PM 人设** | 纯自定义 string(要重写编辑纪律,工程量大) | 继承久经考验的文件编辑/工具本能,最快可用;契合"快点能用上 + 抄成熟的" |
| **D3** | usable-fast 的连接/设置面**不在本 spec**,归 gateway-redesign + copilot-reconciliation | 本 spec 收编全量(与已 design+tasks 的 spec 撞车返工) | 避免重复;代码层 `copilot_chat` role 今天已能解析调用 [copilot.py:419-437](../../../apps/studio/backend/app/services/copilot.py) |
| **D4** | chat-shell(mentions/pills/safe-write)降级,抄成熟产品,最后做 | 现在做(原 spec 取向) | commodity,非差异化价值 |
| **D5** | 规范唯一真相源 = repo docs,经 `add_dirs` 可达,不复制 | 复制进 plugin/prompt | 防漂移 |

---

## 8. 验证与风险

### 验证
- **PoC(先行)**:在本 SDK 版本(`.venv/.../claude_agent_sdk` types.py 已确认字段)证实 `system_prompt` preset+append、`add_dirs`、`plugins`+`skills` 真能协同工作 —— 这是 MVP0 唯一的"机制能不能用"风险点。
- **行为验证**:给定一个真实 skill,问"这个 phase 为什么编译失败" → copilot 应能按需读到对应规范并给出基于 ground-truth 的回答(而非通用臆测)。
- **回归**:`system_prompt` 改动不破坏现有流式/工具事件链路。

### 风险 / 未决
1. **`requirement.md` 需重写**对齐本重构(当前仍是 chat-shell 取向)。MVP0 实现前应同步,否则 requirement↔design 矛盾。
2. **plugin 部署形态**(§5):monorepo `add_dirs` 指 repo docs vs 独立部署 bundle —— 取决于 backend 部署拓扑,需 PM/运维确认。
3. **常驻薄层漂移**(§3.1):浓缩版与源文档可能不同步 —— 靠"薄层只写稳定骨架 + 指向 canonical"缓解。
4. **`exclude_dynamic_sections`**:若多用户共享同一 copilot 预设,可加此项让前缀跨用户可缓存(优化项,非 MVP0 必须)。

---

## 9. 不做什么(MVP0 边界守卫)

- 不做 @mention picker / UI pill / safe-write 拦截 / diff 气泡(Deferred)。
- 不动 `permission_mode` / Bash 旁路(独立 P0)。
- 不碰连接/路由测试/选模型 UI(他属)。
- 不做 brain 场景的细化判定逻辑(MVP1)。
