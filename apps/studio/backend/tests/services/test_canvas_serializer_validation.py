from app.models.skills import SerializeGraphReq
from app.services.canvas_errors import CanvasSerializerFatal
from app.services.skills import _validate_canvas_topology


def test_canvas_serializer_allows_disconnected_phase_nodes() -> None:
    request = SerializeGraphReq.model_validate(
        {
            "phases": [
                {
                    "id": "init",
                    "src": "phases/init/LOGIC.md",
                    "mode": "logic",
                    "depends_on": [],
                },
                {
                    "id": "agent",
                    "src": "phases/agent/SKILL.md",
                    "mode": "skill",
                    "depends_on": [],
                },
            ]
        }
    )

    _validate_canvas_topology(request)


def test_canvas_serializer_still_rejects_unknown_dependencies() -> None:
    request = SerializeGraphReq.model_validate(
        {
            "phases": [
                {
                    "id": "agent",
                    "src": "phases/agent/SKILL.md",
                    "mode": "skill",
                    "depends_on": ["missing"],
                },
            ]
        }
    )

    try:
        _validate_canvas_topology(request)
    except CanvasSerializerFatal as exc:
        assert exc.code == "serializer_orphan"
    else:
        raise AssertionError("expected unknown dependency to be rejected")
