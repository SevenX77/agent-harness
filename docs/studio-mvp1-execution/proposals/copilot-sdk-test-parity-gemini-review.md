这里是对方案 D-corrected 的架构审查及开放决策意见。

### 1) D-corrected 架构审查与潜在风险

D-corrected 整体方向非常精准，特别是自包含的 `run_route_sdk_smoke` 驱动器和受控并发（Semaphore + timeout），成功规避了全局状态污染和子进程炸弹，并且正确利用了现有的按路线更新前端 UI 的机制。

**发现的风险与修正建议：**
- **Pydantic 序列化风险 (CRITICAL):** 方案提到 `RoleTestJobResponse.result` 带有 `extra="forbid"`。如果你在 `routers/llm.py` 中直接往字典里塞 `result["sdk_evidence"] = ...`，当 FastAPI 尝试用 Pydantic 模型将其序列化返回时，会直接抛出 `ValidationError` 并返回 HTTP 500。
  - **修法:** 必须在后端的 `RoleTestResponse` Pydantic 模型中显式添加 `sdk_evidence: Optional[Dict[str, Any]] = None`，否则后端验证过不去，根本到不了前端。
- **角色标识符:** 完全同意使用 `role_kind == "copilot"` 作为判定门，而不是通过 `role_name`。这是领域模型中唯一健壮的类型标识。确保 `config/llm_roles.yaml` 中所有的 copilot 角色都正确打上了 `role_kind: copilot`。
- **清理逻辑:** `with tempfile.TemporaryDirectory() as tmp:` 是对的，但务必确保 CLI 子进程在收到 timeout 或抛出异常时能被完全 SIGTERM 杀掉，否则会产生僵尸进程并锁住临时目录导致磁盘清理失败。

### 2) 开放决策判断

**a) Replace vs Layer (取代还是作为预闸):**
**决断：Replace（完全取代）。**
**理由：** 既然目标是验证真实运行时路径，httpx 探活就成了多余的噪音。保留预闸会引入两种状态（"网络通但 spawn 败"），徒增解释成本，且网络请求和子进程启动加起来会拖慢整体测试速度。只要我们在 `run_route_sdk_smoke` 内部先做配置前置校验（如 `_resolve_route_runtime` 失败提前返回），直接走 SDK spawn 就是最诚实的测试。

**b) 整体判定 (Verdict: Any vs All):**
**决断：任一 admit 路线 OK 即为整体 Pass。**
**理由：** Copilot 的核心设计是 Fallback 路由机制。如果主要提供商（如 Anthropic）宕机，但后备（如 Bedrock）可用，系统在运行时就是可工作的。要求所有路线都通过（All）不符合业务现实，会导致用户面对明明能用的 Copilot 却看到一片红灯。在聚合 copilot 结果时，只要有一个路线状态为 `ok`，整体结果就是 `ok`。

**c) Tool-loop 深度 (证明 Tool Loop 还是 Text-only):**
**决断：V1 阶段使用 Text-only Done。**
**理由：** 引入真实的 Tool Call（例如写个文件让 LLM 去读）会让原本确定性的连通性测试变成依赖 LLM 认知能力的“概率性测试”。你无法保证模型在测试 prompt 下 100% 决定调用工具，一旦模型决定直接回复，测试就会 flaky。Text-only 已经完整走通了：`spawn 子进程 -> 注入 env -> 建立 IPC/Stream -> 接收解析事件` 这个核心管道。具体的 Tool 解析逻辑通过 Mock 单测覆盖即可。在 Smoke 环节，稳定和快速比功能穷尽更重要。

### 3) 有没有更简单的替代设计？

目前 D 的设计已经趋近最优解，它在“复用现有 UI/Job 机制”和“保证底层运行时一致性”之间找到了平衡。

**唯一可以更简单的变体（D-Minimal）：**
如果你想**完全避免任何 API 契约和 schema 的修改**（省去 `sdk_evidence` 的扯皮），可以这样做：
- 把关于哪个路线 fallback、具体证据的信息，直接格式化成结构化的 Markdown/Plain text，塞进现有 `provider_statuses[].message` 字段中。
- 前端原样展示这个 message。
- 整体的 verdict 判定直接在合并 `_run_role_test_targets` 结果时被重写（如果检测到 target 包含 `role_kind == "copilot"`，则应用 "Any OK = Pass" 逻辑）。

这样，改动严格收敛在 `routers/llm.py` 和 `services/copilot.py`，前后端通信契约字节级零修改。如果是 MVP1，强烈建议先用这个 **D-Minimal** 变体。
