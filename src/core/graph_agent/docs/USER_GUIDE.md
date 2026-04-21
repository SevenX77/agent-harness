# Graph Agent 使用指南

## 快速开始

### 1. 安装

```bash
# 克隆仓库
git clone <repository-url>
cd agent-harness

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，添加 API keys
```

### 2. 配置 API Keys

在 `.env` 文件中配置：

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
OPENAI_API_KEY=sk-...

# OneChats (可选)
ONECHATS_API_KEY=...
```

### 3. 运行第一个示例

```bash
python examples/hello_world.py
```

**hello_world.py**：

```python
from graph_agent.core.runner import run_skill
from pathlib import Path

# 加载技能
skill_path = Path("skills/text-segmentation/SKILL.md")

# 准备输入
input_data = {
    "chapter_id": 1,
    "chapter_text": "这是第一章的内容...",
    "chapter_lines": ["第1行", "第2行", ...]
}

# 运行技能
result = run_skill(skill_path, input_data)

# 查看结果
print(f"分段数量: {len(result['segments'])}")
for seg in result['segments']:
    print(f"段落 {seg['index']}: {seg['type']} 类")
```

## 核心概念

### 1. 技能 (Skill)

技能是一个完整的任务单元，由 `SKILL.md` 定义。

**技能结构**：

```
skills/your-skill/
├── SKILL.md           # 技能定义
├── script/            # 工具实现
│   ├── __init__.py
│   ├── tools.py       # 工具函数
│   └── validators.py  # 验证器
└── data/              # 参考数据（可选）
```

### 2. 阶段 (Phase)

每个技能包含多个阶段，按顺序执行。

**阶段类型**：

- **code_only**：纯代码执行，不调用 LLM
- **cognitive**：调用 LLM + 工具

**示例**：

```yaml
phases:
  - name: setup
    type: code_only
    tools: [prepare_data]
  
  - name: process
    type: cognitive
    role: balanced
    tools: [analyze, validate]
  
  - name: review
    type: cognitive
    role: balanced
    tools: [check_quality]
```

### 3. 工具 (Tool)

工具是 Python 函数，供 LLM 调用。

**工具定义**：

```python
from pydantic import BaseModel, Field

class AnalyzeInput(BaseModel):
    text: str = Field(description="要分析的文本")
    options: dict = Field(default={}, description="分析选项")

def analyze(text: str, options: dict = {}) -> dict:
    """
    分析文本内容
    
    Args:
        text: 要分析的文本
        options: 分析选项
    
    Returns:
        分析结果
    """
    # 实现分析逻辑
    return {"result": "..."}
```

**工具注册**：

工具函数会自动被发现和注册，只需：
1. 放在 `script/` 目录下
2. 在 `SKILL.md` 的 `tools` 列表中声明

### 4. 验证器 (Validator)

验证器检查输出质量，验证失败会触发重试。

**验证器签名**：

```python
def validate_output(state: dict) -> tuple[bool, str]:
    """
    验证输出质量
    
    Args:
        state: 当前状态（包含所有输出）
    
    Returns:
        (是否通过, 错误信息)
    """
    segments = state.get("segments", [])
    
    if len(segments) == 0:
        return (False, "未生成任何段落")
    
    for seg in segments:
        if seg["type"] not in ["A", "B", "C"]:
            return (False, f"段落 {seg['index']} 类型无效")
    
    return (True, "验证通过")
```

## 创建新技能

### 步骤 1：创建目录结构

```bash
mkdir -p skills/my-skill/script
touch skills/my-skill/SKILL.md
touch skills/my-skill/script/__init__.py
touch skills/my-skill/script/tools.py
```

### 步骤 2：编写 SKILL.md

```markdown
---
name: my-skill
description: 我的第一个技能
phases:
  - name: setup
    type: code_only
    tools: [prepare]
  
  - name: process
    type: cognitive
    role: balanced
    tools: [analyze, finish_task]
  
  - name: review
    type: cognitive
    role: balanced
    tools: [validate, finish_task]
---

# 技能说明

这个技能用于...

## 阶段 1: setup

准备数据...

## 阶段 2: process

分析数据...

## 阶段 3: review

验证结果...
```

### 步骤 3：实现工具函数

**script/tools.py**：

```python
def prepare(input_data: dict) -> str:
    """准备数据"""
    # 实现准备逻辑
    return "数据准备完成"

def analyze(data: str) -> dict:
    """分析数据"""
    # 实现分析逻辑
    return {"result": "分析结果"}

def validate(result: dict) -> tuple[bool, str]:
    """验证结果"""
    # 实现验证逻辑
    if result.get("result"):
        return (True, "验证通过")
    return (False, "结果为空")
