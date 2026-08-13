"""Built-in RunningHub media model catalog.

Every entry is evidence-anchored: endpoints were matched one-by-one against
RunningHub's official API doc pages, param tables come from the per-model doc
cited in ``doc_source``, and prices are the 2026-08-13 marketplace snapshot
(see docs/studio/mvp1/02_capabilities/media-generation/design-decision.md §3).
Capability differences are data here, never code branches.
"""

from __future__ import annotations

from graph_agent_gateway.media.schema import (
    EnumParamSpec,
    ImageListParamSpec,
    ImageSlotParamSpec,
    IntRangeParamSpec,
    MediaModelSettings,
    MediaModelSpec,
    MediaParamSpec,
    MediaPricing,
    StringParamSpec,
)

_ASPECTS_10 = ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9")
_ASPECTS_14 = _ASPECTS_10 + ("1:4", "4:1", "1:8", "8:1")


def _seedream_params(resolution_values: tuple[str, ...]) -> dict[str, MediaParamSpec]:
    return {
        "prompt": StringParamSpec(required=True, min_length=5, max_length=2000),
        "resolution": EnumParamSpec(values=resolution_values),
        "width": IntRangeParamSpec(min_value=512, max_value=8192),
        "height": IntRangeParamSpec(min_value=512, max_value=8192),
        "sequentialImageGeneration": EnumParamSpec(values=("disabled", "auto")),
        "maxImages": IntRangeParamSpec(min_value=1, max_value=15),
    }


