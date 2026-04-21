# GraphAgent 工具函数编写规范

本文档定义了 GraphAgent 工具函数的编写标准。
当需要创建或审查工具函数时，参考此规范。

---

## 五条铁律

| # | 规则 | 说明 |
|---|------|------|
| 1 | 返回 `str` | 非 str 会被 `str()` 强转。推荐 `json.dumps({...})` |
| 2 | `context: dict` 自动注入 | 命名必须是 `context`，运行时绑定 `state["context"]`，不暴露给 LLM |
| 3 | docstring = prompt 工程 | 第一段 → 工具 description；Args 段 → 参数 description |
| 4 | 类型标注驱动 Schema | `str`/`int`/`float`/`bool`/`list`/`dict` 自动映射；有默认值 → optional |
| 5 | 通过 context 传递大数据 | 返回值只用摘要，大数据存 context |

---

## docstring 规范

LLM 决定是否调用工具，**完全依赖 docstring**。

### 坏的写法

```python
def save_entity(entity_id: str, context: dict) -> str:
    """保存实体。"""  # ❌ 太简略，LLM 不知道什么时候该调用
```

### 好的写法

```python
def save_entity(entity_id: str, name: str, description: str, context: dict) -> str:
    """为当前场景注册一个新实体。

    当发现文本中出现新角色、地点或关键物品时调用此工具。
    每个实体需要一个唯一 ID（格式: CHR_001, LOC_001, PROP_001）。

    Args:
        entity_id: 实体唯一标识（如 CHR_001）。
        name: 实体名称。
        description: 视觉外观描述（服装、特征、状态）。
    """
```

**第一段**（`"""` 到第一个空行）→ 映射为工具的 `description` 字段。
**Args 段**的每个参数描述 → 映射为 schema 中的参数 `description`。

---

## 返回值规范

```python
# ✅ 推荐：返回结构化 JSON 摘要
return json.dumps({
    "status": "ok",
    "entity_id": entity_id,
    "total_entities": len(registry),
    "msg": "已提取实体 CHR_001",
}, ensure_ascii=False)

# ❌ 避免：返回大段文本或原始数据
return str(entire_dataset)  # Agent 上下文会被垃圾数据淹没
```

---

## context 参数规范

`context` 可以在参数列表的**任意位置**（harness 按名称查找注入）：

```python
def tool_a(entity_id: str, context: dict) -> str: ...   # ✅
def tool_b(context: dict, entity_id: str) -> str: ...   # ✅
def tool_c(entity_id: str, name: str, context: dict) -> str: ...  # ✅
```

如果函数**不需要**读写全局状态，可以不声明 `context`：

```python
def simple_calc(a: int, b: int) -> str:  # ✅ 无 context，所有参数暴露给 LLM
    """两数相加。"""
    return str(a + b)
```

---

## 数值钳制规范

LLM 返回的数值可能超出合法范围，必须双向钳制：

```python
# ❌ 直接赋值
confidence = min(val, 1.0)

# ✅ 双向钳制
confidence = max(0.0, min(float(val), 1.0))
```

---

## 完整示例

```python
import json
from typing import Any


def extract_entities(
    text: str,
    entity_type: str = "all",
    context: dict[str, Any] = None,
) -> str:
    """从文本中提取结构化实体。

    当需要从原始文本中识别和提取人物、地点、物品等实体时调用此工具。
    每个实体会被赋予唯一 ID 并存入全局注册表。

    Args:
        text: 待分析的原始文本片段。
        entity_type: 提取类型过滤（"all" | "character" | "location" | "prop"）。
    """
    if context is None:
        context = {}

    registry = context.setdefault("entity_registry", {})

    entity_id = f"ENT_{len(registry) + 1:03d}"
    registry[entity_id] = {
        "text_source": text[:50],
        "entity_type": entity_type,
    }

    return json.dumps(
        {
            "status": "ok",
            "entity_id": entity_id,
            "total_entities": len(registry),
            "msg": f"已提取实体 {entity_id}",
        },
        ensure_ascii=False,
    )
```
