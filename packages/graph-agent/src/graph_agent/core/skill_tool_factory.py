"""Factory for converting SubSkill declarations into LangChain StructuredTools."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

logger = logging.getLogger(__name__)

_TYPE_MAP: dict[str, type[Any]] = {
    "string": str,
    "str": str,
    "int": int,
    "integer": int,
    "float": float,
    "bool": bool,
    "boolean": bool,
}


@dataclass(frozen=True)
class SubSkillSpec:
    """Specification for a sub-skill tool wrapper."""

    name: str  # tool name exposed to LLM (valid Python identifier)
    description: str  # tool description for LLM
    skill_path: str  # path to sub-skill SKILL.md (abs or relative to parent)
    input_schema: dict[str, str]  # {"field": "type, description"}
    _parent_skill_dir: Path | None = None  # injected by loader for relative path resolution


def _build_input_model(name: str, input_schema: dict[str, str]) -> type[BaseModel]:
    """Dynamically create a Pydantic model from input_schema declarations.

    input_schema format: {"field_name": "type, description of field"}
    Supported types: string, int, float, bool
    """
    fields: dict[str, Any] = {}
    for field_name, declaration in input_schema.items():
        parts = declaration.split(",", 1)
        type_str = parts[0].strip().lower()
        description = parts[1].strip() if len(parts) > 1 else field_name

        py_type = _TYPE_MAP.get(type_str)
        if py_type is None:
            raise ValueError(
                f"Unsupported input_schema type '{type_str}' for field '{field_name}'. "
                f"Supported: {list(_TYPE_MAP.keys())}"
            )

        fields[field_name] = (py_type, Field(description=description))

    return cast(type[BaseModel], create_model(f"{name}_Input", **fields))


def _resolve_skill_path(spec: SubSkillSpec) -> Path:
    """Resolve skill_path to absolute Path.

    Relative paths are relative to parent SKILL.md dir.
    """
    p = Path(spec.skill_path)
    if p.is_absolute():
        return p
    if spec._parent_skill_dir is not None:
        return (spec._parent_skill_dir / p).resolve()
    return p.resolve()


def build_skill_tool(
    spec: SubSkillSpec,
    *,
    parent_thread_id: str | None = None,
    parent_trace_dir: Path | None = None,
) -> StructuredTool:
    """Compile a SubSkillSpec into a LangChain StructuredTool.

    The resulting tool, when called, invokes run_skill() with the LLM-provided kwargs
    as initial_context and returns context["final_output"] as a string.
    """

    abs_skill_path = _resolve_skill_path(spec)
    if not abs_skill_path.exists():
        raise ValueError(f"sub_skill '{spec.name}': skill_path not found: {abs_skill_path}")

    input_model = _build_input_model(spec.name, spec.input_schema)

    def _execute(**kwargs: Any) -> str:
        from graph_agent.core.runner import run_skill

        thread_id = f"sub_{parent_thread_id or 'root'}_{spec.name}_{uuid4().hex[:8]}"
        trace_dir = (parent_trace_dir / f"sub_{spec.name}") if parent_trace_dir else None

        logger.info(
            "[SubSkill] Invoking skill_path=%s thread_id=%s",
            abs_skill_path,
            thread_id,
        )
        start = time.time()

        result = run_skill(
            abs_skill_path,
            thread_id=thread_id,
            trace_dir=trace_dir,
            initial_context=dict(kwargs),
        )

        elapsed = time.time() - start
        logger.info("[SubSkill] Completed skill=%s wall_time=%.2fs", spec.name, elapsed)

        final_output = result.get("context", {}).get("final_output")
        if final_output is None:
            return "ERROR: Sub-skill produced no final_output"
        return str(final_output)

    return StructuredTool.from_function(
        func=_execute,
        name=spec.name,
        description=spec.description,
        args_schema=input_model,
    )
