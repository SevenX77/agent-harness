# MVP-2 Research — A5 SchemaEngine + A7 IOManager 决策

## 来源资料

- v1-reset direction doc: `docs/superpowers/specs/2026-04-28-v1-reset-direction.md` §4 MVP-2 + Appendix B A5/A7
- MVP-1 spec: `.kiro/specs/v1-reset-mvp-1-state-split/{requirements,design,tasks}.md`（BusinessData / FrameworkState 已落地，本 MVP 在此基础上）
- Gemini independent design (2026-04-29): job_dc2b328ebc8e（Part A-G，整合到本 spec design.md）
- 当前 schema 解析弥散点（Gemini Part A 现状审计）:
  - `src/core/graph_agent/core/manifest.py:PhaseDef` (Pydantic 校验 output_schema 字段格式)
  - `src/core/graph_agent/core/loader.py` (SKILL.md 文本 → dict 解析逻辑)
  - `src/core/graph_agent/cognitive/finish.py` (FinishTaskInterceptor 读 schema 调用校验器)
  - `src/core/graph_agent/tools/md_to_json.py` (schema 附着 ParsedBlock 供 prompt)
  - `src/core/graph_agent/core/artifact_manager.py` (旧逻辑可能解析 schema)
- 当前 io 路由弥散点（Gemini Part A 现状审计）:
  - `core/manifest.py:IODef` (模型定义)
  - `core/loader.py` (build graph node 时硬编码 hoist_to)
  - `cognitive/finish.py` (finish_task 触发时手动搬字段到 context/data)
  - `tools/io/manager.py` (初步 Resolver，与 ContextBridge 耦合)
  - `core/phase_executor.py` (phase 结束时收集 io_errors)

## Baseline 数据（待 T0 prep 测）

T0 prep 子任务（派 a3 在派 T1 前跑）需要测:
- `loader.py` 当前总行数 + schema/io 相关行数
- `finish.py` 当前总行数 + schema/io 相关行数
- 5 处 schema 解析弥散点的具体函数 / 行号清单
- output_example 解析正则的精确位置 + 缩进敏感性测试用例
- 4 核心 SKILL 的 output_schema / output_example 多样性（用于 SchemaEngine 单元测试设计）

## 决策记录

### D1 — SchemaEngine 模块位置: `core/schema_engine.py`

**选项**:
- A. `src/core/graph_agent/tools/schema_engine.py`（跟 md_to_json 同级，归类为"工具"）
- B. **`src/core/graph_agent/core/schema_engine.py`（基础设施级别，跟 manifest / state / loader 同级）**

**决策: B**

**理由**:
- SchemaEngine 是基础设施而非工具：被 loader（启动期）+ finish_task（运行期）+ md_to_json（prompt 渲染期）+ ContextBridge（V2 委派期）四方共用
- 工具的语义是"LLM 在 agent loop 里调用的可执行单元"，SchemaEngine 不是
- 跟 manifest / state 同级，强调它是 graph_agent 的核心抽象层
- Gemini design 也明确给 `core/schema_engine.py` 路径

### D2 — ContextBridge 演化路径: 共存（视图层）, 不合并

**选项**:
- A. ContextBridge 完全合并进 SchemaEngine（删除 ContextBridge 类）
- B. **ContextBridge 保留为视图层，内部调用 SchemaEngine 取模型（Gemini 推荐）**
- C. ContextBridge 不动，跟 SchemaEngine 各自独立做 schema 处理

**决策: B**

**理由**:
- A 太激进: ContextBridge 是 V2 跨 skill 委派的预留接口（manifest.py:138-150 注释），跟 SchemaEngine 的职责（解析 + 校验）不同。前者负责"父子 skill 字段映射"，后者负责"schema 文本 → 模型"
- C 留下两套解析逻辑，违反 MVP-2 的收拢目标
- B 最小动作: ContextBridge 不再含 schema 解析代码，所有 schema 相关动作通过 `SchemaEngine.get_pydantic_model` 委托。MVP-1 design §5.1 已声明 ContextBridge 跟 BusinessData schema 对接，本 MVP 进一步明确"对接通过 SchemaEngine 中介"

### D3 — A5 / A7 实施顺序: A5 先于 A7

**选项**:
- A. A5 SchemaEngine 先做，A7 IOManager 后做（Gemini 推荐）
- B. A7 先做，A5 后做
- C. 完全并行（codex 拿 A5、a3 拿 A7）

**决策: A**

**理由**:
- A7 IOManager 的 `resolve_hoist` 在搬运前需要做类型预检（避免把 string 搬到 int 字段触发 Pydantic 抛错），这要求 A5 提供 `SchemaObject`/`get_pydantic_model` 接口
- 没有共享中间表示（SchemaObject）的话，A7 只能各自再做一次解析，违反收拢目标
- v1-reset-direction §4 MVP-2 描述说"A5 / A7 彼此独立，可并行实现"——但这里"独立"指的是 **跨 a1/a3 分工独立**，而不是无依赖。Gemini 在 Part D 明确给"A5 是底座"
- 子任务依赖图: T1+T2 (SchemaEngine) → T3 (IOManager) → T4-T7 (改造调用方)
- a1 拿 T1+T2+T3（连续 SchemaEngine + IOManager 主线），a3 拿 T4-T7（短链改造各调用方），双线交叉验证

