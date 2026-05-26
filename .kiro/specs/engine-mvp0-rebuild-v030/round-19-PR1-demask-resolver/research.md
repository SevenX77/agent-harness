# PR-1 Research: 修复公开入口 Resolver 契约断裂与掩盖撤除

## 背景与发现
在对 `packages/graph-agent` V0.3.0 版本的审计中（a1/a3 审计报告），我们发现：
1. **公开入口契约断裂 (a1-1, a1-14):** 
   - `core/runner.py:173` 的 `run_skill` 函数强制要求 `skill_resolver: SkillResolverProtocol` 类型的参数。
   - 但是在生产路径中，例如 CLI (`runner.py` 的 `main` 函数)、README 示例脚本以及部分内部工具（如 `tools/dual_run_shadow.py`），调用 `run_skill`、`compile_skill` 或 `assemble_graph` 时**均未传递此参数**。
2. **测试夹具掩盖 (a1-6):** 
   - 本应在 CLI 运行和冒烟测试中爆炸的缺失参数错误，被 `tests/conftest.py` 中的 `__kwdefaults__` （对 `run_skill`、`compile_skill` 等多达 10 个核心入口进行的猴补丁篡改）所掩盖。
   - （注：审计亦发现了部分测试的 `xfail` 与 `skip`，但这部分实际是由于老旧 V1/V2.1 语料的 deferral，并非针对 resolver 的掩盖，因此本 PR 明确将它们排除在清理范围之外）。

## 代码事实探查
- **契约定义:** `core/skill_resolver_protocol.py` 定义了 `SkillResolverProtocol`。它的核心是 `resolve_skill(skill_id) -> str | Path`，用于将一个 `skill_id` 映射到本地的一个有效的 Skill 根目录（包含 `GRAPH.md`）。这是 V0.3 组合与 Subagent 调用依赖的基石。
- **调用方:** `require_skill_resolver` 会校验传入的 `resolver`，如果为 `None` 则直接抛出 `SkillResolutionError("[F-v3-resolver-missing]")`。
- **问题根因:** 在 V0.3.0 重写中，引入了更严格的模块化依赖注入（DI）机制，去掉了框架层面的全局状态。但这导致处于应用层的入口（CLI 和示例）因为没有构造依赖注入链而脱节。

## 解决方向 (Research 结论)
不能简单地将 `skill_resolver` 改回 `Optional` 或允许传入 `None`，这违背了重写去除全局单例的初衷。
相反，**生产环境（应用层）必须自己构建并提供一个缺省的 Resolver。**
在实际 CLI 和单机场景下，最合理的缺省逻辑是“在当前运行目录（工作区）下的特定文件夹（如 `skills/` 或 `./`）寻找目标 skill”。

因此我们需要：
1. **定义一个生产级的本地目录 Resolver 实现 (LocalWorkspaceResolver)**，放置于新模块 `graph_agent.core.local_resolver` 避免纯协议文件污染。
2. **在 CLI (`main`) 和相关独立脚本中，实例化它并传入**。补充自动化回归测试保障 CLI 链路不再次退化。
3. **在测试层面，立即撤除 `conftest.py` 对 10 个函数猴补丁注入的掩盖**，暴露出因为应用层没传参数引起的红灯，然后通过安全且确定性（禁止 `/tmp` glob 魔术）的显式 fixture 修复，将它们转绿。