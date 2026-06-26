"""Post-probe community auto-share (no-gate) wiring.

After a successful probe the desktop best-effort pushes newly probe-verified
evidence into the community catalog repo's ``incoming/`` area. Best-effort means
a probe must NEVER fail because background sharing failed.
"""

from __future__ import annotations

import pytest
from app.routers import llm as llm_router


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_autoshare_after_probe_swallows_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_router, "load_evidence_library", lambda: None)
    monkeypatch.setattr(llm_router, "load_credentials", lambda: None)

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("github down")

    monkeypatch.setattr(llm_router, "autoshare_probe_evidence", boom)
    # Must not raise — a probe never fails because background sharing did.
    await llm_router._autoshare_after_probe_best_effort()


@pytest.mark.anyio
async def test_autoshare_after_probe_forwards_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_router, "load_evidence_library", lambda: None)
    monkeypatch.setattr(llm_router, "load_credentials", lambda: None)
    captured: dict[str, object] = {}

    async def spy(library: object, credentials: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(llm_router, "autoshare_probe_evidence", spy)
    await llm_router._autoshare_after_probe_best_effort()

    assert set(captured) >= {"github_token", "catalog_repo", "catalog_owner", "enabled", "branch"}
