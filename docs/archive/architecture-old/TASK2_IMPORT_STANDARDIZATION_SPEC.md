# TASK2_IMPORT_STANDARDIZATION_SPEC

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务旨在完成 Monorepo 物理拆分后的逻辑缝合。核心目标是将 `graph-agent` 内部的大量相对导入转换为绝对导入（`from graph_agent...`），并将其作为独立 SDK 包的地位确立下来。同时，将顶层的 `tests/` 目录按业务归属拆分到各子包中，确保每个单元（Package/App）都能在各自的目录下独立运行测试与校验，实现真正的“焦点模式”。

## 2. 当前 Import 状况扫描

经过实测扫描（grep + read），当前代码库处于“物理已分，逻辑未断”的状态：

### A. `packages/graph-agent/src/graph_agent/`
*   **状况**: 存在 100+ 处相对导入。
*   **分布**: 
    *   一级相对 (`from .base import ...`): 约 60 处。
    *   二级相对 (`from ..callbacks import ...`): 约 40 处。
*   **重灾区**: `core/harness.py`, `core/loader.py`, `cognitive/middlewares.py` 等核心逻辑文件。

### B. `apps/studio/backend/app/`
*   **状况**: 表现良好。
*   **内部引用**: 统一使用 `from app.services import ...` 这种绝对路径（相对于其子项目根目录）。
*   **引擎引用**: 已在使用 `from graph_agent import ...`，得益于 Task 1 中 `uv workspace` 的自动链接。

### C. `tests/` 目录现状
*   **结构**: 
    *   `tests/graph_agent/`: 引擎核心测试。
    *   `tests/studio/` & `tests/studio_e2e/`: Studio 相关测试。
    *   `tests/compiler/`, `tests/golden/`, `tests/skills/`: 强依赖引擎的集成测试。
*   **引用**: 绝大部分测试已在使用 `from graph_agent.xxx`。

## 3. 转换规则

### 3.1 `packages/graph-agent` 内部：相对变绝对
所有在 `packages/graph-agent/src/graph_agent/` 下的 Python 文件，必须将其内部的相对导入转换为以 `graph_agent` 开头的绝对导入。

*   **规则示例**:
    *   在 `graph_agent/core/runner.py` 中：
        *   `from .loader import ...` -> `from graph_agent.core.loader import ...`
        *   `from ..callbacks import ...` -> `from graph_agent.callbacks import ...`
*   **工具选择**: 推荐使用 **LibCST** 进行自动化重写。LibCST 相比 `sed` 能更精确地识别导入层级并保持格式。

### 3.2 `tests/` 目录拆分规则
为了实现“焦点模式”，测试代码必须随源码走。

| 原始路径 | 目标路径 |
| :--- | :--- |
| `tests/graph_agent/` | `packages/graph-agent/tests/unit/` |
| `tests/compiler/`, `tests/golden/`, `tests/skills/`, `tests/scripts/` | `packages/graph-agent/tests/integration/` |
| `tests/studio/` | `apps/studio/backend/tests/` |
| `tests/studio_e2e/` | `apps/studio/tests-e2e/` |

### 3.3 配置文件处置
*   **`conftest.py`**: 拆分到对应的 `tests/` 目录下。
*   **`pyproject.toml`**: 更新各子项目的 `[tool.pytest.ini_options]`，确保 `pythonpath` 包含 `src`。

---

## 4. 实施 Sub-steps (a1 指南)

### T2.1: `graph-agent` 内部导入自动化重写 (0.5d)

1.  **准备脚本**: 在 `tools/` 目录下创建 `fix_imports.py`。

