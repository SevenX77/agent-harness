# graph_agent 内聚 + 可靠运行 行动方针

> 来源:2026-04-26 双审计(Gemini 全局设计评测 + Codex 全代码审计)+ Gemini 综合分析。
>
> 目标:把 graph_agent 引擎推到 "**内聚 + 可靠运行**" 状态——
> - schema 里的字段都有真实 runtime 实现(没有"声明了但不装配"的虚假支持)
> - 数据写盘 / agent 状态机不静默丢失或误报完成
> - compile-time validator 自身不会因边角输入崩溃
> - 错误信息能定位到 SKILL.md 具体行号
> - 1.x 时代生产里在用的能力(LogicPhase.max_retries 等)不被偷偷砍掉
>
> 全程保住 PR #5 当前 411 passed 的 baseline。
>
> **PR 策略**:不拆分 PR #5,所有修复直接累加在 `feat/studio-phase0-manifest` 上 big-bang merge。`rules.yaml` 选 [C] Drop。

---

## 执行顺序

**方针 2 → 方针 1 → 方针 3 → 方针 4**

逻辑:从运行时核心向外扩张。
1. 先修引擎状态机(harness.py)——底层不能丢数据/不能误报完成,否则上层 schema 修得再漂亮都没用
2. 再补 schema-runtime 虚假契约(loader.py + manifest.py)——做完这两步,系统逻辑已自洽,411 passed 应保留
3. 然后换 parser 引入行号追踪——给 Studio UI 带来"点击跳行"
4. 最后打磨编译器/验证器边角防御

---

## 方针 2 — 运行时防丢防挂 (P0,1-3 commits) — 先做

**目标**:修复 harness.py 状态机漏洞,防止静默的数据丢失和幽灵 run 被标完成。

| 子任务 | 位置 | 现象 / 修法 |
|---|---|---|
| 2.1 | `harness.py:609` 附近 (Codex 报告 :609,Gemini 复核成 `:465`,以实际为准) | 检测到 `AWAITING_INPUT` 后**没有 return**,继续 auto-save outputs + 发 `RunEndedEvent(status="completed")`。修法:发完中断事件 `return`,跳过 outputs 保存,run 状态用 interrupted/awaiting_input 而非 completed |
| 2.2 | `harness.py:799` (`_save_outputs_via_io`) | `except Exception: logger.warning(...)` 吞了所有写盘失败 → 数据静默丢失。修法:对 schema 声明的 required outputs 重新抛 / run 状态非 completed |
| 2.3 | `loader.py:294` (`load_workflow_from_md` 顶部) | 非 "2.0" schema_version 字符串使函数静默 `return None`,runner.py 把 None 当 harness 用。修法:在 2.0 分支外显式 `raise SkillLoadError`,复用 `compile_skill()` 的 `F-schema-version` 信息 |

**验收**:
- 写一个带 `AWAITING_INPUT` 的 phase,跑一次确认 run 不会被标 completed,且 outputs 没被写
- 写盘失败的测试(monkeypatch IOManager.save_outputs 抛 IOError)→ run 状态 crashed / 至少异常向上抛
- 非 2.0 schema 版本 SKILL.md 跑 `load_workflow_from_md` → 抛 SkillLoadError 而不是 None

---

## 方针 1 — Schema 契约兑现 (P0,4-7 commits)

**目标**:消除 schema 接受但 runtime 不装配的虚假字段。已声明的字段要么实现 runtime,要么从 schema 删除。**不留中间态**。

| 子任务 | 位置 | 决策路径 |
|---|---|---|
| 1.1 LogicPhase 加回重试 | `manifest.py` (LogicPhase 定义) + `loader.py` 的 logic phase builder | 加 `max_retries` + `retry_target` 字段 + Phase runtime 接通(1.x 生产里在用,不能砍) |
| 1.2 sub_skills 装配 | `loader.py:434` (`_phase_from_agent_skill`) + `_phase_from_graph_phase` | `manifest.sub_skills` / `LLMPhase.sub_skills` 通过 `skill_tool_factory.build_skill_tool()` 注入 `Phase.tools`。**或者**从 schema 移除字段——选哪个看 1.x 生产是否在用 |
| 1.3 output_schema 装配 | `loader.py:471` (graph LLM phase 分支) | `LLMPhase.output_schema` 解析 import path,填充 `Phase.output_schema_path` / `Phase.output_schema`。PhaseExecutor 已读这字段,只是 loader 没传 |
| 1.4 LLMPhase.steps 装配或砍 | `manifest.py:196` + 对应 loader/PhaseExecutor 路径 | `when` / `skip_if` / step tools / step validator 全部静默失效。要么实现 step 执行模型,要么从 schema 删 `steps` 字段。**优先看 1.x 生产是否依赖** |
| 1.5 IoOutput.target 枚举 | `manifest.py:114` + `IOManager.save_outputs()` | schema 写 `"artifact"`,runtime 期待 `"artifact_manager"` → 合法 manifest 走 unknown branch + 被 harness warning 吞。统一两端命名 |
| 1.6 retry_target 引用校验 | `manifest.py:194` (model_validator) | retry_target 必须指向 `GraphSkillDef.phases` 里某个 phase name。加 model validator |
| 1.7 phase name 唯一性 | `manifest.py:296` (GraphSkillDef model_validator) | LangGraph node 名是 `f"{phase.name}_execute"`,重名会覆盖路由。加 model validator 拒重复 |
| 1.8 计数字段下界 | `manifest.py:190` 附近 | `max_iterations` / `max_retries` / `max_nudges` 加 `Field(ge=1)`(retries 可能 ge=0) |

