"""Copilot 结构化工具(in-process MCP server):零审批的后端能力面。"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC
from pathlib import Path

from app.models.llm_config import ProviderEndpoint, ProviderRoute, RegistryResponse
from app.services import copilot, copilot_tools
from claude_agent_sdk import PermissionResultAllow


def test_mcp_server_exposes_tools() -> None:
    servers = copilot_tools.build_copilot_mcp_servers()
    assert set(servers) == {"studio"}
    # 读/探测三件的免审批基线仍在(完整全集见 test_copilot_config_tools.py)。
    tool_names = {
        t.name
        for t in (
            copilot_tools.get_llm_roles_tool,
            copilot_tools.compile_skill_tool,
            copilot_tools.run_role_test_tool,
        )
    }
    assert tool_names == {"get_llm_roles", "compile_skill", "run_role_test"}


def test_get_llm_roles_tool_returns_compact_snapshot(
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    result = asyncio.run(copilot_tools.get_llm_roles_tool.handler({}))

    assert "is_error" not in result
    payload = json.loads(result["content"][0]["text"])
    assert "roles" in payload
    assert payload["role_count"] == len(payload["roles"])
    for entry in payload["roles"].values():
        assert set(entry) == {"role_kind", "model_fallback_enabled", "fallback_chain"}


def test_compile_skill_tool_requires_skill_id() -> None:
    result = asyncio.run(copilot_tools.compile_skill_tool.handler({"skill_id": "  "}))

    assert result["is_error"] is True
    assert "skill_id" in result["content"][0]["text"]


def test_compile_skill_tool_reports_failure_as_tool_error() -> None:
    # 不存在的 skill:解析失败必须落成 is_error 工具结果,不许异常炸断事件流。
    result = asyncio.run(
        copilot_tools.compile_skill_tool.handler({"skill_id": "no-such-skill-xyz"})
    )

    assert result["is_error"] is True
    assert result["content"][0]["text"]


def test_run_role_test_tool_requires_role_name() -> None:
    result = asyncio.run(copilot_tools.run_role_test_tool.handler({"role_name": "  "}))

    assert result["is_error"] is True
    assert "role_name" in result["content"][0]["text"]


def test_run_role_test_tool_rejects_unknown_role(monkeypatch) -> None:  # noqa: ANN001
    # 范围自校验:只允许测现有角色,未知角色落成 is_error(不越界)。
    from app.routers import llm

    class _Data:
        roles: dict[str, object] = {}

    monkeypatch.setattr(llm, "_load_roles_or_empty", lambda: _Data())

    result = asyncio.run(copilot_tools.run_role_test_tool.handler({"role_name": "ghost"}))

    assert result["is_error"] is True
    assert "ghost" in result["content"][0]["text"]


def test_run_role_test_tool_compacts_result(monkeypatch) -> None:  # noqa: ANN001
    # 走既有服务路径(test_llm_role 同款: 载入→物化→_run_role_test_targets),
    # 把冗长明细压成 status+message 的紧凑快照回给模型。
    from app.routers import llm

    sentinel_role = object()

    class _Data:
        roles = {"copilot_chat": sentinel_role}

    async def _fake_run(role_name: str, targets: object) -> dict[str, object]:
        return {
            "role_name": role_name,
            "status": "ok",
            "warnings": [{"code": "w1"}],
            "model_groups": [
                {
                    "canonical_id": "openai:gpt-x",
                    "display_name": "GPT-X",
                    "provider_results": [
                        {
                            "status": "ok",
                            "message": None,
                            "warnings": [{"code": "noise"}],
                            "evidence": {"big": "blob"},
                        }
                    ],
                }
            ],
        }

    from app.services import llm_credentials

    monkeypatch.setattr(llm, "_load_roles_or_empty", lambda: _Data())
    monkeypatch.setattr(llm_credentials, "load_credentials", lambda: object())
    monkeypatch.setattr(llm, "_materialize_role_for_response", lambda role, creds: role)
    monkeypatch.setattr(llm, "_role_test_targets", lambda role, creds: [])
    monkeypatch.setattr(llm, "_run_role_test_targets", _fake_run)

    result = asyncio.run(
        copilot_tools.run_role_test_tool.handler({"role_name": "copilot_chat"})
    )

    assert "is_error" not in result
    payload = json.loads(result["content"][0]["text"])
    assert payload["role_name"] == "copilot_chat"
    assert payload["status"] == "ok"
    assert payload["warning_count"] == 1
    group = payload["model_groups"][0]
    assert group["canonical_id"] == "openai:gpt-x"
    assert group["display_name"] == "GPT-X"
    # 冗长明细(evidence / 逐条 warnings)被压掉,每个路由只留 status+message。
    assert set(group["routes"][0]) == {"status", "message"}
    assert group["routes"][0]["status"] == "ok"


# ── search_llm_registry(搜索驱动、结果有界的词汇发现) ─────────────────────────


def _endpoint(
    endpoint_id: str,
    *,
    provider_kind: str = "third_party",
    api_key: str | None = None,
) -> ProviderEndpoint:
    fields: dict[str, object] = {
        "endpoint_id": endpoint_id,
        "display_name": endpoint_id,
        "protocol": "openai_compatible",
        "base_url": f"https://{endpoint_id}.example/v1",
        "provider_kind": provider_kind,
    }
    if api_key is not None:
        fields["api_key"] = api_key
    return ProviderEndpoint.model_validate(fields)


def _route(endpoint_id: str, canonical_id: str, *, status: str = "verified") -> ProviderRoute:
    return ProviderRoute.model_validate(
        {
            "route_id": f"{endpoint_id}:{canonical_id}",
            "endpoint_id": endpoint_id,
            "route_slug": canonical_id,
            "provider_model_id": canonical_id,
            "canonical_id": canonical_id,
            "status": status,
        }
    )


def _registry(
    routes: list[ProviderRoute],
    endpoints: list[ProviderEndpoint],
) -> RegistryResponse:
    routes_by_canonical: dict[str, list[str]] = {}
    for route in routes:
        routes_by_canonical.setdefault(route.canonical_id, []).append(route.route_id)
    return RegistryResponse(
        provider_endpoints={e.endpoint_id: e for e in endpoints},
        provider_routes={r.route_id: r for r in routes},
        canonical_groups=[
            {"canonical_id": cid, "display_name": cid, "routes": rids}
            for cid, rids in sorted(routes_by_canonical.items())
        ],
    )


def _patch_registry(monkeypatch, registry: RegistryResponse) -> None:  # noqa: ANN001
    from app.routers import llm

    async def _fake() -> RegistryResponse:
        return registry

    monkeypatch.setattr(llm, "get_llm_registry", _fake)


def test_search_llm_registry_filters_and_groups(monkeypatch) -> None:  # noqa: ANN001
    endpoints = [
        _endpoint("anthropic", provider_kind="official"),
        _endpoint("openrouter"),
        _endpoint("openai"),
    ]
    routes = [
        _route("anthropic", "claude-opus-4.8"),
        _route("openrouter", "anthropic.claude-opus-4.8"),
        _route("openai", "gpt-4o"),
    ]
    _patch_registry(monkeypatch, _registry(routes, endpoints))

    result = asyncio.run(copilot_tools.search_llm_registry_tool.handler({"query": "opus"}))

    assert "is_error" not in result
    payload = json.loads(result["content"][0]["text"])
    matched = {g["canonical_id"] for g in payload["canonical_groups"]}
    # 只命中含 "opus" 的两个 canonical 组;gpt-4o 被过滤掉。
    assert matched == {"claude-opus-4.8", "anthropic.claude-opus-4.8"}
    official = next(
        g for g in payload["canonical_groups"] if g["canonical_id"] == "claude-opus-4.8"
    )
    # 每条 route 只投影有界的词汇字段;官方直连端点 is_official=True。
    assert official["routes"] == [
        {
            "route_id": "anthropic:claude-opus-4.8",
            "endpoint_id": "anthropic",
            "status": "verified",
            "is_official": True,
        }
    ]
    third_party = next(
        g
        for g in payload["canonical_groups"]
        if g["canonical_id"] == "anthropic.claude-opus-4.8"
    )
    assert third_party["routes"][0]["is_official"] is False


def test_search_llm_registry_result_is_bounded(monkeypatch) -> None:  # noqa: ANN001
    endpoints = [_endpoint("bigprov")]
    routes = [_route("bigprov", f"model-{i:03d}") for i in range(200)]
    _patch_registry(monkeypatch, _registry(routes, endpoints))

    result = asyncio.run(copilot_tools.search_llm_registry_tool.handler({"query": "model"}))

    payload = json.loads(result["content"][0]["text"])
    # 200 条全部匹配,但只返回默认 limit(20)条,total_count 反映匹配总数。
    assert payload["total_count"] == 200
    assert len(payload["canonical_groups"]) == 20
    # 结构上根除 token 撑爆:整串序列化远小于 50KB。
    assert len(result["content"][0]["text"]) < 50_000


def test_search_llm_registry_hard_caps_limit(monkeypatch) -> None:  # noqa: ANN001
    endpoints = [_endpoint("bigprov")]
    routes = [_route("bigprov", f"model-{i:03d}") for i in range(200)]
    _patch_registry(monkeypatch, _registry(routes, endpoints))

    result = asyncio.run(
        copilot_tools.search_llm_registry_tool.handler({"query": "model", "limit": 999})
    )

    payload = json.loads(result["content"][0]["text"])
    assert len(payload["canonical_groups"]) <= 50


def test_search_llm_registry_never_leaks_api_key(monkeypatch) -> None:  # noqa: ANN001
    secret = "sk-supersecret-do-not-leak-abc123"
    endpoints = [_endpoint("anthropic", provider_kind="official", api_key=secret)]
    routes = [_route("anthropic", "claude-opus-4.8")]
    _patch_registry(monkeypatch, _registry(routes, endpoints))

    result = asyncio.run(copilot_tools.search_llm_registry_tool.handler({"query": "opus"}))

    text = result["content"][0]["text"]
    assert secret not in text
    assert "api_key" not in text


def test_get_llm_registry_tool_is_removed() -> None:
    # 旧的全量转储工具被彻底废除(不留别名、不进白名单)。
    assert not hasattr(copilot_tools, "get_llm_registry_tool")
    tool_names = {t.name for t in copilot_tools._copilot_mcp_tools()}
    assert "get_llm_registry" not in tool_names
    assert "search_llm_registry" in tool_names
    assert "mcp__studio__get_llm_registry" not in copilot._DECLARATIVE_ALLOWED_TOOLS
    assert "mcp__studio__search_llm_registry" in copilot._DECLARATIVE_ALLOWED_TOOLS


def test_build_options_attaches_studio_mcp_for_chat_only(tmp_path: Path) -> None:
    async def cb(name, tool_input, ctx):  # noqa: ANN001
        return PermissionResultAllow()

    chat_options = copilot.build_options(None, "key", tmp_path, can_use_tool=cb)
    probe_options = copilot.build_options(None, "key", tmp_path)

    assert set(chat_options.mcp_servers) == {"studio"}
    assert probe_options.mcp_servers == {}


# ── create_skill(skill 实体写工具,经审批;审批面契约见 test_copilot_guardrails)──


def test_create_skill_tool_requires_skill_id() -> None:
    result = asyncio.run(copilot_tools.create_skill_tool.handler({"skill_id": "  "}))

    assert result["is_error"] is True
    assert "skill_id" in result["content"][0]["text"]


def test_create_skill_tool_rejects_invalid_skill_id(
    studio_roots: tuple[Path, Path],
) -> None:
    # 与 POST /api/skills 相同的边界校验(CreateSkillReq pattern),拼写错误在
    # 工具边界一次拒绝,不落半成品目录。
    del studio_roots
    result = asyncio.run(
        copilot_tools.create_skill_tool.handler({"skill_id": "Bad_Name!"})
    )

    assert result["is_error"] is True


def test_create_skill_tool_creates_scaffold_and_registers_index(
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _ = studio_roots

    result = asyncio.run(
        copilot_tools.create_skill_tool.handler({"skill_id": "my-new-skill"})
    )

    assert "is_error" not in result
    payload = json.loads(result["content"][0]["text"])
    assert payload["skill_id"] == "my-new-skill"
    assert payload["directory_path"] == str(skills_dir / "my-new-skill")
    # 索引落库 = UI 可见性的根据;files 缺省时走服务端脚手架,不留裸目录。
    from app.core.backends import get_metadata

    entry = asyncio.run(get_metadata().get_skill_index_entry("my-new-skill"))
    assert entry is not None
    assert (skills_dir / "my-new-skill" / "GRAPH.md").exists()


def test_create_skill_tool_accepts_seed_files(
    studio_roots: tuple[Path, Path],
) -> None:
    # 种子文件必须是合法 skill(与 POST /api/skills 同一条 manifest 校验);
    # 这里用服务端脚手架当种子,验证 files 参数原样落盘而非被忽略。
    from app.services.skills import _scaffold_files_for

    skills_dir, _ = studio_roots
    seed = _scaffold_files_for("seeded-skill")

    result = asyncio.run(
        copilot_tools.create_skill_tool.handler(
            {"skill_id": "seeded-skill", "files": seed}
        )
    )

    assert "is_error" not in result
    graph = (skills_dir / "seeded-skill" / "GRAPH.md").read_text(encoding="utf-8")
    assert "name: seeded-skill" in graph


def test_create_skill_tool_rejects_invalid_seed_manifest(
    studio_roots: tuple[Path, Path],
) -> None:
    # 非法种子(裸标题、无 phases)在创建即被 manifest 校验拒绝,不留半成品。
    del studio_roots
    result = asyncio.run(
        copilot_tools.create_skill_tool.handler(
            {"skill_id": "broken-seed", "files": {"GRAPH.md": "# broken\n"}}
        )
    )

    assert result["is_error"] is True
    assert "MANIFEST_VALIDATION_FAILED" in result["content"][0]["text"]


def test_create_skill_tool_failed_create_rolls_back_and_id_stays_usable(
    studio_roots: tuple[Path, Path],
) -> None:
    # 失败的创建必须回滚目录,skill_id 不被半成品毒死:同名重试(合法内容)成功。
    skills_dir, _ = studio_roots

    bad = asyncio.run(
        copilot_tools.create_skill_tool.handler(
            {"skill_id": "retry-skill", "files": {"GRAPH.md": "# broken\n"}}
        )
    )
    assert bad["is_error"] is True
    assert not (skills_dir / "retry-skill").exists()

    good = asyncio.run(copilot_tools.create_skill_tool.handler({"skill_id": "retry-skill"}))
    assert "is_error" not in good


def test_create_skill_tool_duplicate_reports_error(
    studio_roots: tuple[Path, Path],
) -> None:
    del studio_roots
    result = asyncio.run(
        copilot_tools.create_skill_tool.handler({"skill_id": "text-segmentation"})
    )

    assert result["is_error"] is True
    assert "text-segmentation" in result["content"][0]["text"]


# ── run_skill / get_run_detail(旅程 04:真跑与看结果)────────────────────────


def test_run_skill_tool_requires_skill_id() -> None:
    result = asyncio.run(copilot_tools.run_skill_tool.handler({"skill_id": "  "}))

    assert result["is_error"] is True
    assert "skill_id" in result["content"][0]["text"]


def test_run_skill_tool_starts_run_and_returns_run_id(monkeypatch) -> None:  # noqa: ANN001
    from datetime import datetime

    from app.models.runs import RunMetadata, RunRequest
    from app.services import run_manager as run_manager_module

    captured: dict[str, object] = {}

    async def _fake_start(skill_id: str, request: RunRequest) -> RunMetadata:
        captured["skill_id"] = skill_id
        captured["request"] = request
        return RunMetadata(
            run_id="run-1", status="running", started_at=datetime.now(UTC)
        )

    monkeypatch.setattr(run_manager_module.run_manager, "start_run", _fake_start)

    result = asyncio.run(
        copilot_tools.run_skill_tool.handler(
            {"skill_id": "text-segmentation", "input_data": {"text": "hi"}}
        )
    )

    assert "is_error" not in result
    payload = json.loads(result["content"][0]["text"])
    assert payload["run_id"] == "run-1"
    assert payload["status"] == "running"
    assert payload["detail_hint"] == ".workspace/runs/run-1/"
    assert captured["skill_id"] == "text-segmentation"
    request = captured["request"]
    assert isinstance(request, RunRequest)
    assert request.input_data == {"text": "hi"}
    assert request.golden_id is None


def test_run_skill_tool_passes_golden_id(monkeypatch) -> None:  # noqa: ANN001
    from datetime import datetime

    from app.models.runs import RunMetadata, RunRequest
    from app.services import run_manager as run_manager_module

    captured: dict[str, object] = {}

    async def _fake_start(skill_id: str, request: RunRequest) -> RunMetadata:
        captured["request"] = request
        return RunMetadata(
            run_id="run-2", status="running", started_at=datetime.now(UTC)
        )

    monkeypatch.setattr(run_manager_module.run_manager, "start_run", _fake_start)

    result = asyncio.run(
        copilot_tools.run_skill_tool.handler(
            {"skill_id": "text-segmentation", "golden_id": "g-1"}
        )
    )

    assert "is_error" not in result
    request = captured["request"]
    assert isinstance(request, RunRequest)
    assert request.golden_id == "g-1"
    assert request.input_data is None


def test_run_skill_tool_reports_failure_as_tool_error(monkeypatch) -> None:  # noqa: ANN001
    from app.services import run_manager as run_manager_module

    async def _boom(skill_id: str, request: object) -> object:
        raise RuntimeError("engine unavailable")

    monkeypatch.setattr(run_manager_module.run_manager, "start_run", _boom)

    result = asyncio.run(
        copilot_tools.run_skill_tool.handler({"skill_id": "text-segmentation"})
    )

    assert result["is_error"] is True
    assert "engine unavailable" in result["content"][0]["text"]


def _run_detail_fixture(events: list, final_context: object) -> object:  # noqa: ANN001
    from datetime import datetime

    from app.models.runs import RunDetail, RunMetadata, TokensMetrics

    return RunDetail(
        metadata=RunMetadata(
            run_id="run-9",
            status="failed",
            started_at=datetime.now(UTC),
            metrics=TokensMetrics(input_tokens=10, output_tokens=5, total_tokens=15),
            input_summary="golden g-1",
        ),
        input_data={"text": "hi"},
        events=events,
        final_context=final_context,  # type: ignore[arg-type]
        artifacts=["artifacts/result_latest.json"],
    )


def _event(seq: int, event_type: str, *, error: bool = False) -> object:
    from datetime import datetime

    from graph_agent.core.event_contracts import EventEnvelope, TransportErrorPayload

    return EventEnvelope(
        stream_id="s",
        seq=seq,
        run_id="run-9",
        event_type=event_type,
        payload={},
        cursor=str(seq),
        timestamp=datetime.now(UTC),
        error_code="engine.phase_failed" if error else None,
        error_payload=(
            TransportErrorPayload(
                error_code="engine.phase_failed",
                message="phase exploded",
                retryable=False,
            )
            if error
            else None
        ),
    )


def test_get_run_detail_tool_requires_ids() -> None:
    missing_run = asyncio.run(
        copilot_tools.get_run_detail_tool.handler({"skill_id": "s", "run_id": " "})
    )
    missing_skill = asyncio.run(
        copilot_tools.get_run_detail_tool.handler({"skill_id": " ", "run_id": "r"})
    )

    assert missing_run["is_error"] is True
    assert missing_skill["is_error"] is True


def test_get_run_detail_tool_compacts_detail(monkeypatch) -> None:  # noqa: ANN001
    from app.services import run_manager as run_manager_module

    detail = _run_detail_fixture(
        events=[
            _event(1, "phase_started"),
            _event(2, "phase_started"),
            _event(3, "phase_failed", error=True),
        ],
        final_context={"answer": 42},
    )
    monkeypatch.setattr(
        run_manager_module.run_manager,
        "get_run_detail",
        lambda skill_id, run_id: detail,
    )

    result = asyncio.run(
        copilot_tools.get_run_detail_tool.handler(
            {"skill_id": "text-segmentation", "run_id": "run-9"}
        )
    )

    assert "is_error" not in result
    payload = json.loads(result["content"][0]["text"])
    assert payload["run_id"] == "run-9"
    assert payload["status"] == "failed"
    assert payload["metrics"]["total_tokens"] == 15
    # 事件不整段转储:只给计数 + 错误摘录(结构上防止撑爆上下文)。
    assert "events" not in payload
    assert payload["events_total"] == 3
    assert payload["event_type_counts"] == {"phase_started": 2, "phase_failed": 1}
    assert payload["errors"] == [
        {
            "event_type": "phase_failed",
            "error_code": "engine.phase_failed",
            "message": "phase exploded",
        }
    ]
    assert payload["artifacts"] == ["artifacts/result_latest.json"]
    assert json.loads(payload["final_context_json"]) == {"answer": 42}
    assert payload["final_context_truncated"] is False
    assert payload["detail_hint"] == ".workspace/runs/run-9/"


def test_get_run_detail_tool_truncates_large_final_context(monkeypatch) -> None:  # noqa: ANN001
    from app.services import run_manager as run_manager_module

    detail = _run_detail_fixture(events=[], final_context={"blob": "x" * 20_000})
    monkeypatch.setattr(
        run_manager_module.run_manager,
        "get_run_detail",
        lambda skill_id, run_id: detail,
    )

    result = asyncio.run(
        copilot_tools.get_run_detail_tool.handler(
            {"skill_id": "text-segmentation", "run_id": "run-9"}
        )
    )

    payload = json.loads(result["content"][0]["text"])
    assert payload["final_context_truncated"] is True
    assert len(payload["final_context_json"]) <= copilot_tools._RUN_FINAL_CONTEXT_CHAR_LIMIT


def test_get_run_detail_tool_reports_failure_as_tool_error(monkeypatch) -> None:  # noqa: ANN001
    from app.services import run_manager as run_manager_module

    def _boom(skill_id: str, run_id: str) -> object:
        raise RuntimeError("run not sealed")

    monkeypatch.setattr(run_manager_module.run_manager, "get_run_detail", _boom)

    result = asyncio.run(
        copilot_tools.get_run_detail_tool.handler(
            {"skill_id": "text-segmentation", "run_id": "run-9"}
        )
    )

    assert result["is_error"] is True
    assert "run not sealed" in result["content"][0]["text"]


# ── golden 工具组(旅程 04:验收基准)─────────────────────────────────────────


def _golden_baseline_fixture() -> object:
    from datetime import UTC, datetime

    from app.models.golden import GoldenBaseline, GoldenBaselineCase

    return GoldenBaseline(
        id="g-1",
        source_run_id="run-1",
        linked_input_id="input-1",
        created_at=datetime.now(UTC),
        locked=False,
        content_path="golden/g-1",
        cases=[
            GoldenBaselineCase(
                case_id="c-1",
                node_id="analyze",
                phase_id="analyze",
                expected_output_ref="cases/c-1.json",
            )
        ],
    )


def test_list_golden_tool_requires_skill_id() -> None:
    result = asyncio.run(copilot_tools.list_golden_tool.handler({"skill_id": "  "}))

    assert result["is_error"] is True


def test_list_golden_tool_returns_compact_listing(monkeypatch) -> None:  # noqa: ANN001
    from app.services import golden_diff

    monkeypatch.setattr(
        golden_diff,
        "list_golden_baselines_for_skill",
        lambda skill_id: [_golden_baseline_fixture()],
    )

    result = asyncio.run(
        copilot_tools.list_golden_tool.handler({"skill_id": "text-segmentation"})
    )

    assert "is_error" not in result
    payload = json.loads(result["content"][0]["text"])
    assert payload["golden_count"] == 1
    entry = payload["baselines"][0]
    assert entry["id"] == "g-1"
    assert entry["source_run_id"] == "run-1"
    assert entry["locked"] is False
    assert entry["cases"] == [{"case_id": "c-1", "node_id": "analyze"}]


def test_get_golden_content_tool_requires_ids() -> None:
    result = asyncio.run(
        copilot_tools.get_golden_content_tool.handler({"skill_id": "s", "golden_id": " "})
    )

    assert result["is_error"] is True


def test_get_golden_content_tool_bounds_expected_output(monkeypatch) -> None:  # noqa: ANN001
    from app.models.golden import GoldenBaselineContent, GoldenCaseContent
    from app.services import golden_diff

    captured: dict[str, object] = {}

    def _fake_read(skill_id: str, golden_id: str, *, node_id: object = None) -> object:
        captured["node_id"] = node_id
        return GoldenBaselineContent(
            id=golden_id,
            source_run_id="run-1",
            locked=True,
            cases=[
                GoldenCaseContent(
                    case_id="c-1",
                    node_id="analyze",
                    phase_id="analyze",
                    expected_output={"answer": 42},
                ),
                GoldenCaseContent(
                    case_id="c-2",
                    node_id="draft",
                    phase_id="draft",
                    expected_output={"blob": "x" * 20_000},
                ),
            ],
        )

    monkeypatch.setattr(golden_diff, "read_golden_baseline_content", _fake_read)

    result = asyncio.run(
        copilot_tools.get_golden_content_tool.handler(
            {"skill_id": "text-segmentation", "golden_id": "g-1", "node_id": "analyze"}
        )
    )

    assert "is_error" not in result
    assert captured["node_id"] == "analyze"
    payload = json.loads(result["content"][0]["text"])
    assert payload["id"] == "g-1"
    assert payload["locked"] is True
    small, big = payload["cases"]
    assert json.loads(small["expected_output_json"]) == {"answer": 42}
    assert small["expected_output_truncated"] is False
    assert big["expected_output_truncated"] is True
    assert len(big["expected_output_json"]) <= copilot_tools._GOLDEN_CASE_CHAR_LIMIT


def test_set_golden_baseline_tool_requires_ids() -> None:
    result = asyncio.run(
        copilot_tools.set_golden_baseline_tool.handler({"skill_id": "s", "run_id": " "})
    )

    assert result["is_error"] is True


def test_set_golden_baseline_tool_promotes_run(monkeypatch) -> None:  # noqa: ANN001
    from app.services import golden_diff

    captured: dict[str, object] = {}

    def _fake_set(
        skill_id: str, run_id: str, *, lock: bool, node_id: object = None
    ) -> object:
        captured.update(
            {"skill_id": skill_id, "run_id": run_id, "lock": lock, "node_id": node_id}
        )
        return _golden_baseline_fixture()

    monkeypatch.setattr(golden_diff, "set_golden_baseline_for_run", _fake_set)

    result = asyncio.run(
        copilot_tools.set_golden_baseline_tool.handler(
            {
                "skill_id": "text-segmentation",
                "run_id": "run-1",
                "lock": True,
                "node_id": "analyze",
            }
        )
    )

    assert "is_error" not in result
    payload = json.loads(result["content"][0]["text"])
    assert payload["status"] == "success"
    assert payload["golden_id"] == "g-1"
    assert captured == {
        "skill_id": "text-segmentation",
        "run_id": "run-1",
        "lock": True,
        "node_id": "analyze",
    }


def test_set_golden_baseline_tool_reports_failure_as_tool_error(monkeypatch) -> None:  # noqa: ANN001
    from app.services import golden_diff

    def _boom(skill_id: str, run_id: str, *, lock: bool, node_id: object = None) -> object:
        raise RuntimeError("run not sealed")

    monkeypatch.setattr(golden_diff, "set_golden_baseline_for_run", _boom)

    result = asyncio.run(
        copilot_tools.set_golden_baseline_tool.handler(
            {"skill_id": "text-segmentation", "run_id": "run-1"}
        )
    )

    assert result["is_error"] is True
    assert "run not sealed" in result["content"][0]["text"]


def test_delete_golden_baseline_tool_requires_ids() -> None:
    result = asyncio.run(
        copilot_tools.delete_golden_baseline_tool.handler(
            {"skill_id": "s", "golden_id": " "}
        )
    )

    assert result["is_error"] is True


def test_delete_golden_baseline_tool_deletes(monkeypatch) -> None:  # noqa: ANN001
    from app.services import golden_diff

    captured: dict[str, object] = {}

    def _fake_delete(skill_id: str, golden_id: str) -> None:
        captured.update({"skill_id": skill_id, "golden_id": golden_id})

    monkeypatch.setattr(golden_diff, "delete_golden_baseline_for_skill", _fake_delete)

    result = asyncio.run(
        copilot_tools.delete_golden_baseline_tool.handler(
            {"skill_id": "text-segmentation", "golden_id": "g-1"}
        )
    )

    assert "is_error" not in result
    payload = json.loads(result["content"][0]["text"])
    assert payload["status"] == "success"
    assert captured == {"skill_id": "text-segmentation", "golden_id": "g-1"}
