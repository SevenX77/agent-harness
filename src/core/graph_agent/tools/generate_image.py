"""generate_image — text-to-image, edit, fuse via Gemini / WaveSpeed / ARK."""

from __future__ import annotations

import asyncio
import base64
import logging
import time

import httpx

from .providers import (
    call_chain,
    err,
    get_api_key,
    get_proxy,
    load_image_bytes_sync,
    ok,
    run_async,
    wavespeed_poll,
    wavespeed_submit,
)
from ..config.multimodal_config import ResolvedMultimodalProvider

logger = logging.getLogger(__name__)


async def _image_gemini(
    rp: ResolvedMultimodalProvider, prompt: str, images: list[str] | None
) -> dict:
    try:
        from google import genai  # type: ignore[import-not-found]
        from google.genai import types  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError("Gemini image generation requires google-genai: pip install google-genai") from exc

    api_key, proxy = get_api_key(rp.provider_def), get_proxy(rp.provider_def)
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
    contents: list[object] = [prompt]
    if images:
        for src in images:
            img_bytes, mime = load_image_bytes_sync(src)
            contents.append(
                types.Part.from_bytes(data=img_bytes, mime_type=mime)
            )

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.models.generate_content(
            model=rp.model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"]
            ),
        ),
    )
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise RuntimeError("No candidates in Gemini response")
    content = getattr(candidates[0], "content", None)
    for part in getattr(content, "parts", None) or []:
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            mime = getattr(inline, "mime_type", "image/png") or "image/png"
            encoded = base64.b64encode(inline.data).decode("ascii")
            return {
                "status": "success",
                "image_url": f"data:{mime};base64,{encoded}",
                "model": rp.model_def.code,
                "provider": rp.provider_code,
            }
    raise RuntimeError("No image data in Gemini response")


async def _image_wavespeed(
    rp: ResolvedMultimodalProvider,
    prompt: str,
    images: list[str] | None,
    size: str,
) -> dict:
    if images:
        edit_path = str(rp.provider_options.get("edit_path", ""))
        if not edit_path:
            raise RuntimeError(
                f"No edit_path for WaveSpeed model {rp.model_def.code}"
            )
        payload: dict[str, object] = {"images": images, "prompt": prompt}
        model_path = edit_path
    else:
        payload = {"prompt": prompt, "size": size}
        model_path = rp.model_name
    tid, _ = await wavespeed_submit(rp.provider_def, model_path, payload)
    url, _ = await wavespeed_poll(rp.provider_def, tid)
    return {
        "status": "success",
        "image_url": url,
        "model": rp.model_def.code,
        "provider": rp.provider_code,
    }


async def _image_ark(
    rp: ResolvedMultimodalProvider,
    prompt: str,
    images: list[str] | None,
) -> dict:
    from openai import AsyncOpenAI

    api_key, proxy = get_api_key(rp.provider_def), get_proxy(rp.provider_def)
    async with httpx.AsyncClient(
        proxy=proxy,
        trust_env=False,
        timeout=httpx.Timeout(connect=30, read=120, write=30, pool=60),
    ) as http_client:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=rp.provider_def.base_url,
            http_client=http_client,
        )
        extra: dict[str, object] = {"watermark": False}
        if images:
            extra["image"] = images[0]
        response = await client.images.generate(
            model=rp.model_name,
            prompt=prompt,
            response_format="url",
            extra_body=extra,
        )  # type: ignore[arg-type]
        data_items = getattr(response, "data", None) or []
        if not data_items:
            raise RuntimeError("No image data in ARK response")
        return {
            "status": "success",
            "image_url": data_items[0].url or "",
            "model": rp.model_def.code,
            "provider": rp.provider_code,
        }


