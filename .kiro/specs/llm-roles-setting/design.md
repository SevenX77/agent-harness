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
  4. 组装 `available_models: list[ModelInfo]`，为对应的模型注入 `capabilities = {"thinking": True/False, "max_context_tokens": 128000, ...}`。OpenRouter 等聚合 provider 返回的 `~vendor/model` / `vendor/model` 在写回前 canonicalize 为 `model`，避免同一模型因路由前缀重复展示；如需要保留原始路由 id，写入 `capabilities.provider_model_id`。
  5. API Router 调用 `_persist_test_outcome`，自动将此字典以 `provider-model` 维度写回到 `.studio/llm_credentials.json`。

---

## §3 Frontend UI & State (界面架构与交互动线)

### 3.1 双栏多 UI 模式布局 (Layout)
```tsx
<SettingsPage>
  ├─ <SidebarNav> (General / API Keys / LLM Roles)
  └─ <LlmRolesTab>
      └─ <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(14rem,20vw)] 2xl:grid-cols-[minmax(0,1fr)_minmax(14rem,18rem)]"> (内容区，受 Settings max-width 约束)
          ├─ <ScrollArea> (Roles 主内容区，标题与 Role cards 作为整体上下滚动)
          │   ├─ <SectionTitle trailing={<SaveStatusBadge />} />
          │   └─ <RoleCardList>
          │       ├─ <RoleCard> (所有可见 Role 平铺展示，不使用顶部 tab 选择)
          │           ├─ <RoleHeader modelFallbackSwitch testChainButton saveStatus />
          │           └─ <ModelFallbackChain> (1级 DndContext)
          │               └─ <ModelItem>
          │                   ├─ <ModelItemHeader onClick={openSettings}>
          │                   │   {/* ModelSettingsDialog 承载下沉的 Temperature 和 Max Tokens */}
          │                   └─ <ProviderChain> (2级 DndContext)
          │                       └─ <ProviderTag>
          │                           ├─ <StatusDot aria-label="Connected|Untested|Failed" />
          │                           └─ <CapabilityBadge icon={<BrainCircuit />}> (展示 Thinking 能力)
          │           └─ <AddModelSelect /> (Role card 内添加 model)
          │       └─ <Button>Add Role</Button> (底部添加 Role，与 API Keys Add Provider 模式一致)
          └─ <aside className="sticky top-0"> (右侧模型库)
              ├─ <h3>Available Models</h3>
              ├─ <Input aria-label="Search available models" /> (按 vendor / exact model id / provider label 过滤模型库)
              └─ <ScrollArea>
                  └─ <AvailableModelsSidebar /> (无外层 Card；从 credentials.providers[].available_models 聚合 tested models)
                      └─ <VendorGroup>
                          └─ <SelectableModelCard>
                              ├─ exact model id
                              ├─ provider labels (默认单行截断；点击后仅展开这一行)
                              ├─ <Brain /> + tiny "Thinking" label (空间不足时隐藏文字)
                              └─ selected 时仅展开 provider labels 文本，不额外展示 provider id/detail 区块
```

### 3.1.1 Studio UI Compliance (必须遵守)
LLM Roles 页属于 `apps/studio/frontend` 的 Settings UI，实施前必须读取 `docs/development/FRONTEND_UI_SPEC.md` §2，并按以下约束落地：

