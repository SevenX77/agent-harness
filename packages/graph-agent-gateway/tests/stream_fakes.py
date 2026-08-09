"""Turning a canned answer into the shape a provider actually hands over.

The gateway asks every route for a stream. A test that wants to say "this route
answers X" still thinks in whole messages, so this is where the one becomes the
other — in one place, because a per-file version of it is a per-file opinion
about what a provider chunk looks like, and those drift.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from langchain_core.messages import AIMessage, AIMessageChunk


def as_one_piece(message: AIMessage) -> Iterator[AIMessageChunk]:
    """Yield a whole answer as the single piece a provider with nothing to
    reveal gradually would send.

    Tool calls travel as `tool_call_chunks` because that is how a provider
    sends them and how LangChain reassembles them; handing over finished
    `tool_calls` would test a shape no provider produces.
    """
    yield AIMessageChunk(
        content=message.content,
        tool_call_chunks=[
            {
                "name": call.get("name"),
                "args": json.dumps(call.get("args") or {}),
                "id": call.get("id"),
                "index": index,
            }
            for index, call in enumerate(message.tool_calls or [])
        ],
        usage_metadata=message.usage_metadata,
        response_metadata=dict(message.response_metadata or {}),
        additional_kwargs=dict(message.additional_kwargs or {}),
    )
