# Studio I/O Runtime Data Management - Requirements

状态: Draft for review
日期: 2026-07-06

## 1. 背景

Studio 当前把导入文件、运行时参数、I/O schema 和界面勾选状态混在了多处读写路径里。问题表现为:

- `.workspace/import_files/` 已经是事实上的导入文件真相源，但部分 UI 状态仍像本地配置一样独立维护。
- runtime_config 已经存在，但它应当是由文件树和 schema 生成的运行时投影，而不是第二份可编辑真相。
- 节点导入文件和用户导入文件混在 `import_files/` 下，目录名冲突或误扫风险高。
- input 面板需要从“手动配置弹层/折叠区”变成“始终可见的 I/O 绑定视图”。
- 勾选、取消勾选应直接修改对应 md 的 `io` schema，而不是等运行时再临时拼参数。

## 2. 真相源

REQ-1: `.workspace/import_files/` 必须是导入文件的唯一文件真相源。

- Graph input 和 Test input 文件放在 `.workspace/import_files/` 根目录。
- Phase node 导入文件放在 `.workspace/import_files/.phase/<phase_id>/`。
- `.workspace/import_files/.phase/` 下的节点目录和当前 graph phase 列表保持同步。
- `history/` 和 `.history/` 都不是 runtime import 内容，扫描、复制、匹配时必须忽略。

REQ-2: md 文件里的 `io.inputs` / `io.outputs` 必须是 I/O schema 真相源。

- Graph input schema 来自 `GRAPH.md`。
- Phase input/output schema 来自对应 phase md。
- UI 勾选或取消勾选 input 字段时，直接改 md 里的 `io.inputs`。
- 路径不写入 md schema；路径属于 runtime 文件投影。

REQ-3: `.workspace/runtime_config.json` 必须是生成物。

- 它由 `.workspace/import_files/` 文件树、文件内容解析结果、graph topology、I/O schema 和 runtime 设置生成。
- 它必须在 lint、compile、predict、run 前刷新。
- 它必须在 import 文件树变化、import 文件内容变化、input/output schema 变化后刷新。
- 它不能包含 golden 和 UI 配置。
- run 开始时必须落盘当前 runtime_config 快照到 run 目录。

## 3. 初始化与布局

REQ-4: Skill 初始化必须自动创建 runtime import 标准目录。

新建 skill 时必须得到:

```text
.workspace/
  import_files/
    .phase/
      <phase_id>/
```

对于默认 `init` phase，新建后必须存在 `.workspace/import_files/.phase/init/`。

REQ-5: 运行时布局必须可重建。

- 打开 skill、读取 skill detail、刷新 runtime_config、lint、compile、predict、run 前，都必须能幂等创建缺失目录。
- phase 新增、删除、重命名后，`.phase/<phase_id>/` 目录集合必须按当前 graph topology 重新对齐。
- 非当前 phase 的遗留目录不得保留；skill init 和 graph 结构变化时一起清除。
- 新增 phase 时立即创建 `.workspace/import_files/.phase/<phase_id>/` 空目录；删除 phase 时立即删除对应目录；重命名 phase 时按新 id 重建目录结构。

## 4. 文件解析与类型

REQ-6: 结构化文件应解析字段，非结构化文件应只生成内容类型字段。

- JSON object: 顶层 key 生成字段，类型来自 JSON schema 推断。
- JSON array: 以文件名生成一个 array 字段。
- Markdown / txt: 以文件名生成一个 string 字段，content kind 为 text。
- CSV / TSV: 生成 array 字段，元素为 object；列名可作为预览 metadata。
- PDF / image / audio / video / binary: 不解析内部字段，生成一个 file/media 字段，记录 mime/content kind。
- 解析失败的文件仍进入 manifest，但不生成可绑定字段，并产生诊断。

REQ-7: 文件字段解析必须由 backend/runtime_config 层统一完成。

前端只消费 runtime_config 投影，不自行猜测导入文件字段。

## 5. 自动匹配与冲突

REQ-8: 自动匹配必须是确定性的。

- 匹配范围按 scope 隔离: root input 只匹配 `import_files/` 根目录；phase input 只匹配 `.phase/<phase_id>/`。
- 字段名匹配使用同一套规范化规则。
- 类型必须兼容 schema。
- 已声明 schema 字段按 schema 顺序排在最上方。
- 未声明但可用的文件字段排在后面，顺序按文件树稳定排序。

REQ-9: 多个相同类型字段冲突必须报错。

在同一 scope 内，如果多个 runtime candidate 都能匹配同一个 schema 字段:

