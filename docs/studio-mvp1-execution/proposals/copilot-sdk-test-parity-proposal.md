# 方案：COPILOT_ASSIST-4 —— Copilot 测试走真实 `ClaudeSDKClient` smoke

> 状态：草案待评审（已过一轮内部 8-agent 测绘 + 对抗性复核，现送 Gemini 技术评审）
> 分支：`feat/studio-mvp1-mainbased-2026-06-13`
> 日期：2026-06-14

## 1. 背景与目标

设计单元 `copilot-sdk-test-parity`（COPILOT_ASSIST-4）要求：Studio Settings 里"测试 copilot"必须走 copilot **运行时真正用的** `ClaudeSDKClient`（它会 spawn `claude` CLI 子进程、按 per-session `ANTHROPIC_BASE_URL` env 注入 base_url），让"测试通过 ⟺ 运行可用"成立。

**当前现状（已核实）**：copilot role 的测试和所有其他 role 走**同一条 httpx 连通性探活**——`_role_test_provider_result`(每条路线算测试结果的函数) → `_probe_role_route`(挑探活方式的函数) → `copilot_test._probe_model`(用 httpx 打 messages API 的探活)。这条路**从不 spawn CLI、不注入 env**,所以"测试通过"不证明 spawn / env 注入 / tool-loop 真能用。

**关键纠正**：设计文档（ux-spec）提到要替换一个用 `anthropic.AsyncAnthropic` 的假测试 `_probe_copilot_sdk_tool_call`(llm.py:2150)——**这个符号在本分支后端全局 0 命中,不存在**。所以这是 greenfield(首次新增 SDK smoke),不是替换死代码。"INSTEAD OF vs IN ADDITION TO" 因此退化成一个分层取舍:copilot 路线上,SDK smoke 是**取代** httpx 探活,还是**叠在它上面**。

## 2. 已核实的关键契约事实（决策依据）

1. **前端按 `route_id` 索引每条路线的状态**：`copilotRouteStatusesFromJob`(copilot-role-test.ts:48,把后端 job 的每路线状态映射成 UI 灯的函数)只读 `job.provider_statuses[].route_id` 和 `.status`,做成 route_id→灯 的 map;整体判定的 toast 只读 `result.status`。→ **任何往 `provider_statuses[]` 里塞合成行(非真 route_id)都会撞键/被覆盖;但往 `result` 顶层加一个不被读的新字段是安全的(只读路径无害)**。
2. **`RoleTestResponse` 不是 Pydantic 类**:role-test 的"结果"是一个 untyped `dict[str, Any]`,形状 `{role_name, status, warnings, model_groups}`,塞进 `RoleTestJobResponse.result`(L203 的 Pydantic 模型,`extra="forbid"`)。
3. **`role_kind` 字段存在但 role-test 路径从不读它**:`RoleEntry.role_kind: Literal["graph_agent","copilot"]`(llm_config.py:221)。role-test 端点对所有 role 一视同仁,**只有 copilot.py 用硬编码角色名 `"copilot_chat"` 识别 copilot**。
4. **SDK 注入测试缝是 `_session_factory`**:`copilot.py:89` `_session_factory: Callable[[ClaudeAgentOptions], ClaudeSDKClient]`,现有测试(`test_copilot_event_translator.py`)就靠 monkeypatch 它换成 `FakeClient`。但——`build_options`(copilot.py:125)的 `workspace_dir` 是**必填非 Optional**;`cleanup_all_sessions`(copilot.py:426)是**全局**关所有会话;`_translate_sdk_message`(copilot.py:461)是**两参**(message, tool_names)。

## 3. 候选方案速览（4 选 1）

| 方案 | smoke 结果放哪 | 前端改动 | 契约风险 | 取舍 |
|---|---|---|---|---|
| **A** 独立 copilot-smoke 端点 + 独立前端调用 | 自己的响应,不碰 `RoleTestJobResponse` | 新 mapper、新 poll 循环、新错误路径 | 对现有 0 风险 | **第二套测试系统**:重复 job/poll/灯 全套,违背"和 LLM Roles 一样"。SDK smoke 慢→还得重造 background-job 机制 |
| **B** 留 httpx 探活,另加 `result.sdk_smoke` / `job.sdk_statuses` 新字段 | `provider_statuses` 之外的新字段 | 新增第二个 route_id→灯 mapper | 加性、低 | 每条路线**两次网络往返**(httpx + SDK)、两个状态命名空间、两个灯要调和 |
| **C** copilot 路线直接把 SDK smoke 结果写进现有 `provider_statuses[].status` | 现有行内 | **零** | 形状 0、**语义风险最高** | 静默改变 `provider_statuses[].status` 对 copilot 的含义(连通性→SDK);丢失"可达但 spawn 失败"的诊断粒度;无证据回写位 |
| **D**(推荐) `role_kind`-gated:copilot 路线的 SDK smoke 写进现有 `provider_statuses[].status`,**外加**一个加性的 `result.sdk_evidence` 摘要 | 现有行(灯)+ `result.sdk_evidence`(摘要) | 近零(灯复用现有 mapper;可选读 evidence 做 "N/M SDK Ready") | 形状 0、语义风险**受控且 intentional** | C 的零前端 + B 的证据回写,两全 |

