# Graph Agent 实施文档

## 概述

本文档详细说明 `graph_agent` 的代码实现细节、模块职责和关键算法。

## 目录结构

```
graph_agent/
├── core/                    # 核心引擎
│   ├── harness.py          # 双层控制循环（500行）
│   ├── runner.py           # 任务执行器（300行）
│   ├── compiler.py         # SKILL.md 编译器（400行）
│   ├── loader.py           # 技能加载器（200行）
│   └── callback_bridge.py  # 回调桥接（150行）
├── cognitive/              # 认知机制
│   ├── memory.py           # 工作记忆（100行）
│   ├── finish.py           # 任务完成检测（150行）
│   └── middlewares.py      # 中间件（200行）
├── models/                 # 模型管理
│   ├── resolver.py         # 模型解析（400行）
│   └── reasoning_patch.py  # 推理内容补丁（100行）
├── callbacks/              # 回调和日志
│   └── logging_cb.py       # 结构化日志（300行）
└── utils/                  # 工具函数
    └── llm_utils.py        # LLM 工具（100行）
```

**总代码量**：约 3000 行（不含注释和空行）

## 核心模块实现

### 1. GraphAgentHarness (core/harness.py)

**职责**：实现双层控制循环，编排阶段执行。

**关键方法**：

#### `run(input_data: dict) -> dict`

主执行循环：

```python
def run(self, input_data: dict) -> dict:
    state = self._init_state(input_data)
    
    for phase in self.phases:
        # 1. 计划强制执行
        if not state.get("plan_verified"):
            state = self._enforce_planning(phase, state)
        
        # 2. 执行阶段
        state = self._execute_phase(phase, state)
        
        # 3. 自我检查
        if phase.has_validator:
            state = self._self_check(phase, state)
        
        # 4. 检查点压缩
        if len(state["messages"]) > self.checkpoint_threshold:
            state = self._compact_checkpoint(state)
    
    return state
```

**关键逻辑**：

1. **计划强制执行** (`_enforce_planning`)：
   - 检查 `_working_memory` 是否更新
   - 未更新则注入 `PLANNING_NUDGE`
   - 最多重试 3 次

2. **阶段执行** (`_execute_phase`)：
   - 根据阶段类型选择执行模式：
     - `code_only`：直接调用工具函数
     - `cognitive`：调用 LLM + 工具
   - 注入中间件（工作记忆、死胡同检测）
   - 处理工具调用和响应

3. **自我检查** (`_self_check`)：
   - 调用验证器检查输出
   - 验证失败则重试前一阶段
   - 最多重试 `max_retries` 次（默认 2）

4. **检查点压缩** (`_compact_checkpoint`)：
   - 保留最近 N 条消息
   - 压缩中间消息为摘要
   - 保留所有工具调用结果

### 2. SkillCompiler (core/compiler.py)

**职责**：编译 SKILL.md 为可执行的技能对象。

**编译流程**：

```python
def compile(skill_path: Path) -> Skill:
    # 1. 解析 Markdown
    content = skill_path.read_text()
    frontmatter, body = parse_markdown(content)
    
    # 2. 验证 frontmatter
    validate_frontmatter(frontmatter)
    
    # 3. 加载工具函数
    tools = load_tools(skill_path.parent / "script")
    
    # 4. 构建阶段图
    phases = build_phase_graph(frontmatter["phases"], tools)
    
    # 5. 生成 Skill 对象
    return Skill(
        name=frontmatter["name"],
        phases=phases,
        tools=tools,
        prompt=body
    )
```

**验证规则**：

- `name` 必须是有效的标识符
- `phases` 至少包含 1 个阶段
- 每个阶段的 `tools` 必须在 `script/` 中定义
- `type` 必须是 `code_only` 或 `cognitive`

**错误处理**：

- 编译错误分为 `FATAL` 和 `WARNING`
- `FATAL` 错误阻止技能加载
- `WARNING` 仅记录日志

### 3. ModelResolver (models/resolver.py)

**职责**：根据角色和配置解析具体模型。

**解析流程**：

