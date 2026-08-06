"""Global Studio application settings models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# UI languages Studio's react-i18next bundle ships. Mirrors the frontend
# `supportedLngs` in apps/studio/frontend/src/i18n.ts; keep the two in sync.
SupportedLanguage = Literal["en", "zh-CN"]


class CliSessionProviderSettings(BaseModel):
    """一个 CLI provider 的会话默认(空串 = 跟随 CLI 自身默认,不注入旗标)。"""

    model_config = ConfigDict(extra="forbid")

    model: str = ""
    effort: str = ""


class CliSessionSettings(BaseModel):
    """Open in CLI 的会话配置(提案 2026-08-06 §4):provider 默认 + MoirAI 分角色覆盖。

    agents 键 = MoirAI 角色名(moirai/clotho/lachesis/atropos);值为空的字段继承
    provider 默认。truth 在此,消费在 Tauri(前端 open 时读 settings 传参注入)。
    """

    model_config = ConfigDict(extra="forbid")

    claude: CliSessionProviderSettings = Field(default_factory=CliSessionProviderSettings)
    codex: CliSessionProviderSettings = Field(default_factory=CliSessionProviderSettings)
    agents: dict[str, CliSessionProviderSettings] = Field(default_factory=dict)


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
    remote_model_catalog_enabled: bool = Field(
        default=True,
        description="Whether Studio automatically reads the remote model catalog.",
    )
    cli_sessions: CliSessionSettings = Field(
        default_factory=CliSessionSettings,
        description="Open in CLI session defaults: provider model/effort plus per-MoirAI-agent overrides.",
    )

    @field_validator("user_id", "gitea_host", "default_skills_directory")
    @classmethod
    def strip_string_fields(cls, value: str) -> str:
        """Store surrounding whitespace-free settings values."""
        return value.strip()