**验收**:
- 对 `manifest.py` 每个 execution-bearing 字段 grep loader.py,确认有 `Phase()` 构造对应映射;没映射的字段必须从 schema 砍掉
- 411 passed 不能跌,新增字段全部加单测(每条 1.x-1.8 至少一条 fail-test → green-test)

**调研先行**:1.x 生产 9 个 SKILL.md 哪些用了 `sub_skills` / `steps` / `LogicPhase.max_retries` —— 这决定 1.2/1.4/1.1 是"补 runtime"还是"删 schema"。
检查命令: `grep -rn "sub_skills\|^\s*steps:\|max_retries" src/core/graph_agent/skills/`

---

## 方针 3 — Parser 地基 + 行号追踪 (P1,4-7 commits)

**目标**:换 parser,所有 CompileIssue 能输出 `SKILL.md:42` 而不是 `phases.0.name`,顺带修 YAML 边角崩溃。

| 子任务 | 位置 | 修法 |
|---|---|---|
| 3.1 `ruamel.yaml` 替换 `yaml.safe_load` | `parser.py:35` | 用 `ruamel.yaml.YAML(typ='rt')` round-trip 模式,保留每个 key 的 `lc.line` line number metadata。返回 dict 时附挂 `__lc__` 或类似 metadata |
| 3.2 CompileIssue.location 注入行号 | `compiler.py:171` Pydantic ValidationError 转换处 | `err.get("loc")` 是 `('phases', 0, 'name')` 元组,从 parser 的 line metadata 反查具体行,组合成 `SKILL.md:42:phases.0.name` |
| 3.3 `schema_version` 非字符串容错 | `compiler.py:159` + `loader.py:294` | `str(frontmatter.get("schema_version") or "").strip()`(YAML 把 `2.0` 自动解析成 float 时 `.strip()` 会 AttributeError) |
| 3.4 CRLF frontmatter 兼容 | `parser.py:35` (frontmatter regex) | 改成换行无关解析或 regex 接 `\r?\n` |
| 3.5 dependency 加 ruamel.yaml | `pyproject.toml` | 加 `ruamel.yaml ~= 0.18` 或当前最新 |

**验收**:
- 故意写一个 `phases[0].name` 字段错误的 SKILL.md → CompileIssue.location 显示具体行号
- `schema_version: 2.0`(无引号)不再崩,转成清晰 fatal
- CRLF 文件能被解析

**风险**:`ruamel.yaml` 的 round-trip dict 跟 Pydantic 兼容性可能要垫一层 `dict()` 转换。验证 411 passed 仍绿。

---

## 方针 4 — 编译器/验证器严格模式 (P1,4-7 commits)

**目标**:边角输入不能让 compile_skill 崩成 Python Exception,所有错误聚合到 CompileResult。

| 子任务 | 位置 | 修法 |
|---|---|---|
| 4.1 persona ValidationError 捕获 | `validators/persona_resolution.py:65` | 当前只 `except SkillLoadError`。子 persona 文件 frontmatter 错时会冒 Pydantic ValidationError,破坏聚合契约。加 `except (SkillLoadError, ValidationError)` 转 `F-persona-not-resolved` 或新增 `F-persona-invalid` |
| 4.2 personas.py 相对路径修复 | `personas.py:69` | `adopted_persona: ./subskills/p` 当前会被拼接成 `base_dir/subskills/subskills/p/SKILL.md`(双重前缀)。修法:在 resolve_persona 入口分支处理 `./` / 含 `/` 的相对路径,直接 `base_dir / name / SKILL.md` |
| 4.3 tool_paths 路径越权 | `validators/tool_paths.py:150` | local tool ref 如 `../etc/passwd.x` 当前 compile 通过但 load-time 拒绝,行为不一致。加 `candidate.resolve().is_relative_to(base_dir.resolve())` 校验,F-tool-path-escape |
| 4.4 subgraph load 用 is_file | `loader.py:508` | 当前 `if not child_path.exists():` 通过目录路径,然后 `read_text()` 崩 IsADirectoryError。改 `is_file()` 跟 compile validator 一致 |
| 4.5 stale docstrings 清理 | `compiler.py:122` / `loader.py:7` / `loader.py:424` | docstring 还在写 "TODO" / "Dead code" / "1.x XML body tags",代码已经活了。改成现状描述 |

**验收**:
- pytest 加 4-5 个 hostile-input fixture(损坏 persona / 越权 tool path / 目录冒充 subgraph / 双 `./` persona),全部稳定返 CompileResult
- docstring 描述跟代码一致

---

## 总验收(全 4 方针完成后)

1. **411 passed → 应该接近 ~430-450 passed**(每方针约新增 5-10 个测试)
2. `compile_skill()` 对 hostile/malformed input 全部 graceful return CompileResult
3. `manifest.py` 每个 execution-bearing 字段 → loader.py 有对应 Phase() 构造映射
4. `harness.py` AWAITING_INPUT / 写盘失败两个状态机漏洞修复
5. CompileIssue.location 输出格式从 `phases.0.name` → `SKILL.md:42:phases.0.name`
6. PR #5 整体 big-bang merge ready

---

## 关键设计澄清(避免重蹈覆辙)

- **Persona 循环检测漏检** = 误报。`PersonaSkillDef` schema 没有 `phases` / `adopted_persona` 字段,根本不可能引入循环。`subgraph_cycle.py` 不检查它正确
- **tool_paths 不查函数符号** = 故意设计(non-executing,避免 Studio 保存时 import 用户代码)。AST 解析检查可以将来加,**当前不在 P0/P1 范围**
- **Codex 13 BUG / 4 RISK / 3 POLISH 的合并打包**:不要把它当 20 个独立 todo,而是按 4 方针的内聚维度重组。共同根因(如 schema_version 浮点崩溃在两个文件都触发)合并修
