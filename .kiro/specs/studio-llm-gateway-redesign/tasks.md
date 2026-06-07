---
status: Ready for Review
created: 2026-06-01
owner: Studio + Engine
related_requirements: ./requirements.md
related_design: ./design.md
direction: ./architecture-direction.md
---

# LLM Gateway & Roles Redesign — Tasks

> 执行方式：TDD（先写失败测试，再实现）。每个任务遵循 logging 铁律（跳过/降级必须有 WARNING）。
> 近期承诺范围 = Phase 1 + Phase 2 + Phase 3（对应 ①②③ + 横切形状）。Phase 4 为模块完整性记录，**排期延后**。

## Phase 0: 基线与方向落盘

- [x] 0. 落盘方向决策与勘察结论
  - 写 `architecture-direction.md`（远端服务化分层、不 Rust 化、回归根因）。
  - 写 `requirements.md` / `design.md` / `tasks.md`，统一两份重叠 spec 的方向。
  - _Requirements: 4_

## Phase 1: Save 解耦（Req 1，② save 解耦）

- [ ] 1. 先写失败测试：未配凭证下保存引用未配置路由的角色应成功
  - 在 `apps/studio/backend/tests/.../test_llm_registry_api.py` 新增
    `test_role_save_unconfigured_route_success`：未配 openrouter，PUT 含
    `openrouter-prod:deepseek.deepseek-r1` 的角色断言 200；DELETE 不相干角色断言 200。
  - 确认该测试在修改前失败（当前返回 400）。
  - _Requirements: 1.1, 1.2_

- [ ] 2. 实现 save 解耦
  - `_save_roles_with_active_routes`（`routers/llm.py:4726`）改为以 `known_route_ids=None`
    调用 `validate_references` 与 `save_roles_file`。
  - 保留 schema/格式校验路径的 400 行为（Req 1.3）。
  - 函数签名预留 `user_id` 参数位（Req 4.1）。
  - 跑通新测试 + 既有 roles API 测试。
  - _Requirements: 1.1, 1.3, 1.4, 4.1_

## Phase 2: Resolver 优雅跳过（Req 2，① resolver 移植）

- [ ] 3. 先写失败测试：fallback_chain 跳过未配置路由
  - 在 gateway 包 resolver 测试中新增：chain=[未配置, 已配置] → 解析得到已配置那条；
    断言产生 WARNING；全未配置 → `resolve_role` 抛 `RegistryResolutionError`（`ModelResolver.resolve`
    层断言 `GatewayRoleNotConfiguredError`）；`model_override` 未命中仍 fail-fast。
  - 确认"chain=[未配置, 已配置]"用例在修改前失败（当前崩在第一个）。
  - _Requirements: 2.1, 2.3, 2.4_

- [ ] 4. 实现 resolver 跳过语义
  - `registry/resolver.py:resolve_role` 遍历循环：`route is None` / 非可执行 status /
    endpoint 缺凭证 → `continue` + `logger.warning(role_name, route_id, reason)`（移植旧
    `config/llm_config.py:resolve_role` 语义）。
  - 过滤后 `resolved_routes` 为空 → `raise RegistryResolutionError`（经 `resolver.py:99` 映射为
    `GatewayRoleNotConfiguredError`）。`AllProvidersFailedError` 仅执行期，不用于解析期空链。
  - 执行期错误分类与 `model_override` 单点路径保持不变。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 5. 同步更正引擎文档
  - 更新 `docs/graph-agent-gateway/mvp0/mvp0-alignment.md` "Runtime 行为"：标注解析期对
    fallback_chain 条目"跳过未配置"为有意修订，执行期 fail-fast 不变。
  - _Requirements: 2.1_

## Phase 3: 测试状态 SSOT 回写（Req 3，③ 测试 SSOT）+ 远端形状（Req 4）

- [ ] 6. 先写失败测试：测试结论持久化且可重读
  - 后端测试：Role/Copilot Test 完成后 SSOT 持有每路由 ready/unsupported + reason；
    模拟"重启"（重新 load）后仍可重建状态投影。
  - _Requirements: 3.1, 3.3_

- [ ] 7. 后端：测试结论写回 SSOT
  - Role/Copilot Test 完成时把每路由结论（status + reason + attempted_at）经 Storage seam
    落盘（沿用 credentials `provider_routes[].status` + 必要诊断旁路），预留 `user_id`。
  - 在 `GET /api/llm/registry`（或 roles 读取）响应带出可重建 UI 的测试状态投影。
  - _Requirements: 3.1, 3.3, 4.1, 4.2_

- [ ] 8. 前端：从后端 SSOT 渲染就绪灯，删并行内存真值源
  - `CopilotTab` / `LlmRolesTab`：进入/重挂载/重启后从后端响应渲染就绪灯。
  - `routeStatusOverrides` 降级为"测试进行中"乐观显示，完成后以后端为准。
  - 删除"前端内存态作为唯一真值源"路径。
  - _Requirements: 3.2, 3.4_

- [ ] 9. 更新受影响前端测试 + 同步 studio 文档
  - 更新 SettingsPage/CopilotTab/LlmRolesTab 测试以反映"状态来源=后端"（预期需修改）。
  - 更新 `docs/studio/03_platform/llm-gateway/baseline.md` + `mvp0-alignment.md`。
  - _Requirements: 3.2_

- [ ] 10. 横切自检：远端就绪形状 + 无新反远端债
  - 复核 Phase 1-3 的接口都预留 `user_id` 且经 Storage seam；无 Rust、无 DB/KMS、
    无新明文密钥写入点、无硬编码全局单用户路径。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

## Phase 4: 模块完整性（已记录，排期延后 — 见 docs/deferred-items.md）

- [x] 11. (已撤回 — 无待办) Req 5 经代码核实为误诊：`untested` 已在侧边栏显示
  （`AvailableModelsSidebar.tsx:385`），`needs_setup`=缺密钥/失败属合理隐藏。无改动。
  详见 requirements.md Req 5 / DEF-006。

- [ ] 12. (延后) Req 6：`_probe_copilot_sdk_tool_call` WaveSpeed 失败返回清晰降级提示；
  不做协议翻译。
  - _Requirements: 6.1, 6.2_

- [ ] 13. (延后) Gemini 痛点 4：第三方模型分类归一（`ProviderCard` 统一 `groupOfficialRouteInfos`）。
  - _Requirements: 模块完整性记录，非本切片承诺_

## 债务登记（远端化时偿还，本切片不准加重）

- credentials 明文密钥（仅 `chmod 0600`）→ 远期 KMS/加密。
- LLM 模块无 `user_id`、roles/credentials 全局单文件 → 远期多用户 + DB。
- 测试状态 SSOT 为本地单文件 → 远期远端存储。

> 详见 `docs/deferred-items.md`。
