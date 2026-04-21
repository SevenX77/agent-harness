"""
Multimodal Client Manager - 多模态客户端管理器

管理三类多模态内容生成服务（全部基于实测验证）：
  - 视频理解：Volcengine Seed 1.8 / Seed 2.0 Pro / Google Gemini 3.1 Pro Preview
  - 图片生成：Volcengine Seedream 4.5 / Seedream 5.0-lite
  - 图片编辑：WaveSpeed Nano Banana Pro Edit Ultra
  - 视频生成：WaveSpeed Seedance V1.5 / Veo 3.1 I2V / Veo 3.1 Ref2V
             + 火山方舟 Seedance 1.5-pro（ARK 直连，非 WaveSpeed）

设计原则：
  - 所有 API Key 从 Config 读取，不硬编码
  - WaveSpeed 异步任务使用统一的提交+轮询模式
  - ARK 视频生成使用独立的 _ark_submit / _ark_poll（响应格式不同于 WaveSpeed）
  - Seed 1.8 / 2.0 视频须 base64 传入（Volcengine 服务器无法访问境外 URL）
  - 所有异步方法可直接 await，内部处理轮询
"""

import asyncio
import base64
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

import httpx

from src.core.config import config
from src.core.exceptions import (
    ConfigurationError,
    ImageGenerationError,
    TaskTimeoutError,
    UnsupportedVideoSourceError,
    VideoGenerationError,
    VideoUnderstandingError,
)
from src.core.multimodal_call_logger import call_logger, new_call_id

logger = logging.getLogger(__name__)


# ── 枚举 ──────────────────────────────────────────────────────────────────────


class VideoUnderstandingService(Enum):
    SEED18 = "seed18"
    SEED20_PRO = "seed20_pro"
    GEMINI_31_PRO = "gemini_31_pro"


class ImageService(Enum):
    SEEDREAM_45 = "seedream_45"
    SEEDREAM_50_LITE = "seedream_50_lite"
    NANO_BANANA_EDIT = "nano_banana_edit"


class VideoService(Enum):
    SEEDANCE_V15_I2V = "seedance_v15_i2v"
    SEEDANCE_V15_ARK = "seedance_v15_ark"
    VEO31_I2V = "veo31_i2v"
    VEO31_REF2V = "veo31_ref2v"


class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


# ── 结果数据类 ─────────────────────────────────────────────────────────────────


@dataclass
class VideoUnderstandingResult:
    status: str
    content: str
    service: str
    elapsed_ms: int
    model: str = ""


@dataclass
class ImageResult:
    status: str
    image_url: str
    service: str
    elapsed_ms: int
    model: str = ""
    # 日志用内部字段（WaveSpeed 异步任务分段耗时，直接 API 调用时为 None）
    _submit_ms: Optional[int] = None
    _poll_count: Optional[int] = None


@dataclass
class VideoResult:
    status: str
    video_url: str
    service: str
    elapsed_ms: int
    model: str = ""
    # 日志用内部字段（WaveSpeed 异步任务分段耗时）
    _submit_ms: Optional[int] = None
    _poll_count: Optional[int] = None


@dataclass
class UsageStat:
    total_calls: int = 0
    successful: int = 0
    failed: int = 0
    total_elapsed_ms: int = 0

    @property
    def avg_elapsed_ms(self) -> float:
        return self.total_elapsed_ms / self.successful if self.successful else 0.0


# ── Manager ───────────────────────────────────────────────────────────────────


