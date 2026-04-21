"""understand_video — video analysis via ARK / Gemini."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from pathlib import Path

import httpx

from .providers import (
    call_chain,
    err,
    get_api_key,
    get_proxy,
    ok,
    run_async,
)
from ..config.multimodal_config import ResolvedMultimodalProvider

logger = logging.getLogger(__name__)


async def _vu_ark(
    rp: ResolvedMultimodalProvider,
    video_source: str,
    question: str,
    max_tokens: int,
) -> dict:
    from openai import AsyncOpenAI

    api_key = get_api_key(rp.provider_def)
    proxy = get_proxy(rp.provider_def)
    async with httpx.AsyncClient(
        proxy=proxy,
        trust_env=False,
        timeout=httpx.Timeout(connect=30, read=1800, write=1800, pool=600),
    ) as http_client:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=rp.provider_def.base_url,
            http_client=http_client,
        )

        # Convert to data URI if local file
        if not video_source.startswith(("data:", "http://", "https://")):
            path = Path(video_source)
            if not path.is_file():
                raise RuntimeError(f"Video file not found: {video_source}")
            file_size_mb = path.stat().st_size / (1024 * 1024)
            if file_size_mb > 200:
                raise RuntimeError(
                    f"Video file too large for base64 encoding: {file_size_mb:.0f}MB "
                    f"(max 200MB). Use an HTTP URL instead."
                )
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            video_source = f"data:video/mp4;base64,{data}"

        response = await client.chat.completions.create(
            model=rp.model_name,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "video_url", "video_url": {"url": video_source}},
                    {"type": "text", "text": question},
                ],
            }],
            max_tokens=max_tokens,
        )
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise RuntimeError("No choices in ARK video understanding response")
        return {
            "status": "success",
            "content": choices[0].message.content or "",
            "model": rp.model_def.code,
            "provider": rp.provider_code,
        }


async def _vu_gemini(
    rp: ResolvedMultimodalProvider,
    video_source: str,
    question: str,
    max_tokens: int,
) -> dict:
    try:
        from google import genai  # type: ignore[import-not-found]
        from google.genai import types  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError("Gemini video understanding requires google-genai: pip install google-genai") from exc

    if not video_source.startswith(("http://", "https://")):
        raise RuntimeError(
            "Gemini video understanding requires public HTTPS URL"
        )

    api_key = get_api_key(rp.provider_def)
    proxy = get_proxy(rp.provider_def)
    client_args: dict[str, object] = {"trust_env": False}
    if proxy:
        client_args["proxy"] = proxy
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=rp.provider_def.timeout * 1000,
            client_args=client_args,
        ),
    )
    video_part = types.Part.from_uri(
        file_uri=video_source, mime_type="video/mp4"
    )
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.models.generate_content(
            model=rp.model_name,
            contents=[video_part, question],
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens
            ),
        ),
    )
    return {
        "status": "success",
        "content": response.text or "",
        "model": rp.model_def.code,
        "provider": rp.provider_code,
    }


def understand_video_tool(
    question: str,
    video_source: str,
    role: str = "video_understanding",
    max_tokens: int = 1024,
) -> str:
    """Analyze a video and answer questions about its content.

    Uses multimodal video understanding models to watch a video and respond
    to questions about it, with automatic provider fallback.

    When to use understand_video:
    - Analyzing video content, scenes, actions, or visual elements
    - Extracting information or descriptions from a video
    - Answering specific questions about what happens in a video

    When NOT to use understand_video:
    - For generating new videos (use generate_video)
    - For analyzing still images (use view_image)

    Args:
        question: The question to ask about the video content.
        video_source: Video URL (HTTP/HTTPS) or local file path.
        role: Video understanding role for model and provider selection.
        max_tokens: Maximum tokens in the analysis response.
    """
    if not video_source:
        return err(ValueError("video_source is required"))

    async def _run() -> dict:
        chain = call_chain(role)
        errors: list[str] = []
        for rp in chain:
            start = time.time()
            try:
                ptype = rp.provider_def.type
                if ptype == "ark_openai":
                    result = await _vu_ark(
                        rp, video_source, question, max_tokens
                    )
                elif ptype == "gemini_official":
                    result = await _vu_gemini(
                        rp, video_source, question, max_tokens
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
                    "[%s:%s] VU failed: %s",
                    rp.model_def.code,
                    rp.provider_code,
                    exc,
                )
                errors.append(f"{rp.provider_code}: {exc}")
        raise RuntimeError(
            f"All VU providers failed: {'; '.join(errors)}"
        )

    try:
        return ok(run_async(_run))
    except Exception as exc:
        logger.error("understand_video failed: %s", exc)
        return err(exc)


understand_video_tool.__name__ = "understand_video"
understand_video_tool.__qualname__ = "understand_video"
