# Node 3: 预测与基线 (Predict & Baseline)

## 1. 业务目标
在烧掉真实的 LLM Token 之前，验证整个 Graph 的数据流和 Python 工具逻辑是否通畅。同时，**Predict 的结果是打磨 Golden Baseline 的直接素材**。PM 需要在此阶段与 Copilot 合作，将拟真的（或真实的）跑通结果手工修正为“完美输出”，作为后续自动化质量评估的绝对锚点。

## 2. 工作流分支：Predict 与 Baseline 的同步打磨

PM 在 Compile 通过（[Predict] 按钮亮起）后，进入核心的试飞与打磨阶段。

### 分支 A: Predict -> 同步打磨 Mock Golden (标准稳健路径)
1. **执行 Predict**: PM 选择本地的 JSON/YAML 测试输入文件（加载瞬间通过 Schema 校验），点击 `[ Predict ]`。
2. **底层机制**: 
   - 引擎按拓扑顺序跑过各个 Phase。
   - `Code-only` 节点：执行真实的 Python 逻辑，确保数据组装、工具函数无报错。
   - `Agent-Loop` 节点：调用 Copilot (Mock LLM) 返回拟真/占位结果，不消耗线上真实大模型 Token。
3. **同步打磨 Golden Baseline**: 
   - Predict 跑完后，Studio 界面自动展开**对比与打磨视图**。
   - 左侧：本次 Predict 产生的“拟真输出”。
   - 右侧：准备保存的 `baseline.json/md` 草稿。
   - PM 结合左侧的骨架，在右侧面板与 Copilot（侧边栏）反复对话，一字一句敲定这篇内容的完美形态。
   - 完成后，点击 `[ Save as Golden ]` 锁定基线。

### 分支 B: 真实 Run -> 事后打磨 Golden (敏捷重路径)
1. **直接运行**: PM 确信图逻辑没问题，直接点击 `[ Run ]`（跳至 Node 4）。
2. **事后打磨**:
   - 拿到真实大模型的输出结果后，如果发现有些许瑕疵。
   - PM 将这份真实输出导入右侧打磨面板，跟 Copilot 一起分析偏离点，人工把瑕疵修好。
   - 将修好的这份完美版本保存为 Golden Baseline。

## 3. UI/UX 重点
- **测试输入管理**: 不再使用动态表单。PM 通过文件选择器加载本地数据文件，系统必须提供即时的 Schema 校验反馈。
- **沉浸式打磨区**: 打磨 Golden 不是简单的改改文字，而是需要双屏对比（左边看结构/原始输出，右边写完美输出），下方或右侧固定 Copilot 随时接受质询和提供灵感。