```python
# tools/fix_imports.py
import os
import libcst as cst
from pathlib import Path

class RelativeToAbsoluteTransformer(cst.CSTTransformer):
    def __init__(self, current_module_parts):
        self.current_module_parts = current_module_parts

    def leave_ImportFrom(self, original_node, updated_node):
        if updated_node.level > 0:
            # 计算绝对路径
            base_parts = self.current_module_parts[:-updated_node.level]
            if updated_node.module:
                module_attr = updated_node.module
                if isinstance(module_attr, cst.Name):
                    suffix_parts = [module_attr.value]
                else: # Attribute
                    suffix_parts = self._get_attr_parts(module_attr)
                new_module_parts = base_parts + suffix_parts
            else:
                new_module_parts = base_parts
            
            # 构建新的 Name 或 Attribute 节点
            new_module_node = self._build_module_node(new_module_parts)
            return updated_node.with_changes(level=0, module=new_module_node)
        return updated_node

    def _get_attr_parts(self, node):
        if isinstance(node, cst.Name):
            return [node.value]
        return self._get_attr_parts(node.value) + [node.attr.value]

    def _build_module_node(self, parts):
        res = cst.Name(parts[0])
        for part in parts[1:]:
            res = cst.Attribute(value=res, attr=cst.Name(part))
        return res

def process_file(file_path, package_root):
    rel_path = file_path.relative_to(package_root)
    module_parts = ["graph_agent"] + list(rel_path.with_suffix('').parts)[1:]
    
    with open(file_path, 'r', encoding='utf-8') as f:
        code = f.read()
    
    tree = cst.parse_module(code)
    transformer = RelativeToAbsoluteTransformer(module_parts)
    modified_tree = tree.visit(transformer)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(modified_tree.code)

if __name__ == "__main__":
    pkg_root = Path("packages/graph-agent/src")
    for py_file in pkg_root.rglob("*.py"):
        print(f"Processing {py_file}...")
        process_file(py_file, pkg_root)
```

2.  **执行重写**: 运行 `uv run python tools/fix_imports.py`。
3.  **格式化**: 运行 `uv run ruff format packages/graph-agent`。
4.  **校验**: 
    *   `uv run mypy packages/graph-agent/src --strict`
    *   `uv run python -c "import graph_agent; print('Import OK')"`

### T2.2: 测试目录拆分 (0.3d)

1.  **物理移动**:
    ```bash
    mkdir -p packages/graph-agent/tests
    git mv tests/graph_agent/* packages/graph-agent/tests/
    git mv tests/compiler tests/golden tests/skills tests/scripts packages/graph-agent/tests/
    
    mkdir -p apps/studio/backend/tests
    git mv tests/studio/* apps/studio/backend/tests/
    
    mkdir -p apps/studio/tests-e2e
    git mv tests/studio_e2e/* apps/studio/tests-e2e/
    
    git rm tests/__init__.py tests/conftest.py
    ```
2.  **清理残留**: `rm -rf tests/`。

### T2.3: 验证与修复 (0.2d)

1.  **更新子项目 `pyproject.toml`**:
    *   在 `packages/graph-agent/pyproject.toml` 中添加:
        ```toml
        [tool.pytest.ini_options]
        testpaths = ["tests"]
        pythonpath = ["src"]
        ```
    *   在 `apps/studio/backend/pyproject.toml` 中添加:
        ```toml
        [tool.pytest.ini_options]
        testpaths = ["tests"]
        pythonpath = ["."]
        ```
2.  **运行全量测试**:
    *   `cd packages/graph-agent && uv run pytest`
    *   `cd apps/studio/backend && uv run pytest`

---

## 5. 风险点与缓解

1.  **Circular Import**: 
    *   **风险**: 某些代码以前靠相对导入“躲避”了显式的循环依赖。转换后可能会暴露 `ImportError`。
    *   **缓解**: 如果发生，优先考虑将公共逻辑提取到 `graph_agent.core.types` 或 `graph_agent.core.utils`。
2.  **动态导入路径**:
    *   **风险**: `loader.py` 或 `module_sandbox.py` 中若有基于字符串拼接的路径（如 `f"src.core.{pkg}"`），AST 脚本无法识别。
    *   **缓解**: 需手动 grep `src\.core` 并批量替换。
3.  **Test Fixture 丢失**:
    *   **风险**: `tests/conftest.py` 包含跨项目的 Mock。
    *   **缓解**: 对于通用的 Agent Mock，建议在 `packages/graph-agent` 中创建一个 `graph_agent.testing` 模块，将常用 fixture 导出供其他子项目复用。

## 6. 工时估算

*   **T2.1 (自动化改写)**: 3h (含脚本调试与 MyPy 修复)
*   **T2.2 (目录拆分)**: 1h
*   **T2.3 (测试环境适配与验证)**: 4h
*   **总计**: 8h (1 dev-day) - **合理**。

## 7. 验收 Checklist

- [ ] 运行 `grep -r "from \." packages/graph-agent/src` 返回结果为空（除 `__init__.py` 的极简导出外）。
- [ ] 运行 `grep -r "src\.core" .` 返回结果为空。
- [ ] `packages/graph-agent` 下 `uv run pytest` 全绿。
- [ ] `apps/studio/backend` 下 `uv run pytest` 全绿。
- [ ] `uv run mypy --strict .` 无导入相关的错误。
- [ ] FastAPI Server (`uv run uvicorn`) 能够无错启动。
