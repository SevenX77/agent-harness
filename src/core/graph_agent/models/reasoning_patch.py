"""Reasoning content monkey-patch for DeepSeek/ARK models."""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Monkey-patch: preserve reasoning_content from DeepSeek/ARK models
# ---------------------------------------------------------------------------
# LangChain ChatOpenAI explicitly does NOT extract reasoning_content
# (see langchain_openai/chat_models/base.py L8-11). We patch two layers:
#   1. OpenAI SDK: allow extra fields on ChatCompletionMessage (Pydantic)
#   2. LangChain: extract reasoning_content into AIMessage.additional_kwargs

_reasoning_patch_applied = False
_reasoning_patch_lock = threading.Lock()


def _apply_reasoning_content_patch() -> None:
    """One-time patch to preserve reasoning_content through the LangChain stack."""
    global _reasoning_patch_applied
    if _reasoning_patch_applied:
        return
    with _reasoning_patch_lock:
        if _reasoning_patch_applied:
            return
        _reasoning_patch_applied = True

        # Layer 1: OpenAI SDK — allow extra fields so reasoning_content is not dropped
        try:
            from openai.types.chat.chat_completion_message import ChatCompletionMessage
            import openai
            sdk_version = getattr(openai, "__version__", "0.0.0")
            major = int(sdk_version.split(".")[0])
            if major > 1:
                logger.warning(
                    "[ReasoningPatch] OpenAI SDK v%s detected — skipping model_config patch "
                    "(only tested with v1.x). reasoning_content may not be preserved.",
                    sdk_version,
                )
            elif "extra" not in ChatCompletionMessage.model_config or ChatCompletionMessage.model_config.get("extra") != "allow":
                ChatCompletionMessage.model_config = {
                    **ChatCompletionMessage.model_config,
                    "extra": "allow",
                }
                logger.debug("[ReasoningPatch] OpenAI SDK ChatCompletionMessage: extra=allow")
        except Exception as exc:
            logger.warning("[ReasoningPatch] Failed to patch OpenAI SDK: %s", exc)

        # Layer 2: LangChain — wrap _convert_dict_to_message to extract reasoning_content
        try:
            import langchain_openai.chat_models.base as _lcob
            _original_convert = _lcob._convert_dict_to_message

            def _patched_convert(_dict, *args, **kwargs):
                msg = _original_convert(_dict, *args, **kwargs)
                # For assistant messages, inject reasoning_content if present
                from langchain_core.messages import AIMessage
                if isinstance(msg, AIMessage):
                    rc = _dict.get("reasoning_content")
                    if rc:
                        msg.additional_kwargs["reasoning_content"] = rc
                return msg

            _lcob._convert_dict_to_message = _patched_convert
            logger.debug("[ReasoningPatch] LangChain _convert_dict_to_message: patched")
        except Exception as exc:
            logger.warning("[ReasoningPatch] Failed to patch LangChain: %s", exc)
