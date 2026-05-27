# PR-3 Requirements v4: Persona及死码簇、旧入口与 Context 修补

## 1. 目标
解决 V0.3 引擎中存在的次生缺陷，通过拆除以 `build_graph_nodes` 为代表的已被废弃的死代码簇（并在测试侧安全迁移断言）、为 Context 补全最小鸭子类型、修复 `run_skill` 拦截契约以及防范 `md_to_json` 产生的 `KeyError`。

## 2. 具体要求与验收标准 (Acceptance Criteria)

### 2.1 `build_graph_nodes` 及 Persona 死码整簇拆除
- [ ] 必须移除 `src/graph_agent/core/personas.py` 的相关实现与对外暴露。
- [ ] 必须清理 `skill_builder.py` 中整个失效的函数簇，包括 `build_graph_nodes`、`_inject_persona` 及对应的 `_phase_from_*` 系列函数，以及 `TYPE_CHECKING` 块中失效类的导入，彻底消除 import-on-call 时的 `ImportError` 隐患。
- [ ] 必须将现有的 Persona 专属测试（如 `test_personas_relative_path.py` 等 3 个文件）**重命名并去 Persona 化**，仅将它们作为 `_guard_v030_root` 拦截无效 V2.1 root 的测试保留下来。
- **验收:** `rg "build_graph_nodes|_inject_persona|PersonaSkillDef|adopted_persona|resolve_persona|core\.personas" src/graph_agent tests` 必须输出为空（严格归零）。同时保证该文件的 mypy/ruff 静态分析不会因此前无效的 TYPE_CHECKING 报错。

### 2.2 Context 字典语法补充
- [ ] 在 `Context` 类中实现四个方法：`__getitem__`, `__setitem__`, `__contains__`, `setdefault`。
- **验收:** 新增带有真实 LOGIC action（如调用类似于 `score.py`）的测试，确保下标访问不再抛出 `TypeError`。

### 2.3 `run_skill` 旧入口 Fail-Loud 与 Deferred Guard
- [ ] 在 `_run_skill_dict` 中，当发现目标不是 V0.3 目录时，立即抛出规范的 `SkillLoadError([F-v3-...])`，使得公开方法 `run_skill` 能够捕获并正常返回 `WorkflowResult(success=False, error=...)`。注意由于公开方法存在 `error=str(exc)` 的转换机制，须确保该错误的字面表达真正含有标准 `code` 字符。
- [ ] 在 `md_to_json.py` 工具的 fallback 路径中增加防御（Deferred Path Guard）：当 `run_skill` 返回 `success=False` 时，显式抛出清晰的错误，阻止执行到 `:578` 引发 `KeyError`。
- **验收:** 新增测试确认传入单文件调用 `run_skill` 会返回 `success=False` 的对象且携带预期的业务 code（且字符串断言不被假绿）；构造触发 `md_to_json` 修复分支的数据，断言抛出的不是 `KeyError` 而是明确的 `SkillLoadError`。

### 2.4 Defer 声明
- 本 PR 不深度重构 `md-patch` 技能的执行流，不在本 PR 处理项目元数据过期（如版本号）问题，全部延后到 PR-6。

## 3. 边界约束
- 严禁擅自将 `run_skill` 的返回失败契约修改为向外抛出未处理异常。
- 必须遵循 Tests-First 策略编写并验证上述的所有红灯测试。
