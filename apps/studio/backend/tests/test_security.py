from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from app.core import config
from app.services.terminal_manager import TerminalManager, TerminalRecord, terminal_manager
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_recording_pty() -> None:
    RecordingPtyFactory.reset()


def test_terminal_rejects_invalid_skill_id_with_standard_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.terminal_manager.PtyProcess", RecordingPtyFactory)

    response = client.post("/api/skills/text_segmentation/terminal")

    assert response.status_code == 404
    assert response.json()["error_code"] == "SKILL_NOT_FOUND"
    assert RecordingPtyFactory.commands == []


@pytest.mark.parametrize(
    "skill_id",
    ["../text-segmentation", "text/segmentation", "text\\segmentation", "text.."],
)
def test_terminal_rejects_path_traversal_ids_before_spawn(
    skill_id: str,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del studio_roots
    manager = TerminalManager()
    monkeypatch.setattr("app.services.terminal_manager.PtyProcess", RecordingPtyFactory)

    with pytest.raises(ValueError, match="SKILL_NOT_FOUND"):
        manager.create_terminal(skill_id)

    assert RecordingPtyFactory.commands == []


def test_terminal_rejects_missing_skill_before_spawn(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.terminal_manager.PtyProcess", RecordingPtyFactory)

    response = client.post("/api/skills/not-real/terminal")

    assert response.status_code == 404
    assert response.json()["error_code"] == "SKILL_NOT_FOUND"
    assert RecordingPtyFactory.commands == []


def test_terminal_rejects_symlink_escape_from_skills_root(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    escaped_skill = tmp_path / "escaped-skill"
    escaped_skill.mkdir()
    (escaped_skill / "SKILL.md").write_text(
        "---\nname: escaped\ntype: graph\n---\n", encoding="utf-8"
    )
    try:
        (skills_dir / "evil").symlink_to(escaped_skill, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    monkeypatch.setattr("app.services.terminal_manager.PtyProcess", RecordingPtyFactory)

    response = client.post("/api/skills/evil/terminal")

    assert response.status_code == 404
    assert response.json()["error_code"] == "SKILL_NOT_FOUND"
    assert RecordingPtyFactory.commands == []


def test_terminal_uses_only_server_side_whitelisted_command(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    monkeypatch.setattr("app.services.terminal_manager.PtyProcess", RecordingPtyFactory)
    monkeypatch.setattr(terminal_manager, "command", ["bash", "--noprofile", "--norc"])

    response = client.post(
        "/api/skills/text-segmentation/terminal",
        json={"cmd": ["sh", "-c", "echo injected"]},
    )

    assert response.status_code == 201
    assert RecordingPtyFactory.commands == [["bash", "--noprofile", "--norc"]]
    assert response.json()["cwd"] == (skills_dir / "text-segmentation").as_posix()


def test_terminal_rejects_non_whitelisted_internal_command(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.terminal_manager.PtyProcess", RecordingPtyFactory)
    monkeypatch.setattr(terminal_manager, "command", ["sh", "-c", "echo nope"])

    response = client.post("/api/skills/text-segmentation/terminal")

    assert response.status_code == 500
    assert response.json()["error_code"] == "TERMINAL_SPAWN_FAILED"
    assert RecordingPtyFactory.commands == []


def test_terminal_ttl_uses_config_and_reaps_expired_session(
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del studio_roots
    manager = TerminalManager()
    monkeypatch.setattr(config, "TERMINAL_SESSION_TTL_SECONDS", 1)
    monkeypatch.setattr(manager, "command", ["gemini"])
    monkeypatch.setattr("app.services.terminal_manager.PtyProcess", RecordingPtyFactory)

    session = manager.create_terminal("text-segmentation")
    record = manager._sessions[session.term_id]
    monkeypatch.setattr(
        "app.services.terminal_manager.time.monotonic", lambda: record.expires_at + 0.1
    )

    manager.reap_expired()

    assert session.ttl_seconds == 1
    assert session.term_id not in manager._sessions
    assert RecordingPtyFactory.processes[0].terminated


def test_terminal_background_reaper_task_can_start_and_shutdown() -> None:
    async def scenario() -> None:
        manager = TerminalManager()
        manager.start_reaper()
        assert manager._reaper_task is not None
        assert not manager._reaper_task.done()
        await manager.shutdown()
        assert manager._reaper_task is None

    asyncio.run(scenario())


def test_terminal_bridge_loops_swallow_normal_cancellation() -> None:
    class SlowReadPty:
        def read_nonblocking(self, size: int = 4096, timeout: float = 0.1) -> str | None:
            del size, timeout
            time.sleep(0.05)
            return None

        def write(self, data: object) -> None:
            del data

    class WaitingWebSocket:
        async def receive(self) -> dict[str, object]:
            await asyncio.sleep(10)
            return {"type": "websocket.disconnect"}

        async def send_text(self, data: str) -> None:
            del data

        async def send_bytes(self, data: bytes) -> None:
            del data

    async def scenario() -> None:
        manager = TerminalManager()
        record = TerminalRecord("term", SlowReadPty(), "/tmp", time.monotonic() + 10)
        manager._sessions[record.term_id] = record
        websocket = WaitingWebSocket()
        reader = asyncio.create_task(manager._read_pty_loop(websocket, record))
        writer = asyncio.create_task(manager._write_pty_loop(websocket, record))
        await asyncio.sleep(0)
        reader.cancel()
        writer.cancel()
        results = await asyncio.gather(reader, writer, return_exceptions=True)
        assert results == [None, None]

    asyncio.run(scenario())


def test_terminal_global_concurrency_limit_returns_503(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal_manager._sessions.clear()
    monkeypatch.setattr(config, "MAX_CONCURRENT_TERMINALS", 3)
    monkeypatch.setattr("app.services.terminal_manager.PtyProcess", RecordingPtyFactory)

    responses = [client.post("/api/skills/text-segmentation/terminal") for _ in range(4)]

    assert [response.status_code for response in responses] == [201, 201, 201, 503]
    assert responses[-1].json()["error_code"] == "TERMINAL_LIMIT_REACHED"
    assert responses[-1].json()["details"] == {"limit": 3}


class FakePty:
    def __init__(self) -> None:
        self.terminated = False

    def terminate(self, force: bool = False) -> None:
        del force
        self.terminated = True


class RecordingPtyFactory:
    commands: list[list[str]] = []
    cwds: list[str] = []
    processes: list[FakePty] = []

    @classmethod
    def reset(cls) -> None:
        cls.commands = []
        cls.cwds = []
        cls.processes = []

    @classmethod
    def spawn(cls, command: list[str], cwd: str) -> FakePty:
        process = FakePty()
        cls.commands.append(command)
        cls.cwds.append(cwd)
        cls.processes.append(process)
        return process
