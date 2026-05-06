"""Input validation request and response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ValidateInputReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_file_path: str


class ValidateInputResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validated_data: dict[str, Any]
