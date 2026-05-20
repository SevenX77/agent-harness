# LLM Roles Configuration Design

## §1 Backend Schema (数据层设计)

### 1.1 `RoleEntry` 和 `RoleModelEntry` 变更
将生成参数的作用域从 Role 级彻底下沉到 Model 级。

```python
# [BREAKING] RoleEntry 删除 temperature 字段
class RoleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # temperature: float = 0.7  # [BREAKING] 该字段彻底删除
    model_fallback: bool = False              # [KEEP] 保留作为全局降级开关 (User Q3)
    active_model: str
    system_prompt_prefix: str | None = None
    models: dict[str, RoleModelEntry] = Field(default_factory=dict)

# [NEW] RoleModelEntry 承接参数
class RoleModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    providers: list[str] = Field(default_factory=list)
    # [NEW] 默认值设为 None。在调用消费端时，若该值为 None，则回退到系统全局默认 0.7 (User Q1)
    temperature: float | None = None  
    max_tokens: int | None = None     # [NEW]
```

### 1.2 `ModelInfo` 架构对齐 (承接能力探测)
延续 API Keys Round 3 的 Schema-less 理念，`capabilities` 使用纯字典结构，以容纳任意动态的探测参数。

```python
class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    capabilities: dict[str, Any] = Field(default_factory=dict) # 存储: thinking, max_context_tokens 等
```

---

## §2 API Endpoints (通信与回写设计)

复用现有 Endpoint，重点扩展探活逻辑中的能力注入和持久化。

- **Endpoint**: `POST /api/llm/providers/test`
- **Request**: `ProviderTestRequest` (不变)
- **Response**: `ProviderTestResponse`
- **处理逻辑**:
  1. 系统在探活前检查模型字典，若模型声明支持 `reasoning: true`。
  2. 发起附带 `thinking` 参数的 Payload。
  3. 捕获响应。
  4. 组装 `available_models: list[ModelInfo]`，为对应的模型注入 `capabilities = {"thinking": True/False, "max_context_tokens": 128000, ...}`。
  5. API Router 调用 `_persist_test_outcome`，自动将此字典以 `provider-model` 维度写回到 `.studio/llm_credentials.json`。

---

## §3 Frontend UI & State (界面架构与交互动线)

### 3.1 双栏多 UI 模式布局 (Layout)
```tsx
<SettingsPage>
  ├─ <SidebarNav> (General / API Keys / LLM Roles)
  └─ <LlmRolesTab>
      ├─ <div className="flex-1"> (主内容区)
      │   └─ <RoleCardList>
      │       └─ <RoleCard isSelected>
      │           ├─ <RoleHeader modelFallbackSwitch testChainButton />
      │           └─ <ModelFallbackChain> (1级 DndContext)
      │               └─ <ModelItem>
      │                   ├─ <ModelItemHeader onClick={openSettings}> 
      │                   │   {/* [NEW] ModelSettingsModal 承载下沉的 Temperature 和 Max Tokens */}
      │                   └─ <ProviderChain> (2级 DndContext)
      │                       └─ <ProviderTag>
      │                           ├─ <StatusDot> (🟢⚪🔴)
      │                           └─ <CapabilityBadge icon="🧠"> (展示 Thinking 能力)
      └─ <div className="w-64 border-l"> (右侧模型库)
          └─ <AvailableModelsSidebar onAppendToRole={handleAppend} />
```

### 3.2 Test Chain 聚合并发策略 (User Q4)
为防止触发 429 (Rate Limit)，同时保证测试效率，采用混合调度策略：
- **Model 间**: 并发探活。
- **单 Model 下的 Provider 间**: 串行探活（严格遵循 fallback 顺序测试，第一个失败才测第二个）。
- **全局限流**: 无论多少个 Role 或 Model，最高全局并发限制为 **3** (使用 p-limit 实现)。

### 3.3 UX 动线: 探测与反馈 (User Q2)
- 用户点击 Test Chain 后。
- 系统根据 `llm_roles.yaml` 推断哪些模型理论上支持 Thinking。
- 对这些模型进行 **强校验探活**。
- 若探活通过，UI 中的 `ProviderTag` 上点亮 `🧠` 图标；若探活 400 失败，`🧠` 图标加删除线并置灰，提示用户该下游通道阉割了此能力。
- **Temperature / Max Tokens 设置**: 用户点开 `ModelSettingsModal`，看到占位符 `Default (System: 0.7)`。输入自定义数值后覆盖为明确数值。

---

## §4 Persistence & Migration (持久化与平滑过渡)

### 4.1 YAML 迁移脚本逻辑
后端启动时读取 `config/llm_roles.yaml`：
1. 遍历所有的 `roles` 字典。
2. 若某 Role 中发现外层 `temperature` 字段存在：
   - 提取该数值（例如 0.7）。
   - 将其写入该 Role 内 `models` 字典下的每一个 `RoleModelEntry` 的 `temperature` 字段中。
   - 删除外层的 `temperature` 字段。
3. 如果发生过上述变更，重新序列化并覆盖写入 `llm_roles.yaml`。
4. 确保在后续读取中，如果新角色的 model 配置里未声明 temperature (即 `None`)，在构造实际请求参数时将安全地回退并取系统级默认值。