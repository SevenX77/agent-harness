# PR-5 引擎强类型沙盒安全防线与底层污染修复 (Research)

## 1. 核心问题定位实证

### 1.1 `ModuleSandbox` 泄露 `sys.modules`
- **涉及文件**: `packages/graph-agent/src/graph_agent/core/module_sandbox.py` (L100, L139 附近)
- **事实依据**:
  在 `_load_module` 与 `_load_from_file` 的代码段中，出现了如下注册逻辑以配合前向引用特性：
  ```python
  sys.modules[spec.name] = module
  spec.loader.exec_module(module)
  _rebuild_pydantic_models(module, spec.name)
  ```
  在同步完成编译和 `model_rebuild` 后，没有任何针对这把“借来的”字典锁匙做归还（`pop`）的操作。
- **危害后果**: 在企业级大规模加载各类包含例如 `utils.py` 等命名极其常见的独立模块时，不同的 Skill 会对 `sys.modules['utils']` 或 `sys.modules[sandbox_name]` 进行覆写竞争；且模块卸载无法自动触发，留下了巨额的内存泄露和路由抢占盲区。

### 1.2 `LLMClientManager` 缺锁争抢与连接长期僵死
- **涉及文件**: `packages/graph-agent/src/graph_agent/models/llm_client_manager.py`
- **事实依据**:
  ```python
  class LLMClientManager:
      _clients: ClassVar[dict[str, OpenAI | Anthropic]] = {}
  ```
  该类用于持有针对 Provider 的实际通信实例。`_clients` 映射缓存的读取和写入未加入 `threading.Lock`。并且类方法中缺失清空并安全断开 HTTP Pool `client.close()` 的方法。
- **危害后果**:
  - 无锁：多线程并发触发首次请求时，存在高并发的覆盖实例化现象。
  - 无析构：导致所有初始化后被缓存在底层的 TCP 异步连接池将跟随当前宿主进程长驻。如果在 CLI Watch 模式或者 Server 长运行时触发大量的模型类型变更，将导致连接堆积乃至 OOM。

### 1.3 `hoist_to` 与配置对象被错误地 Monkey-patch (已在 PR-3 解决)
- **涉及文件**: `packages/graph-agent/src/graph_agent/core/loader.py` 与 `packages/graph-agent/src/graph_agent/core/skill_builder.py` 关联链路。
- **事实依据**:
  由于早期实现的“图快”，对于诸如 `hoist_to` 这种依附在 Phase XML 定义层面的配置（表示将本层某变量推向输出空间），曾经通过直接向加载好的 `validator` / `action` 函数进行属性挂载 `func.hoist_to = "xxx"`。
- **当前现状 (无危害)**:
  finding3 (a3-5 猴补丁): grep `\.hoist_to =` 全仓零匹配（猴补丁写入已不存在）；且 V0.3.0 **根本无活的 hoist_to 机制**（无 LLMPhase 类 / 无 hoist_to 字段定义），唯一引用在死代码 `skill_validator.py` → **纯 NO-OP，本 PR 不改 src**。无需测试（机制不存在）；`skill_validator.py` 死代码建议 PR-6 治理清理。

### 1.4 Schema 解析防线 (现状已充分校验)
- **涉及文件**: `packages/graph-agent/src/graph_agent/core/loader.py`。
- **事实依据**:
  经实证代码复核，当前 `loader.py` 中的 `_validate_inline_io_schema` (约 L1202 附近) 已经完整实施了针对 schema 的 `isinstance(schema, dict)` 断言以及 `Draft202012Validator.check_schema(schema)` 的强校验。
- **结论**: 此处已不存在弱类型裸透传的防线缺口，输入结构损坏会在加载阶段正常通过校验器抛出 SchemaError 并 Fail-loud。本 PR 无需修复。
