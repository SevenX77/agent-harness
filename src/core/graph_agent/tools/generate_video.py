"""generate_video — smart mode inference, full Seedance 1.5 Pro support."""

from __future__ import annotations

import logging
import time

from .providers import (
    ark_video_submit_and_poll,
    call_chain,
    err,
    ok,
    run_async,
    wavespeed_poll,
    wavespeed_submit,
)
from ..config.multimodal_config import ResolvedMultimodalProvider

logger = logging.getLogger(__name__)


async def _video_ark(
    rp: ResolvedMultimodalProvider,
    prompt: str,
    first_frame_url: str | None,
    last_frame_url: str | None,
    reference_images: list[str] | None,
    duration: int,
    resolution: str,
    aspect_ratio: str,
    generate_audio: bool,
    camera_fixed: bool,
    return_last_frame: bool,
    draft: bool,
    service_tier: str,
    seed: int,
) -> dict:
    """Call ARK Seedance API with full mode support."""
    content: list[dict[str, object]] = [{"type": "text", "text": prompt}]

    if reference_images:
        for ref_url in reference_images[:4]:
            content.append({
                "type": "image_url",
                "image_url": {"url": ref_url},
                "role": "reference_image",
            })
    else:
        if first_frame_url:
            content.append({
                "type": "image_url",
                "image_url": {"url": first_frame_url},
            })
        if last_frame_url:
            content.append({
                "type": "image_url",
                "image_url": {"url": last_frame_url},
                "role": "last_frame",
            })

    payload: dict[str, object] = {
        "model": rp.model_name,
        "content": content,
        "ratio": aspect_ratio,
        "duration": duration,
        "resolution": resolution,
        "generate_audio": generate_audio,
        "camera_fixed": camera_fixed,
        "watermark": False,
    }
    if return_last_frame:
        payload["return_last_frame"] = True
    if draft:
        payload["draft"] = True
    if service_tier != "default":
        payload["service_tier"] = service_tier
    if seed != -1:
        payload["seed"] = seed

    video_url, poll_count, last_frame = await ark_video_submit_and_poll(
        rp.provider_def, payload
    )
    result: dict[str, object] = {
        "status": "success",
        "video_url": video_url,
        "model": rp.model_def.code,
        "provider": rp.provider_code,
        "poll_count": poll_count,
    }
    if last_frame:
        result["last_frame_url"] = last_frame
    return result


async def _video_wavespeed(
    rp: ResolvedMultimodalProvider,
    prompt: str,
    first_frame_url: str | None,
    reference_images: list[str] | None,
    duration: int,
    resolution: str,
    aspect_ratio: str,
    generate_audio: bool,
    seed: int,
) -> dict:
    """Call WaveSpeed video API."""
    model_code = rp.model_def.code
    if model_code == "VEO31_REF2V":
        if not reference_images:
            raise RuntimeError("Veo 3.1 Ref2V requires images parameter")
        payload: dict[str, object] = {
            "images": reference_images,
            "prompt": prompt,
            "resolution": resolution,
            "generate_audio": generate_audio,
            "seed": seed,
        }
    else:
        if not first_frame_url:
            raise RuntimeError(
                f"{model_code} I2V requires first_frame image"
            )
        if model_code == "VEO31_I2V" and duration not in (4, 6, 8):
            raise RuntimeError(
                f"Veo 3.1 I2V duration must be 4/6/8, got {duration}"
            )
        payload = {
            "image": first_frame_url,
            "prompt": prompt,
            "duration": duration,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "generate_audio": generate_audio,
            "seed": seed,
        }
    tid, _ = await wavespeed_submit(rp.provider_def, rp.model_name, payload)
    url, pc = await wavespeed_poll(rp.provider_def, tid)
    return {
        "status": "success",
        "video_url": url,
        "model": rp.model_def.code,
        "provider": rp.provider_code,
        "poll_count": pc,
    }


