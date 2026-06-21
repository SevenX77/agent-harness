import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const htmlPath = resolve(here, "studio-mvp1-12d-repair-framework-2026-06-15.html");
const html = readFileSync(htmlPath, "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function section(id) {
  const start = html.indexOf(`id:'${id}'`);
  assert(start !== -1, `missing section ${id}`);
  const next = html.indexOf("\n  {\n    id:'", start + 1);
  return html.slice(start, next === -1 ? html.length : next);
}

function allStatusRows() {
  const rows = [];
  const parentPattern = /id:'(d\d+)'[^]*?code:'(D\d+)'[^]*?title:'([^']+)'[^]*?status:'([^']+)'/g;
  let parentMatch;
  while ((parentMatch = parentPattern.exec(html))) {
    rows.push({
      kind: "parent",
      code: parentMatch[2],
      title: parentMatch[3],
      status: parentMatch[4],
    });
  }

  const childPattern = /child\('[^']+'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'/g;
  let childMatch;
  while ((childMatch = childPattern.exec(html))) {
    rows.push({
      kind: "child",
      code: childMatch[1],
      title: childMatch[2],
      status: childMatch[3],
    });
  }
  return rows;
}

const d6 = section("d6");
const s0 = section("s0");
for (const required of [
  "反证测试不靠枚举",
  "deny-by-default",
  "trap/canary",
  "自动发现 surface",
  "allowlist 必须有责任边界",
  "审计必须可复现",
  "能红才修",
]) {
  assert(s0.includes(required), `S0 methodology missing required phrase: ${required}`);
}
assert(!s0.includes("这是从 D12 精修里沉淀"), "S0 must not describe the methodology as D12-derived");

for (const stale of [
  "unconfigured",
  "invalid_config",
  "credential_blocked",
  "route_ready",
  "provider_degraded",
]) {
  assert(!d6.includes(stale), `D6 still uses stale projection word: ${stale}`);
}
for (const canonical of [
  "ready",
  "historical_ready",
  "untested",
  "failed",
  "cooling_down",
  "off",
]) {
  assert(d6.includes(canonical), `D6 missing canonical projection word: ${canonical}`);
}
assert(!d6.includes("ProviderUiState` 仍包含 needs_setup"), "D6 still claims ProviderUiState contains needs_setup");
assert(
  d6.includes("routeStatusOverrides")
    && d6.includes("endpoint.status/last_test_*")
    && d6.includes("普通 upsert 不接受/不采信测试状态字段"),
  "D6.4 must record closed routeStatusOverrides and endpoint status writeback gates",
);

const d12 = section("d12");
assert(
  d12.includes("RunArtifactStore")
    && d12.includes("run_metadata")
    && d12.includes("MetadataStore")
    && d12.includes("runtime artifacts"),
  "D12.5 must record the closed run artifact boundary and metadata distinction",
);

const d3 = section("d3");
assert(!d3.includes("主按钮 Run/Predict 未接 API"), "D3 still says Run/Predict buttons are not wired");
assert(d3.includes("postPredictRun") && d3.includes("startRun") && d3.includes("resumeRun"), "D3 must record current button wiring");

for (const stale of [
  "TracePanel 未挂主 Workspace",
  "Run 按钮仍是 console.info",
  "getMockEdgeContext 生成假边数据",
  "没有 patch_proposed",
  "Rust write_workspace_file 函数实现 stale hash 拒写，但未注册 command",
]) {
  assert(!html.includes(stale), `HTML still contains stale current claim: ${stale}`);
}

const rows = allStatusRows();
function statusOf(code) {
  const row = rows.find((item) => item.code === code);
  assert(row, `missing status row for ${code}`);
  return row.status;
}

const expectedStatuses = new Map([
  ["D1", "ok"],
  ["D4", "ok"],
  ["D4.3", "ok"],
  ["D4.4", "ok"],
  ["D5", "ok"],
  ["D5.2", "ok"],
  ["D5.3", "ok"],
  ["D6", "ok"],
  ["D6.2", "ok"],
  ["D6.3", "ok"],
  ["D6.4", "ok"],
  ["D8", "ok"],
  ["D8.3", "ok"],
  ["D8.4", "ok"],
  ["D9", "ok"],
  ["D9.4", "ok"],
  ["D12", "ok"],
  ["D12.1", "ok"],
]);

for (const [code, expected] of expectedStatuses) {
  assert(statusOf(code) === expected, `${code} must be ${expected} after current Wave evidence`);
}

for (const evidence of [
  "post-Wave 审计",
  "Wave 1 re-repair",
  "FailIfInvokedProvider",
  "credential_ref",
  "endpoint.status/last_test_*",
  "no blocking findings",
  "api/llm.ts",
  "零改动",
  "PM 拍板",
  "cd apps/studio/backend && uv run pytest tests/services/test_productization_run_artifact_flow_red.py -q",
  "57 passed",
  "cd packages/graph-agent && uv run pytest tests/core/test_productization_run_by_artifact_red.py tests/core/test_productization_gateway_dependency_red.py tests/core/test_productization_llm_event_contracts.py tests/models/test_predict_gateway_chat_model.py -q",
  "34 passed",
  "cd packages/graph-agent-gateway && uv run pytest -q",
  "223 passed, 1 xfailed",
  "Fresh D2 gate",
  "backend local providers/run_artifact/resume/publish => 166 passed",
  "graph-agent storage/run_by_artifact => 28 passed",
  "gateway resolver storage => 3 passed",
  "test_run_history_lists_details_and_deletes_runs",
  "sealed RunArtifactStore input_data",
  "uv run pytest tests/core/adapters/ tests/routers/test_llm_registry_api.py tests/routers/test_copilot_ws_endpoint.py tests/routers/test_copilot_sdk_test_job.py tests/routers/test_llm_role_test_results_api.py -q",
  "257 passed",
  "uv run pytest tests/core/adapters/test_productization_import_boundary_red.py tests/core/adapters/test_productization_loopback_endpoints_red.py tests/services/test_productization_engine_transport_switch_red.py tests/core/adapters/test_productization_http_transport_errors_red.py tests/core/adapters/test_productization_native_fs_source_writer_guard_red.py tests/core/adapters/test_productization_gateway_adapter_flow_red.py -q",
  "46 passed",
  "不再定义 execution_fingerprint 算法",
  "test_studio_backend_does_not_define_execution_fingerprint_algorithm",
  "graph_agent.core.topology_projection",
  "serialize_graph_topology_from_markdown",
  "test_studio_backend_does_not_own_graph_parser_or_subgraph_topology_resolver",
  "D8 focused gate",
  "test_engine_compile_does_not_zip_live_skill_dir_for_product_artifact",
  "test_compile_artifact_does_not_write_manifest_side_effects_into_source_root",
  "test_compile_artifact_archive_does_not_use_deflate_compression_for_identity_bytes",
  "ZIP_STORED",
  "deterministic `artifact_bytes`",
  "dead `_zip_directory` helper 已删除",
  "Backend D9 gate",
  "Python source write",
  "X-Studio-Write-Fallback",
  "test_skill_file_native_fs_guard_red.py",
  "test_source_writer_guard_uses_allowlist_fallback_contract",
  "NATIVE_FS_SOURCE_WRITE_ROUTE_ALLOWLIST",
  "NATIVE_FS_REQUIRED",
]) {
  assert(html.includes(evidence), `missing re-repair evidence phrase: ${evidence}`);
}

console.log("repair-framework Wave evidence HTML checks passed");
