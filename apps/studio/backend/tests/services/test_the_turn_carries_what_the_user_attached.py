"""What the user picked reaches the model, and the echo says what reached it.

The resolver decides what one mention becomes
(`test_a_mention_is_something_the_user_picked.py`); these tests hold the turn
itself to F4 ⑤ — the first streamed event echoes what was actually injected —
and to the attachment path: an image travels with the turn as an image content
block, not as a path the copilot is told to go open.
"""

from __future__ import annotations

import base64
from pathlib import Path

from app.models.copilot import CopilotImageAttachment, CopilotMention
from app.services import copilot as copilot_service

_ONE_PIXEL_PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n fake pixels").decode("ascii")


def _skill(tmp_path: Path) -> Path:
    root = tmp_path / "demo-skill"
    root.mkdir()
    (root / "GRAPH.md").write_text("# graph\n", encoding="utf-8")
    return root


def test_the_echo_lists_every_mention_of_the_turn(tmp_path: Path) -> None:
    event = copilot_service._context_resolved_event(
        "demo-skill",
        mentions=[
            CopilotMention(kind="file", ref="GRAPH.md", label="GRAPH.md"),
            CopilotMention(kind="dot", ref="draft.summary", label="draft.summary"),
        ],
        skill_dir=_skill(tmp_path),
    )

    assert "GRAPH.md" in event.detail
    assert "draft.summary" in event.detail
    assert "mentions" in event.summary


def test_the_echo_counts_attachments_it_cannot_show(tmp_path: Path) -> None:
    """An image has no text to print, so the echo states that one went."""
    event = copilot_service._context_resolved_event(
        "demo-skill",
        attachments=[CopilotImageAttachment(media_type="image/png", data=_ONE_PIXEL_PNG, name="shot.png")],
        skill_dir=_skill(tmp_path),
    )

    assert "shot.png" in event.detail
    assert "image" in event.summary


def test_a_turn_with_nothing_attached_still_echoes(tmp_path: Path) -> None:
    event = copilot_service._context_resolved_event("demo-skill", skill_dir=_skill(tmp_path))

    assert event.summary.startswith("Injected this turn:")
    assert event.detail == "(no request context)"


def test_the_prompt_carries_the_mention_contents(tmp_path: Path) -> None:
    prompt = copilot_service._prompt_with_turn_context(
        "demo-skill",
        "what does this graph do?",
        mentions=[CopilotMention(kind="file", ref="GRAPH.md", label="GRAPH.md")],
        skill_dir=_skill(tmp_path),
    )

    assert "# graph" in prompt
    assert "what does this graph do?" in prompt


def test_a_turn_without_context_sends_the_message_unwrapped(tmp_path: Path) -> None:
    prompt = copilot_service._prompt_with_turn_context("demo-skill", "hello", skill_dir=_skill(tmp_path))

    assert prompt == "hello"


def test_an_attached_image_becomes_an_image_content_block() -> None:
    message = copilot_service._turn_message_with_attachments(
        "look at this",
        [CopilotImageAttachment(media_type="image/png", data=_ONE_PIXEL_PNG, name="shot.png")],
    )

    content = message["message"]["content"]
    assert content[0] == {"type": "text", "text": "look at this"}
    assert content[1] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": _ONE_PIXEL_PNG},
    }
    assert message["type"] == "user"


def test_a_turn_without_images_is_sent_as_plain_text() -> None:
    """The SDK takes a bare string; wrapping every turn in blocks would be noise."""
    assert copilot_service._turn_message_with_attachments("hello", []) is None
