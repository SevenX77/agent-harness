"""Strict compile rules v2 — v3 范式 + IO 对齐.

设计稿: docs/compiler/strict-compile-rules-v2.md (post-Gemini-review).

本文件实现 Step A：12 条规则全部走 WARNING，先暴露问题不阻断编译。
按顺序：
- ``check_exit_contract``：内部退出基建（5 rules）
- ``check_io_schema``：边界自我声明（3 rules）
- ``check_io_traceability``：内部闭环溯源（3 rules）
- ``check_pipeline_alignment``：跨域字段覆盖（1 rule）

Step B 阶段：用同一份 SKILL 体检报告驱动 Gemini 系统迁移每个 SKILL，每修一个就把对应规则升级 FATAL。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from ..compiler import CompileIssue

if TYPE_CHECKING:
    from ..manifest import GraphSkillDef


# ---------------------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------------------

_EXIT_CONTRACT_MARKERS = (
    "## ⚠️ 退出契约",
    "# ⚠️ 退出契约",
    "## ⚠ 退出契约",
    "## EXIT CONTRACT",
    "# EXIT CONTRACT",
    "退出契约（最高优先级）",
)

_LEGACY_TOOL_PATTERNS = (
    re.compile(r"\.store_\w+$"),
    re.compile(r"\.safe_\w*store_\w+$"),
    re.compile(r"\.backup_\w+$"),
    re.compile(r"\.finalize_event_timeline$"),
    re.compile(r"\.merge_settings_into_events$"),
)

_FINISH_TASK_FIELD_RE = re.compile(
    r"finish_task\s*\([^)]*?(business_data_md|business_data)\s*=", re.DOTALL
)


def _has_exit_contract_marker(prompt: str) -> bool:
    return any(marker in prompt for marker in _EXIT_CONTRACT_MARKERS)


def _is_legacy_data_piping_tool(tool_path: str) -> bool:
    return any(pat.search(tool_path) for pat in _LEGACY_TOOL_PATTERNS)


def _parse_inline_example(text: str | None) -> set[str]:
    """Lazy field-name extraction from an ``<output_example>`` block.

    Returns a set of field names declared in the example, used for the
    cross-skill coverage check (W-PIPELINE-FIELD-COVERAGE). Missing or
    malformed example yields an empty set; the caller treats that as
    "no info" and skips comparison rather than raising.
    """
    if not text:
        return set()
    fields: set[str] = set()
    for line in text.splitlines():
        m = re.match(r"^\s*-\s+(\w+)\s+\(", line)
        if m:
            fields.add(m.group(1))
    return fields


# ---------------------------------------------------------------------------
# Segment 1: Exit-contract checks (5 rules)
# ---------------------------------------------------------------------------


def check_exit_contract(manifest: "GraphSkillDef") -> list[CompileIssue]:
    """Run inner-phase exit-contract validators."""
    from ..manifest import LLMPhase

    issues: list[CompileIssue] = []
    for phase in manifest.phases:
        if not isinstance(phase, LLMPhase):
            continue

        prompt = (phase.prompt or "").strip()
        if not prompt or len(prompt) < 200:
            # Short prompts (or routers without prompts) bypass these checks.
            continue

        # W-FINISH-TASK-CONTRACT-MISSING
        if "finish_task" in prompt and not _has_exit_contract_marker(prompt):
            issues.append(CompileIssue(
                rule_id="W-FINISH-TASK-CONTRACT-MISSING",
                severity="WARNING",
                location=f"SKILL.md:phases.{phase.name}.prompt",
                message=(
                    f"Phase '{phase.name}' prompt mentions finish_task but lacks "
                    "an explicit exit-contract block at the head. Add "
                    "'## ⚠️ 退出契约（最高优先级）' near the prompt top with required "
                    "fields (reasoning / diagnostics_md / business_data_md) and "
                    "the call sequence. Without it the LLM tends to loop before "
                    "calling finish_task and hits LangGraph recursion_limit."
                ),
            ))

        # W-OUTPUT-SCHEMA-MISSING-WHEN-HOISTING (post-V2 pivot, 2026-04-28):
        # Either output_schema (V2 Pydantic Schema Tag, preferred) or
        # output_example (legacy DynamicSchema markdown bullet, deprecated)
        # satisfies the contract; both missing = silent hoist failure.
        if phase.hoist_to and not (phase.output_schema or phase.output_example):
            issues.append(CompileIssue(
                rule_id="W-OUTPUT-SCHEMA-MISSING-WHEN-HOISTING",
                severity="WARNING",
                location=f"SKILL.md:phases.{phase.name}",
                message=(
                    f"Phase '{phase.name}' declares hoist_to='{phase.hoist_to}' "
                    "but no output_schema (Pydantic dotted path, preferred) and "
                    "no output_example block (legacy markdown bullets). "
                    "ValidationMiddleware needs one to parse + validate + hoist "
                    "business_data_md from finish_task; otherwise hoisting silently no-ops."
                ),
            ))

        # W-LLM-PHASE-NO-OUTPUT-CHANNEL (with is_router exemption)
        if not phase.is_router:
            has_hoist = bool(phase.hoist_to)
            has_schema = bool(phase.output_schema or phase.output_example)
            has_legacy_store = any(
                _is_legacy_data_piping_tool(t) for t in (phase.agent_tools or [])
            )
            if not (has_hoist or has_schema or has_legacy_store):
                issues.append(CompileIssue(
                    rule_id="W-LLM-PHASE-NO-OUTPUT-CHANNEL",
                    severity="WARNING",
                    location=f"SKILL.md:phases.{phase.name}",
                    message=(
                        f"LLM phase '{phase.name}' has no output channel: missing "
                        "hoist_to, output_example/output_schema, and no legacy "
                        "store_*/backup_* tool. Its computed result has nowhere "
                        "to go. If this is an intent-router add 'is_router: true' "
                        "to silence."
                    ),
                ))

        # W-FINISH-TASK-PAYLOAD-NAME-MISMATCH (Gemini's ask)
        if phase.hoist_to and "business_data_md" not in prompt and "business_data" in prompt:
            issues.append(CompileIssue(
                rule_id="W-FINISH-TASK-PAYLOAD-NAME-MISMATCH",
                severity="WARNING",
                location=f"SKILL.md:phases.{phase.name}.prompt",
                message=(
                    f"Phase '{phase.name}' uses hoist_to but prompt references "
                    "'business_data' without the canonical 'business_data_md' "
                    "argument name. ValidationMiddleware reads business_data_md "
                    "from the finish_task call; mismatched naming silently "
                    "drops the payload."
                ),
            ))

        # W-UNATTENDED-WITH-CLARIFICATION-TOOL
        # The prompt-level signal: if the SKILL author writes the prompt
        # in a way that pushes the LLM toward ask_clarification, warn so
        # the author can either (a) tighten the prompt or (b) document
        # that this skill cannot run unattended.
        if phase.prompt and "ask_clarification" in phase.prompt:
            issues.append(CompileIssue(
                rule_id="W-UNATTENDED-WITH-CLARIFICATION-TOOL",
                severity="WARNING",
                location=f"SKILL.md:phases.{phase.name}.prompt",
                message=(
                    f"Phase '{phase.name}' prompt mentions ask_clarification. "
                    "Under runtime unattended=True, the framework intercepts "
                    "this tool with a fixed best-effort message; the SKILL "
                    "author should not rely on a real human reply. Either "
                    "remove the reference or document that this phase requires "
                    "unattended=False."
                ),
            ))

    return issues


# ---------------------------------------------------------------------------
# Segment 2: IO self-declaration checks (3 rules)
# ---------------------------------------------------------------------------


def check_io_schema(manifest: "GraphSkillDef") -> list[CompileIssue]:
    """Each io.inputs / io.outputs entry must self-declare schema + empty policy."""
    from ..manifest import GraphSkillDef

    if not isinstance(manifest, GraphSkillDef):
        return []

    issues: list[CompileIssue] = []
    io = getattr(manifest, "io", None)
    if io is None:
        return []

    for inp in io.inputs:
        loc = f"SKILL.md:io.inputs.{inp.name}"
        if not (inp.schema_ref or inp.example):
            issues.append(CompileIssue(
                rule_id="W-IO-INPUT-NO-SCHEMA",
                severity="WARNING",
                location=loc,
                message=(
                    f"io.inputs.{inp.name} declares no schema. Add either "
                    "'schema_ref: <upstream-skill>.outputs.<key>' (preferred for "
                    "pipeline inputs) or an inline 'example: |' block. Without "
                    "schema, downstream consumers cannot statically verify shape."
                ),
            ))
        if inp.allow_empty is None and inp.on_empty is None and inp.default is None:
            issues.append(CompileIssue(
                rule_id="W-IO-FIELD-MISSING-EMPTY-POLICY",
                severity="WARNING",
                location=loc,
                message=(
                    f"io.inputs.{inp.name} has no empty-value policy. Declare at "
                    "least one of: allow_empty (bool), default, or on_empty "
                    "(phase to short-circuit to). Empty inputs without policy "
                    "have caused LangGraph recursion deadlocks (see e2e history "
                    "2026-04-28)."
                ),
            ))

    for out in io.outputs:
        loc = f"SKILL.md:io.outputs.{out.name}"
        if not (out.schema_ref or out.example):
            issues.append(CompileIssue(
                rule_id="W-IO-OUTPUT-NO-SCHEMA",
                severity="WARNING",
                location=loc,
                message=(
                    f"io.outputs.{out.name} declares no schema. Add either "
                    "'schema_ref: phases.<phase>.output_example' (preferred — "
                    "single source of truth) or an inline 'example: |' block."
                ),
            ))
        if out.allow_empty is None and out.on_empty is None:
            issues.append(CompileIssue(
                rule_id="W-IO-FIELD-MISSING-EMPTY-POLICY",
                severity="WARNING",
                location=loc,
                message=(
                    f"io.outputs.{out.name} has no empty-value policy. Declare "
                    "allow_empty (bool) so downstream consumers know whether an "
                    "empty value is a contract failure or a legitimate state."
                ),
            ))

    return issues


# ---------------------------------------------------------------------------
# Segment 3: IO traceability checks (3 rules)
# ---------------------------------------------------------------------------


def check_io_traceability(manifest: "GraphSkillDef") -> list[CompileIssue]:
    """Schema-ref dangling, input-not-connected, legacy data-piping tools."""
    from ..manifest import GraphSkillDef, LLMPhase

    if not isinstance(manifest, GraphSkillDef):
        return []

    issues: list[CompileIssue] = []
    io = getattr(manifest, "io", None)

    # Build a map of phase outputs (phases.<name>.output_example) for ref check.
    phase_examples: dict[str, str] = {}
    for phase in manifest.phases:
        ex = getattr(phase, "output_example", None)
        if ex:
            phase_examples[phase.name] = ex

    # W-IO-OUTPUT-SCHEMA-REF-DANGLING
    for out in (io.outputs if io else []):
        if out.schema_ref and out.schema_ref.startswith("phases."):
            parts = out.schema_ref.split(".")
            if len(parts) >= 3 and parts[1] not in phase_examples:
                issues.append(CompileIssue(
                    rule_id="W-IO-OUTPUT-SCHEMA-REF-DANGLING",
                    severity="WARNING",
                    location=f"SKILL.md:io.outputs.{out.name}.schema_ref",
                    message=(
                        f"schema_ref '{out.schema_ref}' on io.outputs.{out.name} "
                        f"points to phases.{parts[1]} which has no output_example. "
                        f"Available phases with output_example: {sorted(phase_examples)}"
                    ),
                ))

    # W-IO-INPUT-NOT-CONNECTED. The 1.x DelegatePhase passthrough exemption
    # was removed in MVP-0 B1 (2026-04-28) when the delegate / parallel_delegate
    # modes were dropped; every input is expected to be wired now.
    if io and io.inputs:
        ctx_map_text = " ".join(
            f"{k}={v}" for k, v in (manifest.context_mapping or {}).items()
        )
        for inp in io.inputs:
            ref_pattern = f"input.{inp.name}"
            if ref_pattern not in ctx_map_text:
                issues.append(CompileIssue(
                    rule_id="W-IO-INPUT-NOT-CONNECTED",
                    severity="WARNING",
                    location=f"SKILL.md:io.inputs.{inp.name}",
                    message=(
                        f"io.inputs.{inp.name} is declared but does not appear "
                        "in any context_mapping value (expected '{input."
                        f"{inp.name}}}'). The input is therefore never injected "
                        "into the runtime context. Either remove the unused "
                        "input or wire it through context_mapping."
                    ),
                ))

    # W-LEGACY-DATA-PIPING-TOOL
    for phase in manifest.phases:
        if not isinstance(phase, LLMPhase):
            continue
        for tool_path in (phase.agent_tools or []):
            if _is_legacy_data_piping_tool(tool_path):
                issues.append(CompileIssue(
                    rule_id="W-LEGACY-DATA-PIPING-TOOL",
                    severity="WARNING",
                    location=f"SKILL.md:phases.{phase.name}.agent_tools",
                    message=(
                        f"Phase '{phase.name}' uses legacy data-piping tool "
                        f"'{tool_path}'. The v3 pattern (PR-1~7) replaces "
                        "store_*/safe_*/backup_*/finalize_* with a single "
                        "finish_task(business_data_md=...) call + ValidationMiddleware "
                        "auto-hoist. Migrate when this phase is rewritten."
                    ),
                ))

    return issues


# ---------------------------------------------------------------------------
# Segment 4: Cross-SKILL pipeline coverage (1 rule, downgraded per Gemini)
# ---------------------------------------------------------------------------


_SKILL_OUTPUT_REF_RE = re.compile(r"^([\w\-]+)\.outputs\.([\w]+)$")


def check_pipeline_alignment(
    manifest: "GraphSkillDef",
    skill_path: str | Path | None = None,
) -> list[CompileIssue]:
    """Shallow field-key coverage across SKILLs.

    Per Gemini 2026-04-28 review, full type-checking through the
    Markdown ``parse_output_example`` is a high-false-positive risk
    (formatting drift between SKILL authors). This rule is deliberately
    shallow: when a SKILL declares ``schema_ref: <upstream>.outputs.<key>``,
    we resolve the upstream SKILL.md, find its ``io.outputs.<key>.example``
    (or ``schema_ref`` -> phase output_example), and warn if any field
    name from the downstream input's example is missing upstream.

    No type comparison, no nested-shape match — just key coverage.
    """
    from ..manifest import GraphSkillDef

    if not isinstance(manifest, GraphSkillDef):
        return []

    issues: list[CompileIssue] = []
    io = getattr(manifest, "io", None)
    if not io or not skill_path:
        return issues

    skills_root = Path(skill_path).resolve().parent.parent  # skills/<this>/SKILL.md → skills/

    for inp in io.inputs:
        if not inp.schema_ref:
            continue
        m = _SKILL_OUTPUT_REF_RE.match(inp.schema_ref)
        if not m:
            continue  # not a cross-skill ref; could be intra-skill phases.X.output_example
        upstream_name = m.group(1)
        upstream_key = m.group(2)
        upstream_md = skills_root / upstream_name / "SKILL.md"
        if not upstream_md.exists():
            issues.append(CompileIssue(
                rule_id="W-PIPELINE-FIELD-COVERAGE",
                severity="WARNING",
                location=f"SKILL.md:io.inputs.{inp.name}.schema_ref",
                message=(
                    f"schema_ref '{inp.schema_ref}' targets upstream SKILL "
                    f"'{upstream_name}' but '{upstream_md}' does not exist."
                ),
            ))
            continue

        # Lazy parse upstream YAML to find io.outputs[upstream_key].example.
        # We avoid importing the full loader (cycles); a regex is enough for
        # the shallow check.
        upstream_text = upstream_md.read_text(encoding="utf-8")
        upstream_example = _extract_io_output_example(upstream_text, upstream_key)
        if upstream_example is None:
            issues.append(CompileIssue(
                rule_id="W-PIPELINE-FIELD-COVERAGE",
                severity="WARNING",
                location=f"SKILL.md:io.inputs.{inp.name}.schema_ref",
                message=(
                    f"Upstream SKILL '{upstream_name}' has no inline example "
                    f"on io.outputs.{upstream_key}; cannot verify field "
                    "coverage. Add an example or schema_ref to the upstream "
                    "output declaration."
                ),
            ))
            continue

        downstream_fields = _parse_inline_example(inp.example)
        upstream_fields = _parse_inline_example(upstream_example)
        if not downstream_fields:
            continue  # downstream itself has no example to compare against
        missing = downstream_fields - upstream_fields
        if missing:
            issues.append(CompileIssue(
                rule_id="W-PIPELINE-FIELD-COVERAGE",
                severity="WARNING",
                location=f"SKILL.md:io.inputs.{inp.name}",
                message=(
                    f"Pipeline contract gap: downstream input '{inp.name}' "
                    f"expects fields {sorted(missing)} which upstream "
                    f"'{upstream_name}.outputs.{upstream_key}' does not "
                    f"declare. Available upstream fields: {sorted(upstream_fields)}"
                ),
            ))

    return issues


def _extract_io_output_example(yaml_text: str, output_key: str) -> str | None:
    """Best-effort extraction of ``io.outputs[<key>].example`` block.

    Returns the inner text (without YAML scalar markers) or None if the
    output entry / example block isn't found. The compiler uses this for
    a shallow field-name comparison only, so partial extraction is fine.

    When the output declares ``schema_ref: phases.<phase>.output_example``
    instead of an inline example, this function follows the indirection
    once and returns the referenced phase's output_example body.
    """
    # Find the io.outputs block (under ``io:`` with 2-space indent) and walk
    # entries until name matches.
    out_section = re.search(
        r"^\s{0,4}outputs:\s*\n((?:\s{4,}.*\n?)+)",
        yaml_text,
        flags=re.MULTILINE,
    )
    if not out_section:
        return None
    body = out_section.group(1)
    # Split by per-entry "- name:" markers (any leading indent).
    entries = re.split(r"\n(?=\s+-\s+name:)", body)
    for entry in entries:
        name_match = re.search(r"name:\s*(\w+)", entry)
        if not name_match or name_match.group(1) != output_key:
            continue
        ex_match = re.search(r"example:\s*\|\s*\n((?:\s{6,}.*\n?)+)", entry)
        if ex_match:
            return ex_match.group(1)
        # Fall back to schema_ref: phases.X.output_example
        ref_match = re.search(r"schema_ref:\s*phases\.(\w+)\.output_example", entry)
        if ref_match:
            phase_name = ref_match.group(1)
            return _extract_phase_output_example(yaml_text, phase_name)
    return None


def _extract_phase_output_example(yaml_text: str, phase_name: str) -> str | None:
    """Extract a phase's ``output_example`` block from raw YAML text."""
    phase_section_re = re.compile(
        r"^\s{2}-\s+name:\s+" + re.escape(phase_name) + r"\s*\n"
        r"((?:\s{4,}.*\n?)+)",
        re.MULTILINE,
    )
    m = phase_section_re.search(yaml_text)
    if not m:
        return None
    body = m.group(1)
    ex_match = re.search(r"output_example:\s*\|\s*\n((?:\s{6,}.*\n?)+)", body)
    if ex_match:
        return ex_match.group(1)
    return None
