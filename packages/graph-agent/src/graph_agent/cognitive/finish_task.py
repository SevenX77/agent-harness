"""V2.1 finish_task LangChain tool factory."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from graph_agent.cognitive.md2json import Md2JsonResult
from graph_agent.cognitive.md_patch import MdPatchClient
from graph_agent.core.exceptions import GraphAgentFatalError, make_error_payload

_AGENT_OUTPUT_SCHEMA_INVALID_CODE = "[F-v3-agent-output-schema-invalid]"
_COGNITIVE_OUTPUT_SCHEMA_INVALID_CODE = "[F-v3-cognitive-output-schema-invalid]"


class FinishTaskInput(BaseModel):
    """Input schema for the V2.1 finish_task tool."""

    reasoning: str = Field(default="", description="Reasoning or explanation of the submitted work.")
    diagnostics_md: str = Field(default="", description="Additional diagnostic markdown or details.")
    business_data_md: str = Field(..., description="Final structured/unstructured business markdown output.")


Md2JsonConverter = Callable[[str, dict[str, Any] | None], Md2JsonResult]


def build_finish_task_tool(
    output_schema: dict[str, Any] | None,
    md2json: Md2JsonConverter,
    patcher: MdPatchClient | None = None,
    max_patch_attempts: int = 3,
) -> StructuredTool:
    """Build the V2.1 finish_task StructuredTool."""

    _check_output_schema(output_schema)

    def _finish_task(
        business_data_md: str,
        reasoning: str = "",
        diagnostics_md: str = "",
    ) -> dict[str, Any]:
        if not isinstance(business_data_md, str) or not business_data_md.strip():
            return _structured_error(
                Md2JsonResult(data={}, validation_errors=[], repaired=False),
                attempts=0,
                markdown="" if not isinstance(business_data_md, str) else business_data_md,
                kind="invalid_markdown",
            )

        result = md2json(business_data_md, output_schema)
        if not result.validation_errors:
            return {"ok": True, "data": result.data, "repaired": result.repaired}
        if patcher is None or output_schema is None:
            return _structured_error(result, attempts=0, markdown=business_data_md)

        current_markdown = business_data_md
        current_result = result
        for attempt in range(1, max_patch_attempts + 1):
            patched_markdown = patcher.patch(
                current_markdown,
                output_schema,
                current_result.validation_errors,
                attempt,
            )
            if not isinstance(patched_markdown, str) or not patched_markdown.strip():
                current_result = Md2JsonResult(
                    data={},
                    validation_errors=[
                        {
                            "path": [],
                            "schema_path": [],
                            "message": "md-patch returned empty or non-string markdown",
                            "validator": "md_patch",
                        }
                    ],
                    repaired=True,
                )
                continue

            current_markdown = patched_markdown
            current_result = md2json(current_markdown, output_schema)
            if not current_result.validation_errors:
                return {
                    "ok": True,
                    "data": current_result.data,
                    "repaired": True,
                    "attempts": attempt,
                }

        return _structured_error(
            current_result,
            attempts=max_patch_attempts,
            markdown=current_markdown,
        )

    return StructuredTool.from_function(
        func=_finish_task,
        name="finish_task",
        description="Submit phase final output. Markdown will be parsed to dict and validated.",
        args_schema=FinishTaskInput,
    )



def _check_output_schema(output_schema: dict[str, Any] | None) -> None:
    if output_schema is None:
        return
    try:
        Draft202012Validator.check_schema(output_schema)
    except SchemaError as exc:
        _raise_output_schema_invalid(exc.message, cause=exc)
    if not output_schema:
        return
    known_keys = {
        "$schema",
        "additionalProperties",
        "properties",
        "required",
        "type",
    }
    if not any(key in output_schema for key in known_keys):
        _raise_output_schema_invalid("expected JSON object schema")
    if output_schema.get("type") not in {None, "object"}:
        _raise_output_schema_invalid("expected object schema")
    if "properties" in output_schema and not isinstance(output_schema["properties"], dict):
        _raise_output_schema_invalid("properties must be object")


def _raise_output_schema_invalid(message: str, *, cause: BaseException | None = None) -> None:
    full_message = f"{_COGNITIVE_OUTPUT_SCHEMA_INVALID_CODE} output_schema invalid: {message}"
    exc = GraphAgentFatalError(
        full_message,
        payload=make_error_payload(_COGNITIVE_OUTPUT_SCHEMA_INVALID_CODE, full_message),
    )
    if cause is not None:
        raise exc from cause
    raise exc


def _structured_error(
    result: Md2JsonResult,
    *,
    attempts: int,
    markdown: str,
    kind: str = "parse_or_validation_failed",
) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": _AGENT_OUTPUT_SCHEMA_INVALID_CODE,
            "kind": kind,
            "attempts": attempts,
            "validation_errors": result.validation_errors,
            "markdown_excerpt": markdown[:500],
        },
    }


__all__ = ["FinishTaskInput", "Md2JsonConverter", "build_finish_task_tool"]
