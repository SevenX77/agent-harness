# Skill Studio UI/UX 工作流总览

**目标**: 定义产品经理 (PM) 在 Skill Studio 中的完整工作流闭环，并为每个节点的界面 (UI) 与交互 (UX) 提供详细的设计参考。

## 工作流节点索引 (Workflow Nodes)

0. [00_settings.md](./00_settings.md) — 设置与配置 (运行底座: 凭证 / 角色 / copilot / 路径)
1. [01_init.md](./01_init.md) — 发现与初始化 (入口与环境准备)
2. [02_authoring.md](./02_authoring.md) — 编辑 (搭图 / SKILL.md 编写)
3. [03_compile.md](./03_compile.md) — **Compile**(编译校验 + 错误呈现)· ✅ 走查回写完成
4. [04_run-and-verify.md](./04_run-and-verify.md) — **运行与验收**(predict 试飞 + run 真跑 + trace 去黑盒 + golden 验收)· ✅ 走查回写完成
5. [05_debugging.md](./05_debugging.md) — **Debug**(调试续跑)· ✅ 走查回写完成
6. [06_eval.md](./06_eval.md) — **保存与发布**(publish + autocommit)· ✅ 走查回写完成

> **结构 (PM 2026-06-03)**: compile / predict+run+trace+golden / debug **分三个节点(03/04/05)**,不合并成一个大节点。golden 跟着 predict/run 走(放 04)。

### 走查状态
- ✅ **03 compile / 04 运行与验收 / 05 debug**: 全部走查 + **全量 atom actions 回写**进各节点文档(含决策 + 原话 + 测试关键点)。对引擎的设计需求 3 份 prompt 已抛出(见 `_reorg/engine-prompt-*` + `gemini-prompt-batch-loop`)。
- ✅ **06 保存与发布**: 走查回写完成(PM 2026-06-04 定 **publish=占坑低优先**:本地 git autocommit 存档 + Artifact Registry 最小发布;commit-msg/confetti/独立按钮=stale-doc 删;团队协作/发布鉴权占坑未来)。
- 🎉 **全 7 节点走查完成**(00–06);14 个能力全有完整走查记录。

> **设计原则**: 业务流先于界面流。确保 PM 的每一步操作都有明确的目的、清晰的反馈，以及失败时的退路。
