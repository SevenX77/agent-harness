---
ws_id: WS-E6-purity-extensions
modules:
  - 02-mechanism/01-compile
  - 01-contract/03-compile-rules
  - 02-mechanism/04-run-outer/01-graph-exec
  - 01-contract/02-skill-syntax
depends_on: []
blocks: []
owns_files:
  - packages/graph-agent/src/graph_agent/core/purity.py
  - packages/graph-agent/tests/core/test_purity_characterization.py
  - packages/graph-agent/tests/core/validators/test_tool_paths_escape.py
  - packages/graph-agent/tests/core/validators/test_purity_le2.py
spec_ssot:
  - docs/engine/mvp1/02-mechanism/01-compile/mvp1-alignment.md §2/§6/§8
  - docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md §2.1/§6
  - docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md §2/§5/§8
  - docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md §2.3.3/§6
status: drafted
created: 2026-06-06
related_plan: docs/engine/mvp1/_impl/IMPL_PLAN.md
related_backlog: docs/engine/mvp1/_impl-backlog.md
review_flow: Claude 写需求书 -> Codex 写 RED 测试 -> Claude 契约门 -> Codex 写 task.md + Gemini prompt -> Gemini 实现 GREEN -> Codex 审 -> Codex 回写 baseline -> Claude 终审
---

# WS-E6 purity 扩展 - 需求书

> 本需求书是 WS-E6 的流水线输入。下一步是 Codex 按 §6 写失败测试；未见 RED、未过 Claude 契约门，不得开始实现或写 Gemini 实施任务书。

## 1. 目标(intent + why)

把 engine 编译期 purity 门从“只挡本地写 API”扩展到 mvp1 LOGIC 干净契约要求的硬禁范围：skill-local action 不能在源码里做 `run_skill` 编排、文件系统访问或变更、`sys.path` hack、import 越界。这样 LOGIC action 会被约束成确定性纯变换，复杂编排必须回到声明式 `iterate` / `SUBGRAPH`，而不是藏在 Python action 里绕过图执行模型。目标机制细节以 `spec_ssot` 为唯一真理，本需求书只定义范围、契约、测试和验收边界。

## 2. SSOT 指针(grounding,IR2/IR5)

- 目标唯一真理：
  - `docs/engine/mvp1/02-mechanism/01-compile/mvp1-alignment.md` §2、§6、§8：purity 扫描器归编译机制，目标 delta 是扩硬禁 `run_skill` / FS / `sys.path`。
  - `docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md` §2.1、§6：编译期 purity 校验失败统一落 `[F-v3-logic-action-purity-violation]`。
  - `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md` §2、§5、§8：LOGIC LE2 硬禁来源。
  - `docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md` §2.3.3、§6：action V4 干净执行契约与测试关键点。
- 实施计划：`docs/engine/mvp1/_impl/IMPL_PLAN.md` §二/§三/§四/§六，WS-E6 为全并发 P1，但 `run_skill` 禁令会影响 WS-E1 LOGIC 子步骤能否声明“完整 LOGIC 干净”。
- Backlog 来源：`docs/engine/mvp1/_impl-backlog.md` I2/I6。
- 现状锚点：
  - `docs/engine/mvp1/02-mechanism/01-compile/baseline.md`
  - `docs/engine/mvp1/01-contract/03-compile-rules/baseline.md`
  - `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md`
- 必读源码(实现前先读并回述关键符号/现状；行号只作 grounding，不作编辑坐标)：
  - `packages/graph-agent/src/graph_agent/core/purity.py:44` 的 `scan_python_purity`，现状 AST walk 只收集 local-write API 与语法错误。
  - `packages/graph-agent/src/graph_agent/core/purity.py:69` 的 `scan_tool_imports_context`，现状只额外禁止 tool 导入 Context facade。
  - `packages/graph-agent/src/graph_agent/core/loader.py:727` / `:748` / `:763`，action/tool 加载前调用 `_raise_on_purity_violations`，命中后通过 `_purity_fatal` 发 `[F-v3-logic-action-purity-violation]`。
  - `packages/graph-agent/src/graph_agent/core/error_registry.py:47`，现状已注册 `[F-v3-logic-action-purity-violation]`；本 WS 默认只读核对，不抢 WS-E3 的错误契约文件锁。
  - 既有测试：`packages/graph-agent/tests/core/test_purity_characterization.py`、`packages/graph-agent/tests/core/validators/test_tool_paths_escape.py`。

