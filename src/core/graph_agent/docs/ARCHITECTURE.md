# Graph Agent 架构设计文档

## 概述

`graph_agent` 是一个基于 LangGraph 的认知代理框架，专为复杂的多阶段任务设计。它通过双层控制架构、工作记忆机制和自我验证循环，确保 LLM 代理能够可靠地完成结构化任务。

## 核心设计理念

### 1. 双层控制架构

```
┌─────────────────────────────────────────────────────────────┐
│                    外层控制循环 (Harness)                     │
│  - 阶段编排（planning → execution → review）                 │
│  - 计划强制执行                                              │
│  - 自我检查和重试                                            │
│  - 检查点压缩                                                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    中间件层 (Middleware)                      │
│  - 工作记忆注入                                              │
│  - 死胡同检测和剪枝                                          │
│  - 澄清请求处理                                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    核心代理 (DeerFlow)                        │
│  - LLM 调用                                                  │
│  - 工具执行                                                  │
│  - 流式输出                                                  │
└─────────────────────────────────────────────────────────────┘
```

**设计原因**：
- **外层控制**：确保任务按预定阶段执行，防止跳过关键步骤
- **中间件**：实时干预，注入上下文和约束
- **核心代理**：专注于 LLM 交互和工具调用

### 2. 工作记忆机制

每个阶段强制要求 LLM 先调用 `update_working_memory` 记录执行计划，然后才能执行业务工具。

**工作记忆内容**：
- 本阶段目标
- 执行步骤顺序
- 所需数据来源
- 预期产出

**优势**：
- 强制显式规划，减少盲目执行
- 提供可审计的执行轨迹
- 支持计划验证和纠偏

### 3. 自我验证循环

每个阶段完成后，自动进入 `review` 阶段验证输出质量。如果验证失败，自动重试前一阶段。

```
segment → review → (验证失败) → segment → review → (通过) → 下一阶段
```

**验证层次**：
1. **格式验证**：输出是否符合 schema
2. **语义验证**：内容是否符合业务规则
3. **完整性验证**：是否遗漏必要信息

### 4. 检查点压缩

长任务会产生大量上下文，导致 token 超限。检查点压缩机制自动总结历史消息，保留关键信息。

**压缩策略**：
- 保留最近 N 条消息（默认 10）
- 压缩中间消息为摘要
- 保留所有工具调用结果

## 模块架构

### 核心模块

```
graph_agent/
├── core/                    # 核心引擎
│   ├── harness.py          # 双层控制循环
│   ├── runner.py           # 任务执行器
│   ├── compiler.py         # SKILL.md 编译器
│   └── loader.py           # 技能加载器
├── cognitive/              # 认知机制
│   ├── memory.py           # 工作记忆
│   ├── finish.py           # 任务完成检测
│   └── middlewares.py      # 中间件（注入、剪枝）
├── models/                 # 模型管理
│   ├── resolver.py         # 模型解析和选择
│   └── reasoning_patch.py  # 推理内容补丁
├── callbacks/              # 回调和日志
│   ├── logging_cb.py       # 结构化日志
│   └── callback_bridge.py  # 回调桥接
└── deerflow/               # DeerFlow 集成
    ├── config/             # 配置管理
    └── reflection/         # 反射工具
```

### 技能系统

```
skills/
├── text-segmentation/      # 文本分段
│   ├── SKILL.md           # 技能定义（声明式）
│   ├── script/            # 工具实现（Python）
│   └── data/              # 参考数据
├── event-extraction/       # 事件提取
├── batch-analysis/         # 批量分析
├── global-synthesis/       # 全局综合
└── story-deconstruction/   # 故事解构（编排器）
```

**SKILL.md 结构**：
```yaml
---
name: text-segmentation
description: 将章节文本分段并分类
phases:
  - name: setup
    type: code_only
    tools: [prepare_chapter]
  - name: segment
    type: cognitive
    role: balanced
    tools: [parse_segmentation_output, store_segments, ...]
  - name: review
    type: cognitive
    role: balanced
    tools: [validate_segments, log_ambiguous_segments, ...]
---

# 阶段说明
...
```

## 关键设计决策

### 1. 为什么使用声明式 SKILL.md？

**问题**：传统代码式定义难以维护，LLM 难以理解。

**方案**：使用 Markdown + YAML frontmatter 定义技能。

**优势**：
- LLM 友好：可以直接读取和理解
- 人类可读：非程序员也能理解流程
- 版本控制友好：diff 清晰

### 2. 为什么强制工作记忆？

**问题**：LLM 经常跳过规划直接执行，导致错误。

**方案**：第一次调用必须是 `update_working_memory`，否则注入提示。

**优势**：
- 强制显式规划
- 提供审计轨迹
- 支持计划验证

### 3. 为什么需要 review 阶段？

**问题**：LLM 输出质量不稳定，需要验证。

**方案**：每个阶段后自动进入 review，验证失败自动重试。

**优势**：
- 自动质量保证
- 减少人工检查
- 支持多层验证

### 4. 为什么使用角色化模型选择？

**问题**：不同任务需要不同能力的模型。

**方案**：定义角色（balanced, fast, creative），运行时解析为具体模型。

**优势**：
- 解耦技能定义和模型选择
- 支持多提供商（Anthropic, OpenAI, OneChats）
- 支持运行时降级

## 性能优化

### 1. 并发执行

- 批量分析支持并发处理多个章节
- 使用 `asyncio` 和 `ThreadPoolExecutor`

### 2. 缓存机制

- 模型配置缓存（避免重复解析 YAML）
- 技能编译缓存（避免重复编译 SKILL.md）

### 3. 流式输出

- 支持 LLM 流式响应
- 实时显示工具调用进度

## 可扩展性

### 1. 新增技能

1. 创建 `skills/your-skill/SKILL.md`
2. 实现 `skills/your-skill/script/*.py` 工具函数
3. 在编排器中调用

### 2. 新增模型提供商

1. 在 `llm_roles.yaml` 添加 provider
2. 实现对应的 API 适配器（如需要）

### 3. 自定义中间件

1. 在 `cognitive/middlewares.py` 添加中间件函数
2. 在 `harness.py` 注册中间件

## 安全性

### 1. 输入验证

- 所有工具函数参数使用 Pydantic 验证
- 文件路径检查（防止路径遍历）

### 2. 错误隔离

- 工具执行错误不会导致整个任务失败
- 支持重试和降级

### 3. 日志审计

- 所有 LLM 调用记录 token 使用
- 所有工具调用记录输入输出
- 支持追溯完整执行轨迹

## 未来规划

### 短期（1-2个月）

- [ ] 支持多模态输入（图片、音频）
- [ ] 优化检查点压缩算法
- [ ] 添加更多内置验证器

### 中期（3-6个月）

- [ ] 支持分布式执行
- [ ] 添加 Web UI
- [ ] 支持人工干预点

### 长期（6-12个月）

- [ ] 自动技能学习
- [ ] 跨技能知识迁移
- [ ] 自适应模型选择

## 参考资料

- [LangGraph 文档](https://langchain-ai.github.io/langgraph/)
- [认知循环指南](./COGNITIVE_LOOP_GUIDE.md)
- [配置参考](./CONFIG_REFERENCE.md)
- [技能编写指南](./SKILL_AUTHORING_GUIDE.md)
