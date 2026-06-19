"""Global Studio application settings models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# UI languages Studio's react-i18next bundle ships. Mirrors the frontend
# `supportedLngs` in apps/studio/frontend/src/i18n.ts; keep the two in sync.
SupportedLanguage = Literal["en", "zh-CN"]


class AppSettings(BaseModel):
    """Global settings persisted in ``app_settings.json``."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(
        default="",
        description="Studio User ID used as the local Git author name.",
    )
    gitea_host: str = Field(
        default="",
        description="Base URL for the user's self-hosted Gitea instance.",
    )
    default_skills_directory: str = Field(
        default="",
        description="Absolute directory where Studio creates new skills by default.",
    )
    language: SupportedLanguage = Field(
        default="en",
        description="Studio UI language, applied via react-i18next on the frontend.",
    )

    @field_validator("user_id", "gitea_host", "default_skills_directory")
    @classmethod
    def strip_string_fields(cls, value: str) -> str:
        """Store surrounding whitespace-free settings values."""
        return value.strip()
