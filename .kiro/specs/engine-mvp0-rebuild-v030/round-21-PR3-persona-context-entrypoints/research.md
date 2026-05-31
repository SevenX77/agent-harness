# PR-3 Research v3: Persona 遗迹、旧入口与 Context 断层审计

## 1. Persona 必崩路径分析 (a3-1)
**现状考古调查:**
- `PersonaSkillDef` 已经在 V2.1 cutover 时被彻底移除。当前 AST Schema 中根本不存在 `adopted_persona` 字段。
- 在 `skill_builder.py` 等文件中残留的导入与注入逻辑是死路径。
- 已有的相关测试（`test_personas_relative_path` 等）实际上在防守 `_guard_v030_root` 对 V2.1 root 的拒绝逻辑，这些测试不能被直接删除，而是应该去除其中的 persona 业务含义后予以保留。
**定性:** 典型的**实现缺陷（Cutover 清扫不彻底）**，需干净拆除死代码。

## 2. Context Facade 字典语法兼容缺失分析 (a1-8)
**现状调查:**
- V0.3.0 的 `Context` 门面只提供了 `.get()`, `.set()`, `.update()`, `.has()`。
- 审计实证：真实活着的 e2e fixture `score.py:2` (LOGIC action) 高度依赖 `context["segments"]` 的字典下标提取。这会导致执行期必抛 `TypeError`。
**定性:** **设计缺陷**。需要为 `Context` 增补最小够用的 4 个标准字典方法以满足历史习惯。

## 3. 旧入口硬切未收口分析 (a1-3, a1-4)
**现状调查:**
- **旧文件硬拒绝:** `run_skill` 遇到单文件时会继续往后走，最终由于底层深层属性缺失（如没有 `trace_dir` 挂载或路径拼接错）引发异常，未能实现预期的 public API `WorkflowResult(success=False)` 返回契约。
- **`md_to_json.py` 裸漏 KeyError:** `md_to_json` 在遇到错误时会拉起 `md-patch`。但 `md-patch` 由于工具参数被新引擎拦截，会直接导致 `run_skill` 返回失败 (`success=False`)；而 `md_to_json` 在 `:578` 缺乏对失败状态的检查，直接去取 `result["context"]["final_results"]` 导致 `KeyError`。
**定性与结论:** 
- `run_skill` 必须内部拦截并以 `[F-v3-]` 错误码**返回**失败结果。
- `md_to_json` 的重构逻辑（如何正确做 Patch）过于庞大，将**显式 Defer 到 PR-6**；但在本 PR 必须修补其由于 `run_skill` 失败而导致的 `KeyError` 漏网之鱼（Deferred Path Guard）。
- PyProject 版本元数据和文档更新一并延后到 PR-6。