_CATALOG: tuple[MediaModelSpec, ...] = (
    MediaModelSpec(
        id="rh-image-v2-t2i",
        provider="runninghub",
        display_name="全能图片V2-文生图-低价渠道版",
        modality="image",
        task="t2i",
        channel="economy",
        endpoint_kind="standard",
        endpoint="/openapi/v2/rhart-image-n-g31-flash/text-to-image",
        pricing=MediaPricing(unit="per_image", amount=0.19),
        params={
            "prompt": StringParamSpec(required=True),
            "resolution": EnumParamSpec(required=True, values=("1k", "2k", "4k")),
            "aspectRatio": EnumParamSpec(values=_ASPECTS_14),
        },
        doc_source="AI-story-forge:docs/api/runninghub/nbv2_t2i_rh.md",
    ),
    MediaModelSpec(
        id="rh-image-v2-i2i",
        provider="runninghub",
        display_name="全能图片V2-图生图-低价渠道版",
        modality="image",
        task="i2i",
        channel="economy",
        endpoint_kind="standard",
        endpoint="/openapi/v2/rhart-image-n-g31-flash/image-to-image",
        pricing=MediaPricing(unit="per_image", amount=0.19),
        params={
            "prompt": StringParamSpec(required=True),
            "imageUrls": ImageListParamSpec(required=True, max_items=10, max_size_mb=30),
            "resolution": EnumParamSpec(required=True, values=("1k", "2k", "4k")),
            "aspectRatio": EnumParamSpec(values=_ASPECTS_14),
        },
        doc_source="AI-story-forge:docs/api/runninghub/nbv2_i2i_rh.md",
    ),
    MediaModelSpec(
        id="rh-image-pro-t2i",
        provider="runninghub",
        display_name="全能图片PRO-文生图-低价渠道版",
        modality="image",
        task="t2i",
        channel="economy",
        endpoint_kind="standard",
        endpoint="/openapi/v2/rhart-image-n-pro/text-to-image",
        pricing=MediaPricing(unit="per_image", amount=0.4),
        params={
            "prompt": StringParamSpec(required=True),
            "resolution": EnumParamSpec(required=True, values=("1k", "2k", "4k")),
            "aspectRatio": EnumParamSpec(values=_ASPECTS_10),
        },
        doc_source="AI-story-forge:docs/api/runninghub/nbp_t2i_rh.md",
    ),
    MediaModelSpec(
        id="rh-image-pro-i2i",
        provider="runninghub",
        display_name="全能图片PRO-图生图-低价渠道版",
        modality="image",
        task="i2i",
        channel="economy",
        endpoint_kind="standard",
        endpoint="/openapi/v2/rhart-image-n-pro/edit",
        pricing=MediaPricing(unit="per_image", amount=0.4),
        params={
            "prompt": StringParamSpec(required=True),
            "imageUrls": ImageListParamSpec(required=True, max_items=10, max_size_mb=10),
            "resolution": EnumParamSpec(required=True, values=("1k", "2k", "4k")),
            "aspectRatio": EnumParamSpec(values=_ASPECTS_10),
        },
        doc_source="AI-story-forge:docs/api/runninghub/nbp_i2i_rh.md",
    ),
    MediaModelSpec(
        id="rh-seedream-v4-t2i",
        provider="runninghub",
        display_name="seedream-v4-文生图",
        modality="image",
        task="t2i",
        channel="official",
        endpoint_kind="standard",
        endpoint="/openapi/v2/seedream-v4/text-to-image",
        pricing=MediaPricing(unit="per_image", amount=0.14),
        params=_seedream_params(("1k", "2k", "4k")),
        doc_source="AI-story-forge:docs/api/runninghub/sd4.0_t2i_rh.md",
    ),
    MediaModelSpec(
        id="rh-seedream-v4.5-t2i",
        provider="runninghub",
        display_name="seedream-v4.5-文生图",
        modality="image",
        task="t2i",
        channel="official",
        endpoint_kind="standard",
        endpoint="/openapi/v2/seedream-v4.5/text-to-image",
        pricing=MediaPricing(unit="per_image", amount=0.2),
        params=_seedream_params(("2k", "4k")),
        doc_source="AI-story-forge:docs/api/runninghub/sd4.5_t2i_rh.md",
    ),
    MediaModelSpec(
        id="rh-video-x-i2v",
        provider="runninghub",
        display_name="全能视频X-图生视频-低价渠道版-v1.5",
        modality="video",
        task="i2v",
        channel="economy",
        endpoint_kind="standard",
        endpoint="/openapi/v2/rhart-video-g/image-to-video",
        pricing=MediaPricing(unit="per_second", amount=0.04),
        params={
            "prompt": StringParamSpec(required=True, min_length=5, max_length=20000),
            "imageUrls": ImageListParamSpec(max_items=7, max_size_mb=10),
            "resolution": EnumParamSpec(required=True, values=("720p", "480p")),
            "aspectRatio": EnumParamSpec(
                required=True, values=("2:3", "3:2", "1:1", "16:9", "9:16")
            ),
            "duration": IntRangeParamSpec(min_value=6, max_value=30),
        },
        doc_source="AI-story-forge:docs/api/runninghub/vx_i2v_rh.md",
    ),
    MediaModelSpec(
        id="rh-video-v3.1-pro-flf2v",
        provider="runninghub",
        display_name="全能视频V3.1-pro-首尾帧生视频-低价渠道版",
        modality="video",
        task="flf2v",
        channel="economy",
        endpoint_kind="standard",
        endpoint="/openapi/v2/rhart-video-v3.1-pro/start-end-to-video",
        pricing=MediaPricing(unit="per_run", amount=0.9),
        params={
            "prompt": StringParamSpec(required=True, min_length=5, max_length=8000),
            "firstFrameUrl": ImageSlotParamSpec(required=True, max_size_mb=10),
            "lastFrameUrl": ImageSlotParamSpec(max_size_mb=10),
            "resolution": EnumParamSpec(required=True, values=("720p", "1080p", "4k")),
            "aspectRatio": EnumParamSpec(required=True, values=("16:9", "9:16")),
            "duration": EnumParamSpec(values=("8",)),
        },
        doc_source="AI-story-forge:docs/api/runninghub/vv_i2v_rh.md",
    ),
    MediaModelSpec(
        id="rh-seedance-2.0-i2v",
        provider="runninghub",
        display_name="seedance2.0/图生视频",
        modality="video",
        task="i2v",
        channel="official",
        endpoint_kind="ai_app",
        endpoint="seedance2.0/图生视频",
        pricing=MediaPricing(unit="per_second", amount=0.6),
        params={
            "prompt": StringParamSpec(),
            "firstFrameUrl": ImageSlotParamSpec(required=True),
            "lastFrameUrl": ImageSlotParamSpec(),
        },
        doc_source="AI-story-forge:docs/api/runninghub/seedance-2.0-guide.md",
    ),
    MediaModelSpec(
        id="rh-seedance-2.0-ref2v",
        provider="runninghub",
        display_name="seedance2.0/多模态视频",
        modality="video",
        task="ref2v",
        channel="official",
        endpoint_kind="ai_app",
        endpoint="seedance2.0/多模态视频",
        pricing=MediaPricing(unit="per_second", amount=0.6),
        params={
            "prompt": StringParamSpec(),
            "images": ImageListParamSpec(max_items=9),
        },
        doc_source="AI-story-forge:docs/api/runninghub/seedance-2.0-guide.md",
    ),
)


def runninghub_catalog() -> tuple[MediaModelSpec, ...]:
    return _CATALOG


def catalog_by_id() -> dict[str, MediaModelSpec]:
    return {spec.id: spec for spec in _CATALOG}


def validate_model_settings(model_id: str, settings: MediaModelSettings) -> None:
    """Reject settings that the model's documented param schema cannot accept.

    This is the single validation exit for per-model defaults: the HTTP
    boundary calls it, so everything behind the boundary may assume settings
    are legal (fail-fast principle).
    """

    spec = catalog_by_id().get(model_id)
    if spec is None:
        raise ValueError(f"unknown media model: {model_id}")

    for name, value in settings.defaults.items():
        param = spec.params.get(name)
        if param is None:
            raise ValueError(f"{model_id}: unknown param {name!r}")
        if isinstance(param, EnumParamSpec):
            if not isinstance(value, str) or value not in param.values:
                raise ValueError(
                    f"{model_id}: param {name!r} must be one of {list(param.values)}, got {value!r}"
                )
        elif isinstance(param, IntRangeParamSpec):
            if not isinstance(value, int) or not (
                param.min_value <= value <= param.max_value
            ):
                raise ValueError(
                    f"{model_id}: param {name!r} must be an int in "
                    f"[{param.min_value}, {param.max_value}], got {value!r}"
                )
        else:
            raise ValueError(
                f"{model_id}: param {name!r} of type {param.type!r} does not take a default"
            )
