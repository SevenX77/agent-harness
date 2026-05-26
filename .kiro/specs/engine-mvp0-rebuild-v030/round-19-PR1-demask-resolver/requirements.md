# PR-1 Requirements: 去掩盖与修复 Resolver 入口断裂

## 1. 目标
恢复 `packages/graph-agent` V0.3.0 在无掩盖（无猴补丁）的真实环境下的可用性，重塑其在 CLI、外部调用和官方示例中的核心接口契约。

## 2. 约束 (Cutover Discipline)
本次 PR 必须将“去除测试夹具中的 Resolver 注入掩盖”与“修复底层 Resolver 逻辑断裂”放置在**同一个 PR (原子操作)**中完成，以保证主干分支的测试基线处于持续真实且诚实的状态。

## 3. 具体要求与验收标准 (Acceptance Criteria)

### 3.1 去掩盖测试基线
- [ ] 必须移除 `tests/conftest.py` 中 `_set_kw_default` 循环关于 `__kwdefaults__` 的劫持逻辑。**范围是全部 10 个函数**：`compile_skill`, `assemble_graph`, `SkillLoader.compile_skill`, `load_workflow_from_md`, `run_skill`, `_run_skill_dict`, `_run_v030_skill_dict`, `build_skill_tool`, `parallel_map`, `md_to_json`。
- [ ] **保留约束：** 不得修改 `conftest.py` 中的 19 个 `xfail(strict=False)` 语料门禁，也不得修改 `test_loader_based_smoke.py:11` 的全局 `skip` 及文件内的 parametrize。
- **验收:** 进行上述删除后运行测试，必须且只暴露出“Resolver 缺失相关”的诚实红灯（`TypeError` 或 `[F-v3-resolver-missing]`）。原有 19 个 xfailed 必须保持 xfailed 不变。

### 3.2 CLI 与工具生态的契约修复
- [ ] 在 `graph_agent.core.local_resolver` 新模块中实现 `LocalWorkspaceResolver`。
- [ ] `core/runner.py` 内的 CLI `main()` 函数，必须实例化该 Resolver 并传给被调用的 `run_skill`。
- [ ] 内部工具 `tools/dual_run_shadow.py` 在调用编译和图装配 API 时，必须显式构建并传入该 Resolver。
- [ ] README.md 文档内关于如何调用 API 的示例，必须更新并加入实例化本地 Resolver 的示例代码。
- **验收:** 必须新增**自动化测试**明确断言 `runner.main()` 的确构造并传入了 Resolver（不只是手动验证），且新增 `LocalWorkspaceResolver` 的单测。

### 3.3 测试用例代码层的显式修正
- [ ] 提供一个标准的 `pytest.fixture`（如 `mock_skill_resolver`）。
- [ ] **安全约束：** 新的夹具实现必须依赖测试自身的 `tmp_path` 或确定性的 registry 寻址，**严禁**复用旧机制里跨 `/tmp/pytest-of-*` 目录的全局模糊 glob 匹配魔法。
- [ ] 修改之前大面积失败的测试，让它们显式声明并使用此 fixture。
- **验收:** 去掩盖造成的 Resolver 缺失红灯，通过安全的显式传参后全部转化为真实的绿灯（不改变原有 xfail 数量，不锁死 "981 passed" 这种绝对数字）。