**为何 D**:A 是为一个"应该和 LLM Roles 一样"的按钮造第二套系统;B 保留两套探活、两个灯;C 静默重载语义且无证据位。D 复用现有 job/poll/route_id-灯 机器(一套系统一个按钮一个 mapper),让用户看到的灯**就是** SDK smoke 结果,同时用加性 `result.sdk_evidence` 给"证据回写 credentials/draft"和"N/M SDK Ready"一个干净的家。

## 4. 推荐方案:D-corrected（对抗性复核后的修正版）

对抗复核确认 D 的架构选择正确,但指出**原始 D 的代码草图按字面写不能跑**(门在没有 `role_kind` 的函数里、全局 teardown、workspace=None、translate 少传参)。下面是修正后的、可实现的 D:

### 4.1 判别符 plumbing(修 OBJ-1 CRITICAL)
`_role_test_provider_result`(L1804)签名里**没有 `RoleEntry`、没有 `role_kind`**——`RoleEntry` 只在 job 边界(L936/948)加载,`_role_test_targets`(L978)有它但 `RoleTestTarget`(L153)只存 `report_entry/route/endpoint/entry`,丢了 `role_kind`。
→ **修法**:给 `RoleTestTarget` 加 `role_kind` 字段,在 `_role_test_targets` 从 `role.role_kind` 填充;在 `run_target`(L1019,调度处)按 `target.role_kind == "copilot"` 分流(而非改 `_role_test_provider_result` 签名,保持其稳定)。非 copilot 路径**逐字节不变**(回归测试守护)。

### 4.2 自包含 smoke driver(修 OBJ-2/3/4,放 `services/copilot.py`,SDK 语义留在 ③a)
不要直接调 `stream_query`(它多路线 fallback 把异常聚合成 "all configured Copilot providers failed: …",copilot.py:286–313,会**掩盖**单路线确定性错误串),写一个**单路线** driver:

```python
async def run_route_sdk_smoke(route, credential_provider, *, timeout_s: float) -> RouteSdkSmokeResult:
    logger.info("phase=sdk_smoke action=start route=%s", route.route_id)
    try:
        api_key, base_url, env = _resolve_route_runtime(route, credential_provider)
    except ValueError as exc:                       # 配置缺失,不建 client
        return RouteSdkSmokeResult(route.route_id, "failed", str(exc))
    if not api_key:
        return RouteSdkSmokeResult(route.route_id, "failed", f"Endpoint {route.endpoint_id} 未配置 API key")
    with tempfile.TemporaryDirectory() as tmp:      # OBJ-4: workspace_dir 必填,给真目录
        opts = build_options(base_url, api_key, workspace_dir=tmp, env_overrides=env)
        client = _session_factory(opts)             # ← 注入缝(测试里换 FakeClient);本地 client,不进全局 _sessions
        tool_names: dict[str, str] = {}             # OBJ-2: _translate_sdk_message 两参
        try:
            async with asyncio.timeout(timeout_s):  # OBJ-6: 挂死的 spawn 不拖垮整个 job
                await _ensure_client_connected(client)
                await client.query(SMOKE_PROMPT)
                async for msg in client.receive_response():
                    for ev in _translate_sdk_message(msg, tool_names):
                        if isinstance(ev, CopilotEventError):
                            return RouteSdkSmokeResult(route.route_id, "failed", ev.message)
                        if isinstance(ev, CopilotEventToolUseResult) and ev.success:
                            saw_tool = True          # 见 4.4 tool-loop 决策
                        if isinstance(ev, CopilotEventDone):
                            return _verdict(saw_tool, route.route_id)
            return _verdict(saw_tool, route.route_id)
        except Exception as exc:                     # 已映射,非吞掉
            ev = _error_event_for_exception(exc)
            logger.warning("phase=sdk_smoke route=%s failed type=%s: %s",
                           route.route_id, type(exc).__name__, ev.message)  # OBJ-10: 记原始异常类型
            return RouteSdkSmokeResult(route.route_id, "failed", ev.message)
        finally:
            await _close_session(client)             # OBJ-3: 只关本地 client,绝不 cleanup_all_sessions()
            logger.info("phase=sdk_smoke action=end route=%s", route.route_id)
```
复用:`_resolve_route_runtime`、`build_options`、`_session_factory`、`_ensure_client_connected`、`_translate_sdk_message`、`_error_event_for_exception`、`_close_session`、`CopilotEventDone/Error/ToolUseResult`。

