"""V2.1 exit-contract prompt injection."""

from __future__ import annotations

from langchain_core.messages import AnyMessage, HumanMessage


def inject_exit_contract(
    messages: list[AnyMessage],
    exit_contract: str,
) -> list[AnyMessage]:
    """Append ``exit_contract`` as a standalone User Message at the tail.

    V2.1 keeps completion criteria out of the system prompt.  Before each
    model call, the runtime appends this contract as the final human message so
    recency bias keeps the exit criteria visible throughout the ReAct loop.
    """
    new_messages = list(messages)
    stripped_contract = exit_contract.strip()
    if not stripped_contract:
        return new_messages
    new_messages.append(HumanMessage(content=stripped_contract))
    return new_messages


__all__ = ["inject_exit_contract"]