- **组件复用**: 交互组件优先使用本地 `@/components/ui/*` wrapper。`ModelSettingsDialog` 必须基于 `ui/dialog.tsx`；加载态使用 `ui/skeleton.tsx`；长列表使用 `ui/scroll-area.tsx`；右侧模型库搜索使用 `ui/input.tsx`；状态说明使用 `ui/tooltip.tsx`；状态/能力标识使用 `ui/badge.tsx`；`model_fallback` 使用 `ui/switch.tsx` 或现有 Settings 约定的二态控件。
- **Settings 表单结构**: Temperature / Max Tokens 表单必须使用 `FieldSet` / `FieldGroup` / `Field` / `FieldLabel` / `FieldDescription`，输入控件使用 `ui/input.tsx`。不要在业务组件里手写 label-description-control 三段式布局。
- **Auto-save**: LLM Roles 变更遵循 API Keys 页交互：字段变更、排序变更、append/remove 后 debounce 写回 `/api/llm/roles`，并在 `SectionTitle` trailing 或 Role header 中显示 `Pending` / `Saving` / `Saved` / `Save failed`。除非引入明确事务型提交，不保留独立 `Save` 按钮。
- **Token 化样式**: 新增 UI 不得 hardcode hex 或 Tailwind 具体色值（如 `bg-green-500`、`text-red-400`）。背景、边框、文字、状态均使用语义 token 或本地组件 variant；如缺少 success/warning 状态 token，先在设计系统层补语义 variant，再在业务组件使用。
- **圆角与密度**: 卡片、侧栏、弹窗、badge 等圆角不得超过 `rounded-md`，优先保持 Settings/API Keys 页的紧凑桌面工具密度。
- **响应式宽度**: LLM Roles 可作为数据密集页放宽到 `max-w-5xl` / `max-w-6xl`，但主列必须 `min-w-0`。`SectionTitle` 必须位于 Roles 主列 `ScrollArea` 内，与 Role cards 作为同一个滚动整体；右侧模型库与 Roles 主列同级。桌面端右侧模型库必须固定在页面视口内，但宽度采用 `minmax(14rem, 20vw)` 的自适应列，超宽时可封顶到 `18rem`，不要固定占用 `18rem`；采用无外层 Card 的 title + search input + `ScrollArea` 结构，效果参考 shadcn 文档页侧栏；窄宽度下右侧模型库折到下方，避免横向挤压和文本穿模。
- **Available Models 数据源**: 右侧模型库只展示 provider test / manual probing 写回的 `credentials.providers[*].available_models`，不得再使用 `RolesData.models` 的模型缩写。模型名称显示 canonical exact model id；OpenRouter 等聚合 provider 的路由前缀 `~vendor/` / `vendor/` 在写入和展示侧都要归一化，保证同一 canonical id 合并并展示多个 provider label。调用 provider 时仍保留原始 provider model id（例如 `capabilities.provider_model_id`），避免展示归一化破坏真实请求参数。跨 provider 等价关系必须保守：只合并 canonical id 完全一致，或由 provider metadata / curated alias map 显式声明等价的模型；不要用模糊搜索规则自动合并 `latest`、dated snapshot、minor version、fast variant 等命名相近但语义不同的模型。
- **Available Models 交互**: 按推断 vendor 分组；搜索支持 vendor、exact model id、provider label，并额外做大小写与标点不敏感匹配（如 `gpt5` 匹配 `gpt-5`，`claude opus 4` 匹配 `claude-opus-4`）。右侧列表的 `ScrollArea` 隐藏 scrollbar 且不保留内侧 gutter；model card 必须 `w-full min-w-0` 适应父容器，避免横向截断。model card hover 只改变背景色，不显示 hover ring/border；selected 状态保留 primary ring 高亮。第二行显示 provider label，默认单行截断，点击后只展开这一行完整文本，不渲染额外 provider id/detail 区块。
- **图标与可访问性**: 工具按钮使用 lucide 图标（如 `Settings`, `GripVertical`, `Brain`, `Play`, `Trash2`），并提供 `aria-label` 与 `Tooltip`。Thinking 能力在 Available Models 中使用 `Badge` + `Brain` 图标 + tiny `Thinking` 文本，窄宽度下可隐藏文字但保留 `aria-label`。状态点不能只靠颜色表达，必须有文本/tooltip/aria-label。

### 3.2 Test Chain 聚合并发策略 (User Q4)
为防止触发 429 (Rate Limit)，同时保证测试效率，采用混合调度策略：
- **Model 间**: 并发探活。
- **单 Model 下的 Provider 间**: 串行探活（严格遵循 fallback 顺序测试，第一个失败才测第二个）。
- **全局限流**: 无论多少个 Role 或 Model，最高全局并发限制为 **3**。可使用 `p-limit`，也可在前端 hook 内实现有单测覆盖的小型 limiter；二者只能选一种，避免重复并发控制。

### 3.3 UX 动线: 探测与反馈 (User Q2)
- 用户点击 Test Chain 后。
- 系统根据 `llm_roles.yaml` 推断哪些模型理论上支持 Thinking。
- 对这些模型进行 **强校验探活**。
- 若探活通过，UI 中的 `ProviderTag` 使用 `CapabilityBadge` + `BrainCircuit` 图标标记 Thinking 可用；若探活 400 失败，展示 disabled variant + tooltip，说明该 provider-model 通道不支持 Thinking。
- **Temperature / Max Tokens 设置**: 用户点开 `ModelSettingsDialog`。空值表示继承系统默认，`Input` 的 `value` 必须同步真实值；默认说明写入 `FieldDescription`（例如 `Blank uses system default 0.7`），不要把真实默认值塞进 placeholder。
- 错误与进行中状态必须实时反馈：Test Chain 运行中显示 spinner/progress，失败 provider 保留错误摘要 tooltip，最终状态写回 capabilities 并驱动 UI badge。

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
