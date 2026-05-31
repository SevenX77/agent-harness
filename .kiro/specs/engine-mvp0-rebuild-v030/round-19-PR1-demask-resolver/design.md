# PR-1 Design: 强拆掩盖层与 Resolver 契约修复

## 1. 契约继承与变动表 (SOP-06)

| 影响面 | 变更摘要 | 兼容性分类 | 迁移路径 |
| :--- | :--- | :--- | :--- |
| `run_skill` 函数签名 | `skill_resolver` 维持强制参数状态不变。 | [COMPATIBLE] | 内部 API，签名未变。 |
| CLI `graph-agent` (`runner.main`) | 内部实例化默认的 Resolver 并传入 `run_skill`，使 CLI 命令恢复可用。 | [COMPATIBLE] | 纯修复，使破坏的 CLI 功能恢复工作。 |
| README 示例脚本 | 示例代码中增加 `LocalWorkspaceResolver` 的实例化，展示生产用法。 | [BREAKING] | 修复过期文档。用户需要照抄新的 `run_skill` 调用样例。 |
| 测试环境 `conftest.py` | 移除全部 10 个函数上的 `__kwdefaults__` 猴补丁注入。 | [BREAKING] | 内部测试行为规范。之前隐式依赖补丁的测试需显式传入 resolver 夹具。 |

## 2. 关键设计决策: 生产环境下的 Resolver 策略

在 V0.3.0 的架构中，不再有“全局配置自动推断出的魔术 Resolver”。框架层（`core/` 目录下的 `compiler`, `assembler`, `runner`）坚持要求外界注入 `SkillResolverProtocol`。

对于**外部应用层（CLI, 独立工具, README 示例）**，我们需要提供一个标准的落地实现。
**设计:**
新增一个针对本地单机使用场景的实现 `LocalWorkspaceResolver`。
**明确落点:** 为避免塞进纯协议文件 `skill_resolver_protocol.py` 导致含糊，新建模块文件 `graph_agent.core.local_workspace_resolver` 存放该类：
```python
class LocalWorkspaceResolver:
    """A standard resolver for CLI and standalone usage."""
    def __init__(self, search_paths: list[Path]):
        self.search_paths = search_paths
        
    def resolve_skill(self, skill_id: str) -> Path:
        validate_skill_id(skill_id)
        matches = []
        for path in self.search_paths:
            for candidate in (path / skill_id, path / skill_id.replace(".", "/")):
                if candidate.is_dir() and (candidate / "GRAPH.md").is_file():
                    matches.append(candidate.resolve())
        unique_matches = tuple(dict.fromkeys(matches))
        if len(unique_matches) == 1:
            return unique_matches[0]
        if len(unique_matches) > 1:
            raise SkillResolutionError(
                skill_id,
                "Ambiguous skill id",
                code="[F-v3-skill-id-ambiguous]",
            )
        raise SkillResolutionError(skill_id, "Not found in search paths")
```
Resolver 会同时收集 literal 与 dotted-id 候选；唯一命中才返回，多命中必须 fail-loud 抛歧义码。这样比 silent first-match 更符合零静默失败原则，避免 search path 顺序意外改变实际调用的子 skill。
在 CLI `runner.main()` 中，默认将当前执行目录的 `skills` 子文件夹（或当前目录）作为 `search_paths` 传入。

## 3. 测试修缮与 Tests-First 红灯转绿策略

1. **撤去掩盖（红灯阶段）：**
   - 彻底删除 `tests/conftest.py` 中的 `_set_kw_default` 循环。必须删除**全部 10 个**函数的掩盖，包括：`compile_skill`, `assemble_graph`, `SkillLoader.compile_skill`, `load_workflow_from_md`, `run_skill`, `_run_skill_dict`, `_run_v030_skill_dict`, `build_skill_tool`, `parallel_map`, `md_to_json`。
   - **红灯形态差异:** 删除默认值后，各调用点的失败形态将不统一（需注意分辨）：部分报 `TypeError: missing required argument`，部分内部抛 `[F-v3-resolver-missing]`，还有部分（如 `SkillLoader.compile_skill` 处理无子节点）可能静默逃过仍显绿。这都属于“诚实红灯/行为”范围。
   - **保留语料 Deferral 机制:** `conftest.py` 中因 "V1 layout skill awaiting V2.1 cutover" 设置的 19 个 `xfail(strict=False)`，以及 `test_loader_based_smoke.py:11` 因 V2.1 语料回归设置的模块级 `skip`，均属于语料格式迁移范畴 (PR G §10 范围)，**本 PR 不作任何删改，必须保留**（同时 `test_loader_based_smoke.py` 中的 parametrize 预存 BUG 也不碰）。

2. **契约修复（转绿阶段）：**
   - 对 CLI (`main`) 和 `tools/dual_run_shadow.py` 注入 `LocalWorkspaceResolver` 实例。
   - 提供显式的 `mock_skill_resolver` 测试夹具 (fixture)。**核心约束:** 该夹具必须是确定性、Scoped（基于测试自身的 tmp_path 或固定的 registry）的设计，**严禁**把旧机制里对 `/tmp/pytest-of-*` 的跨全局模糊 Glob 匹配平移过来继续掩盖。
   - 增加**自动化回归测试:** 新增针对 CLI `runner.main()` 的自动化测试，明确断言其正确构造并传递了 Resolver；同时为 `LocalWorkspaceResolver` 增加单测。
