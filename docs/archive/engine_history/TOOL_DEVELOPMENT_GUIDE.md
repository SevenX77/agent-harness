# TOOL_DEVELOPMENT_GUIDE

本指南说明如何为 `graph_agent` 编写工具函数。

## 1. 设计原则

1. 工具是 framework 与业务之间的最小接缝
2. 工具函数尽量保持单一职责
3. 业务工具放在 skill 本地 `tools/`，不要污染 framework
4. framework 自带工具只保留跨项目通用能力

## 2. 函数签名约定

`graph_agent` 的工具包装器会把普通 Python 函数适配成 LangChain tool。

推荐签名：

```text
def tool_name(ctx, arg1, arg2="") -> str
```

约定如下：

- 优先使用 `ctx` 作为上下文参数名
- 向后兼容 `context`，但新代码不要再新增这个命名
- 没有上下文依赖的工具可以不接 `ctx`
- 返回值统一转换为字符串给 LLM

## 3. 不要使用 `@tool`

`graph_agent` 依赖 `_wrap_tool_for_langchain()` 对普通函数做包装。

因此：

- 不要给 skill 本地工具加 `@tool`
- 不要直接返回 LangChain `BaseTool`
- 不要在工具层再做一层 schema 包装

## 4. 上下文读写规则

推荐模式：

1. 从 `ctx` 读取输入
2. 进行纯确定性处理或调用外部服务
3. 将关键结果写回 `ctx`
4. 返回简短、可读的字符串摘要

适合写入 `ctx` 的内容：

- 下游 Phase 需要复用的结构化结果
- 调试和可观测性需要的中间产物
- 最终 `io.outputs` 声明会读取的结果

不适合写入 `ctx` 的内容：

- 超大二进制内容
- 只能由宿主项目管理的句柄或连接对象
- 与单次运行无关的全局缓存

## 5. 参数与返回值

工具参数建议保持简单：

- `str`
- `int`
- `bool`
- `list[str]`
- `dict[str, Any]` 对应的 JSON 字符串

如果 LLM 传入的是 dict/list，包装器会先尝试转成 JSON 字符串再交给 Pydantic 校验。

返回值建议：

- 成功：一句摘要，说明做了什么、产出了什么
- 失败：抛异常，或者返回清晰的错误文本

## 6. 非阻塞歧义处理

如果工具发现规则、输入或边界不清晰：

- 不要静默吃掉
- 不要擅自终止整个 workflow
- 优先让 agent 调用 `log_ambiguity`

工具函数本身适合做的是：

- 返回可解释的错误
- 或把必要上下文写入 `ctx`，让下一次 agent 决策更稳

## 7. 异步调用

如果底层实现是 async：

- 不要在工具里直接 `asyncio.run()`
- 使用 `tools._providers.run_async()` 做桥接

这样可以避免在已有事件循环内再次启动 loop 导致崩溃。

## 8. 与多模态工具协作

framework 自带的多模态工具位于 `graph_agent/tools/`，它们是通用能力。

业务工具如果要复用多模态能力，推荐方式是：

1. 由业务工具准备 prompt / 输入数据
2. 调用通用多模态工具或统一客户端
3. 只把业务相关的解释与组装逻辑留在 skill 本地

## 9. 错误处理建议

- 确定性输入错误：直接抛 `ValueError` / `FileNotFoundError`
- 可重试外部错误：抛原始异常，让上层 trace 留痕
- 非致命问题：写入 `ctx` 或返回警告文本，但不要伪装成成功

## 10. 最佳实践清单

- 优先使用 `ctx`
- 返回字符串摘要
- 只写必要的 `ctx` 字段
- 不直接依赖宿主项目的具体文件管理类
- 不在工具里复制 framework 层已有逻辑
