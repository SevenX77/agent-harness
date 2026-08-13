"""Media generation domain schema.

Isolated from the LLM registry on purpose: media models must never be
resolvable by the role→route system, so nothing here imports or extends the
LLM registry types (design: docs/graph-agent-gateway/mvp1/14-media-generation/).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

MediaModality = Literal["image", "video"]
MediaTask = Literal["t2i", "i2i", "i2v", "flf2v", "ref2v"]
MediaChannel = Literal["economy", "official"]
MediaEndpointKind = Literal["standard", "ai_app"]
MediaProbeStatus = Literal["ok", "auth_failed", "network_error"]
MediaPricingUnit = Literal["per_image", "per_second", "per_run"]


class StringParamSpec(BaseModel):
    """Free-text request parameter (e.g. prompt)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["string"] = "string"
    required: bool = False
    min_length: int | None = None
    max_length: int | None = None


class EnumParamSpec(BaseModel):
    """Closed-choice parameter; UI defaults may only pick from ``values``."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["enum"] = "enum"
    required: bool = False
    values: tuple[str, ...] = Field(min_length=1)
    default: str | None = None


class IntRangeParamSpec(BaseModel):
    """Bounded integer parameter (e.g. duration seconds)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["int_range"] = "int_range"
    required: bool = False
    min_value: int
    max_value: int


class ImageListParamSpec(BaseModel):
    """Reference-image list input with provider-documented limits."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["image_list"] = "image_list"
    required: bool = False
    max_items: int
    max_size_mb: int | None = None


class ImageSlotParamSpec(BaseModel):
    """Single named image input (e.g. first/last frame)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["image_slot"] = "image_slot"
    required: bool = False
    max_size_mb: int | None = None


MediaParamSpec = Annotated[
    StringParamSpec
    | EnumParamSpec
    | IntRangeParamSpec
    | ImageListParamSpec
    | ImageSlotParamSpec,
    Field(discriminator="type"),
]


class MediaPricing(BaseModel):
    """Price evidence from the provider's marketplace page; never invented."""

    model_config = ConfigDict(extra="forbid")

    unit: MediaPricingUnit
    amount: float = Field(gt=0)
    currency: Literal["CNY"] = "CNY"


class MediaModelSpec(BaseModel):
    """One catalog entry: what the provider documents this model accepts."""

    model_config = ConfigDict(extra="forbid")

    id: str
    provider: Literal["runninghub"]
    display_name: str
    modality: MediaModality
    task: MediaTask
    channel: MediaChannel
    endpoint_kind: MediaEndpointKind
    endpoint: str
    pricing: MediaPricing | None = None
    params: dict[str, MediaParamSpec] = Field(default_factory=dict)
    doc_source: str | None = None


class MediaModelSettings(BaseModel):
    """Host-persisted per-model user settings; validated against the catalog."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    defaults: dict[str, str | int] = Field(default_factory=dict)


class MediaProviderCredential(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr = SecretStr("")
    base_url: str = "https://www.runninghub.cn"


class MediaProbeResult(BaseModel):
    """Outcome of the zero-cost account probe (L1 connectivity)."""

    model_config = ConfigDict(extra="forbid")

    status: MediaProbeStatus
    checked_at: str
    latency_ms: int | None = None
    remain_coins: str | None = None
    remain_money: str | None = None
    message: str | None = None


class MediaProviderState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential: MediaProviderCredential = Field(default_factory=MediaProviderCredential)
    last_probe: MediaProbeResult | None = None
    model_settings: dict[str, MediaModelSettings] = Field(default_factory=dict)


class MediaGenerationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: dict[str, MediaProviderState] = Field(default_factory=dict)
