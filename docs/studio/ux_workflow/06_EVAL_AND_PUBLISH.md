# Node 6: 评估与交付 (Evaluation & Publish)

## 1. 业务目标
在得到一次成功的真实 Run 之后，PM 需要判断这个输出“是否足够好”。如果满意，结束当前开发周期并将 Skill 提交到团队的代码仓库中生效。

## 2. 界面元素与交互逻辑

### 2.1 意图偏离检测与 Diff 视图
- **对比机制**:
  - 将当前 Run 的最终 `artifacts` 产出，与我们在 [Node 3](./03_PREDICT_AND_BASELINE.md) 中准备的 **Golden Baseline** 进行对比。
- **UI 表现**:
  - **并排分屏视图 (Split-view Diff)**: 左侧是当前真实结果，右侧是 Golden Baseline。
  - 差异高亮：文本对比或者 JSON 结构对比。
- **强制诊断 (Mandatory Diagnosis)**:
  - 在对比面板旁边，**必须展示大模型裁判（Copilot Judge）的诊断报告**。
  - Copilot 不仅要指出哪里不一样，还必须从“意图偏离”的角度进行综合打分和评述（例如：“整体结构相符，得分 85/100；扣分点在于第二段的语气过于生硬，没有达到 `SKILL.md` head 描述中要求的‘活泼’风格”）。
  - PM 依据这份强制给出的诊断报告，做出最终的验收决策。

### 2.2 发布流程 (Publish)
- **条件**: 如果 PM 对比 Diff 和诊断报告后认为结果符合验收标准。
- **UI 操作**: 
  - 界面右上角提供 **[ Publish ]** 按钮。
  - 点击后，可以出现一个轻量级的弹窗或下拉浮层，提供一个**可选的 Commit Message 输入框**。
  - **智能托底**: PM 可以手动填入发布说明；如果 PM 留空直接点确认，Copilot 会根据本次 Run 的改动（比如调整了哪个 Prompt 或 Tool）**自动生成一段清晰的 Commit Message**。
- **底层机制**:
  - 触发后端的自动化集成逻辑，执行 `git add SKILL.md && git commit -m "<PM填写的或Copilot生成的Message>" && git push`。
  - **注意**: UI 不需要给 PM 展示复杂的终端命令，只需要提示“✅ 已成功发布到代码库”的撒花特效即可。PM 绝不需要切出 Studio 去终端手动提交。

## 3. 闭环完成
- 发布成功后，本次 Skill 迭代周期闭环。PM 可以回到主页开始新的探索。
