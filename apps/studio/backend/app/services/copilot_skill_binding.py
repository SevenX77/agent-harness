"""Session-bound skill identity for the Copilot MCP tool surface.

A Copilot session is opened on exactly ONE skill workspace: ``stream_query``
receives the authoritative ``skill_id`` from the frontend and resolves it to a
single cwd (``copilot._resolve_copilot_workspace_dir``). "Which skill am I
working on" therefore has a single owner and is not a free parameter — yet every
structured tool used to declare ``skill_id`` in its input schema and read it back
out of ``args``. The only thing a model can do with a required field it has no
authoritative source for is guess, and the manifest ``name:`` sitting in the open
``GRAPH.md`` is the obvious thing to guess. When a skill directory is copied, that
``name:`` still says the SOURCE skill, so the guess resolves through the global
index to a DIFFERENT directory and the write lands there (observed twice on
2026-08-15; both times only the human approval card stopped it).

Prior art borrowed, and what was rejected:

- Taken from this repo's own CLI-session fix (``apps/studio/tauri/src/native_fs.rs``
  ``registered_skill_id_for_root``): "the index is the registry that answers this,
  so the id is read from there rather than accepted from whoever opened the
  session." Same defect, same remedy, one layer over.
- Taken from the shape of the existing write-boundary hook
  (``copilot._make_write_boundary_hook``): the binding is created per session and
  every call is checked against it, rather than trusting a one-time setup.
- Rejected: *validating* a model-supplied ``skill_id`` against the session's.
  Validation leaves the illegal state representable and turns a structural
  guarantee into a runtime comparison a future tool can forget to run. Removing
  the field from the model-facing schema makes the wrong call unutterable
  (AGENTS.md Coding Standards, "让非法状态不可表示").
- Rejected: binding only the id. The id→directory mapping is mutable (the index
  key is a bare directory name, so opening a same-named folder repoints it), so
  a binding that remembers only the id can still drift onto another tree. The
  binding therefore records the resolved workspace root too and re-checks the
  pair before every call.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_agent_sdk import SdkMcpTool

logger = logging.getLogger(__name__)

#: The argument name that always means "the skill this session has open".
#: Tools that MINT a new skill use ``new_skill_id`` instead — that id is not a
#: reference to an existing skill, so there is nothing for the model to guess.
SKILL_ID_ARG = "skill_id"


@dataclass(frozen=True)
class CopilotSkillBinding:
    """The one skill a Copilot session may touch.

    Both halves are load-bearing: ``skill_id`` is what the Studio services take,
    ``workspace_root`` is the directory that id resolved to when the session
    opened. Keeping both is what makes an index repoint detectable instead of
    silently redirecting the session's writes.
    """

    skill_id: str
    workspace_root: Path


def bind_tools_to_open_skill(
    tools: list[SdkMcpTool[Any]],
    binding: CopilotSkillBinding,
) -> list[SdkMcpTool[Any]]:
    """Return the tool surface with ``skill_id`` removed from the model's reach.

    Only tools that declare ``skill_id`` are rewritten; the rest (LLM config,
    web fetch) are passed through untouched, so a tool that has nothing to do
    with the open skill never fails because of the skill index.
    """

    return [
        _bind_one(tool, binding) if _declares_skill_id(tool.input_schema) else tool
        for tool in tools
    ]


def _bind_one(tool: SdkMcpTool[Any], binding: CopilotSkillBinding) -> SdkMcpTool[Any]:
    return dataclasses.replace(
        tool,
        input_schema=_schema_without_skill_id(tool.input_schema),
        handler=_bound_handler(tool.name, tool.handler, binding),
    )


def _bound_handler(
    tool_name: str,
    handler: Callable[[Any], Awaitable[dict[str, Any]]],
    binding: CopilotSkillBinding,
) -> Callable[[Any], Awaitable[dict[str, Any]]]:
    async def bound(args: dict[str, Any]) -> dict[str, Any]:
        violation = _binding_violation(binding)
        if violation is not None:
            logger.warning(
                "phase=copilot_guardrail action=skill_binding_deny tool=%s detail=%s",
                tool_name,
                violation,
            )
            return _tool_error(f"{tool_name}: {violation}")
        # Unconditional overwrite, not a default: the value must never be able to
        # come from the model, even if a caller replays an old argument shape.
        return await handler({**(args or {}), SKILL_ID_ARG: binding.skill_id})

    return bound


def _binding_violation(binding: CopilotSkillBinding) -> str | None:
    """Why this session's id no longer names its own workspace, or None."""

    from app.services.skills import resolve_skill_dir

    try:
        resolved = resolve_skill_dir(binding.skill_id)
    except Exception:  # noqa: BLE001 — any resolution failure is the same fact
        return (
            f"the open workspace {binding.workspace_root} is no longer registered under "
            f"skill id {binding.skill_id!r}; reopen the folder in Studio before editing it"
        )
    if _same_directory(resolved, binding.workspace_root):
        return None
    return (
        f"skill id {binding.skill_id!r} now resolves to {resolved}, but this session is "
        f"open on {binding.workspace_root}; refusing to act on a different skill"
    )


def _same_directory(left: Path, right: Path) -> bool:
    # normcase is the cross-platform half of this: on Windows it folds case and
    # separators (the same tree reached as D:\x and d:/x must compare equal),
    # on POSIX it is the identity, so case stays significant where it matters.
    return _comparable(left) == _comparable(right)


def _comparable(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))


def _declares_skill_id(schema: type[Any] | dict[str, Any]) -> bool:
    properties = _properties_of(schema)
    return properties is not None and SKILL_ID_ARG in properties


def _schema_without_skill_id(schema: type[Any] | dict[str, Any]) -> type[Any] | dict[str, Any]:
    if not isinstance(schema, dict):
        return schema
    if _is_json_schema(schema):
        properties = {
            name: value
            for name, value in schema["properties"].items()
            if name != SKILL_ID_ARG
        }
        required = [name for name in schema.get("required", []) if name != SKILL_ID_ARG]
        return {**schema, "properties": properties, "required": required}
    return {name: value for name, value in schema.items() if name != SKILL_ID_ARG}


def _properties_of(schema: type[Any] | dict[str, Any]) -> dict[str, Any] | None:
    """The parameter map of either accepted schema form, or None for a TypedDict."""

    if not isinstance(schema, dict):
        return None
    return schema["properties"] if _is_json_schema(schema) else schema


def _is_json_schema(schema: dict[str, Any]) -> bool:
    return schema.get("type") == "object" and isinstance(schema.get("properties"), dict)


def _tool_error(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


__all__ = ["SKILL_ID_ARG", "CopilotSkillBinding", "bind_tools_to_open_skill"]