def generate_video_tool(
    prompt: str,
    first_frame_image: str = "",
    last_frame_image: str = "",
    reference_images: list[str] | None = None,
    duration: int = 5,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
    generate_audio: bool = False,
    camera_fixed: bool = False,
    return_last_frame: bool = False,
    draft: bool = False,
    service_tier: str = "default",
    role: str = "video_gen",
) -> str:
    """Generate a video with smart mode inference based on provided inputs.

    Automatically selects the generation mode based on which image parameters
    are provided. Supports text-to-video, first-frame I2V, first-plus-last-frame
    transition, and reference-image character consistency.

    Mode inference rules:
    - reference_images provided: reference image mode (1-4 images, use bracket
      notation like [img1] [img2] in prompt to refer to each image)
    - first_frame_image and last_frame_image: first-plus-last-frame transition
    - first_frame_image only: image-to-video first-frame mode
    - none of the above: text-to-video mode

    When to use generate_video:
    - Creating short video clips from text descriptions
    - Animating a still image into video (provide first_frame_image)
    - Creating smooth transitions between two frames
    - Generating character-consistent video from reference images

    When NOT to use generate_video:
    - For analyzing existing video content (use understand_video)
    - For generating still images (use generate_image)

    Args:
        prompt: Video description. Include action, camera movement, mood, and
            visual style. For reference mode use [img1] [img2] etc.
        first_frame_image: URL or local file path for the first-frame image.
            Empty for text-to-video mode.
        last_frame_image: URL or local file path for the last-frame image.
            Requires first_frame_image to be set.
        reference_images: List of 1-4 reference image URLs or paths for
            character consistency mode.
        duration: Video duration in seconds (4 to 12).
        resolution: 480p, 720p, or 1080p.
        aspect_ratio: 16:9, 9:16, 4:3, 1:1, 3:4, 21:9, or adaptive.
        generate_audio: Generate audio along with the video.
        camera_fixed: Lock the camera in place during generation.
        return_last_frame: Return the last frame URL for chaining consecutive
            videos. The last_frame_url will be included in the result JSON.
        draft: Generate a low-cost preview draft video first.
        service_tier: default for online inference, flex for offline at
            half price.
        role: Video generation role for model and provider selection.
    """
    first_frame = first_frame_image or None
    last_frame = last_frame_image or None

    if last_frame and not first_frame:
        return err(ValueError("last_frame_image requires first_frame_image"))

    async def _run() -> dict:
        chain = call_chain(role)
        errors: list[str] = []
        for rp in chain:
            start = time.time()
            try:
                ptype = rp.provider_def.type
                if ptype == "ark_openai":
                    result = await _video_ark(
                        rp, prompt, first_frame, last_frame, reference_images,
                        duration, resolution, aspect_ratio,
                        generate_audio, camera_fixed, return_last_frame,
                        draft, service_tier, -1,
                    )
                elif ptype == "wavespeed":
                    result = await _video_wavespeed(
                        rp, prompt, first_frame, reference_images,
                        duration, resolution, aspect_ratio,
                        generate_audio, -1,
                    )
                else:
                    errors.append(
                        f"{rp.provider_code}: unsupported type {ptype}"
                    )
                    continue
                result["elapsed_ms"] = int((time.time() - start) * 1000)
                return result
            except Exception as exc:
                logger.warning(
                    "[%s:%s] video gen failed: %s",
                    rp.model_def.code,
                    rp.provider_code,
                    exc,
                )
                errors.append(f"{rp.provider_code}: {exc}")
        raise RuntimeError(
            f"All video providers failed: {'; '.join(errors)}"
        )

    try:
        return ok(run_async(_run))
    except Exception as exc:
        logger.error("generate_video failed: %s", exc)
        return err(exc)


generate_video_tool.__name__ = "generate_video"
generate_video_tool.__qualname__ = "generate_video"