class MultimodalClientManager:
    """
    多模态客户端管理器（单例式，所有方法为 classmethod）。

    使用方式：
        result = await MultimodalClientManager.understand_video(
            service=VideoUnderstandingService.SEED18,
            video_source="/path/to/video.mp4",
            question="描述视频内容"
        )
    """

    _usage: dict[str, UsageStat] = {}

    # ── 视频理解 ──────────────────────────────────────────────────────────────

    @classmethod
    async def understand_video(
        cls,
        service: VideoUnderstandingService,
        video_source: str,
        question: str,
        max_tokens: int = 1024,
        task_id: str = "unknown",
    ) -> VideoUnderstandingResult:
        """
        理解视频内容，返回结构化描述。

        Args:
            service: 使用哪个视频理解服务
            video_source: 本地文件路径 或 公开视频 URL
            question: 提问内容
            max_tokens: 最大回复 token 数
            task_id: 业务任务 ID（供日志追踪使用）
        """
        call_id = new_call_id()
        start = time.time()
        ark_services = {VideoUnderstandingService.SEED18, VideoUnderstandingService.SEED20_PRO}
        provider = "volcengine" if service in ark_services else "google_official"
        request_data = {"video_source": video_source, "question": question, "max_tokens": max_tokens}

        try:
            if service == VideoUnderstandingService.SEED18:
                result = await cls._understand_seed18(video_source, question, max_tokens)
            elif service == VideoUnderstandingService.SEED20_PRO:
                result = await cls._understand_seed20_pro(video_source, question, max_tokens)
            elif service == VideoUnderstandingService.GEMINI_31_PRO:
                result = await cls._understand_gemini(video_source, question, max_tokens)
            else:
                raise VideoUnderstandingError(f"不支持的视频理解服务：{service}")

            elapsed_ms = int((time.time() - start) * 1000)
            result.elapsed_ms = elapsed_ms
            cls._record(service.value, success=True, elapsed_ms=elapsed_ms)
            logger.info("[%s] 视频理解完成，耗时 %dms", service.value, elapsed_ms)

            call_logger.log_call(
                call_id=call_id, task_id=task_id,
                task_type="video_understanding",
                model=service.value, provider=provider,
                request=request_data,
                response={"output_text": result.content},
                execution={"total_ms": elapsed_ms, "submit_ms": None, "poll_count": None, "retry_count": 0},
            )
            return result

        except (VideoUnderstandingError, UnsupportedVideoSourceError) as e:
            elapsed_ms = int((time.time() - start) * 1000)
            cls._record(service.value, success=False, elapsed_ms=0)
            call_logger.log_error(
                call_id=call_id, task_id=task_id,
                task_type="video_understanding",
                model=service.value, provider=provider,
                request=request_data, error=e,
                stage="processing",
                execution={"total_ms": elapsed_ms, "submit_ms": None, "poll_count": None, "retry_count": 0},
            )
            raise
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            cls._record(service.value, success=False, elapsed_ms=0)
            wrapped = VideoUnderstandingError(f"视频理解失败 [{service.value}]", original_error=e)
            call_logger.log_error(
                call_id=call_id, task_id=task_id,
                task_type="video_understanding",
                model=service.value, provider=provider,
                request=request_data, error=wrapped,
                stage="processing",
                execution={"total_ms": elapsed_ms, "submit_ms": None, "poll_count": None, "retry_count": 0},
            )
            raise wrapped from e

    @classmethod
    async def _understand_seed18(
        cls, video_source: str, question: str, max_tokens: int
    ) -> VideoUnderstandingResult:
        """Volcengine Seed 1.8 视频理解（OpenAI SDK，视频 base64 传入）"""
        cfg = config.multimodal
        if not cfg.ark_api_key:
            raise ConfigurationError("ARK_API_KEY 未配置", config_key="ARK_API_KEY")

        import httpx
        from openai import AsyncOpenAI

        # ARK 为国内服务器，显式绕过系统代理，并设置足够长的超时
        _http_client = httpx.AsyncClient(
            trust_env=False,
            timeout=httpx.Timeout(connect=30.0, read=1800.0, write=1800.0, pool=600.0),
        )
        client = AsyncOpenAI(
            api_key=cfg.ark_api_key,
            base_url=cfg.ark_base_url,
            http_client=_http_client,
        )

        data_url = await cls._get_video_base64_url(video_source)
        logger.debug("[seed18] base64 编码完成，发起请求...")

        response = await client.chat.completions.create(
            model=cfg.seed18_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "video_url",
                            "video_url": {"url": data_url},
                        },
                        {"type": "text", "text": question},
                    ],
                }
            ],
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content or ""
        return VideoUnderstandingResult(
            status="success",
            content=content,
            service=VideoUnderstandingService.SEED18.value,
            elapsed_ms=0,
            model=cfg.seed18_model,
        )

    @classmethod
    async def _understand_seed20_pro(
        cls, video_source: str, question: str, max_tokens: int
    ) -> VideoUnderstandingResult:
        """Volcengine Seed 2.0 Pro 视频理解（OpenAI SDK，视频 base64 传入，接口与 Seed 1.8 相同）"""
        cfg = config.multimodal
        if not cfg.ark_api_key:
            raise ConfigurationError("ARK_API_KEY 未配置", config_key="ARK_API_KEY")

        import httpx
        from openai import AsyncOpenAI

        # ARK 为国内服务器，显式绕过系统代理，并设置足够长的超时
        _http_client = httpx.AsyncClient(
            trust_env=False,
            timeout=httpx.Timeout(connect=30.0, read=1800.0, write=1800.0, pool=600.0),
        )
        client = AsyncOpenAI(
            api_key=cfg.ark_api_key,
            base_url=cfg.ark_base_url,
            http_client=_http_client,
        )

        data_url = await cls._get_video_base64_url(video_source)
        logger.debug("[seed20_pro] base64 编码完成，发起请求...")

        response = await client.chat.completions.create(
            model=cfg.seed20_pro_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "video_url",
                            "video_url": {"url": data_url},
                        },
                        {"type": "text", "text": question},
                    ],
                }
            ],
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content or ""
        return VideoUnderstandingResult(
            status="success",
            content=content,
            service=VideoUnderstandingService.SEED20_PRO.value,
            elapsed_ms=0,
            model=cfg.seed20_pro_model,
        )

    @classmethod
    async def _understand_gemini(
        cls, video_source: str, question: str, max_tokens: int
    ) -> VideoUnderstandingResult:
        """Google Gemini 3.1 Pro Preview 视频理解（google.genai SDK，直接传 URL）"""
        cfg = config.multimodal
        if not cfg.gemini_api_key:
            raise ConfigurationError("GEMINI_API_KEY 未配置", config_key="GEMINI_API_KEY")

        from google import genai
        from google.genai import types

        http_opts_kwargs: dict = {"timeout": 120_000}
        client_args: dict = {"trust_env": False}
        gemini_proxy = os.getenv("GEMINI_PROXY")
        if gemini_proxy:
            client_args["proxy"] = gemini_proxy
        http_opts_kwargs["client_args"] = client_args

        client = genai.Client(
            api_key=cfg.gemini_api_key,
            http_options=types.HttpOptions(**http_opts_kwargs),
        )

        if video_source.startswith("http://") or video_source.startswith("https://"):
            video_part = types.Part.from_uri(
                file_uri=video_source, mime_type="video/mp4"
            )
        else:
            raise UnsupportedVideoSourceError(
                "Gemini 当前只支持公开 URL，不支持本地文件（需先上传至 File API）",
                details={"source": video_source},
            )

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=cfg.gemini_31_pro_model,
                contents=[video_part, question],
                config=types.GenerateContentConfig(max_output_tokens=max_tokens),
            ),
        )

        content = response.text or ""
        return VideoUnderstandingResult(
            status="success",
            content=content,
            service=VideoUnderstandingService.GEMINI_31_PRO.value,
            elapsed_ms=0,
            model=cfg.gemini_31_pro_model,
        )

    # ── 图片生成 ──────────────────────────────────────────────────────────────

    @classmethod
    async def generate_image(
        cls,
        service: ImageService,
        prompt: str,
        size: str = "2048x2048",
        task_id: str = "unknown",
        **kwargs,
    ) -> ImageResult:
        """
        文生图。

        Args:
            service: 使用哪个图片生成服务（目前仅 SEEDREAM_45 支持文生图）
            prompt: 图片描述
            size: 尺寸（如 "1024x1024"，Seedream 最大 "2048x2048"）
            task_id: 业务任务 ID（供日志追踪使用）
        """
        call_id = new_call_id()
        start = time.time()
        request_data = {"prompt": prompt, "size": size}

        try:
            if service == ImageService.SEEDREAM_45:
                result = await cls._generate_image_seedream(prompt, size, **kwargs)
            elif service == ImageService.SEEDREAM_50_LITE:
                result = await cls._generate_image_seedream50_lite(prompt, size, **kwargs)
            else:
                raise ImageGenerationError(
                    f"服务 {service} 不支持文生图，请使用 edit_image()"
                )

            elapsed_ms = int((time.time() - start) * 1000)
            result.elapsed_ms = elapsed_ms
            cls._record(service.value, success=True, elapsed_ms=elapsed_ms)
            logger.info("[%s] 图片生成完成，耗时 %dms", service.value, elapsed_ms)

            call_logger.log_call(
                call_id=call_id, task_id=task_id,
                task_type="image_generation",
                model=service.value, provider="volcengine",
                request=request_data,
                response={"output_url": result.image_url},
                execution={"total_ms": elapsed_ms, "submit_ms": None, "poll_count": None, "retry_count": 0},
            )
            return result

        except ImageGenerationError as e:
            elapsed_ms = int((time.time() - start) * 1000)
            cls._record(service.value, success=False, elapsed_ms=0)
            call_logger.log_error(
                call_id=call_id, task_id=task_id,
                task_type="image_generation",
                model=service.value, provider="volcengine",
                request=request_data, error=e,
                stage="processing",
                execution={"total_ms": elapsed_ms, "submit_ms": None, "poll_count": None, "retry_count": 0},
            )
            raise
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            cls._record(service.value, success=False, elapsed_ms=0)
            wrapped = ImageGenerationError(f"图片生成失败 [{service.value}]", original_error=e)
            call_logger.log_error(
                call_id=call_id, task_id=task_id,
                task_type="image_generation",
                model=service.value, provider="volcengine",
                request=request_data, error=wrapped,
                stage="processing",
                execution={"total_ms": elapsed_ms, "submit_ms": None, "poll_count": None, "retry_count": 0},
            )
            raise wrapped from e

    @classmethod
    async def edit_image(
        cls,
        service: ImageService,
        image_url: str,
        prompt: str,
        resolution: str = "4k",
        output_format: str = "png",
        task_id: str = "unknown",
        **kwargs,
    ) -> ImageResult:
        """
        图片编辑。

        Args:
            service: 使用哪个图片编辑服务（目前仅 NANO_BANANA_EDIT）
            image_url: 原始图片公开 URL（需确保 MIME 为 image/jpeg 或 image/png）
            prompt: 编辑指令
            resolution: 输出分辨率（"4k" / "2k"）
            output_format: 输出格式（"png" / "jpeg"）
            task_id: 业务任务 ID（供日志追踪使用）
        """
        call_id = new_call_id()
        start = time.time()
        request_data = {"image_url": image_url, "prompt": prompt, "resolution": resolution}

        try:
            if service == ImageService.NANO_BANANA_EDIT:
                result = await cls._edit_image_nano_banana(
                    image_url, prompt, resolution, output_format
                )
            else:
                raise ImageGenerationError(f"不支持的图片编辑服务：{service}")

            elapsed_ms = int((time.time() - start) * 1000)
            result.elapsed_ms = elapsed_ms
            cls._record(service.value, success=True, elapsed_ms=elapsed_ms)
            logger.info("[%s] 图片编辑完成，耗时 %dms", service.value, elapsed_ms)

            call_logger.log_call(
                call_id=call_id, task_id=task_id,
                task_type="image_editing",
                model=service.value, provider="wavespeed",
                request=request_data,
                response={"output_url": result.image_url},
                execution={"total_ms": elapsed_ms, "submit_ms": result._submit_ms, "poll_count": result._poll_count, "retry_count": 0},
            )
            return result

        except ImageGenerationError as e:
            elapsed_ms = int((time.time() - start) * 1000)
            cls._record(service.value, success=False, elapsed_ms=0)
            call_logger.log_error(
                call_id=call_id, task_id=task_id,
                task_type="image_editing",
                model=service.value, provider="wavespeed",
                request=request_data, error=e,
                stage="processing",
                execution={"total_ms": elapsed_ms, "submit_ms": None, "poll_count": None, "retry_count": 0},
            )
            raise
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            cls._record(service.value, success=False, elapsed_ms=0)
            wrapped = ImageGenerationError(f"图片编辑失败 [{service.value}]", original_error=e)
            call_logger.log_error(
                call_id=call_id, task_id=task_id,
                task_type="image_editing",
                model=service.value, provider="wavespeed",
                request=request_data, error=wrapped,
                stage="processing",
                execution={"total_ms": elapsed_ms, "submit_ms": None, "poll_count": None, "retry_count": 0},
            )
            raise wrapped from e

    @classmethod
    async def _generate_image_seedream(
        cls, prompt: str, size: str, **kwargs
    ) -> ImageResult:
        """
        Volcengine Seedream 4.5 文生图（OpenAI SDK images.generate）

        注意：Volcengine 的图片生成走 OpenAI SDK 而非标准 POST，
        需传 response_format="url" 以确保返回 URL 而非 base64。
        """
        cfg = config.multimodal
        if not cfg.ark_api_key:
            raise ConfigurationError("ARK_API_KEY 未配置", config_key="ARK_API_KEY")

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=cfg.ark_api_key, base_url=cfg.ark_base_url)

        response = await client.images.generate(
            model=cfg.seedream45_model,
            prompt=prompt,
            size=size,
            response_format="url",
            extra_body={"watermark": False},
            **kwargs,
        )

        image_url = response.data[0].url
        return ImageResult(
            status="success",
            image_url=image_url,
            service=ImageService.SEEDREAM_45.value,
            elapsed_ms=0,
            model=cfg.seedream45_model,
        )

    @classmethod
    async def _generate_image_seedream50_lite(
        cls, prompt: str, size: str, **kwargs
    ) -> ImageResult:
        """
        Volcengine Seedream 5.0-lite 文生图（OpenAI SDK images.generate）

        相比 Seedream 4.5：
        - size 支持 "2K" / "4K" 字符串简写（也接受 "2048x2048" 等像素值）
        - 支持图生图（image 参数）及网页搜索增强
        """
        cfg = config.multimodal
        if not cfg.ark_api_key:
            raise ConfigurationError("ARK_API_KEY 未配置", config_key="ARK_API_KEY")

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=cfg.ark_api_key, base_url=cfg.ark_base_url)

        response = await client.images.generate(
            model=cfg.seedream50_lite_model,
            prompt=prompt,
            size=size,
            response_format="url",
            extra_body={"watermark": False},
            **kwargs,
        )

        image_url = response.data[0].url
        return ImageResult(
            status="success",
            image_url=image_url,
            service=ImageService.SEEDREAM_50_LITE.value,
            elapsed_ms=0,
            model=cfg.seedream50_lite_model,
        )

    @classmethod
    async def _edit_image_nano_banana(
        cls,
        image_url: str,
        prompt: str,
        resolution: str,
        output_format: str,
    ) -> ImageResult:
        """
        WaveSpeed Nano Banana Pro Edit Ultra 图片编辑（异步提交+轮询）

        注意：API 字段是 "images"（数组），不是 "image"（字符串）。
        """
        cfg = config.multimodal
        payload = {
            "images": [image_url],
            "prompt": prompt,
            "resolution": resolution,
            "output_format": output_format,
        }
        wavespeed_task_id, submit_ms = await cls._wavespeed_submit(cfg.nano_banana_edit_path, payload)
        result_url, poll_count = await cls._wavespeed_poll(wavespeed_task_id)
        return ImageResult(
            status="success",
            image_url=result_url,
            service=ImageService.NANO_BANANA_EDIT.value,
            elapsed_ms=0,
            model=cfg.nano_banana_edit_path,
            _submit_ms=submit_ms,
            _poll_count=poll_count,
        )

    # ── 视频生成 ──────────────────────────────────────────────────────────────

    @classmethod
    async def generate_video(
        cls,
        service: VideoService,
        prompt: str,
        image_url: Optional[str] = None,
        images: Optional[list[str]] = None,
        duration: int = 5,
        resolution: str = "1080p",
        aspect_ratio: str = "16:9",
        generate_audio: bool = False,
        seed: int = -1,
        task_id: str = "unknown",
        **kwargs,
    ) -> VideoResult:
        """
        视频生成。

        WaveSpeed 服务：SEEDANCE_V15_I2V / VEO31_I2V / VEO31_REF2V
        ARK 直连服务：SEEDANCE_V15_ARK（最高 720p，不支持 1080p）

        Args:
            service: 选择视频生成模型
            prompt: 视频描述
            image_url: 参考图 URL（I2V 模式必须提供）
            images: 参考图 URL 列表（Ref2V 模式使用，仅 WaveSpeed）
            duration: 视频时长（秒）
            resolution: 分辨率（"1080p" / "720p"；ARK 模式若传 "1080p" 自动降级）
            aspect_ratio: 宽高比（"16:9" / "9:16"）
            generate_audio: 是否生成音效（Veo 3.1 / Seedance 1.5-pro ARK 支持）
            seed: 随机种子，-1 为随机
            task_id: 业务任务 ID（供日志追踪使用）
        """
        call_id = new_call_id()
        start = time.time()
        request_data = {
            "prompt": prompt,
            "image_url": image_url,
            "images": images,
            "duration": duration,
            "resolution": resolution,
            "generate_audio": generate_audio,
        }

        try:
            if service == VideoService.SEEDANCE_V15_ARK:
                result = await cls._generate_video_ark(
                    prompt=prompt,
                    image_url=image_url,
                    duration=duration,
                    resolution=resolution,
                    aspect_ratio=aspect_ratio,
                    generate_audio=generate_audio,
                    seed=seed,
                    **kwargs,
                )
            else:
                result = await cls._generate_video_wavespeed(
                    service=service,
                    prompt=prompt,
                    image_url=image_url,
                    images=images,
                    duration=duration,
                    resolution=resolution,
                    aspect_ratio=aspect_ratio,
                    generate_audio=generate_audio,
                    seed=seed,
                    **kwargs,
                )
            elapsed_ms = int((time.time() - start) * 1000)
            result.elapsed_ms = elapsed_ms
            cls._record(service.value, success=True, elapsed_ms=elapsed_ms)
            logger.info("[%s] 视频生成完成，耗时 %dms", service.value, elapsed_ms)
            _provider = "volcengine" if service == VideoService.SEEDANCE_V15_ARK else "wavespeed"

            call_logger.log_call(
                call_id=call_id, task_id=task_id,
                task_type="video_generation",
                model=service.value, provider=_provider,
                request=request_data,
                response={"output_url": result.video_url, "video_duration_s": duration},
                execution={
                    "total_ms": elapsed_ms,
                    "submit_ms": result._submit_ms,
                    "poll_count": result._poll_count,
                    "retry_count": 0,
                },
            )
            return result

        except (VideoGenerationError, TaskTimeoutError) as e:
            elapsed_ms = int((time.time() - start) * 1000)
            cls._record(service.value, success=False, elapsed_ms=0)
            _provider = "volcengine" if service == VideoService.SEEDANCE_V15_ARK else "wavespeed"
            stage = "polling" if isinstance(e, TaskTimeoutError) else "submit"
            call_logger.log_error(
                call_id=call_id, task_id=task_id,
                task_type="video_generation",
                model=service.value, provider=_provider,
                request=request_data, error=e,
                stage=stage,
                execution={"total_ms": elapsed_ms, "submit_ms": None, "poll_count": None, "retry_count": 0},
            )
            raise
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            cls._record(service.value, success=False, elapsed_ms=0)
            _provider = "volcengine" if service == VideoService.SEEDANCE_V15_ARK else "wavespeed"
            wrapped = VideoGenerationError(f"视频生成失败 [{service.value}]", original_error=e)
            call_logger.log_error(
                call_id=call_id, task_id=task_id,
                task_type="video_generation",
                model=service.value, provider=_provider,
                request=request_data, error=wrapped,
                stage="processing",
                execution={"total_ms": elapsed_ms, "submit_ms": None, "poll_count": None, "retry_count": 0},
            )
            raise wrapped from e

    @classmethod
    async def _generate_video_wavespeed(
        cls,
        service: VideoService,
        prompt: str,
        image_url: Optional[str],
        images: Optional[list[str]],
        duration: int,
        resolution: str,
        aspect_ratio: str,
        generate_audio: bool,
        seed: int,
        **kwargs,
    ) -> VideoResult:
        cfg = config.multimodal

        model_map = {
            VideoService.SEEDANCE_V15_I2V: cfg.seedance_v15_i2v_path,
            VideoService.VEO31_I2V: cfg.veo31_i2v_path,
            VideoService.VEO31_REF2V: cfg.veo31_ref2v_path,
        }
        model_path = model_map[service]

        if service == VideoService.VEO31_REF2V:
            if not images:
                raise VideoGenerationError(
                    "Veo 3.1 Reference-to-Video 需要提供 images 参数（参考图列表）"
                )
            payload = {
                "images": images,
                "prompt": prompt,
                "resolution": resolution,
                "generate_audio": generate_audio,
                "seed": seed,
                **kwargs,
            }
        else:
            if not image_url:
                raise VideoGenerationError(
                    f"{service.value} 为图生视频模式，需要提供 image_url 参数"
                )
            # Veo 3.1 I2V 仅支持 duration ∈ {4, 6, 8}
            if service == VideoService.VEO31_I2V and duration not in (4, 6, 8):
                raise VideoGenerationError(
                    f"Veo 3.1 Image-to-Video 的 duration 只支持 4/6/8 秒，传入了 {duration}"
                )
            payload = {
                "image": image_url,
                "prompt": prompt,
                "duration": duration,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "generate_audio": generate_audio,
                "seed": seed,
                **kwargs,
            }

        wavespeed_task_id, submit_ms = await cls._wavespeed_submit(model_path, payload)
        result_url, poll_count = await cls._wavespeed_poll(wavespeed_task_id)

        return VideoResult(
            status="success",
            video_url=result_url,
            service=service.value,
            elapsed_ms=0,
            model=model_path,
            _submit_ms=submit_ms,
            _poll_count=poll_count,
        )

    # ── ARK 视频生成（Seedance 1.5-pro 直连） ────────────────────────────────

    @classmethod
    async def _generate_video_ark(
        cls,
        prompt: str,
        image_url: Optional[str],
        duration: int,
        resolution: str,
        aspect_ratio: str,
        generate_audio: bool,
        seed: int,
        **kwargs,
    ) -> VideoResult:
        """
        火山方舟 Seedance 1.5-pro 视频生成（ARK /contents/generations/tasks 接口）

        注意：
        - Seedance 1.5-pro 在 ARK 上最高只支持 720p（不支持 1080p）
        - 宽高比参数名为 ratio（非 aspect_ratio），值与 WaveSpeed 相同
        - 轮询终态为 "succeeded"，视频 URL 在 content.video_url
        """
        cfg = config.multimodal
        if not cfg.ark_api_key:
            raise ConfigurationError("ARK_API_KEY 未配置", config_key="ARK_API_KEY")

        # Seedance 1.5-pro 不支持 1080p，静默降级到 720p
        if resolution == "1080p":
            logger.warning("[seedance_v15_ark] 不支持 1080p，自动降级为 720p")
            resolution = "720p"

        content: list[dict] = [{"type": "text", "text": prompt}]
        if image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})

        payload: dict = {
            "model": cfg.seedance_v15_ark_model,
            "content": content,
            "ratio": aspect_ratio,
            "duration": duration,
            "resolution": resolution,
            "generate_audio": generate_audio,
            "watermark": False,
        }
        if seed != -1:
            payload["seed"] = seed

        submit_url = f"{cfg.ark_base_url}/contents/generations/tasks"
        ark_task_id, submit_ms = await cls._ark_submit(submit_url, payload)
        result_url, poll_count = await cls._ark_poll(ark_task_id)

        return VideoResult(
            status="success",
            video_url=result_url,
            service=VideoService.SEEDANCE_V15_ARK.value,
            elapsed_ms=0,
            model=cfg.seedance_v15_ark_model,
            _submit_ms=submit_ms,
            _poll_count=poll_count,
        )

    @classmethod
    async def _ark_submit(cls, submit_url: str, payload: dict) -> Tuple[str, int]:
        """
        提交 ARK 异步视频生成任务，返回 (task_id, submit_ms)。
        """
        cfg = config.multimodal
        headers = {
            "Authorization": f"Bearer {cfg.ark_api_key}",
            "Content-Type": "application/json",
        }

        submit_start = time.time()
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                response = await client.post(submit_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                task_id = data["id"]
                submit_ms = int((time.time() - submit_start) * 1000)
                logger.debug("[ark] 任务已提交，task_id=%s", task_id)
                return task_id, submit_ms
            except httpx.HTTPStatusError as e:
                raise VideoGenerationError(
                    f"ARK 提交失败：{e.response.status_code} {e.response.text}",
                    original_error=e,
                ) from e

    @classmethod
    async def _ark_poll(cls, task_id: str) -> Tuple[str, int]:
        """
        轮询 ARK 视频生成任务直到完成，返回 (video_url, poll_count)。
        终态为 "succeeded"，视频 URL 在响应的 content.video_url 字段。
        """
        cfg = config.multimodal
        poll_url = f"{cfg.ark_base_url}/contents/generations/tasks/{task_id}"
        headers = {"Authorization": f"Bearer {cfg.ark_api_key}"}

        deadline = time.time() + cfg.ark_video_timeout
        poll_count = 0

        async with httpx.AsyncClient(timeout=30) as client:
            while time.time() < deadline:
                await asyncio.sleep(cfg.ark_video_poll_interval)
                poll_count += 1

                try:
                    response = await client.get(poll_url, headers=headers)
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    raise VideoGenerationError(
                        f"ARK 轮询失败：{e.response.status_code}", original_error=e
                    ) from e

                result = response.json()
                status = result.get("status", "")

                if status == "succeeded":
                    content = result.get("content", {})
                    video_url = (
                        content.get("video_url")
                        if isinstance(content, dict)
                        else None
                    )
                    if not video_url:
                        raise VideoGenerationError(
                            f"ARK 任务 {task_id} 完成但 content.video_url 为空"
                        )
                    logger.debug("[ark] task_id=%s 已完成，polls=%d", task_id, poll_count)
                    return video_url, poll_count

                if status in ("failed", "canceled"):
                    error_msg = result.get("error", "unknown error")
                    raise VideoGenerationError(
                        f"ARK 任务失败（{status}）：{error_msg}",
                        details={"task_id": task_id},
                    )

                logger.debug(
                    "[ark] task_id=%s 状态=%s，继续等待... (poll=%d)",
                    task_id, status, poll_count,
                )

        raise TaskTimeoutError(
            f"ARK 任务 {task_id} 超时（>{cfg.ark_video_timeout}s）",
            details={"task_id": task_id, "timeout": cfg.ark_video_timeout},
        )

    # ── WaveSpeed 通用异步客户端 ───────────────────────────────────────────────

    @classmethod
    async def _wavespeed_submit(cls, model_path: str, payload: dict) -> Tuple[str, int]:
        """
        提交 WaveSpeed 异步任务，返回 (task_id, submit_ms)。
        网络异常时自动重试（最多 max_retries 次）。
        """
        cfg = config.multimodal
        if not cfg.wavespeed_api_key:
            raise ConfigurationError(
                "WAVESPEED_API_KEY 未配置", config_key="WAVESPEED_API_KEY"
            )

        url = f"{cfg.wavespeed_base_url}/{model_path}"
        headers = {
            "Authorization": f"Bearer {cfg.wavespeed_api_key}",
            "Content-Type": "application/json",
        }

        last_error: Optional[Exception] = None
        submit_start = time.time()
        for attempt in range(cfg.wavespeed_max_retries):
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    task_id = data["data"]["id"]
                    submit_ms = int((time.time() - submit_start) * 1000)
                    logger.debug("[wavespeed] 任务已提交，task_id=%s", task_id)
                    return task_id, submit_ms
            except httpx.HTTPStatusError as e:
                raise VideoGenerationError(
                    f"WaveSpeed 提交失败：{e.response.status_code} {e.response.text}",
                    original_error=e,
                ) from e
            except Exception as e:
                last_error = e
                if attempt < cfg.wavespeed_max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(
                        "[wavespeed] 提交失败（第 %d 次），%ds 后重试: %s",
                        attempt + 1,
                        wait,
                        e,
                    )
                    await asyncio.sleep(wait)

        raise VideoGenerationError(
            "WaveSpeed 提交失败（超过最大重试次数）", original_error=last_error
        )

    @classmethod
    async def _wavespeed_poll(cls, task_id: str) -> Tuple[str, int]:
        """
        轮询 WaveSpeed 任务状态直到完成，返回 (result_url, poll_count)。
        固定 poll_interval 间隔，超过 timeout 抛出 TaskTimeoutError。
        """
        cfg = config.multimodal
        poll_url = f"{cfg.wavespeed_base_url}/predictions/{task_id}/result"
        headers = {"Authorization": f"Bearer {cfg.wavespeed_api_key}"}

        deadline = time.time() + cfg.wavespeed_timeout
        poll_count = 0

        async with httpx.AsyncClient(timeout=30) as client:
            while time.time() < deadline:
                await asyncio.sleep(cfg.wavespeed_poll_interval)
                poll_count += 1

                retries_left = cfg.wavespeed_max_retries
                while retries_left > 0:
                    try:
                        response = await client.get(poll_url, headers=headers)
                        response.raise_for_status()
                        break
                    except Exception as e:
                        retries_left -= 1
                        if retries_left == 0:
                            raise VideoGenerationError(
                                f"WaveSpeed 轮询失败：{e}", original_error=e
                            ) from e
                        await asyncio.sleep(2)

                data = response.json()["data"]
                status = data.get("status", "")

                if status == "completed":
                    outputs = data.get("outputs", [])
                    if not outputs:
                        raise VideoGenerationError(
                            f"WaveSpeed 任务 {task_id} 完成但 outputs 为空"
                        )
                    logger.debug("[wavespeed] task_id=%s 已完成，polls=%d", task_id, poll_count)
                    return outputs[0], poll_count

                if status == "failed":
                    error_msg = data.get("error", "unknown error")
                    raise VideoGenerationError(
                        f"WaveSpeed 任务失败：{error_msg}",
                        details={"task_id": task_id},
                    )

                logger.debug(
                    "[wavespeed] task_id=%s 状态=%s，继续等待... (poll=%d)",
                    task_id, status, poll_count,
                )

        raise TaskTimeoutError(
            f"WaveSpeed 任务 {task_id} 超时（>{cfg.wavespeed_timeout}s）",
            details={"task_id": task_id, "timeout": cfg.wavespeed_timeout},
        )

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    @classmethod
    async def _get_video_base64_url(cls, source: str) -> str:
        """
        将视频来源转换为 base64 data URL（供 Seed 1.8 使用）。

        处理逻辑：
        - 本地文件路径 → 直接读取
        - HTTP/HTTPS URL → 下载后编码
        """
        if source.startswith("data:"):
            return source

        if source.startswith("http://") or source.startswith("https://"):
            logger.debug("[base64] 从 URL 下载视频: %s", source)
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                response = await client.get(source)
                response.raise_for_status()
                video_bytes = response.content
        else:
            import os

            if not os.path.isfile(source):
                raise UnsupportedVideoSourceError(
                    f"本地文件不存在：{source}", details={"source": source}
                )
            with open(source, "rb") as f:
                video_bytes = f.read()

        if len(video_bytes) > 50 * 1024 * 1024:
            raise UnsupportedVideoSourceError(
                f"视频文件过大（{len(video_bytes) // 1024 // 1024}MB > 50MB），Seed 1.8 不支持",
                details={"source": source, "size_mb": len(video_bytes) // 1024 // 1024},
            )

        b64 = base64.b64encode(video_bytes).decode("utf-8")
        return f"data:video/mp4;base64,{b64}"

    # ── 使用统计 ──────────────────────────────────────────────────────────────

    @classmethod
    def _record(cls, service_id: str, success: bool, elapsed_ms: int) -> None:
        if service_id not in cls._usage:
            cls._usage[service_id] = UsageStat()
        stat = cls._usage[service_id]
        stat.total_calls += 1
        stat.total_elapsed_ms += elapsed_ms
        if success:
            stat.successful += 1
        else:
            stat.failed += 1

    @classmethod
    def get_usage_stats(cls) -> dict:
        """返回各服务的调用统计摘要"""
        return {
            sid: {
                "total_calls": s.total_calls,
                "successful": s.successful,
                "failed": s.failed,
                "avg_elapsed_ms": round(s.avg_elapsed_ms),
            }
            for sid, s in cls._usage.items()
        }

    @classmethod
    def reset_usage_stats(cls) -> None:
        """重置统计（测试用）"""
        cls._usage.clear()


# ── 便捷入口（模块级函数）─────────────────────────────────────────────────────


async def understand_video(
    service: VideoUnderstandingService,
    video_source: str,
    question: str,
    max_tokens: int = 1024,
) -> VideoUnderstandingResult:
    return await MultimodalClientManager.understand_video(
        service, video_source, question, max_tokens
    )


async def generate_image(
    service: ImageService,
    prompt: str,
    size: str = "2048x2048",
    **kwargs,
) -> ImageResult:
    return await MultimodalClientManager.generate_image(service, prompt, size, **kwargs)


async def edit_image(
    service: ImageService,
    image_url: str,
    prompt: str,
    **kwargs,
) -> ImageResult:
    return await MultimodalClientManager.edit_image(service, image_url, prompt, **kwargs)


async def generate_video(
    service: VideoService,
    prompt: str,
    image_url: Optional[str] = None,
    images: Optional[list[str]] = None,
    **kwargs,
) -> VideoResult:
    return await MultimodalClientManager.generate_video(
        service, prompt, image_url, images, **kwargs
    )
