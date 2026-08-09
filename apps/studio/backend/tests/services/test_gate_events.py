"""闸门结果领域事件(决议 2026-08-03 D2/D3)。

前端的闸门状态机只知道自己发起的动作;copilot 经 MCP 发起同一个动作时前端收不到
任何信号,于是工具栏停在 compile、错误抽屉不弹、run 不切 Trace。补法是:闸门在
**service 层**广播一条钉住数据集的领域事件,HTTP 路由与 MCP 工具两条发起路径因此
天然发同一条,前端订阅后按同一套归约推进状态。

"发在 service 层"是这批测试真正锁住的东西——若发在 router 层,MCP 路径不会发事件,
状态对等在实现层即被破坏,而行为测试只走 HTTP 路径时是看不出来的。故除行为测试外
另有一条结构测试,直接钉住发布点的归属模块。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from app.services.event_bus import event_bus
from fastapi.testclient import TestClient

from tests.conftest import copy_skill

BACKEND_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "app").is_dir() and (parent / "tests").is_dir()
)


def _source(relative: str) -> str:
    return (BACKEND_ROOT / relative).read_text(encoding="utf-8")


class _RecordedEvents:
    """Record what the gate publishes, without depending on loop plumbing.

    The websocket delivery path is already covered by
    ``test_api.test_events_ws_broadcasts_to_multiple_clients``; what these tests
    need to pin is that the gate itself publishes the right payload, so they
    stand in for the bus rather than driving a socket that would block when the
    event never arrives.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.events: list[dict[str, object]] = []

        async def _record(_topic: str, event: dict[str, object]) -> None:
            self.events.append(event)

        monkeypatch.setattr(event_bus, "publish", _record)

    def of_gate(self, gate: str) -> list[dict[str, object]]:
        return [
            event
            for event in self.events
            if event.get("type") == "skill_gate" and event.get("gate") == gate
        ]


def test_event_payload_pins_the_dataset() -> None:
    """载荷必须钉住 skill_id 与内容标识,前端才能只重算对应 skill 的闸门状态。"""
    from app.services.gate_events import build_skill_gate_event

    event = build_skill_gate_event(
        skill_id="demo.skill",
        gate="compile",
        outcome="fail",
        content_hash="sha256:abc",
        defect_count=3,
    )

    assert event["type"] == "skill_gate"
    assert event["skill_id"] == "demo.skill"
    assert event["gate"] == "compile"
    assert event["outcome"] == "fail"
    assert event["content_hash"] == "sha256:abc"
    assert event["defect_count"] == 3
    assert event["run_id"] is None
    assert isinstance(event["timestamp"], str) and event["timestamp"]


def test_publish_failure_never_breaks_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """广播是旁路:事件总线出问题不得把闸门本身带崩。"""
    import asyncio

    from app.services import gate_events

    async def _explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("event bus down")

    monkeypatch.setattr(event_bus, "publish", _explode)

    asyncio.run(
        gate_events.publish_skill_gate(skill_id="demo.skill", gate="compile", outcome="pass")
    )


def test_compile_success_publishes_a_pass_event(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    input_dir = skills_dir / "text-segmentation" / ".workspace" / "import_files"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "case-a.json").write_text('{"input_text":"chapter one"}', encoding="utf-8")
    recorded = _RecordedEvents(monkeypatch)

    response = client.post("/api/skills/text-segmentation/compile")

    assert response.status_code == 200
    events = recorded.of_gate("compile")
    # 每一次闸门发生由 started 定界(决议 2026-08-09 D4),与 predict / run 对称。
    # 没有它,copilot 连续两次编译出同样产物时,两条终态事件在前端紧邻,第二条的
    # 副作用会被当成重复到达折叠掉,错误抽屉不弹。
    assert [event["outcome"] for event in events] == ["started", "pass"]
    assert all(event["skill_id"] == "text-segmentation" for event in events)
    assert str(events[-1]["content_hash"]).startswith("sha256:")
    assert events[-1]["defect_count"] == 0


def test_compile_failure_publishes_a_fail_event_with_the_defect_count(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills_dir, workspaces_dir = studio_roots
    skill_dir = copy_skill(skills_dir, workspaces_dir, "text-segmentation")
    phase_path = skill_dir / "phases" / "setup" / "LOGIC.md"
    phase_path.write_text(
        phase_path.read_text(encoding="utf-8").replace("---\n", "---\nmode: bogus\n", 1),
        encoding="utf-8",
    )
    recorded = _RecordedEvents(monkeypatch)

    response = client.post("/api/skills/text-segmentation/compile")

    assert response.status_code >= 400
    events = recorded.of_gate("compile")
    assert [event["outcome"] for event in events] == ["started", "fail"]
    assert events[-1]["skill_id"] == "text-segmentation"
    assert int(events[-1]["defect_count"]) >= 1
    # 诊断随事件下发:接收方渲染的必须是同一份聚合诊断,而不是自己再算一遍
    # (AGENTS.md「diagnostics SSOT」)。
    carried = events[-1]["errors"]
    assert isinstance(carried, list) and len(carried) == int(events[-1]["defect_count"])
    assert all("message" in row and "severity" in row for row in carried)


def test_a_crashed_compile_still_announces_an_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """宣告了开始就必须宣告结束——否则接收方永远停在 `compiling`。

    补 `started` 之后,编译如果死在 CompileFailedError 之外的异常上(skill 找不到、
    磁盘错、引擎内部崩),而没有任何终态事件跟上,前端就会停在开始事件写下的
    `compiling` 上,再没有事件能推走它——正是决议 2026-08-09 D1 要根除的那类卡死。
    崩溃也是一种结束,按结束上报;异常本身照常抛出,不被吞掉。
    """
    import asyncio

    from app.services import skills as skills_module

    recorded = _RecordedEvents(monkeypatch)

    async def _explode(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("engine adapter blew up")

    monkeypatch.setattr(skills_module, "_compile_skill_for_studio", _explode)

    with pytest.raises(RuntimeError):
        asyncio.run(
            skills_module.compile_skill_for_studio(
                "user", "demo.skill", storage=None, metadata=None
            )
        )

    assert [event["outcome"] for event in recorded.of_gate("compile")] == ["started", "fail"]


def test_gate_events_are_published_from_services_not_routers() -> None:
    """D2:发布点必须在 HTTP 路由与 MCP 工具的公共下游。

    若某个 router 自己发闸门事件,MCP 路径就不会发——这条结构断言把该退化钉死在
    单测里,而不是等某次真机会话发现前端不动了才回头查。
    """
    for router in ("app/routers/skills.py", "app/routers/runs.py"):
        assert "publish_skill_gate" not in _source(router), (
            f"{router} 不得自行发布闸门事件:发布点属于 service 层"
        )

    for service in (
        "app/services/skills.py",
        "app/services/predictor.py",
        "app/services/run_manager.py",
    ):
        assert "publish_skill_gate" in _source(service), f"{service} 必须发布其闸门的领域事件"


def test_gate_event_module_declares_the_three_gates() -> None:
    """闸门取值是契约的一部分,前端归约器按它分派。"""
    tree = ast.parse(_source("app/services/gate_events.py"))
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert {"compile", "predict", "run"} <= literals
    assert {"started", "pass", "fail"} <= literals