## 3. 文件归属(并发锁,IR1)

本 WS owns 见 frontmatter `owns_files`。允许新增 `packages/graph-agent/tests/core/validators/test_purity_le2.py`，用于覆盖 LE2 扩展在真实 `SkillLoader.compile_skill` 路径上的 RED/GREEN。

禁止触碰：

- `packages/graph-agent/src/graph_agent/core/error_registry.py`：WS-E3 owns。现状已有 purity violation 码；若 Codex 发现必须新增或改注册元数据，先停下回报 PM 与 WS-E3 协调，不得直接改。
- `packages/graph-agent/src/graph_agent/core/loader.py`：当前计划未把 loader 纳入 WS-E6 owns，因为现有加载路径已经调用 purity scanner。若 RED 证明必须改 loader 才能保真上报，先回报 PM 扩 owns 或拆分，不得偷偷越界。
- `packages/graph-agent/src/graph_agent/core/module_sandbox.py`：导入隔离机制归 `01-compile` baseline 现状，但本 WS 目标是 purity 扫描规则扩展；不重写 sandbox。
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py`：WS-E1 owns。LOGIC runtime 纯返回、Context mutation 退场不在 WS-E6。
- `packages/graph-agent/src/graph_agent/core/exceptions.py`、`packages/graph-agent/src/graph_agent/core/result.py`：WS-E3 owns。
- `packages/graph-agent/src/graph_agent/callbacks/events.py`、`packages/graph-agent/src/graph_agent/callbacks/emit.py`：WS-E4 owns。
- `apps/studio/**`、`packages/graph-agent-gateway/**`：不在 engine purity WS 范围。

共享文件协调：

- WS-E6 与 WS-E3 在错误码注册层只有只读/协调关系，不并发改同一文件。
- WS-E6 交付后，WS-E1 若选择“完整 LOGIC 干净契约”验收，可以把 `run_skill` FATAL 纳入 E1 LOGIC 子步骤；若 E6 未完成，WS-E1 只能按其需求书显式降级 scope。

## 4. 现状锚点(baseline)

现状 `scan_python_purity(path)` 会解析 Python 源码并扫描调用点；它能报语法错误、写模式 `open()`、部分 path mutation API、`os`/`shutil` 文件系统 mutation API、`tempfile` 临时文件 API。它不会硬禁 `run_skill` 编排，不会把只读文件系统访问纳入 purity violation，也不会拦 `sys.path` 修改或通过 import/路径 hack 绕出 action 边界。loader 已把 scanner 结果接到 `[F-v3-logic-action-purity-violation]`，错误码也已注册。

## 5. 目标行为(可测的契约)

### 5.1 `run_skill` 编排必须在编译期失败

- skill-local action 源码中直接或间接取得 engine `run_skill` 入口并调用时，编译必须失败。
- 失败必须发生在 `SkillLoader.compile_skill` 的编译期，不允许等到 LOGIC runtime 执行动作时才失败。
- 失败 payload code 必须是 `[F-v3-logic-action-purity-violation]`，并保留源码路径/行号定位语义。
- 该禁令只针对被 loader 当作 skill-local action/tool 源码扫描的文件；engine 自身内置模块、测试辅助和 public SDK 暴露 `run_skill` 不应因本 WS 误报。

### 5.2 文件系统访问与变更必须在编译期失败

- skill-local action 不得直接读、写、创建、删除、移动、复制、改权限、创建临时文件或使用等价本地文件系统 API。
- 只读文件访问也属于 LE2 硬禁范围；action 如需输入文件，必须通过声明式 IO、built-in 工具或后续 `run_context/io_manager` 机制，而不是自己碰本地 FS。
- 现有 local-write API 回归不得削弱：已经会失败的写文件、path mutation、`os`/`shutil` mutation、`tempfile` 场景仍必须失败。
- 失败统一落 `[F-v3-logic-action-purity-violation]`。

### 5.3 `sys.path` hack 必须在编译期失败

- skill-local action 不得修改或扩展 `sys.path`，也不得通过等价方式改变 Python import 搜索边界来绕过 skill/source root。
- 失败必须是编译期 purity FATAL，不能靠 runtime import error 或 module sandbox 偶然失败。
- 现有测试里为了测试包导入而出现的 `sys.path` 操作不属于 skill-local action 扫描对象，本 WS 不得把这些测试文件误判成 skill 违规。

### 5.4 import 越界必须在编译期失败

- skill-local action 不得通过 import 或 import 辅助 API 越过 action 边界取得运行编排入口、本地文件系统逃逸能力或动态加载任意本地模块的能力。
- “越界”的权威语义以 `skill-syntax` 的 action 寻址契约、`compile-rules` 的 purity 规则和 `01-compile` 的 module sandbox 边界为准；本需求书不复制允许/禁止清单。
- Codex 的 RED 测试至少要覆盖通过 import 取得 `run_skill` 编排入口、通过 import/路径 hack 绕出本地 action 边界这两类高风险回归。

### 5.5 错误契约与兼容性

- 本 WS 复用现有 `[F-v3-logic-action-purity-violation]`，默认不新增错误码、不改 `ERROR_REGISTRY` key set、不改 `ErrorCodeMetadata` 形状。
- purity violation 的 `api` / `reason` 文案可由实现者决定，但必须能让使用者看懂违规类别，并在测试中断言关键语义而不是脆弱全文。
- 纯标准库计算、字符串处理、JSON 解析、普通函数调用等非副作用 action 不能被误杀。
- 现有 tool Context facade import 禁令不回归。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

Codex 必须先写 RED 测试，Claude 契约门通过后才能写实施任务书。标 ★ 的必须走真实 `SkillLoader.compile_skill` 或等价编译路径，不许只 mock scanner 到绿。

- Scanner 单元：新增或扩展 `test_purity_characterization.py`，覆盖 `run_skill`、文件系统读、`sys.path` 修改、import 越界相关源码片段会产出 `PurityViolation`；纯计算、普通只读数据转换、现有安全调用仍不产出 violation。
- 既有回归：保留并扩展现有 local-write API、`tempfile`、path mutation、`os`/`shutil` mutation 的断言；不得让当前已覆盖的违规变成非违规。
- ★ `run_skill` 编译期 FATAL：构造最小 V0.3 skill，action 源码调用 `run_skill`，`SkillLoader.compile_skill` 必须抛 `SkillLoadError`，payload code 为 `[F-v3-logic-action-purity-violation]`。
- ★ FS 读写编译期 FATAL：最小 V0.3 skill 中 action 直接读文件或写文件时都必须在 compile 阶段失败，且 code 相同。
- ★ `sys.path` 编译期 FATAL：最小 V0.3 skill 中 action 修改 import 搜索边界时必须在 compile 阶段失败，且 code 相同。
- ★ import 越界编译期 FATAL：最小 V0.3 skill 中 action 通过 import/动态加载路径取得禁止能力时必须在 compile 阶段失败，且 code 相同。
- 负面编译路径：最小 V0.3 skill 中纯 action 仍能 compile；现有 `test_in_tree_action_reference_still_loads` 不回归。
- 错误码注册回归：断言本 WS 不改变 `ERROR_REGISTRY` key set 或 `ErrorCodeMetadata` 形状；若测试环境已有 WS-E3 改动，则至少断言 purity violation code 仍注册为编译期 FATAL。
- tool Context facade 回归：`scan_tool_imports_context` 的既有禁令仍有效，不被 purity 扩展覆盖掉。
- 误报保护：engine 包内公开 `run_skill`、内置工具模块和测试辅助文件不应因为本 WS 逻辑被全仓扫描误杀；测试应聚焦 loader 扫描 skill-local action/tool 文件的路径。
- 验证命令至少覆盖：`uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_tool_paths_escape.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q`。

## 7. 硬依赖约束(若 WS 内组件间有强制先后)

1. Scanner 单元行为必须先稳定；真实 loader 编译路径测试只能承接同一套 violation 语义，不能写两套互相矛盾的规则。
2. 真实 compile-path 测试必须确认错误码、定位和非违规 action 兼容性，才允许 Codex 写给 Gemini 的实施任务书。
3. 与 WS-E1 的顺序约束是交付级：E6 完成后，E1 才能把 `run_skill` 禁令作为完整 LOGIC 干净契约验收项；E6 未完成时，E1 必须显式降级。

## 8. 验收标准(硬退出,IR4)

- [ ] §6 RED 测试先失败，契约门通过后实现到 GREEN。
- [ ] skill-local action 中 `run_skill` 编排在 `SkillLoader.compile_skill` 阶段报 `[F-v3-logic-action-purity-violation]`。
- [ ] skill-local action 中文件系统读、写、变更、临时文件等直接 FS 访问在 compile 阶段报同一 purity FATAL。
- [ ] skill-local action 中 `sys.path` hack 在 compile 阶段报同一 purity FATAL。
- [ ] import 越界高风险路径在 compile 阶段报同一 purity FATAL。
- [ ] 已有 local-write API、tool Context facade import 禁令不回归。
- [ ] 纯计算 action、现有 in-tree action compile 路径不被误杀。
- [ ] `ERROR_REGISTRY` 不因本 WS 改动；purity violation code 仍是编译期 FATAL。
- [ ] 不修改 `loader.py`、`module_sandbox.py`、`error_registry.py`、`graph_assembler.py`。若最终确需改，必须有 PM 明确扩 owns 记录。
- [ ] 至少一条真实 compile-path e2e 通过，不是纯 scanner mock 到绿。
- [ ] `uv run pytest packages/graph-agent/tests/core/test_purity_characterization.py packages/graph-agent/tests/core/validators/test_tool_paths_escape.py packages/graph-agent/tests/core/validators/test_purity_le2.py -q` 通过。

## 9. 不做(范围锁定,IR7)

- 不改 LOGIC runtime 执行模型，不砍 Context mutation，不把 action 改成纯返回；这些归 WS-E1。
- 不实现 `iterate` / `SUBGRAPH` 迁移，不替现有 live action 改业务逻辑。
- 不改 `error_registry.py`、不新增错误码、不做错误契约 V2 details/diagnostics/remediation/doc_url；这些归 WS-E3。
- 不改 `loader.py` 或 `module_sandbox.py`，除非契约门后 PM 明确扩 owns。
- 不改 V4 trace 事件或 diagnostic event；这些归 WS-E4。
- 不做 checkpoint、resume、golden、studio、gateway 相关改动。
- 不扫描整个仓库 Python 文件当 purity 对象；purity 对象是 loader 识别的 skill-local action/tool 文件。
- 范围外问题记 `docs/deferred-items.md`，不得顺手改。

## 10. baseline 回写指令(IR6)

实现落地后，Codex 按真实代码回写：

- `docs/engine/mvp1/02-mechanism/01-compile/baseline.md`：记录 `scan_python_purity` 已覆盖的真实 hard-ban 范围、错误码和仍不覆盖的边界。
- `docs/engine/mvp1/01-contract/03-compile-rules/baseline.md`：记录 purity 规则现状已从 local-write 扩展到 LE2 对应项；若 `ERROR_REGISTRY` 未改，必须诚实写“复用既有码”。
- `docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md`：只回写 LE2 编译期 purity guard 已落地；不得把 LE1 纯返回、Context mutation 退场、iterate 迁移提前写成现状。
- 如 `docs/engine/mvp1/01-contract/02-skill-syntax/baseline.md` 有对应现状差异表，也只按真实代码更新 purity 相关行，不提前写其它 LOGIC 目标。

## 11. 评审检查点

- 契约门(Claude 审测试)：重点查 RED 是否忠实编码 LE2 目标，是否覆盖真实 compile path，是否把 `run_skill`、FS、`sys.path`、import 越界都落到同一 purity FATAL，并且没有把 WS-E1/WS-E3/WS-E4 范围拉进来。
- Codex 审查退出：只按 §8 硬退出条件，不按“scanner 单测绿了”主观放行；尤其要看真实 `SkillLoader.compile_skill` 路径、非违规 action 兼容性和错误码注册不变。
- Claude 终审：看意图是否落实、baseline 是否照真实代码诚实回写、测试是否存在只 mock 到绿或把未来 LOGIC runtime 目标当现状。

## 12. 给 Codex 的交接:按写作规范写 kiro task.md

契约门通过后，Codex 据已批准测试写 kiro `task.md`，落点 `.kiro/specs/engine-mvp1/task-ws-e6-purity-extensions.md`，遵守：

- 来源 = 已批准测试，测试是契约；不凭空设计实现步骤。
- 格式 = Phase 分段 + `- [ ]` 勾选项 + 每条挂 `_Requirements: <模块.功能>` + 验证命令。
- frontmatter 指回本需求书和 `spec_ssot`，不重写设计。
- 嵌入编排注解：`owns_files`、实现者 = Gemini、§8 硬退出。
- 行号 Codex 落地时自己重新核；本需求书行号只作 grounding。
- 不跑 `/kiro:spec-tasks`，避免 clobber。
- 同步输出 Gemini prompt，包含工作区路径、必读文件、RED 测试结果、owns_files/禁止触碰、目标行为、验证命令、回报格式。
- 完整规范见 `docs/development/task-spec-standard.md` §四 4.2。