### D4 — 跟 MVP-1 BusinessData 的 schema 对接接口

**当前 (MVP-1 后)**: `BusinessData` 是 Pydantic v2 BaseModel `extra="allow"`，没有强制字段 schema，靠运行时动态接受任意字段。

**MVP-2 后**: BusinessData 仍保持 `extra="allow"`（不破坏向后兼容），但提供工厂函数:

```python
def build_business_data_for_skill(skill_manifest, schema_engine) -> type[BusinessData]:
    """根据 SKILL 的 output_schema 创建带强类型字段的 BusinessData 子类。
    
    返回的子类继承 BusinessData，但额外含 SchemaEngine 解析出的字段（带类型标注）。
    LangGraph 用这个子类构造 initial_state["data"]。
    """
    schema = schema_engine.parse_from_md(skill_manifest.output_schema_md)
    pydantic_model = schema_engine.get_pydantic_model(schema)
    return create_model(
        f"BusinessData_{skill_manifest.name}",
        __base__=BusinessData,
        **pydantic_model.model_fields,
    )
```

**理由**:
- BusinessData 基类保持 `extra="allow"` 兼容老 SKILL（output_schema 缺失时仍能跑）
- 工厂动态生成子类，把 schema 字段强类型化（`extra="allow"` 仍然 honor，但已声明字段会强制校验）
- 不破坏 MVP-1 design §1.1 模型定义

### D5 — 跟 MVP-3 Loader 的接口契约

**MVP-2 后, MVP-3 启动前的边界**:
- `loader.py` 通过 `SchemaEngine.parse_from_md` 解析 SKILL 文本，**不再自己 regex 拆 markdown**
- `loader.py` 不再保存 schema dict，改保存 `SchemaObject` 对象（不可变 dataclass）
- 跨 phase / 跨函数传递 schema 时，传递 `SchemaObject` 而非 raw dict 或 str

**MVP-3 时**:
- loader 拆为 `Parser / ManifestValidator / ModuleSandbox / PhaseBuilder`，其中 Parser 调用 SchemaEngine 完成 schema 解析
- A9 `_resolve_output_schema_path` 改用 PEP 451 importlib namespace（这条 hack 跟 SchemaEngine 不冲突——SchemaEngine 处理 schema 内部，A9 处理路径解析外部）

### D6 — io_errors 存储归宿: `FrameworkState.io_errors`（不用 metrics）

**Gemini Part C 原话**: "io_errors 统一存入 `FrameworkState.metrics["io_errors"]`"

**主控修订**: 改为 `FrameworkState.io_errors: list[str]`（MVP-1 design §1.1 已声明此字段）

**理由**:
- MVP-1 design §1.1 已声明 `io_errors: list[str] = Field(default_factory=list)`，是顶层字段而非 metrics 子键
- Gemini 写 design 时可能没看到 MVP-1 的最终 design.md，建议用 MVP-1 已落地的字段
- metrics 字典的语义是"指标数据"（token 数、wall time 等），io_errors 是错误清单不应混入

### D7 — output_example 缩进敏感性: 完全保留现有正则

**问题**: Gemini Part F 提到"4 SKILL 的 output_example 解析对空格和缩进极度敏感"

**决策**: T1 实施时**完全复制**现有 loader.py 中的 output_example regex 到 SchemaEngine，**不重写**。

**理由**:
- 重写正则风险高（4 SKILL compile 都依赖现有解析行为，破坏 = MVP-2 验收红线 §Req 7 失败）
- MVP-2 目标是"路径收拢"，不是"算法重画"
- 缩进敏感性根治放到 MVP-3 (loader 拆解时统一用 markdown AST 而非 regex) 或 MVP-5 (CI 收紧时配 SKILL.md 格式化工具)

### D8 — SchemaEngine 缓存策略

**问题**: `get_pydantic_model(schema)` 每次都重建 Pydantic 类是性能浪费（启动期）+ 类身份不一致（运行期 isinstance 失败）

**决策**: 用 `functools.lru_cache(maxsize=128)` 装饰 `get_pydantic_model`，cache key = schema 的 hashable 表示（推荐 `tuple(sorted(schema.items()))` 或 schema 的 sha256 摘要）。

**理由**:
- 4 SKILL 总共 < 30 个不同 schema，cache 大小完全够
- 同一 schema 多次调用返回同一类，让 isinstance 检查可靠
- 启动期一次性 warm cache（在 loader.compile_skill 期间）

## 不在 MVP-2 处理的相关问题（明确 defer）

- `loader.py` 整体拆解 (Parser / ManifestValidator / ...) → MVP-3
- A9 `_resolve_output_schema_path` PEP 451 改写 → MVP-3
- output_example regex 重写为 markdown AST 解析 → MVP-3 / MVP-5
- finish_task 不再是 LangChain Tool → MVP-4
- phase_executor 整体拆解 → MVP-4
- 全库 mypy strict / ruff / coverage 收紧 → MVP-5
