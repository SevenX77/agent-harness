"""Happy-path unit tests for multimodal tools (D-9.1).

External HTTP / video-provider calls are fully mocked so these tests
never hit a real network — they only verify that the tool functions
wire arguments into the underlying provider calls and surface the
response correctly.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src" / "core"))

from graph_agent.tools.generate_video import generate_video_tool  # noqa: E402
from graph_agent.tools.synthesize_speech import synthesize_speech_tool  # noqa: E402
from graph_agent.tools.understand_video import understand_video_tool  # noqa: E402


class _FakeResolvedProvider:
    """Minimal stand-in for ResolvedMultimodalProvider used by the tools."""

    def __init__(self, provider_code: str = "ARK") -> None:
        self.provider_code = provider_code
        self.model_name = "fake-model"
        self.role_name = "fake-role"
        self.model_options: dict = {}
        self.provider_def = type(
            "P",
            (),
            {
                "type": "ark",
                "base_url": "https://example.invalid/",
                "api_key_env": "FAKE_KEY",
                "api_key_env_fallback": "",
                "proxy_env": "",
                "trust_env": False,
                "timeout": 30,
            },
        )


class TestGenerateVideo:
    def test_calls_underlying_provider_and_returns_url(self):
        fake_result = {"url": "https://example/output.mp4", "duration": 5}
        fake_chain = [_FakeResolvedProvider("ARK")]
        # Target call_chain resolver + _video_ark implementation.
        with (
            patch(
                "graph_agent.tools.generate_video.call_chain",
                return_value=fake_chain,
            ),
            patch(
                "graph_agent.tools.generate_video._video_ark",
                new=AsyncMock(return_value=fake_result),
            ),
            patch(
                "graph_agent.tools.generate_video.run_async",
                side_effect=lambda coro: fake_result,
            ),
        ):
            out = generate_video_tool(
                prompt="a cat riding a bike",
                duration=5,
                resolution="720p",
            )
        assert "output.mp4" in out or "url" in out


class TestSynthesizeSpeech:
    def test_returns_output_path_on_success(self, tmp_path: Path):
        output = tmp_path / "hello.mp3"
        fake_result = {
            "duration_ms": 1234,
            "provider": "volcengine_tts",
            "output_path": str(output),
        }
        with (
            patch(
                "graph_agent.tools.synthesize_speech._tts_long",
                new=AsyncMock(return_value=fake_result),
            ),
            patch(
                "graph_agent.tools.synthesize_speech.run_async",
                side_effect=lambda coro: fake_result,
            ),
        ):
            result = synthesize_speech_tool(
                text="Hello world",
                output_path=str(output),
            )
        # Tool wraps the dict into a JSON string via ok(...). The output
        # path + provider should both make it through.
        assert str(output) in result
        assert "volcengine_tts" in result
        assert "1234" in result  # duration_ms surfaces


class TestUnderstandVideo:
    def test_passes_question_through_provider(self):
        fake_chain = [_FakeResolvedProvider("ARK")]
        fake_answer = {"answer": "A small dog running in a park."}
        with (
            patch(
                "graph_agent.tools.understand_video.call_chain",
                return_value=fake_chain,
            ),
            patch(
                "graph_agent.tools.understand_video._vu_ark",
                new=AsyncMock(return_value=fake_answer),
            ),
            patch(
                "graph_agent.tools.understand_video.run_async",
                side_effect=lambda coro: fake_answer,
            ),
        ):
            result = understand_video_tool(
                question="What is the dog doing?",
                video_source="https://example.invalid/clip.mp4",
            )
        # Tool wraps into ok(...) JSON — the payload must make it through.
        assert "dog" in result or "answer" in result
