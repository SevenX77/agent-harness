# Graph Agent 文档中心

欢迎使用 Graph Agent！这是一个基于 LangGraph 的认知代理框架，专为复杂的多阶段任务设计。

## 📚 文档导航

### 新手入门

- **[使用指南 (USER_GUIDE.md)](./USER_GUIDE.md)** ⭐ 推荐从这里开始
  - 快速开始
  - 核心概念
  - 创建第一个技能
  - 常见问题

### 深入理解

- **[架构设计 (ARCHITECTURE.md)](./ARCHITECTURE.md)**
  - 设计理念
  - 双层控制架构
  - 工作记忆机制
  - 自我验证循环
  - 关键设计决策

- **[实施文档 (IMPLEMENTATION.md)](./IMPLEMENTATION.md)**
  - 代码结构
  - 核心模块实现
  - 关键算法
  - 性能优化
  - 测试策略

### 专题指南

- **[认知循环指南 (COGNITIVE_LOOP_GUIDE.md)](./COGNITIVE_LOOP_GUIDE.md)**
  - 计划强制执行
  - 自我检查机制
  - 死胡同检测
  - 检查点压缩

- **[配置参考 (CONFIG_REFERENCE.md)](./CONFIG_REFERENCE.md)**
  - llm_roles.yaml 配置
  - multimodal_roles.yaml 配置
  - 环境变量
  - 模型选择策略

- **[技能编写指南 (SKILL_AUTHORING_GUIDE.md)](./SKILL_AUTHORING_GUIDE.md)**
  - SKILL.md 语法
  - 阶段定义
  - 工具注册
  - 最佳实践

- **[工具开发指南 (TOOL_DEVELOPMENT_GUIDE.md)](./TOOL_DEVELOPMENT_GUIDE.md)**
  - 工具函数规范
  - 参数验证
  - 错误处理
  - 测试方法

- **[集成指南 (INTEGRATION_GUIDE.md)](./INTEGRATION_GUIDE.md)**
  - 集成到现有项目
  - API 参考
  - 部署建议

## 🚀 快速开始

### 1. 安装

```bash
git clone <repository-url>
cd agent-harness
pip install -r requirements.txt
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env，添加 API keys
```

### 3. 运行示例

```bash
python examples/hello_world.py
```

## 📖 学习路径

### 初学者路径

1. 阅读 [使用指南](./USER_GUIDE.md) 的"快速开始"部分
2. 运行 `examples/hello_world.py`
3. 阅读 [技能编写指南](./SKILL_AUTHORING_GUIDE.md)
4. 创建你的第一个技能

### 进阶路径

1. 阅读 [架构设计](./ARCHITECTURE.md) 理解设计理念
2. 阅读 [认知循环指南](./COGNITIVE_LOOP_GUIDE.md) 理解控制机制
3. 阅读 [实施文档](./IMPLEMENTATION.md) 理解代码实现
4. 贡献代码或创建高级技能

### 运维路径

1. 阅读 [配置参考](./CONFIG_REFERENCE.md)
2. 阅读 [集成指南](./INTEGRATION_GUIDE.md) 的"部署建议"
3. 设置监控和日志
4. 优化性能

## 🎯 核心特性

### 1. 双层控制架构

外层控制循环确保任务按预定阶段执行，中间件层实时干预注入上下文。

```
外层控制 → 中间件 → 核心代理
```

### 2. 工作记忆机制

强制 LLM 先规划再执行，提供可审计的执行轨迹。

```python
# LLM 必须先调用
update_working_memory("我的执行计划...")

# 然后才能调用业务工具
analyze_data(...)
```

### 3. 自我验证循环

每个阶段自动验证输出质量，失败自动重试。

```
segment → review → (失败) → segment → review → (通过)
```

### 4. 声明式技能定义

使用 Markdown + YAML 定义技能，LLM 友好且易维护。

```yaml
---
name: my-skill
phases:
  - name: process
    type: cognitive
    role: balanced
    tools: [analyze, validate]
---
```

## 📊 项目结构

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
│   └── middlewares.py      # 中间件
├── models/                 # 模型管理
│   └── resolver.py         # 模型解析和选择
├── callbacks/              # 回调和日志
│   └── logging_cb.py       # 结构化日志
├── deerflow/               # DeerFlow 集成
└── docs/                   # 文档（你在这里）
    ├── README.md           # 文档索引
    ├── USER_GUIDE.md       # 使用指南
    ├── ARCHITECTURE.md     # 架构设计
    ├── IMPLEMENTATION.md   # 实施文档
    └── ...
```

## 🛠️ 技能示例

### 文本分段

```python
from graph_agent.core.runner import run_skill
from pathlib import Path

result = run_skill(
    Path("skills/text-segmentation/SKILL.md"),
    {
        "chapter_id": 1,
        "chapter_text": "...",
        "chapter_lines": [...]
    }
)

print(f"分段数量: {len(result['segments'])}")
```

### 事件提取

```python
result = run_skill(
    Path("skills/event-extraction/SKILL.md"),
    {
        "chapter_id": 1,
        "segments": [...]
    }
)

print(f"事件数量: {len(result['events'])}")
```

### 完整流程

```python
result = run_skill(
    Path("skills/story-deconstruction/SKILL.md"),
    {
        "chapters": [...]
    }
)

print(f"处理了 {len(result['chapters'])} 章")
```

## 🔧 配置示例

### llm_roles.yaml

```yaml
roles:
  balanced:
    model: CL46T  # Claude Sonnet 4.6 Thinking
    fallback: [GPT4, CL35S]
  
  fast:
    model: GPT4T  # GPT-4 Turbo
    fallback: [CL35S]
```

### .env

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
LOG_LEVEL=INFO
MAX_CONCURRENT_TASKS=5
```

## 📈 性能指标

基于 25 章小说的 E2E 测试：

- **总执行时间**: ~12 分钟
- **平均每章**: ~30 秒
- **Token 使用**: ~500K tokens
- **准确率**: >95%

## 🤝 贡献指南

欢迎贡献！请遵循以下步骤：

1. Fork 仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 📝 更新日志

### v1.0.0 (2026-04-11)

- ✅ 双层控制架构
- ✅ 工作记忆机制
- ✅ 自我验证循环
- ✅ 5 个内置技能
- ✅ 完整文档体系

## 🐛 故障排查

### 常见问题

1. **"No available model for role"**
   - 检查 API key 是否配置
   - 检查 `llm_roles.yaml` 是否正确

2. **"Validation failed after max retries"**
   - 检查验证规则是否过严
   - 查看日志了解具体错误

3. **"Context length exceeded"**
   - 降低 `checkpoint_threshold`
   - 增加压缩频率

详见 [使用指南 - 常见问题](./USER_GUIDE.md#常见问题)

## 📞 获取帮助

- **GitHub Issues**: <repository-url>/issues
- **文档**: <repository-url>/docs
- **示例**: <repository-url>/examples

## 📄 许可证

Apache-2.0

## 🙏 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - 核心框架
- [Anthropic](https://www.anthropic.com/) - Claude API
- [OpenAI](https://openai.com/) - GPT API

---

**开始使用**: [使用指南](./USER_GUIDE.md) | **理解架构**: [架构设计](./ARCHITECTURE.md) | **深入代码**: [实施文档](./IMPLEMENTATION.md)
