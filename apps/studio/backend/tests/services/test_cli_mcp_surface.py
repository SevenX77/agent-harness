"""CLI 表面 MCP 出口(N5):同一批工具的 streamable HTTP 挂载。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anyio
from app.services import cli_mcp_surface, copilot_tools


def test_cli_toolset_is_panel_minus_cascade_deletes() -> None:
    panel = {t.name for t in copilot_tools._copilot_mcp_tools()}
    cli = set(cli_mcp_surface.cli_tool_names())

    assert cli == panel - set(cli_mcp_surface.CLI_EXCLUDED_TOOL_NAMES)
    # 级联删除类不进 CLI 首版(终端误批一次即清凭据,代价不对称)。
    assert cli_mcp_surface.CLI_EXCLUDED_TOOL_NAMES == frozenset(
        {"delete_llm_endpoint", "delete_llm_route"}
    )
    assert "compile_skill" in cli
    assert "run_skill" in cli


def test_cli_server_lists_and_calls_tools_in_memory() -> None:
    # 官方内存会话(mcp.shared.memory):不开真端口,验证 Server 实例本身
    # 走完整 MCP 协议(list_tools / call_tool),错误结果按 isError 回传。
    from mcp.shared.memory import create_connected_server_and_client_session

    async def _exercise() -> tuple[set[str], Any]:
        server = cli_mcp_surface.build_cli_mcp_server()
        async with create_connected_server_and_client_session(server) as session:
            listed = await session.list_tools()
            result = await session.call_tool(
                "compile_skill", {"skill_id": "no-such-skill-xyz"}
            )
            return {t.name for t in listed.tools}, result

    names, result = anyio.run(_exercise)

    assert "compile_skill" in names
    assert "delete_llm_endpoint" not in names
    assert "delete_llm_route" not in names
    assert result.isError is True


def test_mcp_endpoint_requires_bearer_token(studio_roots: tuple[Path, Path]) -> None:
    del studio_roots
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.post("/mcp", json={})

    assert response.status_code == 401


def test_mcp_endpoint_initializes_with_token(studio_roots: tuple[Path, Path]) -> None:
    del studio_roots
    from app.main import app
    from fastapi.testclient import TestClient

    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "cli-mcp-test", "version": "0"},
        },
    }
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json=initialize,
            headers={
                "Authorization": "Bearer studio-test-token",
                "Accept": "application/json, text/event-stream",
            },
        )

    assert response.status_code == 200
    assert "mcp-session-id" in response.headers


def test_mcp_endpoint_serves_exact_path_without_redirect(
    studio_roots: tuple[Path, Path],
) -> None:
    # The URL handed to CLI clients is `<base>/mcp`. A Starlette Mount would
    # 307 that to `/mcp/`, and an MCP client that drops Authorization across a
    # redirect (or refuses to re-POST) silently loses the whole tool surface.
    del studio_roots
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={
                "Authorization": "Bearer studio-test-token",
                "Accept": "application/json, text/event-stream",
            },
            follow_redirects=False,
        )

    assert response.status_code != 307, "/mcp must be served directly, not redirected"