```python
def resolve(role: str, thinking: bool = None) -> ModelConfig:
    # 1. 查找角色定义
    role_config = self.roles.get(role)
    if not role_config:
        raise ValueError(f"Unknown role: {role}")
    
    # 2. 解析模型代码
    model_code = role_config["model"]
    model_config = self.models.get(model_code)
    
    # 3. 选择提供商
    provider = self._select_provider(model_config)
    
    # 4. 构建模型配置
    return ModelConfig(
        provider=provider,
        model_name=model_config["providers"][provider],
        reasoning=thinking if thinking is not None else model_config.get("reasoning", False),
        max_tokens=model_config.get("min_max_tokens", 4096)
    )
```

**提供商选择策略**：

1. 检查环境变量（优先级最高）
2. 按 `providers` 顺序尝试
3. 检查 API key 是否存在
4. 返回第一个可用的提供商

**降级策略**：

- 如果首选模型不可用，自动降级到备选模型
- 降级链在 `llm_roles.yaml` 中定义
- 记录降级日志

### 4. WorkingMemory (cognitive/memory.py)

**职责**：管理工作记忆的存储和注入。

**存储格式**：

```python
{
    "_working_memory": {
        "phase": "segment",
        "content": "执行计划内容...",
        "updated_at": "2026-04-11T15:30:00"
    }
}
```

**注入机制**：

```python
def inject_memory(messages: list) -> list:
    memory = state.get("_working_memory")
    if not memory:
        return messages
    
    # 在最后一条消息前注入
    reminder = {
        "role": "system",
        "content": f"[工作记忆] {memory['content']}"
    }
    return messages[:-1] + [reminder, messages[-1]]
```

**更新策略**：

- 每个阶段开始时清空
- 只保留当前阶段的记忆
- 支持增量更新

### 5. LoggingCallback (callbacks/logging_cb.py)

**职责**：记录结构化日志，支持审计和调试。

**日志类型**：

1. **阶段日志**：
   ```
   [Phase Start] segment
   [Phase End] segment | metrics={'total_input_tokens': 1000, 'total_output_tokens': 500}
   ```

2. **LLM 调用日志**：
   ```
   [LLM Call] segment | in=1000 out=500
   ```

3. **工具调用日志**：
   ```
   [Tool Call] segment.parse_segmentation_output | result=content='Parsed 13 segments'
   ```

4. **验证日志**：
   ```
   [Validation Fail] review | retry=0 | errors=Segment 6: 25 sentences
   ```

5. **重试日志**：
   ```
   [Retry] review → segment
   ```

**日志级别**：

- `INFO`：正常执行流程
- `WARNING`：验证失败、降级
- `ERROR`：工具执行错误
- `DEBUG`：详细调试信息（默认关闭）

## 关键算法

### 1. 检查点压缩算法

**目标**：将长消息历史压缩为摘要，保留关键信息。

**算法**：

```python
def compact_checkpoint(messages: list, keep_recent: int = 10) -> list:
    if len(messages) <= keep_recent:
        return messages
    
    # 1. 保留最近 N 条
    recent = messages[-keep_recent:]
    
    # 2. 压缩中间消息
    to_compress = messages[:-keep_recent]
    
    # 3. 提取关键信息
    summary = {
        "tool_calls": extract_tool_calls(to_compress),
        "working_memory": extract_working_memory(to_compress),
        "key_decisions": extract_decisions(to_compress)
    }
    
    # 4. 生成摘要消息
    summary_msg = {
        "role": "system",
        "content": f"[历史摘要] {format_summary(summary)}"
    }
    
    return [summary_msg] + recent
```

**保留规则**：

- 所有工具调用和结果
- 最后一次工作记忆更新
- 关键决策点（finish_task 调用）

### 2. 死胡同检测算法

**目标**：检测 LLM 是否陷入重复循环。

**算法**：

```python
def detect_dead_end(messages: list, window: int = 5) -> bool:
    if len(messages) < window:
        return False
    
    recent = messages[-window:]
    
    # 1. 提取工具调用序列
    tool_sequence = [
        msg.get("tool_calls", [])
        for msg in recent
        if msg.get("role") == "assistant"
    ]
    
    # 2. 检测重复模式
    if len(tool_sequence) < 3:
        return False
    
    # 3. 检查是否连续 3 次相同
    if tool_sequence[-1] == tool_sequence[-2] == tool_sequence[-3]:
        return True
    
    return False
```

**干预策略**：

- 检测到死胡同后注入提示
- 建议尝试不同的工具或方法
- 最多干预 2 次，之后强制终止

### 3. 模型降级算法

**目标**：当首选模型不可用时，自动降级到备选模型。

**算法**：

