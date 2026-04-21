"""Built-in multimodal and TTS tools for graph_agent."""
from __future__ import annotations

from .generate_image import generate_image_tool
from .generate_video import generate_video_tool
from .synthesize_speech import synthesize_speech_tool
from .understand_video import understand_video_tool

__all__ = [
    "generate_image_tool",
    "generate_video_tool",
    "understand_video_tool",
    "synthesize_speech_tool",
]
