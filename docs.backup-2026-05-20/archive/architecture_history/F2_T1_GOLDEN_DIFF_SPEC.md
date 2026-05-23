# F2_T1_GOLDEN_DIFF_SPEC (Golden Diff 可视化)

**版本**: 1.0
**日期**: 2026-05-05
**状态**: 待执行 (a1 codex)

## 1. Executive Summary

本任务旨在为 PM 提供自动化的技能输出质量评估工具。通过将当前运行（Run）的输出与预设的黄金标准（Golden Baseline）进行字段级比对，系统能够自动计算相似度得分，并以直观的左右分屏视图展示文本、数值、列表及嵌套字典的差异。这将显著减少 PM 的肉眼比对负担，使 prompt 调优过程更加定量化和透明化。

## 2. PM 痛点

### 2.1 现状
*   **肉眼比对**: 跑完技能后，PM 必须在 Trace 或日志中手动寻找输出字段，并回忆或翻阅之前的“最佳实践”进行对比，效率极低。
*   **主观偏差**: 缺乏统一的质量标准，不同时间点或不同 PM 对同一输出的评价标准可能不一致。
*   **回归风险**: 修改 prompt 后，可能修复了 A 点但导致 B 字段质量下降，这种微小变化在长文本输出中极难被发现。

### 2.2 理想 UX
*   **一键对比**: 运行结束后，点击“Compare to Golden”直接进入对比视图。
*   **多维差异展示**: 
    *   **文本**: 高亮行级增删（绿增红删）。
    *   **数值**: 显示绝对差值及百分比变化。
    *   **字典/列表**: 支持递归展开，仅显示有差异的部分。
*   **相似度得分**: 顶部显示总分（0-100），并根据分值自动改变颜色（红-黄-绿）。
*   **基准晋升**: 评估满意后，点击“Promote to Golden”将当前输出设为新的基准。

## 3. 后端 API 契约

### 3.1 改造 `models/compare.py`
扩展 `CompareResult` 以支持结构化差异：
```python
class FieldDifference(BaseModel):
    field_path: str        # e.g. "output.answer"
    type: str              # "text", "number", "bool", "list", "dict"
    current_value: Any
    golden_value: Any
    score: float           # 该字段的相似度 (0.0 - 1.0)
    changed: bool

class CompareResult(BaseModel):
    differences: list[FieldDifference]
    total_score: float     # 整体相似度 (0.0 - 100.0)
    golden_run_id: str
```

### 3.2 完善 `routers/compare.py`
实现 `POST /api/skills/{skill_id}/runs/{run_id}/compare`：
*   **逻辑**: 
    1.  从存储加载当前 Run 的 `final_state.json`。
    2.  加载该 Skill 的最新 Golden 输出。
    3.  执行深度比对算法（数值计算 delta，文本计算 Levenshtein 或简单 line-diff）。
    4.  返回 `CompareResult`。

### 3.3 完善 `routers/golden.py`
实现 `POST /api/skills/{skill_id}/golden`：
*   **逻辑**: 接收 `run_id`，将该运行的输出复制到 `golden/` 目录下并更新元数据。

---

## 4. 前端组件设计

### 4.1 目录结构
```
apps/studio/frontend/src/
├── components/diff/
│   ├── DiffView.tsx           # 主容器，左右分屏布局
│   ├── DiffHeader.tsx         # 顶部 Score Badge 与操作按钮
│   ├── DiffField.tsx          # 递归调度器
│   └── views/
│       ├── TextDiffView.tsx   # 文本对比 (基于 line-by-line)
│       ├── NumberDiffView.tsx # 数值对比 (+/- delta)
│       └── ArrayDiffView.tsx  # 列表比对
├── hooks/
│   └── useGoldenDiff.ts       # 封装 compare API 调用逻辑
└── utils/
    └── diffAlgorithms.ts      # 前端辅助比对工具
```

### 4.2 类型映射表

| 字段类型 | UI 组件 | 样式特征 |
| :--- | :--- | :--- |
| `str` | `TextDiffView` | 左右分栏，红色背景代表删除，绿色背景代表新增 |
| `int/float` | `NumberDiffView` | 蓝色字显示 Golden，黑色字显示 Current，括号显示百分比 |
| `bool` | `DiffField` | 简单的图标对比 (✅ vs ❌) |
| `dict` | `DiffField` (递归) | 缩进显示，带有折叠箭头 |

---

## 5. 实施 Sub-steps (a1 指南)

### T1.1: 后端比对引擎 (4h)
1.  在 `app/services/skills.py` 增加 `compare_with_golden` 函数。
2.  实现深度递归比对，对于字符串使用 `difflib.ndiff` 或简单的字符比对。
3.  完善 `routers/compare.py` 接口。

### T1.2: 通用 Diff 组件库 (6h)
1.  实现 `TextDiffView.tsx`: 自定义行比对逻辑，高亮差异字符。
2.  实现 `NumberDiffView.tsx`: 自动计算并展示变化率。
3.  实现 `DiffField.tsx`: 核心递归引擎，能够处理嵌套对象。

### T1.3: 主视图与集成 (4h)
1.  在 `RightPanel.tsx` 增加 `diff` Tab。
2.  在 Trace 结束后（`RunStatus === 'success'`）在底部显示“View Comparison”悬浮按钮。
3.  实现 `DiffHeader` 中的“Promote to Golden”功能。

### T1.4: 联调与美化 (2h)
1.  适配暗色模式，确保红/绿对比色在深色背景下不刺眼。
2.  测试在大规模 JSON 输出下的渲染性能。

## 6. 风险与缓解
*   **列表对齐**: 如果列表元素顺序变了，Diff 会全红。
    *   *缓解*: V1 仅支持有序比对，若列表较大且顺序无关，建议在 SDK 侧声明字段属性（未来扩展）。
*   **大文本性能**: 极长文本的 Diff 计算会卡顿。
    *   *缓解*: 对超过 5000 字符的文本仅进行概览比对，点击详情后再完整渲染。

## 7. 验收 Checklist
- [ ] Run 成功后，可以进入比对 Tab。
- [ ] 文本字段能够清晰看到改动了哪些单词/行。
- [ ] 数值变化自动显示百分比（如：Cost increased by 12%）。
- [ ] 点击 Promote 按钮后，再次运行能看到对比基准已更新。
- [ ] 嵌套字典的层级显示正确且可折叠。
