"""Skill template response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SkillTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    type: str
    content: str

