"""synthesize_speech — Volcengine TTS with Edge TTS fallback."""

from __future__ import annotations

import base64
import contextlib
import importlib
import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, TypedDict, cast

from graph_agent.tools.providers import err, ok, run_async

logger = logging.getLogger(__name__)

_VOLCENGINE_TTS_URL = "https://openspeech.bytedance.com/api/v1/tts"
_VOLCENGINE_MAX_BYTES = 1024
_VOLCENGINE_SUCCESS_CODE = 3000


class _TTSResult(TypedDict):
    provider: str
    duration_ms: int


def _split_at_sentence_boundaries(text: str, max_bytes: int = _VOLCENGINE_MAX_BYTES) -> list[str]:
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]
    delimiters = ("。", "！", "？", "；", "，", "、")
    chunks: list[str] = []
    remaining = text
    while remaining:
        encoded = remaining.encode("utf-8")
        if len(encoded) <= max_bytes:
            chunks.append(remaining)
            break
        prefix = encoded[:max_bytes].decode("utf-8", errors="ignore")
        split_pos = -1
        for d in delimiters:
            pos = prefix.rfind(d)
            if pos > split_pos:
                split_pos = pos
        if split_pos <= 0:
            split_pos = len(prefix) - 1
        chunks.append(remaining[: split_pos + 1])
        remaining = remaining[split_pos + 1 :]
    return [c for c in chunks if c.strip()]


def _probe_duration_ms(file_path: str) -> int:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return int(float(result.stdout.strip()) * 1000)
    except (subprocess.SubprocessError, ValueError) as exc:
        logger.warning("ffprobe failed for %s: %s — reporting duration as 0", file_path, exc)
        return 0


def _concat_audio_files(paths: list[str], output: str) -> None:
    if len(paths) == 1:
        import shutil

        shutil.copy2(paths[0], output)
        return
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in paths:
            f.write(f"file '{p}'\n")
        list_path = f.name
    try:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                list_path,
                "-c",
                "copy",
                output,
            ],
            capture_output=True,
            timeout=60,
            check=True,
        )
    finally:
        Path(list_path).unlink(missing_ok=True)


async def _tts_volcengine(text: str, output_path: str) -> _TTSResult:
    import httpx

    app_id = os.getenv("VOLCENGINE_TTS_APP_ID", "")
    token = os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN", "")
    if not (app_id and token):
        raise RuntimeError("Volcengine TTS not configured")

    voice = os.getenv(
        "VOLCENGINE_TTS_VOICE",
        "zh_male_jieshuoxiaoshuai_moon_bigtts",
    )
    payload = {
        "app": {
            "appid": app_id,
            "token": token,
            "cluster": "volcano_tts",
        },
        "user": {"uid": "story-forge"},
        "audio": {
            "voice_type": voice,
            "encoding": "mp3",
            "speed_ratio": 1.0,
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": text,
            "operation": "query",
            "model": "seed-tts-1.1",
        },
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _VOLCENGINE_TTS_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer;{token}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = cast(dict[str, Any], resp.json())
    if data.get("code") != _VOLCENGINE_SUCCESS_CODE:
        raise RuntimeError(
            f"Volcengine TTS error code={data.get('code')}: {data.get('message', '')}"
        )
    audio_b64 = data.get("data", "")
    if not audio_b64:
        raise RuntimeError("Volcengine returned empty audio data")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_bytes(base64.b64decode(audio_b64))
    duration_ms = int(data.get("addition", {}).get("duration", "0"))
    return {"provider": "volcengine", "duration_ms": duration_ms}


async def _tts_edge(text: str, output_path: str) -> _TTSResult:
    try:
        edge_tts = importlib.import_module("edge_tts")
    except ImportError as exc:
        raise ImportError("Edge TTS fallback requires edge-tts: pip install edge-tts") from exc

    voice = os.getenv("EDGE_TTS_VOICE", "zh-CN-YunyangNeural")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    await edge_tts.Communicate(text, voice).save(output_path)
    duration_ms = _probe_duration_ms(output_path)
    return {"provider": "edge_tts", "duration_ms": duration_ms}


async def _tts_single(text: str, output_path: str) -> _TTSResult:
    """Synthesize one chunk with Volcengine -> Edge TTS fallback."""
    try:
        return await _tts_volcengine(text, output_path)
    except Exception as e:
        logger.warning("Volcengine TTS failed, falling back to Edge TTS: %s", e)
    return await _tts_edge(text, output_path)


async def _tts_long(text: str, output_path: str) -> _TTSResult:
    """Synthesize long text: split -> synthesize chunks -> concat."""
    chunks = _split_at_sentence_boundaries(text)
    if len(chunks) <= 1:
        return await _tts_single(text, output_path)

    temp_dir = Path(output_path).parent / "_tts_chunks"
    temp_dir.mkdir(parents=True, exist_ok=True)
    chunk_paths: list[str] = []
    total_ms = 0
    provider = "unknown"
    try:
        for i, chunk in enumerate(chunks):
            cp = str(temp_dir / f"chunk_{i:03d}.mp3")
            result = await _tts_single(chunk, cp)
            chunk_paths.append(cp)
            total_ms += result["duration_ms"]
            provider = result["provider"]
        _concat_audio_files(chunk_paths, output_path)
    finally:
        for cp in chunk_paths:
            Path(cp).unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            temp_dir.rmdir()
    return {"provider": provider, "duration_ms": total_ms}


def synthesize_speech_tool(
    text: str,
    output_path: str,
) -> str:
    """Convert text to speech audio using TTS providers.

    Synthesizes speech from text using Volcengine TTS with Edge TTS fallback.
    Automatically splits long text at sentence boundaries and concatenates
    the results. Writes the audio MP3 file to the specified output path.

    When to use synthesize_speech:
    - Converting narration or dialogue text into spoken audio
    - Generating voiceover audio files for video production

    When NOT to use synthesize_speech:
    - For generating music or sound effects
    - For transcribing audio to text (speech-to-text)

    Args:
        text: The text content to convert to speech.
        output_path: Absolute file path where the output audio MP3 will be
            written. Parent directories are created automatically.
    """
    if not text.strip():
        return err(ValueError("Text is empty"))

    try:
        result = run_async(lambda: _tts_long(text, output_path))
        return ok(
            {
                "status": "success",
                "audio_path": output_path,
                "duration_ms": result["duration_ms"],
                "provider": result["provider"],
                "text_bytes": len(text.encode("utf-8")),
            }
        )
    except Exception as exc:
        logger.error("synthesize_speech failed: %s", exc)
        return err(exc)


synthesize_speech_tool.__name__ = "synthesize_speech"
synthesize_speech_tool.__qualname__ = "synthesize_speech"
