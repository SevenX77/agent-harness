---
module: 04_platform/gateway
doc: mvp1-alignment
status: FROZEN（Gateway ③b 包已有 schema/resolver/fallback 代码；Studio 侧仍有 5 态投影、materializer、health/draft 等内核散在后端 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [settings-six-state-provider-health, model-group-role-materialization, copilot-sdk-test-parity]
aligns_with: docs/graph-agent-gateway/mvp1/（gateway ③b SSOT）· 01_workflows/00_settings-ux-spec.md（四层边界）
---

# gateway — MVP1 Alignment

> **Tier**: platform | **Owns**: Studio gateway platform = ③a 消费/适配边界；③b 公共内核 owner 在 `docs/graph-agent-gateway/mvp1/` | **现状**: Gateway ③b 包已有 schema/resolver/fallback 代码；Studio 侧仍有 5 态投影、materializer、health/draft 等内核散在后端 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `studio-settings` · `settings` · `llm-copilot-http-api` · `copilot-assist` · `docs/graph-agent-gateway/mvp1/`

## 1. 定义
`gateway` is the model/provider/role routing platform block. It owns provider and route descriptors, capability matching, role resolution, fallback chains, runtime health/circuit state, and graph-agent model adapter behavior. HTTP glue is documented separately in `llm-copilot-http-api/`.

Source workflow basis: `01_workflows/00_settings-ux-spec.md:340`, `01_workflows/00_settings-ux-spec.md:361`, `01_workflows/00_settings-ux-spec.md:395`, `01_workflows/00_settings-ux-spec.md:433`.

## 2. 数据流 / 机制（设计细节）
本模块只记录 Studio 如何消费 gateway ③b 公共内核；公共内核机制不在 Studio 文档复述。SSOT 在 [`docs/graph-agent-gateway/mvp1/`](../../../../graph-agent-gateway/mvp1/)：provider/route/schema 见 [`04-orch-registry-schema`](../../../../graph-agent-gateway/mvp1/04-orch-registry-schema/mvp1-alignment.md)，role materialize / route resolution 见 [`02-orch-role-resolution`](../../../../graph-agent-gateway/mvp1/02-orch-role-resolution/mvp1-alignment.md)，endpoint 标准化见 [`03-orch-credentials-endpoints`](../../../../graph-agent-gateway/mvp1/03-orch-credentials-endpoints/mvp1-alignment.md)，capability/model group 见 [`05-orch-capabilities-and-models`](../../../../graph-agent-gateway/mvp1/05-orch-capabilities-and-models/mvp1-alignment.md)，fallback / circuit / probe 见 [`07-orch-fallback-circuit-probe`](../../../../graph-agent-gateway/mvp1/07-orch-fallback-circuit-probe/mvp1-alignment.md)，六态测试状态 SSOT 见 [`08-orch-test-status-ssot`](../../../../graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md)。

1. **Studio 写入/读取**：Settings 与 Copilot/Graph Agent roles 只通过 ③a HTTP 壳提交 endpoint、route、role、profile 意图；gateway ③b 返回标准 registry / resolved route / projection 结果，Studio 不自行重新定义 provider registry、六态、fallback 或 route resolution。
2. **Studio 渲染/消费**：前端只消费 ③a DTO 中的 gateway 投影结果（provider state、model group、fallback chain、role test/probe 结果），并把颜色、文案、拖拽排序、保存状态等应用加工留在 Studio。
3. **现状 drift**：baseline 仍记录 Studio 后端里散落的 5 态 projection、materializer、health/draft 等内核实现痕迹；目标是这些公共内核以 gateway SSOT 为准，Studio 只保留消费、适配和渲染边界。

## 3. 接口契约
- Settings/API Keys produce provider endpoints, credentials, and model inventory.
- LLM Roles/Copilot produce abstract role mappings and fallback chains.
- Engine asks gateway/model resolver for executable chat model runtimes.
- Gateway tracks runtime health/circuits and projects statuses back to Settings.
- Companion platform doc: `llm-copilot-http-api/` owns `/api/llm` and `/api/copilot` HTTP/WS DTOs.

## 4. 设计决策基础（PM 原话）
- `failed(reason)` vs `historical_ready` 文案 = 六态标签(见 `studio-settings`/`settings` 已决):`historical_ready`=曾连通(直接显示)、`failed`=失败(带 reason: missing_config/endpoint_unreachable/model_failed)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| GATEWAY-1 | 六态归属 | 单元 `settings-six-state-provider-health`；**为什么**：6 态标准投影是 ③b gateway 公共内核，Studio 只渲染消费 |
| GATEWAY-2 | materialize | 单元 `model-group-role-materialization`；**为什么**：materialize/model group/endpoint 标准化归 ③b 内核 |
| GATEWAY-3 | copilot route | 单元 `copilot-sdk-test-parity`；**为什么**：gateway 只把 `copilot_chat` 当 role 解析 route，不感知 SDK session |

## 6. 测试关键点
1. 六态归属: baseline 现状为 `llm_state_projection.py` 仍旧 5 态且应下沉 ③b ⚠️；目标为 6 态标准投影由 gateway ③b 内核提供，Studio 只渲染/消费。
2. materialize: baseline 现状为 Studio materializer/llm.py 仍混 HTTP glue + 内核 ⚠️；目标为 materialize/endpoint 标准化/role resolve 归 ③b，Studio 只传意图/包装 HTTP。
3. copilot route: baseline 现状为 Copilot SDK 调用归 ③a，route 解析归 ③b；目标为 gateway 只把 `copilot_chat` 当 role 解析，不感知 SDK session。

## 7. 涉及 region / platform
`studio-settings` · `settings` · `llm-copilot-http-api` · `copilot-assist` · `docs/graph-agent-gateway/mvp1/`

## 8. gaps / 报警
- 🚨 六态归属: `llm_state_projection.py` 仍旧 5 态且应下沉 ③b ⚠️；目标 6 态标准投影由 gateway ③b 内核提供，Studio 只渲染/消费。
- 🚨 materialize: Studio materializer/llm.py 仍混 HTTP glue + 内核 ⚠️；目标 materialize/endpoint 标准化/role resolve 归 ③b，Studio 只传意图/包装 HTTP。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `studio-settings` · `settings` · `llm-copilot-http-api` · `copilot-assist` · `docs/graph-agent-gateway/mvp1/`