- 不允许静默选择一个。
- 不生成 binding。
- UI 显示冲突，但 checkbox 仍可操作，用户仍然可以手动修改 md schema。
- lint/compile 必须报明确错误。
- 这里的 lint/compile 报错只阻止本次检查/编译动作产出通过结果；不阻止用户继续编辑、勾选、取消勾选或修正文件。

REQ-10: schema、文件树、文件内容变化后必须自动重新匹配。

- import 文件新增、删除、重命名、内容更新后，runtime_config 刷新并推送给前端。
- input schema 改变后，前端基于新 schema 和最新 runtime_config 重新派生勾选状态。
- 不允许靠组件 mount、tab 切换、window focus 这类非数据变化触发宽泛 refetch。

## 6. Input UX

REQ-11: IO 面板中的 Configure input 按钮必须移除。

- 该区域改为标题和始终展开的内容。
- 匹配上的字段和文件按 input schema 顺序排在最上方。
- 缺失字段、冲突字段、未匹配字段必须有清晰状态。
- 不再有手动 Save input config 按钮。

REQ-12: 勾选操作必须直接写回 md。

- 勾选字段: 在当前 md 的 `io.inputs.properties` 中加入字段定义。
- 取消勾选字段: 从当前 md 的 `io.inputs.properties` 中移除字段定义。
- checkbox 的语义就是用户手动修改 md 里的 `io.inputs` schema。
- 写回后，上方 input schema 示例必须实时反映最新 md schema。
- 写入必须使用已有 skill 文件写入链路，保证 hash 冲突处理、lint 刷新和事件推送一致。

REQ-13: autosave 必须符合项目统一并发语义。

- panel 上所有修改都必须直接改真实数据源，行为与 Properties 面板一致。
- 所有手动保存按钮必须移除。
- 正在保存时显示轻量 `saving` 小 tag；保存完成或失败按现有 autosave 状态语义显示。
- 防抖期间只保留最新快照。
- 有请求 in-flight 时，新保存需求覆盖 pending payload。
- 被 supersede 的旧响应不得写成本地 saved/error，不得弹陈旧 toast，不得用旧服务端快照覆盖最新草稿。

REQ-14: Import 按钮必须同时支持导入文件和文件夹。

- 同一个 import 入口必须能选择单个或多个文件。
- 同一个 import 入口必须能选择文件夹。
- 文件和文件夹导入后都进入当前 scope 的标准 import_files 路径。
- 导入完成后刷新 runtime_config 并重新匹配字段。

## 7. 文件行 UX

REQ-15: 文件路径必须有 tooltip。

- 行内路径可截断。
- hover 时显示完整相对路径。
- 可访问绝对路径时，tooltip 或上下文菜单可提供绝对路径复制。

REQ-16: 文件行必须支持打开文件和打开文件夹。

- 编辑按钮打开 `.workspace/import_files/...` 对应文件，并必须真实读取磁盘内容。
- 打开文件夹按钮打开该文件所在目录。
- 文件夹导入项打开其自身目录。

REQ-17: 删除按钮语义必须和文件真相源一致。

如果 UI 展示的是从 `.workspace/import_files/` 派生的文件行，删除应删除对应 import 文件或目录，并触发 runtime_config 刷新；不应只删除前端临时状态。

## 8. Output / Artifacts 对齐

REQ-18: Output 和 artifacts 使用同一套 I/O 运行时模型。

- output schema 仍由 md `io.outputs` 管理。
- output/artifact 文件展示、路径 tooltip、打开文件、打开文件夹、冲突诊断和顺序规则与 input 一致。
- output/artifact 的文件真相源和 runtime 快照位置由对应设计源定义；本规格要求交互和投影模型一致。

## 9. 验收标准

- 新建 skill 后，文件树中存在 `.workspace/import_files/.phase/<默认 phase>/`。
- `.workspace/import_files/.history/` 下文件不会出现在 runtime_config 或 IO 面板。
- Configure input 按钮消失，配置内容始终展开。
- 按 input schema 顺序显示匹配字段，且文件树/schema/import 内容变化后自动更新。
- 相同 scope 内多个同名同类型字段会在 UI 和 lint/compile 中报冲突；UI 仍允许勾选/取消勾选。
- 勾选/取消勾选后，对应 md 的 `io.inputs` 立即变化。
- panel 修改出现 `saving` 小 tag，不再需要保存按钮。
- import 入口能同时选择文件和文件夹。
- 导入文件编辑器能加载真实文件内容。
- 文件路径 hover 能看到完整路径，点击打开文件夹能定位到对应目录。
- run 目录包含 runtime_config 快照。