async def _openai_compatible_generate(
    client: object,
    rp: ResolvedMultimodalProvider,
    prompt: str,
    images: list[str] | None,
) -> dict:
    """Shared generation logic for openai_compatible image providers."""
    import tempfile

    messages: list[dict[str, object]] = []
    content_parts: list[dict[str, object]] = [{"type": "text", "text": prompt}]
    if images:
        for src in images:
            img_bytes, mime = load_image_bytes_sync(src)
            b64_str = base64.b64encode(img_bytes).decode("ascii")
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64_str}"},
            })
    messages.append({"role": "user", "content": content_parts})

    response = await client.chat.completions.create(  # type: ignore[union-attr]
        model=rp.model_name,
        messages=messages,  # type: ignore[arg-type]
    )
    choice = response.choices[0] if response.choices else None
    if not choice or not choice.message:
        raise RuntimeError("Empty response from openai_compatible_image provider")

    # Extract base64 image from response content (inline image parts)
    msg_content = choice.message.content or ""
    raw_parts = getattr(choice.message, "parts", None) or []
    for part in raw_parts:
        if hasattr(part, "inline_data") and hasattr(part.inline_data, "data"):
            img_bytes_out = part.inline_data.data
            if isinstance(img_bytes_out, str):
                img_bytes_out = base64.b64decode(img_bytes_out)
            # Write to a temp file. IMPORTANT: the returned path points to an
            # unmanaged temporary file. The host-project caller (e.g., artifact_saver)
            # must delete it after consumption to avoid disk accumulation.
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.write(img_bytes_out)
            tmp.close()
            logger.info(
                "Image written to temp file %s — caller must clean up", tmp.name,
            )
            return {
                "status": "success",
                "image_url": tmp.name,
                "model": rp.model_def.code,
                "provider": rp.provider_code,
            }

    # Fallback: check if content contains a URL or base64 data
    if msg_content.startswith("http"):
        return {
            "status": "success",
            "image_url": msg_content.strip(),
            "model": rp.model_def.code,
            "provider": rp.provider_code,
        }

    raise RuntimeError(
        f"openai_compatible_image provider returned no image data. "
        f"Response content length: {len(msg_content)}"
    )


async def _image_openai_compatible(
    rp: ResolvedMultimodalProvider,
    prompt: str,
    images: list[str] | None,
) -> dict:
    """Generate image via OpenAI-compatible chat/completions API (e.g., OC_GEMINI proxy)."""
    from openai import AsyncOpenAI

    api_key, proxy = get_api_key(rp.provider_def), get_proxy(rp.provider_def)
    if proxy:
        async with httpx.AsyncClient(
            proxy=proxy,
            trust_env=False,
            timeout=httpx.Timeout(connect=30, read=120, write=30, pool=60),
        ) as http_client:
            client = AsyncOpenAI(api_key=api_key, base_url=rp.provider_def.base_url, http_client=http_client)
            return await _openai_compatible_generate(client, rp, prompt, images)
    else:
        client = AsyncOpenAI(api_key=api_key, base_url=rp.provider_def.base_url)
        return await _openai_compatible_generate(client, rp, prompt, images)


def generate_image_tool(
    prompt: str,
    reference_images: list[str] | None = None,
    size: str = "1024x1024",
    role: str = "ref_image_gen",
) -> str:
    """Generate or edit an image using AI image generation models.

    Produces an image from a text description, or edits/fuses existing images
    with automatic provider fallback.

    When to use generate_image:
    - Creating reference images, concept art, or scene illustrations
    - Editing an existing image with text instructions (provide reference_images)
    - Compositing multiple image elements (provide reference_images, set role to image_fuse)

    When NOT to use generate_image:
    - For video generation (use generate_video)
    - For understanding existing image content (use view_image)

    Args:
        prompt: Detailed image description in English. Include composition,
            style, lighting, and subject details for best results.
        reference_images: List of image URLs or local file paths to use as
            input for editing or fusion. Leave empty for text-to-image.
        size: Output image dimensions like 1024x1024 or 2048x2048.
        role: Provider selection role. ref_image_gen for text-to-image,
            image_edit for editing, image_fuse for compositing.
    """

    async def _run() -> dict:
        chain = call_chain(role)
        errors: list[str] = []
        for rp in chain:
            start = time.time()
            try:
                ptype = rp.provider_def.type
                if ptype == "gemini_official":
                    result = await _image_gemini(rp, prompt, reference_images)
                elif ptype == "wavespeed":
                    result = await _image_wavespeed(
                        rp, prompt, reference_images, size
                    )
                elif ptype == "ark_openai":
                    result = await _image_ark(rp, prompt, reference_images)
                elif ptype == "openai_compatible_image":
                    result = await _image_openai_compatible(
                        rp, prompt, reference_images
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
                    "[%s:%s] image gen failed: %s",
                    rp.model_def.code,
                    rp.provider_code,
                    exc,
                )
                errors.append(f"{rp.provider_code}: {exc}")
        raise RuntimeError(
            f"All image providers failed: {'; '.join(errors)}"
        )

    try:
        return ok(run_async(_run))
    except Exception as exc:
        logger.error("generate_image failed: %s", exc)
        return err(exc)


generate_image_tool.__name__ = "generate_image"
generate_image_tool.__qualname__ = "generate_image"