### 4.3 受控并发(修 OBJ-6 HIGH)
`_run_role_test_targets` 用 `asyncio.gather`(L1039)**无并发上限**。httpx 时是 N 个廉价请求;换 smoke 就是**每次点测试 N 个并发 `claude` CLI 子进程 spawn**。→ smoke 这条腿包 `asyncio.Semaphore(1..2)` + per-smoke `asyncio.timeout`。**这是推荐的一部分,不是开放问题**。

### 4.4 证据 + 判定(修 OBJ-8 MEDIUM)
`result["sdk_evidence"] = {"tested": bool, "passed": int, "total": int, "routes": {route_id: {"status","message"}}}`(加性,前端只读路径安全)。
判定取舍:现有 `_merge_role_test_status`(blocked>failed>warning>ok)会让**一条** SDK-failed 路线把整 role 判 `failed`。但 copilot 运行时只需**一条** fallback 路线能用。→ **推荐:copilot 的 `result.status` 改成"任一 admit 路线 smoke ok 即 pass",从 `sdk_evidence` 算**,而非继承 merge。

### 4.5 验证诚实声明(修 OBJ-5/9 HIGH/MEDIUM)
- mocked 单测(monkeypatch `_session_factory`→`FakeClient`)只验**接线/翻译/错误映射/分流**,**不证 spawn/env**——因为它把子进程换成了内存假对象。**单测全绿 ≠ 真路径可用**,必须诚实写明。
- 外加一个 creds-gated `@pytest.mark.live`(无凭证 CI skip)集成测试,驱动**真 `ClaudeSDKClient`** 打真 endpoint,断言 `CopilotEventDone`。这才真正 discharge COPILOT_ASSIST-4 的保证。
- 落地前先 grep 前端 `RoleTestResponse` 的**解析路径**(不只读路径):若是裸 `as` cast→加性字段安全;若是 `.strict()` schema→需把 `sdk_evidence` 加进 schema。

## 5. 需要你/Gemini 拍板的开放决策

1. **replace vs layer httpx(真正的 crux)**:D 在 copilot admit 路线上**取代** httpx 探活(只留 admission 预闸)。若每点一次测试 spawn N 个 CLI 子进程的代价不可接受,fallback 是 **B 的预闸**:留廉价 httpx 当快速预过滤,只对连通的路线 spawn smoke。我倾向 D-取代;B-预闸 作为成文的逃生口。
2. **判定聚合**:copilot 的整体 verdict = "所有路线都 ok"(继承 merge,更严)还是 "任一 admit 路线 ok"(从 evidence 算,贴合 fallback 语义)?我倾向**任一 ok**。
3. **tool-loop 深度**:ux-spec §3.4 说"发真工具调用"证明 tool loop。纯 `"Reply with one short word."`(text-only Done)只证 spawn+env,不证 `ToolUseBlock→ToolResultBlock` 翻译 + `_ALLOWED_TOOL_SET` gating + tool-result loop——而这正是 httpx 够不到、copilot 运行时依赖的行为。我倾向 smoke **故意触发一个只读工具**(往 tempdir 写个小文件、让模型 `Read` 它),pass 判据 = `CopilotEventToolUseResult(success) → Done`。若降级成 text-only 当 V1,必须**显式记为 scope cut**,不能静默弱化。
4. **并发上限与 timeout**:Semaphore(1 vs 2)、每 smoke timeout 多少秒?(子进程 spawn 成本)
5. **判别符**:用 `role_kind == "copilot"`(typed,但现在全后端没人读)还是 `role_name == "copilot_chat"`(copilot.py 现用的硬编码名)?需确认每个 materialized copilot role 都可靠带 `role_kind="copilot"`,否则 gate 会漏判落回 httpx。我倾向 `role_kind`。

## 6. 改动符号表(D-corrected)

| 层 | 符号 | 改动 |
|---|---|---|
| `services/copilot.py` | `run_route_sdk_smoke(route, credential_provider, *, timeout_s)` | **新** 单路线 driver(见 4.2) |
| `services/copilot.py` | `RouteSdkSmokeResult` dataclass | **新** `{route_id, status: Literal["ok","failed","blocked"], message}` |
| `routers/llm.py` | `RoleTestTarget`(L153) | **改** 加 `role_kind` 字段 |
| `routers/llm.py` | `_role_test_targets`(L978) | **改** 填 `role_kind=role.role_kind` |
| `routers/llm.py` | `run_target`(L1019) | **改** copilot+admit→`copilot.run_route_sdk_smoke`,否则现有 httpx;Semaphore+timeout |
| `routers/llm.py` | `_run_role_test_targets`(L1002) | **改** copilot 时组装 `result["sdk_evidence"]` + 按 4.4 算 verdict |
| `api/llm.ts` | `RoleTestResponse` | **改** 加可选 `sdk_evidence?`(type-only) |
| `copilot-role-test.ts` `copilotRouteStatusesFromJob` | — | **不变**(灯已 SDK-driven) |

