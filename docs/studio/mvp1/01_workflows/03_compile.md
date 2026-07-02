# 03 · Compile(编译校验 + 错误呈现) — Workflow 节点

> **Tier**: workflow
> **旅程位**: authoring 搭图/编辑 → **compile 编译绿灯** → predict 试飞(下游 [04 运行与验收](./04_run-and-verify.md))
> **走查完整记录**(全部 atom actions + 决策 + 原话 + 测试关键点)。

## 旅程位
搭好图 → 实时 lint / 手动 Compile 校验 → **compile-pass(绿灯)才解锁 Predict**。检查内容(结构/字段/拓扑/IO 数据流/mention)由引擎 FROZEN spec 定,studio 只触发 + 呈现。

## Atom actions
| # | 动作 | 区域 | status |
|---|---|---|---|
| A1 | 编辑时实时 lint(防抖 800ms → POST /lint → 引擎编译查错) | editor/后台 | live |
| A2 | lint 状态 → build stage(checking→编译中 / failed→失败 / passed→通过) | 动作条 | live |
| A3 | 错误上下文标①:canvas 节点警告/错误小标志 + tooltip | canvas | target-design |
| A4 | 错误上下文标②:properties/io 特定属性旁 tooltip | properties/io | target-design |
| A5 | 错误上下文标③:编辑器 IDE 式行内标记 | editor | target-design |
| A6 | 点 Compile → drawer(不覆盖侧栏,可复制) | drawer | target-design |
| A7 | ~~底部浮层卡片列错误~~ | — | **删除**(现 CompileErrorPanel) |
| A8 | stage 门控 Compile→Predict→Run 逐级解锁 | 动作条 | live(predict-pass 段 bug) |
| A9 | predict-pass 永不置位 → Run 点不了 | 动作条 | bug(predict 桩,接 predict 时修) |
| A10 | 引擎 compile 检查(结构/字段/拓扑/IO 数据流/mention)+ F-v3-* 错误码 | 引擎 | live(FROZEN) |
| A11 | lint 失败退路(网络错/请求失败 → failed + 信息) | 动作条 | live |
| A12 | 空内容 → idle(没东西不报错) | — | live |
| A13 | 画布拓扑改动(连线/断线/删节点 → 改写 GRAPH.md)写盘成功后自动 relint,新结果替换三处投影(不许只清旧标记不重查) | canvas/后台 | live |

## 决策
- 错误呈现 = **3 处上下文标(canvas 节点 / 属性旁 / 编辑器行)+ 点 Compile 弹 drawer(可复制、不盖侧栏)**;删旧底部浮层卡片。
- 实时 lint **只标红(上下文),不弹全局面板/toast**(避免编辑中途不完整一直全局报错);详细汇总只在 Compile drawer 看。
- Compile 按钮保留(点 = 看详细错误 drawer);实时 lint 通过自动驱动 compile-pass。
- compile 检查内容 + F-v3 错误码沿用引擎 FROZEN spec,不自创。
- **lint 触发语义 = skill 源真相变更**,不是"编辑器文本变更":编辑器打字(防抖 800ms)和画布拓扑改动(写盘 GRAPH.md 成功后)都必须触发 relint;画布改动只清旧投影、不重查 = 缺陷(2026-07-01 PM 定)。
- **实时 lint 返回该次编译聚合出的全部错误**:引擎按 compile-rules「同阶段尽量聚合」收集,studio 展开完整 issues 列表投影,不得只取首错(2026-07-01 PM 定,废除"实时 lint = 单错误消费者"假设)。

## 原话(留底)
> 起源:PM 问"编译面板在哪里?""800ms编译一次,编译面板一直报错吗?"→ 核实:浮层只列不跳、只由手动 Compile 填;800ms lint 只改按钮色致编辑中途一直红。据此重做:
> "1. 方向对: 错误3处显示: 1. canvas节点, 警告错误小标志, tooltip显示此处错误/警告; 2. properties、io设置面板, 在特定的属性旁 tooltip显示此处错误/警告; 3. 编辑器, 就和ide的编译错误显示方式一样"
> "2. 把那个浮层卡片的面板去掉, 改成点击compile, 弹出一个drawer(不覆盖侧边栏), 列出详细的编译错误, 可以复制"

## 测试关键点
- 实时 lint 错误标在**对应**的节点/属性/编辑器行(不是全局)。
- 画布断线 → 对应节点立即亮 `[F-v3-graph-phase-island]`,无需打开编辑器或打字。
- 多个独立缺陷(多孤岛/多未知依赖/多节点缺块)一次全部显示;修掉一个不应"冒出"同阶段的下一个。
- 编辑中途不完整 → 只上下文标红,不弹全局面板/toast。
- 点 Compile → drawer 列全部错误(file:line - field - message),可复制、不覆盖侧栏。
- 门控:compile-pass 解锁 predict;predict-pass 解锁 run。

## 引擎需求
- compile 错误定位补齐(每条带 节点 + 字段 + 行 + 严重度)→ 引擎契约 [`compile-rules`](../../../engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md)。
- 错误聚合兑现「同阶段尽量聚合」(compile-rules §2.1):拓扑等阶段内的独立缺陷(多孤岛/多未知依赖)一次收齐、批量抛;完整缺陷集经异常 seam(`compile_result.issues`)暴露给 studio,每条 issue 显式带 source_path/line/field_path 定位轴(不再靠 location 字符串反解析)。
