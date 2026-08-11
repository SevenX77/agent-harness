"""Asking a role a question without taking on LangChain.

LangChain is not a universal standard. Plenty of applications talk to models
over ordinary chat protocols and never import it, and a gateway that only
speaks ``BaseChatModel`` is a gateway those applications cannot install. So
this module is the second of the three faces the gateway shows: plain messages
in, plain data out, no LangChain type crossing the boundary either way.

What it is NOT is a second way of calling providers. The whole point of the
route chain — trying the next route when one fails, skipping a route that is
marked down, recording usage — is the product; a consumer who skips LangChain
must not thereby lose it. So this face takes the same resolved role and runs
the same orchestration as the ChatX face, and converts only at the edge. There
was once a parallel implementation here, with its own per-protocol
serialization, and the lesson it left is exactly why there is not one now: two
wire paths for one call disagree, and then nobody can say which one production
takes.

The third face is elsewhere: hand back the resolved route and call it yourself
(:mod:`graph_agent_gateway.resolve`). Use that one when even the calling should
be yours.

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md D10
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, convert_to_messages

from graph_agent_gateway.registry import ResolvedRole

__all__ = ["PlainAnswer", "chat_plainly"]


@dataclass(frozen=True)
class PlainAnswer:
    """One answer, and which route gave it.

    Which route answered is part of the answer rather than a side channel:
    after a fallback chain has been walked, "what did it say" and "who said it"
    are the same question asked twice.
    """

    text: str
    route_id: str
    endpoint_id: str
    model: str
    protocol: str
    usage: Mapping[str, int] = field(default_factory=dict)
    finish_reason: str | None = None
    reasoning: str | None = None


def chat_plainly(
    resolved_role: ResolvedRole,
    messages: Sequence[Mapping[str, Any]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    ledger: Any = None,
    credential_provider: Any = None,
    callbacks: Sequence[Any] = (),
) -> PlainAnswer:
    """Ask ``resolved_role`` and get plain data back.

    ``messages`` are ordinary ``{"role": ..., "content": ...}`` mappings — the
    shape every chat protocol already uses, so a caller has nothing to build.

    Only the settings a caller genuinely overrides per call are parameters here.
    Everything else the request carries was already settled when the role was
    materialized; re-listing it would invite two answers to the same question.
    """
    from graph_agent_gateway.call.chat_model import GatewayChatModel

    # Left out rather than defaulted: the ChatX face owns what "no budget given"
    # means, and repeating its default here would be a second answer to the same
    # question, free to drift from the first.
    budget: dict[str, Any] = {} if max_tokens is None else {"max_tokens": max_tokens}
    model = GatewayChatModel(
        resolved_role.role_name,
        resolved_role,
        temperature=temperature,
        callbacks=callbacks,
        client_manager=ledger,
        credential_provider=credential_provider,
        **budget,
    )
    answer = model.invoke(convert_to_messages([dict(message) for message in messages]))
    return _plainly(answer)


def _plainly(answer: BaseMessage) -> PlainAnswer:
    metadata = dict(getattr(answer, "response_metadata", {}) or {})
    reasoning = (
        answer.additional_kwargs.get("reasoning_content")
        if isinstance(answer, AIMessage)
        else None
    )
    return PlainAnswer(
        text=_text_of(answer.content),
        route_id=str(metadata.get("route_id", "")),
        endpoint_id=str(metadata.get("endpoint_id", "")),
        model=str(metadata.get("model", "")),
        protocol=str(metadata.get("protocol", "")),
        usage=dict(metadata.get("usage") or {}),
        finish_reason=_optional_text(metadata.get("finish_reason")),
        reasoning=reasoning if isinstance(reasoning, str) and reasoning.strip() else None,
    )


def _text_of(content: object) -> str:
    """The answer as text, however the provider chose to shape it.

    Providers that answer in content blocks are not answering something else,
    so a caller who asked plainly gets the text joined rather than a shape to
    take apart.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, Mapping) and isinstance(block.get("text"), str):
                parts.append(str(block["text"]))
        return "".join(parts)
    return ""


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