## 7. 给评审者的问题（请重点回答）
- D-corrected 的架构与 OBJ-1~10 的修法是否正确、有无遗漏的风险?
- 开放决策 1（replace vs layer）、2（verdict any-vs-all）、3（tool-loop 深度）你的判断?
- 有没有比 D 更简单、同样满足"测试通过 ⟺ 运行可用 + 不破前端契约"的设计被我们漏了?

## 8. 评审记录（Gemini + 自核,2026-06-14）

全文见 `./copilot-sdk-test-parity-gemini-review.md`。

**Gemini 确认 / 共识**：
- D-corrected 架构方向正确（自包含 driver + 受控并发避开全局污染和子进程炸弹,正确复用现有按路线更新 UI 机制）。
- 决策 1 **取代 httpx**(Gemini 同 D)：既然要验真实运行路径,httpx 就是多余噪音;只要 driver 内先做配置前置校验,直接 spawn 最诚实。
- 决策 2 **任一 admit 路线 ok = 整体 pass**(Gemini 同)：copilot 核心是 fallback,主商宕机后备可用时运行时就是可用的,要求全通不符业务现实。
- 判别符用 `role_kind == "copilot"`(Gemini 同),需确保 `config/llm_roles.yaml` 所有 copilot 角色都打了 `role_kind: copilot`。
- 新增提醒:CLI 子进程在 timeout/异常时必须确保被 SIGTERM 杀掉,否则僵尸进程锁住 tempdir 致清理失败。

**Gemini 的 CRITICAL（经自核为误报,但其直觉指向真问题）**：
- Gemini 担心 `result["sdk_evidence"]` 撞 `extra="forbid"` 返 500。**自核(llm.py:204/211):`RoleTestJobResponse.result` 是 `dict[str, Any] | None`,`extra="forbid"` 只管该模型顶层字段,不管 `result` 字典内部——加 key 后端安全,无 500。** 没有 `RoleTestResponse` 严格模型(Gemini 误设其存在)。其直觉的真落点 = 前端解析路径(本方案 OBJ-9 已记):落地前要 grep 前端是否对 `RoleTestResponse` 用 `.strict()` schema 解析,是则需把字段加进 schema。

**Gemini 与对抗复核的真分歧 —— 决策 3 tool-loop 深度**：
- 对抗复核(OBJ-7):smoke 必须**发真工具调用**(写文件让模型 `Read`),否则没证 `ToolUseBlock→ToolResultBlock` 翻译 + tool-loop,是 ux-spec"发真工具调用"的 near-miss。
- Gemini:**V1 用 text-only Done**。真工具调用把确定性连通测试变成"依赖 LLM 是否决定调工具"的**概率性测试→flaky**;text-only 已完整走通 `spawn→注入 env→建 IPC/stream→收解析事件` 核心管道;tool 解析逻辑用 mock 单测覆盖即可;smoke 环节稳定 > 功能穷尽。
- **我的综合倾向**:Gemini 的 flaky 论对 smoke 很关键(不稳定的 smoke 比没有还糟)。倾向 **V1 text-only + tool 逻辑走 mock 单测 + creds-gated live 测证管道**,并把"不在 smoke 里强制工具调用"显式记为 V1 scope cut。但这是产品/质量取舍,PM 拍板。

**Gemini 的简化变体 D-Minimal（值得 PM 评估）**：
- 把证据格式化成结构化文本塞进现有 `provider_statuses[].message`,前端原样展示;verdict 在 `_run_role_test_targets` 合并时对 copilot 重写"any ok"。→ **前后端通信契约字节级零修改**,改动收敛在 `routers/llm.py` + `services/copilot.py`。Gemini 建议 MVP1 先上 D-Minimal。
- **取舍**:`sdk_evidence`(D,机器可读)直接支撑设计要的"证据回写 credentials/draft" + "N/M SDK Ready" 头;塞 message(D-Minimal)是文本 blob,回写/计数要再解析。**faithfulness(机器可读证据) vs 最小爆炸半径**——PM 取舍。

**当前可定/待定**：
- ✅ 共识可直接落地:D 架构 + 10 个 OBJ 修法、取代 httpx、any-ok verdict、role_kind 判别符。
- ⏳ 待 PM 定:① tool-loop 深度(text-only vs 真工具调用)② D vs D-Minimal(机器可读证据 vs 零契约改动)。
- 🔍 落地前自核:前端 `RoleTestResponse` 解析路径是否严格 schema(OBJ-9)。
