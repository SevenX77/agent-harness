"""The copilot's one way to read a page the person had to log in to see.

Why a tool at all, when OpenCLI is a command line and the copilot has Bash:
Bash is execution-class and is forced through approval on every single call by
``_execution_requires_approval_hook``. Reading one page of provider docs would
raise an approval card, and reading ten would raise ten. A tool whose whole
vocabulary is "go to a URL, read the text" has a side effect that can be stated
in full, which is what lets it sit on the no-approval list instead.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from app.services import copilot_tools, web_access


def _call(**args: Any) -> dict[str, Any]:
    return asyncio.run(copilot_tools.fetch_web_page_tool.handler(args))


def _result_text(result: dict[str, Any]) -> str:
    return str(result["content"][0]["text"])


def test_a_page_the_person_is_logged_into_comes_back_as_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        web_access,
        "fetch_page",
        lambda url, **kwargs: web_access.WebPage(
            url=url,
            title="Models",
            content="# Models\n\nvision-pro takes images.",
            continues_at=None,
        ),
    )

    result = _call(url="https://platform.example.com/models")

    assert "is_error" not in result
    payload = json.loads(_result_text(result))
    assert payload["title"] == "Models"
    assert "vision-pro takes images." in payload["content"]


def test_a_long_page_tells_the_model_how_to_continue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        web_access,
        "fetch_page",
        lambda url, **kwargs: web_access.WebPage(
            url=url, title="Long", content="...", continues_at=20000
        ),
    )

    result = _call(url="https://example.com/long")

    assert json.loads(_result_text(result))["continues_at"] == 20000


def test_the_start_offset_reaches_the_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake(url: str, **kwargs: Any) -> web_access.WebPage:
        seen.update(kwargs)
        return web_access.WebPage(url=url, title="", content="", continues_at=None)

    monkeypatch.setattr(web_access, "fetch_page", fake)

    _call(url="https://example.com/long", start=20000)

    assert seen["start"] == 20000


def test_a_bridge_that_is_not_ready_asks_the_person_instead_of_reporting_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure mode this guards against is an agent concluding "this
    provider documents nothing" when the truth is "nobody opened Chrome"."""

    monkeypatch.setattr(
        web_access,
        "fetch_page",
        lambda url, **kwargs: web_access.BridgeNotReady(
            cli_installed=True,
            daemon_running=True,
            extension_connected=False,
            what_the_person_must_do="打开 Chrome,启用 OpenCLI 扩展,并登录目标站点。",
        ),
    )

    result = _call(url="https://example.com")

    assert result.get("is_error") is True
    assert "Chrome" in _result_text(result)


def test_a_missing_url_is_refused_at_the_boundary() -> None:
    result = _call(url="   ")

    assert result.get("is_error") is True


def test_the_tool_is_pre_allowed_and_never_counted_as_a_write() -> None:
    from app.services.copilot import _DECLARATIVE_ALLOWED_TOOLS, _MCP_APPROVAL_WRITE_TOOLS

    assert "fetch_web_page" in {tool.name for tool in copilot_tools.copilot_mcp_tools()}
    assert "mcp__studio__fetch_web_page" in _DECLARATIVE_ALLOWED_TOOLS
    assert "mcp__studio__fetch_web_page" not in _MCP_APPROVAL_WRITE_TOOLS


def test_both_no_approval_lists_name_the_same_mcp_tools() -> None:
    """Two surfaces pre-allow MCP tools: the in-app copilot
    (``_DECLARATIVE_ALLOWED_TOOLS``) and an external `claude` session opened
    against Studio's MCP endpoint (``CLAUDE_STUDIO_ALLOWED_TOOLS`` in
    apps/studio/tauri/src/lib.rs). They held the same 20 names by hand and by
    luck; adding the 21st is when that stops being safe. Nothing enforced the
    agreement, so a tool added to one surface would silently be missing from
    the other — the exact drift this repo keeps paying for.
    """

    import re
    from pathlib import Path

    from app.services.copilot import _DECLARATIVE_ALLOWED_TOOLS

    lib_rs = Path(__file__).resolve().parents[3] / "tauri" / "src" / "lib.rs"
    body = lib_rs.read_text(encoding="utf-8")
    const = re.search(
        r"const CLAUDE_STUDIO_ALLOWED_TOOLS: &str = concat!\((.*?)\);", body, re.DOTALL
    )
    assert const is not None, f"allow-list constant not found in {lib_rs}"

    cli_side = set(re.findall(r"mcp__studio__[a-z_]+", const.group(1)))
    copilot_side = {name for name in _DECLARATIVE_ALLOWED_TOOLS if name.startswith("mcp__studio__")}

    assert cli_side == copilot_side, (
        "the copilot and Open-in-CLI no-approval lists disagree; "
        f"only in copilot: {sorted(copilot_side - cli_side)}; "
        f"only in lib.rs: {sorted(cli_side - copilot_side)}"
    )
