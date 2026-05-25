# round-14 现状调研: Task B skill-compilation cutover

署名：a2
日期：2026-05-25

## 1. Loader 与 Manifest 的分支并存现状
在当前的 `packages/graph-agent/src/graph_agent/core/loader.py` 和 `manifest.py` 实现中，存在着典型的“为了向后兼容而妥协”的双轨逻辑：

- **XML + YAML 拓扑解析双轨**: `GRAPH.md` 的拓扑解析仍尝试从 markdown body 提取 `<phase />` 标签（见 `_extract_phase_attrs`）。即使在引入了 YAML 的 `phases:` 后，代码中还专门用了一个 `_phase_refs_to_raw_attrs` 方法（L166）把新的 YAML 格式“倒退”回旧的 XML-style raw 属性去进行旧版拓扑图检验。
- **Physical + Inline IO 双轨**: 当前只要 YAML 里面没有显式的 `io.inputs`，系统依然会悄悄 fallback 去调用 `_validate_io_schema` 去读 `io_inputs_ref` 指向的磁盘 JSON 文件。
- **SkillNodeAST 的残留**: 在 `manifest.py` 中，`SkillNodeAST` 依然与 `AgentNodeAST` 并列存在于 `PhaseAST` 联合类型中，导致后续所有的 schema visitor 都需要兼顾 `mode: skill` 和 `mode: agent`。

这种状态使得整个 Compiler 的维护成本极高，任何新的 IO 或者图连通性检查（如后续的 A7/A8 数据流校验）都需要同时照顾两条分支。

## 2. 已经 Ready 的基础设施
- **B5/B6 已 Ship**: Agent body 的 5 类 XML 提取，以及 `@type` Mention 校验在前期任务中已经成功并入主干。这意味着 AST 构建的最底层 parser 是完备的。
- **SkillResolverProtocol (PR δ)**: PR δ 已经将 `SkillResolverProtocol` DI 注入接口建设完毕（例如 `compile_skill` 签名已接纳 `skill_resolver` 参数）。这使得 B7 (子图目标解析) 可以直接消费该 Protocol 接口去递归调用，无需重新发明外部寻址逻辑。
- **StateMapper (PR γ2)**: 刚落地不久的三区隔离和 StateMapper 同样强烈需求 Compiler 侧能提供统一、干净的 AST（比如强制统一的 inline IO schema），来生成 phase-local input 漏斗，B1-B4 的完成恰好能填补这一块编译期的空缺。

## 3. Serializer 的隐性债务
在检索漏读点时，我审查了 `packages/graph-agent/src/graph_agent/core/graph_serializer.py`，这部分原本没有在原始 brief 的雷达内。
代码中的 `_render_fresh_graph` 函数直接硬编码了 `<input src="{manifest.io_inputs_ref}" />`。如果 B4 在 `manifest.py` 中直接砍掉 `io_inputs_ref`，这里必然引发 `AttributeError` 或阻断 Studio 的保存流程，这是一个必须在同一 PR 拔除的毒瘤。