```python
def resolve_with_fallback(role: str) -> ModelConfig:
    fallback_chain = get_fallback_chain(role)
    
    for model_code in fallback_chain:
        try:
            config = resolve_model(model_code)
            if is_available(config):
                if model_code != fallback_chain[0]:
                    log_fallback(fallback_chain[0], model_code)
                return config
        except Exception as e:
            log_error(model_code, e)
            continue
    
    raise RuntimeError(f"No available model for role: {role}")
```

**降级链示例**：

```
balanced → claude-sonnet-4-6 → gpt-4 → claude-3-5-sonnet
```

## 错误处理

### 1. 工具执行错误

**策略**：

- 捕获所有工具异常
- 返回错误消息给 LLM
- LLM 可以选择重试或使用其他工具

**示例**：

```python
try:
    result = tool_func(**args)
except Exception as e:
    result = {
        "error": str(e),
        "suggestion": "请检查输入参数或尝试其他工具"
    }
```

### 2. LLM 调用错误

**策略**：

- 区分临时错误（rate limit）和永久错误（invalid key）
- 临时错误自动重试（指数退避）
- 永久错误立即失败

**重试配置**：

```python
retry_config = {
    "max_retries": 3,
    "initial_delay": 1.0,
    "backoff_factor": 2.0,
    "max_delay": 60.0
}
```

### 3. 验证错误

**策略**：

- 验证失败触发重试
- 重试时注入错误信息
- 超过最大重试次数后失败

**错误注入示例**：

```
[验证失败] 上一次输出存在以下问题：
1. Segment 6: 25 sentences - consider splitting
请修正后重新输出。
```

## 性能优化

### 1. 并发执行

**batch-analysis 并发实现**：

```python
async def analyze_batch(chapters: list) -> list:
    tasks = [
        analyze_chapter(ch)
        for ch in chapters
    ]
    return await asyncio.gather(*tasks)
```

**并发控制**：

- 使用 `asyncio.Semaphore` 限制并发数
- 默认最大并发：5

### 2. 缓存机制

**配置缓存**：

```python
@lru_cache(maxsize=1)
def load_llm_config() -> dict:
    return yaml.safe_load(open("llm_roles.yaml"))
```

**技能编译缓存**：

```python
_skill_cache = {}

def load_skill(path: Path) -> Skill:
    if path in _skill_cache:
        return _skill_cache[path]
    
    skill = compile_skill(path)
    _skill_cache[path] = skill
    return skill
```

### 3. 流式输出

**实现**：

```python
async def stream_response(agent, input_data):
    async for chunk in agent.astream(input_data):
        if "messages" in chunk:
            for msg in chunk["messages"]:
                if msg.get("role") == "assistant":
                    yield msg.get("content", "")
```

## 测试策略

### 1. 单元测试

**覆盖范围**：

- 所有工具函数
- 验证器
- 模型解析器
- 检查点压缩

**示例**：

```python
def test_parse_segmentation_output():
    output = """
    段落1（1-10）：A类
    段落2（11-20）：B类
    """
    result = parse_segmentation_output(output)
    assert len(result) == 2
    assert result[0]["type"] == "A"
```

### 2. 集成测试

**测试场景**：

- 单章节完整流程
- 多章节并发处理
- 验证失败重试
- 模型降级

### 3. E2E 测试

**测试数据**：

- 25 章真实小说数据
- 覆盖所有事件类型（A/B/C）

**验证指标**：

- 输出格式正确性
- 事件分类准确性
- Token 使用量
- 执行时间

## 部署建议

### 1. 环境要求

- Python 3.10+
- 8GB+ RAM
- 支持异步 I/O

### 2. 配置建议

**生产环境**：

```yaml
# llm_roles.yaml
roles:
  balanced:
    model: CL46T  # Claude Sonnet 4.6 Thinking
    fallback: [GPT4, CL35S]
```

**开发环境**：

```yaml
roles:
  balanced:
    model: GPT4T  # GPT-4 Turbo (更便宜)
```

### 3. 监控指标

- Token 使用量（按阶段统计）
- 执行时间（按阶段统计）
- 重试次数
- 错误率

## 故障排查

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

## 参考资料

- [架构设计文档](./ARCHITECTURE.md)
- [认知循环指南](./COGNITIVE_LOOP_GUIDE.md)
- [配置参考](./CONFIG_REFERENCE.md)
