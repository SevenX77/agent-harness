# PR-5 引擎强类型沙盒安全防线与底层污染修复要求 (Requirements)

## 1. 目标
通过实施严格的沙盒安全边界重建和资源收敛策略，彻底修复 V0.3.0 引擎的四项重大隐患：彻底清除 `sys.modules` 的常驻污染；根除单例缓存下的并发争抢和连接泄漏（OOM）；解决 `hoist_to` 等因函数对象被直接猴补丁（Monkey-Patch）引发的多实例串改；补强加载初期的强类型 schema 防线。

## 2. 具体要求与验收标准 (Acceptance Criteria)

### 2.1 LLMClientManager 并发安全与连接显式清理
- **要求**: 
  - 为 `LLMClientManager` 引入 `_lock: ClassVar[threading.Lock] = threading.Lock()`，为涉及 `_clients` 映射实例化的代码区加锁。
  - 新增提供公共生命周期钩子 `@classmethod def close_all(cls) -> None:`：必须支持在加锁环境中遍历 `_clients`，主动调用各个 Client 的 `close()` 方法释放 TCP 资源，并随后 `clear()` 缓存。
- **验收**:
  - [Red/Green] 新增专门针对多线程初始化和调度 `LLMClientManager` 的测试断言（并发安全）；
  - [Red/Green] 新增显式调用 `close_all` 的断言测试，确认所有的 Client Mock 都能正确进入关闭流程。

### 2.2 ModuleSandbox 沙盒全局隔离与痕迹擦除
- **要求**: 
  - 在 `core/module_sandbox.py` 的加载点，强制使用 `try...finally` 进行原子化的挂载防护。无论后续 `exec_module` 还是 `_rebuild_pydantic_models` 是成是败，`finally` 内必须安全且即时通过 `sys.modules.pop(..., None)` 进行痕迹擦除。
- **验收**:
  - [Red/Green] 编写多级挂载的模拟模块加载测试。载入两个不同目录且内容相悖的同名（比如 utils.py）沙盒模块。使用主进程查询 `sys.modules` 必须返回空；且两个沙盒获取内部类的 id() 分配互不污染。
  - [Red/Green] **核心安全证据 a**：含 `from __future__ import annotations` + `Literal[...]` 的模型，load+pop 后 `model_validate` 仍成功（确认 forward-ref 运行期不被 pop 破坏）。
  - [Red/Green] **核心安全证据 b**：`model_rebuild` 失败路径下，`sys.modules` 的 key 仍被清理（验证 try/finally 的异常安全保证）。

### 2.3 根除 hoist_to 等配置项的 Monkey-Patch 竞争
- **要求**: 
  - finding3 (a3-5 猴补丁): grep `\.hoist_to =` 全仓零匹配（猴补丁写入已不存在）；且 V0.3.0 **根本无活的 hoist_to 机制**（无 LLMPhase 类 / 无 hoist_to 字段定义），唯一引用在死代码 `skill_validator.py` → **纯 NO-OP，本 PR 不改 src**。
- **验收**:
  - [NO-OP] 无需测试（机制不存在）；`skill_validator.py` 死代码建议 PR-6 治理清理。

### 2.4 Schema 强类型编译期校验
- **要求**: 
  - 现状已校验充分。经复核，当前 `loader.py` 中的 `_validate_inline_io_schema` 方法已对 schema 进行了 `isinstance(schema, dict)` 及 `Draft202012Validator.check_schema(schema)` 的强校验。
- **验收**:
  - [已解决] 本 PR 不修。无对应的红灯测试。
