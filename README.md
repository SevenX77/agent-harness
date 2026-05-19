# agent-harness

## What is this?
GraphAgent Harness 是一个**文档驱动**的 LLM 工作流引擎，外加配套的本地 Skill Studio。它允许 PM 在不编写复杂代码的情况下，通过界面打磨多阶段 Agent 工作流。

## Why does this exist?
原型期的 Agent 应用通常充斥着“单轮对话”或硬编码的脚本调用。本项目旨在解决两大痛点：
1. **测试生产分离**：确保在本地打磨的 `SKILL.md` 工作流，能够一字不差地在生产集群（Cloud）中安全运行。
2. **可视化黑盒**：告别命令行调参，通过原生的 Studio 桌面端清晰展示 Agent 循环、Context 状态机映射以及 Token 消耗。

## Architecture Overview
本项目遵循严格的研发端与生产端物理隔离原则，详见 [PROD_DEV_SEPARATION.md](docs/architecture/PROD_DEV_SEPARATION.md)：
- **Engine (`packages/graph-agent`)**：提炼后的纯净 Python SDK，负责编译、解析并驱动基于 LangGraph 的 Agent 循环。
- **Studio (`apps/studio/{frontend,backend,tauri}`)**：基于 Tauri 的本地优先应用，服务于内部产品经理（PM）进行技能开发。前端 React Flow 画布与后端 FastAPI 伴生进程。
- **Skills (`skills/`)**：语料库，存储各种用于测试 `Engine` 和 `Studio` 能力的 SKILL 用例。
*(注：面向 C 端的生产端云服务位于外部独立仓库 `agent-harness-cloud`，通过 pip 拉取本 Engine 执行。)*

## Five Pillars of Documentation
整个仓库的文档收敛为 5 个核心逻辑支柱，拒绝冗杂与散落：
1. **宏观域 (Macro)**: `docs/architecture/` — 系统边界与双层认知架构。
2. **引擎内核 (Engine)**: `docs/engine/` — Graph 流转规则、LLM 路由及文件规范。
3. **编排与交互 (Studio UX)**: `docs/studio/` — 端到端用户旅程与 Trace 瀑布流交互。
4. **项目开发规范 (Development)**: `docs/development/` & `docs/llm-providers/` — 前端组件规范及大模型接入指南。
5. **当前实施图纸 (Specs)**: `.kiro/specs/` — 当前活跃的架构演进施工单。
*(Level 3 文档与 Level 4 Specs 之间通过文档末尾的指引建立双向关联，保障追溯。)*

## Quick Start
（仅限本地开发使用）
```bash
# 1. 确保安装好 uv 和 Node
# 2. 安装 Python 层依赖
uv sync

# 3. 启动本地 Studio 前端与伴生后端
cd apps/studio/frontend
npm install
npm run dev

# 4. 在界面中打开 `skills/` 下的某个 fixture 进行调试。
```

## Project Status
当前处于 **MVP0 打磨阶段**。
重点补齐 7 大模块能力，核心聚焦于：
- [x] Tauri 壳子接入与双端基座分离
- [ ] React Flow 微观拓扑与 Context 状态机可视化 (In Progress)
- [ ] 结构化 Compile 报错及 Trace 数据透视 (In Progress)
- [ ] LLM Role 编排中心与连通性测试 (In Progress)

## Roadmap
- **M1**: 内部工具成型，PM 可在本地获得无缝的保存、断点调试体验，消除业务逻辑黑盒。
- **M2**: 补齐 Cloud CI 流水线验证，支持 Predict 模拟试飞与 Golden Baseline 对比。
- **M3**: 生产端 10000+ 并发就绪，内部发布自动通过灰度上线。

## Contributing
参考 [CONTRIBUTING.md](docs/development/CONTRIBUTING.md) 了解本仓库的提交流程和远程 GUI 测试规范。

## License
Apache-2.0
