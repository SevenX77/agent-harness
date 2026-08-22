"""How big a turn's images may be, and why the number is that number.

Design: `docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md`
decision COPILOT_ASSIST-11 ②④.

The whole turn — sentence, mentions and images — leaves in ONE WebSocket frame,
and uvicorn caps a frame at 16 MiB. Over that the connection is closed and the
message disappears without an error anyone can read, so the boundary refuses the
turn while there is still someone to tell.

The composer refuses the same thing at pick time, which is where the user can
still act on it. That means the number exists in two languages, so the last test
here reads the frontend's copy and asserts they have not drifted apart.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest
from app.models.copilot import (
    TURN_IMAGE_BUDGET_BYTES,
    CopilotImageAttachment,
    CopilotWsRequestPayload,
)
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[5]
FRONTEND_INTAKE = (
    REPO_ROOT
    / "apps"
    / "studio"
    / "frontend"
    / "src"
    / "components"
    / "copilot"
    / "composer"
    / "attachment-intake.ts"
)


def _image(byte_count: int) -> dict[str, str]:
    return {
        "kind": "image",
        "media_type": "image/png",
        "data": base64.b64encode(b"A" * byte_count).decode("ascii"),
        "name": f"{byte_count}-bytes.png",
    }


def test_a_turn_within_the_budget_is_accepted() -> None:
    payload = CopilotWsRequestPayload(
        user_message="look at this",
        session_id="s-1",
        attachments=[CopilotImageAttachment(**_image(1024))],
    )

    assert len(payload.attachments) == 1


def test_a_turn_over_the_budget_is_refused_at_the_boundary() -> None:
    with pytest.raises(ValidationError) as caught:
        CopilotWsRequestPayload(
            user_message="look at this",
            session_id="s-1",
            attachments=[CopilotImageAttachment(**_image(TURN_IMAGE_BUDGET_BYTES + 1))],
        )

    assert "budget" in str(caught.value).lower()


def test_the_budget_is_the_whole_turn_not_one_image() -> None:
    """Two halves that each fit still cannot both ride: one frame carries both."""
    half = TURN_IMAGE_BUDGET_BYTES // 2 + 1024

    with pytest.raises(ValidationError):
        CopilotWsRequestPayload(
            user_message="compare these",
            session_id="s-1",
            attachments=[
                CopilotImageAttachment(**_image(half)),
                CopilotImageAttachment(**_image(half)),
            ],
        )


def test_data_that_is_not_base64_is_refused_rather_than_forwarded() -> None:
    """A malformed payload must die here, not inside the provider SDK.

    `data` is handed to the model as an image content block; letting a
    non-decodable string through only moves the failure somewhere the user
    cannot be told about it.
    """
    with pytest.raises(ValidationError) as caught:
        CopilotImageAttachment(kind="image", media_type="image/png", data="not base64 !!")

    assert "base64" in str(caught.value).lower()


def test_the_frontend_refuses_at_the_same_number() -> None:
    """One rule, two languages — checked, not hoped.

    The composer has to know the limit to refuse a picked file before the user
    has typed anything, and the boundary has to know it because a rule cannot
    depend on a client remembering to follow it. Two constants is two truths
    unless something asserts they agree; this is that something.
    """
    source = FRONTEND_INTAKE.read_text(encoding="utf-8")
    match = re.search(
        r"export const TURN_IMAGE_BUDGET_BYTES\s*=\s*([0-9*\s]+)$",
        source,
        re.MULTILINE,
    )
    assert match, "the frontend constant moved or was renamed"

    expression = match.group(1).strip()
    assert re.fullmatch(r"[0-9*\s]+", expression), expression
    frontend_value = 1
    for factor in expression.split("*"):
        frontend_value *= int(factor.strip())

    assert frontend_value == TURN_IMAGE_BUDGET_BYTES
