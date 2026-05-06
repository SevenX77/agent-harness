"""Patch Agent tools for md-patch skill.

These tools are called by the LLM inside the md-patch graph_agent to fix
items that failed Pydantic validation in md_to_json().

Context keys used:
    diagnostic_report   str             — current diagnostic text (read-only)
    error_items         list[dict]      — failed items as {item_id, fields} patch targets
    valid_results       list[dict]      — already-valid dicts (do NOT touch)
    schema              type[BaseModel] — Pydantic class for re-validation
    patches             dict[str, dict] — accumulated {item_id: {field: value}} patches
    added_items         list[dict]      — {item_id, fields} items added via add_missing_item
    final_results       list[dict]      — written by finalize, read by validate
    finalized           bool            — set True after finalize() runs
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def get_diagnostics(context: dict[str, Any]) -> str:
    """Return the current diagnostic report text.

    Use this to review which items/fields need to be fixed before patching.
    """
    report = context.get("diagnostic_report", "")
    logger.info("get_diagnostics: report length=%d chars", len(report))
    return str(report)


def apply_field_patch(item_id: str, field: str, value: Any, context: dict[str, Any]) -> str:
    """Patch a single field on an error item.

    Args:
        item_id: The target item id (matches the '## Header' text
                 shown in the diagnostic report).
        field:   The field name to fix (e.g., 'climax_intensity').
        value:   The corrected value.  Use the correct Python type:
                 integers for int fields, floats for float fields, strings for str.
        context: Graph agent context dict (injected automatically).

    Returns:
        Confirmation string.
    """
    patches: dict[str, dict[str, Any]] = context.setdefault("patches", {})
    patches.setdefault(item_id, {})[field] = value
    logger.info("apply_field_patch: item_id=%r field=%r value=%r", item_id, field, value)
    return f"OK: patched item item_id={item_id!r} field={field!r} → {value!r}"


def add_missing_item(item_md: str, context: dict[str, Any]) -> str:
    """Add a completely new item by parsing a fresh MD snippet.

    Use this when an entire item is missing from the original output and
    cannot be fixed via field patches.

    Args:
        item_md: A complete Markdown block starting with '## item_id'.
        context: Graph agent context dict (injected automatically).

    Returns:
        Confirmation string with how many items were parsed.
    """
    from graph_agent.tools.md_to_json import parse_md  # local import to match skill pattern

    schema = context["schema"]
    try:
        new_blocks = parse_md(item_md, schema)
    except Exception as exc:
        logger.warning("add_missing_item: parse_md failed: %s", exc)
        return f"ERROR: failed to parse MD snippet — {exc}"

    new_items = [{"item_id": block.meta.id, "fields": block.data} for block in new_blocks]
    context.setdefault("added_items", []).extend(new_items)
    logger.info("add_missing_item: added %d item(s) from MD snippet", len(new_items))
    return f"OK: added {len(new_items)} item(s) from MD snippet"


def finalize(context: dict[str, Any]) -> str:
    """Merge valid_results + patched error_items + added_items into final_results.

    Must be called exactly once after all patches are applied.

    Data flow:
        valid_results   — passed through unchanged (already Pydantic-validated)
        error_items     — {item_id, fields}; patches applied via item_id matching
        added_items     — new items parsed by add_missing_item

    final_results = valid_results + patched_error_item_fields + added_item_fields

    Returns:
        Summary of merged item counts.
    """
    valid: list[dict[str, Any]] = list(context.get("valid_results", []))
    error_items: list[dict[str, Any]] = list(context.get("error_items", []))
    patches: dict[str, dict[str, Any]] = context.get("patches", {})
    added: list[dict[str, Any]] = list(context.get("added_items", []))

    # Apply patches to error_items, matching by item_id. Keep framework ids out
    # of final_results so downstream Pydantic validation sees user data only.
    patched: list[dict[str, Any]] = []
    for item in error_items:
        item_id = item.get("item_id")
        fields = dict(item.get("fields", {}))
        if item_id and item_id in patches:
            fields.update(patches[item_id])
            patch_keys = list(patches[item_id].keys())
            logger.debug("finalize: applied patch for item_id=%r fields=%s", item_id, patch_keys)
        patched.append(fields)

    added_fields = [dict(item.get("fields", {})) for item in added]
    context["final_results"] = valid + patched + added_fields
    context["finalized"] = True

    summary = (
        f"OK: finalized {len(context['final_results'])} items "
        f"({len(valid)} valid + {len(patched)} patched + {len(added)} added)"
    )
    logger.info("finalize: %s", summary)
    return summary


def validate(context: dict[str, Any]) -> tuple[bool, str | list[str]]:
    """Re-validate final_results against the schema.

    Called automatically by the graph_agent after each LLM phase if configured
    as the phase validator.

    Returns:
        (True, 'all items valid') on success.
        (False, diagnostic_report_str) on failure — triggers LLM retry.
    """
    from graph_agent.tools.md_to_json import (  # local import
        BlockMeta,
        DiagnosticReport,
        ParsedBlock,
        diagnose,
    )

    if not context.get("finalized"):
        logger.warning("validate: called before finalize — rejecting")
        return False, "请先调用 finalize 工具，再进行验证。"

    schema = context["schema"]
    final_results: list[dict[str, Any]] = context.get("final_results", [])

    blocks = [
        ParsedBlock(meta=BlockMeta(id=f"final_result_{i}"), data=item)
        for i, item in enumerate(final_results)
    ]
    report: DiagnosticReport = diagnose(blocks, schema)

    if report.all_valid:
        logger.info("validate: all %d items valid", len(report.valid_items))
        return True, "all items valid"

    diagnostic_text = report.to_prompt_string()
    logger.warning(
        "validate: %d error(s) remain after patch — returning diagnostic",
        len(report.errors),
    )
    return False, diagnostic_text
