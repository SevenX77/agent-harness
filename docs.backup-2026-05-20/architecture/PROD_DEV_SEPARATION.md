---
status: Living
target_goal: "明确定义本仓库作为研发端与外部生产端的物理和逻辑边界，确立双端一致性原则"
linked_code_paths:
  - packages/graph-agent/src/graph_agent/
  - apps/studio/tauri/src/
linked_specs:
  - .kiro/specs/harness-split/
  - .kiro/specs/tauri-t2/
last_updated: 2026-05-19
---

# 生产与研发分离架构 (Prod/Dev Separation)

## 1. 问题陈述
### 1.1 单仓的局限
在早期的单体架构中，测试用的代码、脚手架与引擎核心高度耦合，导致本地测试环境过于沉重，无法轻量化地提供给非技术背景的产品经理 (PM) 使用，同时也使得生产端部署包含了大量无关的研发态冗余逻辑。

### 1.2 用户与 PM 的两套体验
PM 在本地打磨 Agent (编写 SKILL.md、测试 Prompt) 需要强视觉反馈的 GUI (Studio)，而最终给 C 端消费者提供服务的生产端则需要高并发、无状态的推理集群。这使得我们必须将工程视角划分为“开发侧 (研发端)”和“消费者侧 (生产端)”。

## 2. 双仓架构
为解决上述痛点，我们实施了严格的物理分离：

### 2.1 本仓 (agent-harness): Engine + 研发端 Studio
本仓库定位为**内部研发基座**，包含两个核心部分：
- **Engine (`packages/graph-agent`)**: 纯净、独立的 Python SDK，提供标准的 Workflow 编译与执行接口。
- **Studio (`apps/studio/`)**: 专为 PM 打造的桌面端应用，提供可视化图表、调试工具及 LLM 评测能力。

### 2.2 兄弟仓 (agent-harness-cloud): 生产端 (独立)
面向 C 端用户的在线推理集群独立维护在 `agent-harness-cloud` 仓库中。它不包含任何图形界面逻辑，仅通过 `pip` 引用本仓库发布的 Engine SDK。

## 3. Tauri 本地优先
Studio 前端放弃纯 Web 形式，全面拥抱 Tauri：
- **无缝本地 I/O**: 使得 PM 能够使用“双击打开文件夹”的心智，直接读写操作系统上的 SKILL 目录。
- **内置 Sidecar**: Tauri 启动时拉起内置的 FastAPI Python 引擎作为守护进程，消除环境配置门槛。

## 4. 双端 100% 执行一致性原则 (The Consistency Contract)
**这是本项目的核心铁律**：
- 同一份 `SKILL.md` 文件。
- 同一套锁定的 Engine SDK (`graph-agent`) 版本。
- 在 Studio 桌面端 (Mock/测试阶段) 的执行逻辑，必须与 `agent-harness-cloud` (线上真实运行) **完全一致**。
绝对不允许存在任何仅限研发端生效或仅限生产端生效的分叉执行分支。

## 相关 Spec
- [harness-split](../../.kiro/specs/_archive/harness-split/)
- [tauri-t2](../../.kiro/specs/_archive/tauri-t2/)