```

### 步骤 4：测试技能

```python
from graph_agent.core.runner import run_skill
from pathlib import Path

skill_path = Path("skills/my-skill/SKILL.md")
input_data = {"data": "测试数据"}

result = run_skill(skill_path, input_data)
print(result)
```

## 高级用法

### 1. 使用工作记忆

工作记忆用于记录执行计划，强制 LLM 先规划再执行。

**在工具中更新工作记忆**：

```python
def update_working_memory(plan: str) -> str:
    """
    更新工作记忆
    
    Args:
        plan: 执行计划
    """
    # 这是一个特殊工具，由框架自动处理
    return "WORKING_MEMORY_UPDATED"
```

**LLM 使用示例**：

```
我的执行计划：
1. 首先调用 prepare 准备数据
2. 然后调用 analyze 分析数据
3. 最后调用 validate 验证结果

<tool_call>
  <name>update_working_memory</name>
  <args>{"plan": "1. prepare 2. analyze 3. validate"}</args>
</tool_call>
```

### 2. 自定义验证器

**创建多层验证器**：

```python
def validate_format(segments: list) -> tuple[bool, str]:
    """格式验证"""
    for seg in segments:
        if "index" not in seg or "type" not in seg:
            return (False, f"段落缺少必要字段")
    return (True, "格式正确")

def validate_semantics(segments: list) -> tuple[bool, str]:
    """语义验证"""
    for seg in segments:
        if seg["type"] == "A" and "setting" not in seg["content"]:
            return (False, f"A类段落应包含场景描述")
    return (True, "语义正确")

def validate_completeness(segments: list, original_text: str) -> tuple[bool, str]:
    """完整性验证"""
    restored = "".join(seg["content"] for seg in segments)
    if restored != original_text:
        return (False, "文本还原失败")
    return (True, "完整性正确")
```

**在 review 阶段调用**：

```yaml
- name: review
  type: cognitive
  role: balanced
  tools: [validate_format, validate_semantics, validate_completeness, finish_task]
```

### 3. 并发处理

**批量处理多个章节**：

```python
import asyncio
from graph_agent.core.runner import run_skill_async

async def process_chapters(chapters: list):
    skill_path = Path("skills/text-segmentation/SKILL.md")
    
    tasks = [
        run_skill_async(skill_path, {"chapter": ch})
        for ch in chapters
    ]
    
    results = await asyncio.gather(*tasks)
    return results

# 运行
chapters = [...]
results = asyncio.run(process_chapters(chapters))
```

### 4. 自定义模型选择

**在 llm_roles.yaml 中定义角色**：

```yaml
roles:
  fast:
    model: GPT4T
    fallback: [CL35S]
  
  balanced:
    model: CL46T
    fallback: [GPT4, CL35S]
  
  creative:
    model: GPT4
    fallback: [CL46T]
```

**在 SKILL.md 中使用**：

```yaml
phases:
  - name: brainstorm
    type: cognitive
    role: creative  # 使用创意模型
    tools: [generate_ideas]
  
  - name: implement
    type: cognitive
    role: fast  # 使用快速模型
    tools: [write_code]
```

### 5. 流式输出

**启用流式输出**：

```python
from graph_agent.core.runner import stream_skill

async def main():
    skill_path = Path("skills/my-skill/SKILL.md")
    input_data = {"data": "..."}
    
    async for chunk in stream_skill(skill_path, input_data):
        print(chunk, end="", flush=True)

asyncio.run(main())
```

## 配置参考

### 1. llm_roles.yaml

**完整示例**：

```yaml
models:
  CL46T:
    name: "Claude Sonnet 4.6 Thinking"
    reasoning: true
    min_max_tokens: 8192
    fc_supported: true
    providers:
      OC_CL_ANT: "claude-sonnet-4-6-thinking"
      OC_CL: "claude-sonnet-4-6-thinking"
      ANT: "claude-sonnet-4-6"
    provider_options:
      OC_CL_ANT:
        max_max_tokens: 16384

providers:
  OC_CL_ANT:
    name: "OneChats (Claude)"
    base_url: "https://chatapi.onechats.ai/v1"
    api_key_env: "ONECHATS_API_KEY"
  
  ANT:
    name: "Anthropic"
    base_url: "https://api.anthropic.com"
    api_key_env: "ANTHROPIC_API_KEY"

roles:
  balanced:
    model: CL46T
    fallback: [GPT4, CL35S]
```

### 2. 环境变量

```bash
# API Keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
ONECHATS_API_KEY=...

# 日志级别
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR

