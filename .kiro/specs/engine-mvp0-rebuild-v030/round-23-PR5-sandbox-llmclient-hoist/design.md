# PR-5 引擎强类型沙盒安全防线与底层污染修复设计 (Design)

## 1. 契约继承与变动表 (SOP-06)

本 PR 聚焦于 V0.3.0 引擎底层的并发安全、内存防泄漏与严格对象隔离的健壮性补强，属于 charter 范围内批准项。重点修复 `ModuleSandbox` 的跨 Skill 全局污染、`LLMClientManager` 的连接泄漏及猴补丁（Monkey-Patching）的引用竞争。

### 1.1 核心组件继承与影响表面

| 影响面 | 变更摘要 | 兼容性分类 | 迁移路径 |
| :--- | :--- | :--- | :--- |
| **`LLMClientManager` 并发安全与生命周期** | [NEW] 引入 `_lock: ClassVar[threading.Lock]` 保护所有读写操作；[NEW] 新增 `@classmethod def close_all(cls) -> None`，用于关闭并清理 httpx Client 缓存池。 | [COMPATIBLE] | 业务获取 Client 接口签名不变。上层长驻调度器（如 CLI/Studio Watcher）在结束或重置生命周期时，调用 `close_all()` 释放 TCP 连接防止 OOM。 |
| **`ModuleSandbox` 隔离漏洞 (sys.modules)** | [BREAKING] 改用 `try...finally` 包裹两处注入（`sys.modules[spec.name] = module` 和 `sys.modules[sandbox_name] = module`），并在 `exec_module` 与 `model_rebuild` 后立即弹出清理。 | [COMPATIBLE] | 运行期唯一反查 `sys.modules` 的是 md_to_json/skill_builder 的独立 `_graph_agent_skill_` 注册（PR-5 不动它）；且 Pydantic `model_rebuild` 为同步执行，load+pop 后 `model_validate` 仍成立（forward-ref 在 rebuild 时已解析）。 |
| **`hoist_to` 及其它运行时配置挂载** | [NO-OP] finding3 (a3-5 猴补丁): grep `\.hoist_to =` 全仓零匹配（猴补丁写入已不存在）；且 V0.3.0 **根本无活的 hoist_to 机制**（无 LLMPhase 类 / 无 hoist_to 字段定义），唯一引用在死代码 `skill_validator.py` → **纯 NO-OP，本 PR 不改 src**。 | [COMPATIBLE] | 无需测试（机制不存在）；`skill_validator.py` 死代码建议 PR-6 治理清理。 |
| **Schema 结构防御** | [NO-OP] 已在现有代码中解决。复核发现 `loader.py` 中 `_validate_inline_io_schema` 已经在使用 `Draft202012Validator.check_schema(schema)` 并断言 `isinstance(schema, dict)`，本 PR 不修。 | [COMPATIBLE] | 维持现状，无真实缺口。 |

## 2. 关键修复设计决策

### 2.1 [Must-Fix] LLMClientManager 无锁并发与长进程连接泄露
**缺陷:** 现在的 `LLMClientManager._clients` 字典由多核随时按需写入，高并发时会发生数据竞争导致客户端重复初始化；且 `OpenAI()` 与 `Anthropic()` 底层各持有 `httpx.Client` 连接池，无显式 `close()` 机制在长驻后台重跑时累积出内存 OOM 炸弹。
**设计:**
1. 为 `LLMClientManager` 加入线程锁机制：在任何新建 Client 的链路（如 `_get_openai_client`，`_get_anthropic_client`）均获取该锁。
2. 暴露 `close_all` 供长生命周期主控调用：
   ```python
   @classmethod
   def close_all(cls) -> None:
       with cls._lock:
           for client in cls._clients.values():
               if hasattr(client, "close"):
                   client.close()
           cls._clients.clear()
   ```

### 2.2 [Must-Fix] ModuleSandbox 沙盒残留导致同名模块抢占
**缺陷:** `core/module_sandbox.py` 为了使得有前置注解 (`from __future__ import annotations`) 的 Pydantic Class 能在 `model_rebuild` 时解析引用，在两处（`module_sandbox.py:100` 的 `sys.modules[spec.name] = module` 和 `:139` 的 `sys.modules[sandbox_name] = module`）进行了写入。然而代码在同步装载和 rebuild 后未做剔除，导致此映射泄露并在其他 Skill 使用同名模块时发生串台竞争。
**设计:**
改写加载期的 `exec_module`，确保两处均使用 `try...finally` 保护：
```python
sys.modules[spec.name] = module
try:
    spec.loader.exec_module(module)
    _rebuild_pydantic_models(module, spec.name)
finally:
    sys.modules.pop(spec.name, None)
```
同理，`:139` 处的 `sandbox_name` 挂载也必须使用相同的 `try...finally` 弹出。
**不可变隔离**：由于 `model_rebuild()` 已经在此生命周期闭环，离开 `finally` 后再弹出，不会引发运行期反射的异常，确保系统级 `sys.modules` 的极致纯净。

### 2.3 [Regression-Lock] hoist_to 猴补丁（Monkey-Patching）回归锁
**缺陷:** 曾经在早期的 a3-5 中存在对原函数对象直接赋值 `func.hoist_to = "key"` 的竞争隐患。
**设计:**
finding3 (a3-5 猴补丁): grep `\.hoist_to =` 全仓零匹配（猴补丁写入已不存在）；且 V0.3.0 **根本无活的 hoist_to 机制**（无 LLMPhase 类 / 无 hoist_to 字段定义），唯一引用在死代码 `skill_validator.py` → **纯 NO-OP，本 PR 不改 src**。无需测试（机制不存在）；`skill_validator.py` 死代码建议 PR-6 治理清理。

### 2.4 [No-Op] Schema 弱类型无校验裸透传 (已解决)
**事实复核:** 现状已校验充分。经复核，当前 `loader.py` 中的 `_validate_inline_io_schema` 方法已对 schema 进行了 `isinstance(schema, dict)` 及 `Draft202012Validator.check_schema(schema)` 的强校验。
**设计:**
已解决，本 PR 不修。原型期把事情做对，不为不存在的问题造修法。
