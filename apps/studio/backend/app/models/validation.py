"""Input validation request and response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ValidateInputReq(BaseModel):
    """The input a caller is about to run with, submitted for checking.

    A PAYLOAD, not a path. The field used to be ``input_file_path: str`` and the
    service read exactly that path off the local disk — which no client ever
    sent (the only caller, ``useInputPlayground.validateRemote``, posts the input
    object) and which no design asked for: ``STUDIO_REQUEST_AUDIT.md`` describes
    this route as an "explicit validation command for a submitted payload" on
    both the backend and frontend rows, and the reorg catalog recorded the
    ``{input_file_path}`` shape as a cloud/multi-tenant leftover at odds with the
    local single-user model. So the file-reading branch is DELETED rather than
    bounded: there was nothing to keep working.

    ``input_data`` rather than a bare free-form object at the top level, matching
    ``RunRequest.input_data`` and ``PredictRunRequest.input_data``. The envelope
    is what makes ``extra="forbid"`` mean anything here — a top-level passthrough
    dict cannot refuse a field, and a skill input named like a future control
    field would silently become one.
    """

    model_config = ConfigDict(extra="forbid")

    input_data: dict[str, Any] = Field(default_factory=dict)


class ValidateInputResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validated_data: dict[str, Any]
