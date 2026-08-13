# 决议:role 模型归网关、厂商归属单一事实源(2026-08-13)

用户裁决原话:「找成熟做法,第一性原理,从底层修复,模块化思维,高内聚低耦合,
把单独的功能拆开可复用」——批准台账 P34 与 P32 两项结构性变更,并给出实施原则。
本文件按「方案落盘」规矩记录决策、关键设计决定与验收判据;实施分两个 PR 串行进行
(P34 先、P32 后),各自更新台账对应行。

## 决策一(P34):role 的领域模型归网关所有

### 问题

`graph_agent_gateway.role.materialize_role` 读 `role.model_groups`、`role.intent`、
`role.model_fallback_enabled`,而网关自己的 `registry/schema.py:RoleEntry` 一个都
没有——这三个字段连同 `RoleIntent` / `RoleProviderModel` / `RoleModelGroup` 全部
定义在 `apps/studio/backend/app/models/llm_config.py`。把网关自己的 `RoleEntry`
喂给网关自己的 `materialize_role`,得到的是空链 + `NO_AVAILABLE_ROUTE`。网关的
测试为此手搓假类(`test_productization_role_materialization_red.py`:
「Fixtures — the role/group shape the materializer walks (duck-typed)」),因为这个
包没有能表达自己输入的类型。这与 #778 修掉的 `route.evidence` 同类:SDK 依赖只有
某个宿主才有的形状,AGENTS.md 禁止的方向。

### 决定

1. **模型搬家(成熟先例 = #772/#778 的 route/endpoint 模式)**:
   `RoleIntent`、`RoleProviderModel`、`RoleModelGroup` 移入网关
   `registry/schema.py`;网关 `RoleEntry` 增加 `model_fallback_enabled` /
   `intent` / `model_groups` 三个字段(带默认值,构造方不受影响)。
   `DEFAULT_ROLE_TEMPERATURE` 随字段默认值一起移入(温度=表盘份额的语义本来
   就在网关 `registry/bounds.py`,`AUTHORED_TEMPERATURE_MAX` 已在那里)。
2. **Studio 子类只留 Studio 的东西**:`role_kind`(UI 分类)与
   `materialization_report`(对网关 report 的投影)。三个搬走的模型在 Studio 不留
   转发别名,消费方直接 import `graph_agent_gateway.registry`(#772 先例)。
3. **迁移垫片死在 Studio 层**:`_migrate_legacy_provider_preference`
   (official_first/ready_first → manual_order)不随模型入 SDK。实测真机
   `llm_roles.yaml` 里旧值出现 0 次,垫片守着空数据,直接删除。
   `provider_preference` 字段本身保留(真机数据有 4 处、材料化按
   provider_models 列表顺序走就是 manual_order 语义)。
4. **健康存储走 Port/Adapter**:网关在 `registry/contracts.py` 定义
   `ActiveCircuit` + `HealthStore` Protocol(网关只读
   scope/scope_id/retry_at/reason_code/message 五个成员和一个
   `get_active_circuits` 方法);Studio 的 `SqliteLlmHealthStore` /
   `RuntimeCircuit` 结构性满足,不改动。熔断持久化本体的下沉是台账 §7 另一项,
   不在本决议范围。
5. **契约上真类型**:`MaterializeRoleRequest` 变为
   `role: RoleEntry` / `credentials: RouteRegistry` /
   `health_store: HealthStore | None`;`materialization.py` 剩余的 `_value()`
   鸭子读取全部删除,连同 `_value` 助手本身。网关测试的手搓假类换成真模型。
   Studio 适配器 `materialize_role` 的返回值与内部变量同步收紧。

### 验收判据

- 新增网关测试先红后绿:纯网关 `RoleEntry` + `RegistrySnapshot` 能走通
  `materialize_role`;`inspect` 断言契约注解;源码扫描断言 `_value` 不复存在。
- 门禁全绿:`ruff` / `mypy --strict`(gateway) / `mypy`(studio) /
  pytest ×3 / 前端四连 / pip-audit。
- 行为不变:studio backend 全套(≈1685)与网关全套(≈575)零改语义通过
  (测试改动仅限换掉假类与 import 路径)。

## 决策二(P32):「这个模型归谁」只有一个作答处

### 问题

厂商归属的 if-链在仓里有三份:网关
`registry/model_naming.py:_infer_owner_from_text`(#779 起为权威)、Studio 后端
`app/routers/llm.py:_section_label_from_display_name`(且**优先于**网关答案)、
前端 `AvailableModelsSidebar.tsx:fallbackModelGroupSection`。三次成律已触发;
且组级归属用多数票(`_dominant_section_label`),把「模型自己声明的厂商」和
「从端点猜的」等权计票——#779 点验发现的 6 条残留(MiniMax-M1 等)正是这么来的:
同一模型在 OpenRouter 上带 `minimax/` 前缀(声明),在代理上裸名(猜测),
多数票让猜测赢了声明。

### 决定

1. **网关多暴露一个事实**:`ModelIdentityProjection` 增加
   `owner_source: Literal["model_id", "declared_vendor", "endpoint_context"]`
   (内部 `_OwnerReading.source` 已有,公开它;`confidence` 保持由它派生)。
2. **组级归属选举下沉网关、拆成可复用函数**:新函数(定名
   `elect_model_group_section(projections) -> str`,`registry/model_naming.py`)
   按来源分层选举——`model_id` 层优先,其次 `declared_vendor`,最后
   `endpoint_context`;同层内多数票,平票取字典序保证确定性。声明压过猜测,
   与 #779 的路由级规则同一条原理。
3. **Studio 后端删掉自己的两条链**:`_section_label_from_display_name` 整个删除;
   `_dominant_section_label` 由网关选举函数取代。
4. **前端删掉第三条链**:`fallbackModelGroupSection` 删除;
   `section_label` 在 API 契约(后端响应模型与前端 `llm.ts` 类型)改为**必填**
   ——网关 `_section_for_owner` 恒返回非空,可选性是给兜底链留的洞,兜底链
   死了洞一起补上。
5. 手册 `docs/graph-agent-gateway/USAGE.md` §3.8 同 PR 补充 `owner_source`
   与选举函数;MVP1 设计源 05 单元涉及行同步。

### 验收判据

- 网关选举函数测试先红后绿(含「一条声明胜过多条猜测」用例)。
- 源码扫描式测试:studio 后端与前端不再含厂商 if-链
  (删除后以现有 ratchet 风格锁住)。
- 真机点验:MiniMax-M1 / Trinity Large 类分组落到声明厂商的分区;
  Healer / Hunter(无任何声明)留在端点语境分区且 `confidence=medium`,
  属诚实答案,不算缺陷。
- 门禁全绿(同上,前端四连必跑)。