# 并发控制
MAX_CONCURRENT_TASKS=5

# 重试配置
MAX_RETRIES=2
RETRY_DELAY=1.0
```

## 调试技巧

### 1. 启用详细日志

```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

### 2. 查看工作记忆

```python
result = run_skill(skill_path, input_data)
print("工作记忆:", result.get("_working_memory"))
```

### 3. 查看 Token 使用

```python
result = run_skill(skill_path, input_data)
print("Token 使用:", result.get("_metrics"))
```

### 4. 导出执行轨迹

```python
from graph_agent.callbacks.logging_cb import export_trace

result = run_skill(skill_path, input_data)
export_trace(result, "trace.json")
```

## 常见问题

### Q1: 如何跳过某个阶段？

A: 在 SKILL.md 中使用条件：

```yaml
phases:
  - name: optional_phase
    type: cognitive
    role: balanced
    condition: "state.get('need_optional', False)"
    tools: [...]
```

### Q2: 如何传递数据到下一个阶段？

A: 通过 `state` 传递：

```python
def phase1_tool(data: str) -> dict:
    result = process(data)
    # 返回的数据会自动添加到 state
    return {"phase1_result": result}

def phase2_tool(state: dict) -> dict:
    # 访问上一阶段的结果
    prev_result = state["phase1_result"]
    return {"phase2_result": process(prev_result)}
```

### Q3: 如何处理大文件？

A: 使用分块处理：

```python
def process_large_file(file_path: str) -> dict:
    results = []
    with open(file_path) as f:
        for chunk in read_chunks(f, chunk_size=1000):
            result = process_chunk(chunk)
            results.append(result)
    return {"results": results}
```

### Q4: 如何自定义重试策略？

A: 在 SKILL.md 中配置：

```yaml
phases:
  - name: process
    type: cognitive
    role: balanced
    max_retries: 5  # 最多重试 5 次
    retry_delay: 2.0  # 重试延迟 2 秒
    tools: [...]
```

### Q5: 如何集成到现有项目？

A: 作为库使用：

```python
from graph_agent.core.runner import run_skill
from pathlib import Path

def my_existing_function(data):
    # 现有逻辑
    ...
    
    # 调用 graph_agent
    skill_path = Path("skills/my-skill/SKILL.md")
    result = run_skill(skill_path, {"data": data})
    
    # 继续现有逻辑
    ...
    return result
```

## 最佳实践

### 1. 技能设计

- **单一职责**：每个技能只做一件事
- **明确输入输出**：在 SKILL.md 中清晰定义
- **分阶段执行**：复杂任务拆分为多个阶段

### 2. 工具设计

- **纯函数**：避免副作用
- **类型注解**：使用 Pydantic 定义输入
- **错误处理**：返回有意义的错误信息

### 3. 验证器设计

- **多层验证**：格式 → 语义 → 完整性
- **清晰错误**：返回具体的错误位置和原因
- **可修复**：错误信息应指导 LLM 如何修正

### 4. 性能优化

- **并发处理**：独立任务使用 asyncio
- **缓存结果**：重复计算使用缓存
- **流式输出**：长任务使用流式响应

## 示例项目

### 1. 文本分段

完整示例见 `skills/text-segmentation/`

**功能**：将章节文本分段并分类（A/B/C类）

**使用**：

```python
result = run_skill(
    Path("skills/text-segmentation/SKILL.md"),
    {
        "chapter_id": 1,
        "chapter_text": "...",
        "chapter_lines": [...]
    }
)
```

### 2. 事件提取

完整示例见 `skills/event-extraction/`

**功能**：从段落中提取事件

**使用**：

```python
result = run_skill(
    Path("skills/event-extraction/SKILL.md"),
    {
        "chapter_id": 1,
        "segments": [...]
    }
)
```

### 3. 故事解构

完整示例见 `skills/story-deconstruction/`

**功能**：编排多个技能，完成完整的故事分析流程

**使用**：

```python
result = run_skill(
    Path("skills/story-deconstruction/SKILL.md"),
    {
        "chapters": [...]
    }
)
```

## 参考资料

- [架构设计文档](./ARCHITECTURE.md)
- [实施文档](./IMPLEMENTATION.md)
- [认知循环指南](./COGNITIVE_LOOP_GUIDE.md)
- [配置参考](./CONFIG_REFERENCE.md)
- [技能编写指南](./SKILL_AUTHORING_GUIDE.md)
- [工具开发指南](./TOOL_DEVELOPMENT_GUIDE.md)

## 获取帮助

- GitHub Issues: <repository-url>/issues
- 文档: <repository-url>/docs
- 示例: <repository-url>/examples
