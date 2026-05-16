"""Dry-run schema 2.0 -> V2.1 skill codemod.

The migrator intentionally writes candidates only.  It does not mutate the
source skill tree and it marks uncertain mechanical mappings for human review.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from graph_agent.core.parser import _parse_frontmatter, _strip_frontmatter, extract_raw_blocks

REVIEW_MARKER = "<!--TODO: CODEMOD_REVIEW-->"
_REVIEW_PREFIX = "<!--TODO: CODEMOD_REVIEW:"
_SIMPLE_TYPES = {
    "str": "string",
    "string": "string",
    "int": "integer",
    "integer": "integer",
    "float": "number",
    "number": "number",
    "bool": "boolean",
    "boolean": "boolean",
    "dict": "object",
    "object": "object",
    "list": "array",
    "array": "array",
}


@dataclass(frozen=True)
class ReviewMarker:
    path: str
    reason: str


@dataclass
class CodemodReport:
    source: Path
    out_dir: Path
    written_files: list[str] = field(default_factory=list)
    review_markers: list[ReviewMarker] = field(default_factory=list)
    mapping_decisions: list[str] = field(default_factory=list)

    def add_written(self, path: Path) -> None:
        self.written_files.append(path.relative_to(self.out_dir).as_posix())

    def add_review(self, path: Path, reason: str) -> None:
        self.review_markers.append(ReviewMarker(path.relative_to(self.out_dir).as_posix(), reason))


def migrate_skill_md(source: Path, out_dir: Path, *, force: bool = False) -> CodemodReport:
    """Generate a V2.1 candidate tree from one schema 2.0 ``SKILL.md``."""
    source_path = _resolve_source(source)
    output_path = Path(out_dir)
    if output_path.exists():
        if not force:
            raise FileExistsError(f"{output_path} already exists; pass force=True or --force")
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True)

    text = source_path.read_text(encoding="utf-8")
    frontmatter = _to_builtin(_parse_frontmatter(text))
    body = _strip_frontmatter(text)
    report = CodemodReport(source=source_path, out_dir=output_path)

    _write_io_schemas(frontmatter.get("io") or {}, output_path, report)
    phases = frontmatter.get("phases")
    if isinstance(phases, list) and phases:
        _migrate_graph_skill(frontmatter, phases, output_path, report)
    else:
        _migrate_simple_skill(frontmatter, body, output_path, report)
    _write_report(report)
    return report


def default_candidate_dir(source: Path) -> Path:
    source_path = _resolve_source(source)
    return source_path.parent.with_name(source_path.parent.name + ".v21_candidate")


def _resolve_source(source: Path) -> Path:
    path = Path(source)
    if path.is_dir():
        path = path / "SKILL.md"
    if not path.is_file():
        raise FileNotFoundError(f"schema 2.0 SKILL.md not found: {path}")
    return path


def _to_builtin(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _to_builtin(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_builtin(v) for v in value]
    return value


def _write_io_schemas(io_def: dict[str, Any], out_dir: Path, report: CodemodReport) -> None:
    io_dir = out_dir / "io"
    io_dir.mkdir(parents=True, exist_ok=True)
    for key, filename in (("inputs", "inputs.json"), ("outputs", "outputs.json")):
        schema, review_reasons = _json_schema_for_io_items(io_def.get(key) or [], key)
        path = io_dir / filename
        _write_text(path, json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n", report)
        for reason in review_reasons:
            report.add_review(path, reason)
    report.mapping_decisions.append("io.inputs/io.outputs -> io/inputs.json + io/outputs.json")


def _json_schema_for_io_items(items: Any, key: str) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": True,
    }
    if not isinstance(items, list):
        reasons.append(f"io.{key} is not a list")
        return schema, reasons
    properties = schema["properties"]
    required = schema["required"]
    assert isinstance(properties, dict)
    assert isinstance(required, list)
    for item in items:
        if not isinstance(item, dict) or not item.get("name"):
            reasons.append(f"io.{key} contains an unmappable item")
            continue
        raw_type = str(item.get("type") or "string")
        json_type = _SIMPLE_TYPES.get(raw_type)
        if json_type is None:
            json_type = "string"
            reasons.append(f"io.{key}.{item['name']} has unmappable type {raw_type!r}")
        prop = {"type": json_type}
        for legacy_key in ("source", "target", "path"):
            if legacy_key in item:
                prop[f"x-legacy-{legacy_key}"] = item[legacy_key]
        properties[str(item["name"])] = prop
        required.append(str(item["name"]))
    return schema, reasons


def _migrate_graph_skill(
    frontmatter: dict[str, Any],
    phases: list[Any],
    out_dir: Path,
    report: CodemodReport,
) -> None:
    phase_entries: list[tuple[str, str]] = []
    used_slugs: set[str] = set()
    for index, raw_phase in enumerate(phases):
        phase = raw_phase if isinstance(raw_phase, dict) else {}
        phase_name = str(phase.get("name") or f"phase_{index + 1}")
        slug = _unique_slug(phase_name, used_slugs)
        used_slugs.add(slug)
        phase_entries.append((slug, f"phases/{slug}"))
        _write_phase_candidate(phase_name, slug, phase, out_dir, report)
    _write_graph(frontmatter, phase_entries, out_dir, report)
    report.mapping_decisions.append("YAML phases[] -> GRAPH.md phase tags + phases/<id> node files")


def _migrate_simple_skill(
    frontmatter: dict[str, Any],
    body: str,
    out_dir: Path,
    report: CodemodReport,
) -> None:
    blocks = extract_raw_blocks(body, ["phase_config", "system_prompt", "user_prompt", "exit_contract"])
    phase_name = _phase_name_from_config(blocks.get("phase_config", "")) or "main"
    slug = _unique_slug(phase_name, set())
    phase: dict[str, Any] = {
        "name": phase_name,
        "mode": "llm",
        "prompt": blocks.get("system_prompt", ""),
        "user_prompt_template": blocks.get("user_prompt", ""),
        "agent_tools": _tools_from_phase_config(blocks.get("phase_config", "")),
    }
    if "exit_contract" in blocks:
        phase["exit_contract"] = blocks["exit_contract"]
    _write_phase_candidate(phase_name, slug, phase, out_dir, report)
    _write_graph(frontmatter, [(slug, f"phases/{slug}")], out_dir, report)
    report.mapping_decisions.append("XML body simple skill -> one SKILL phase candidate")


def _write_graph(
    frontmatter: dict[str, Any],
    phase_entries: list[tuple[str, str]],
    out_dir: Path,
    report: CodemodReport,
) -> None:
    graph_fm = {
        "schema_version": "2.1",
        "name": str(frontmatter.get("name") or "codemod-skill"),
        "description": str(frontmatter.get("description") or ""),
        "metadata": {
            "legacy_type": frontmatter.get("type"),
            "context_mapping": frontmatter.get("context_mapping") or {},
        },
    }
    body_lines = ['<input src="io/inputs.json" />', '<output src="io/outputs.json" />']
    previous: str | None = None
    for phase_id, src in phase_entries:
        depends = ' depends_on=""' if previous is None else f' depends_on="{previous}"'
        body_lines.append(f'<phase id="{phase_id}" src="{src}"{depends} />')
        previous = phase_id
    _write_markdown(out_dir / "GRAPH.md", graph_fm, "\n".join(body_lines) + "\n", report)


def _write_phase_candidate(
    phase_name: str,
    slug: str,
    phase: dict[str, Any],
    out_dir: Path,
    report: CodemodReport,
) -> None:
    mode = str(phase.get("mode") or "llm")
    reasons = _review_reasons_for_phase(phase)
    if mode == "logic":
        _write_logic_phase(phase_name, slug, phase, reasons, out_dir, report)
    else:
        _write_skill_phase(phase_name, slug, phase, reasons, out_dir, report)


def _write_logic_phase(
    phase_name: str,
    slug: str,
    phase: dict[str, Any],
    reasons: list[str],
    out_dir: Path,
    report: CodemodReport,
) -> None:
    steps = phase.get("execute_steps") or []
    callable_name = steps[0] if isinstance(steps, list) and steps else "TODO.codemod.missing_callable"
    if not steps:
        reasons.append("logic phase missing execute_steps")
    frontmatter = {
        "mode": "logic",
        "name": phase_name,
        "metadata": _legacy_phase_metadata(phase),
    }
    body = _review_comments(reasons) + f"<python_callable>\n{callable_name}\n</python_callable>\n"
    path = out_dir / "phases" / slug / "LOGIC.md"
    _write_markdown(path, frontmatter, body, report)
    for reason in reasons:
        report.add_review(path, reason)


def _write_skill_phase(
    phase_name: str,
    slug: str,
    phase: dict[str, Any],
    reasons: list[str],
    out_dir: Path,
    report: CodemodReport,
) -> None:
    prompt = str(phase.get("prompt") or "")
    user_prompt = str(phase.get("user_prompt_template") or "")
    exit_contract = str(phase.get("exit_contract") or "").strip()
    if not exit_contract:
        exit_contract = "Review migrated prompt, then call finish_task when the phase is complete."
    frontmatter = {
        "mode": "skill",
        "name": phase_name,
        "tools": phase.get("agent_tools") or phase.get("tools") or [],
        "metadata": _legacy_phase_metadata(phase),
    }
    body = _review_comments(reasons)
    body += f"<system_prompt>\n{prompt.strip()}\n</system_prompt>\n"
    if user_prompt:
        body += f"<user_prompt>\n{user_prompt.strip()}\n</user_prompt>\n"
    body += f"<exit_contract>\n{exit_contract}\n</exit_contract>\n"
    path = out_dir / "phases" / slug / "SKILL.md"
    _write_markdown(path, frontmatter, body, report)
    for reason in reasons:
        report.add_review(path, reason)


def _legacy_phase_metadata(phase: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in (
        "llm_role",
        "max_iterations",
        "max_nudges",
        "max_retries",
        "retry_target",
        "output_schema",
        "validator",
        "execute_steps",
    ):
        if key in phase:
            metadata[f"legacy_{key}"] = phase[key]
    return metadata


def _review_reasons_for_phase(phase: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    steps = phase.get("execute_steps")
    if isinstance(steps, list) and len(steps) > 1:
        reasons.append("logic phase has multiple execute_steps")
    if not str(phase.get("exit_contract") or "").strip():
        reasons.append("missing exit_contract; generated default candidate")
    for key in ("validator", "output_schema", "retry_target", "max_retries"):
        if phase.get(key) is not None:
            reasons.append(f"legacy {key} requires human mapping")
    if phase.get("llm_role"):
        reasons.append("legacy llm_role requires human review")
    for key in ("prompt", "user_prompt_template"):
        text = str(phase.get(key) or "")
        reasons.extend(_complex_text_reasons(text, key))
    return _dedupe(reasons)


def _complex_text_reasons(text: str, field: str) -> list[str]:
    reasons: list[str] = []
    if re.search(r"<ref\b", text, re.IGNORECASE):
        reasons.append(f"{field} contains cross-file <ref>")
    if re.search(r"<step\b.*<step\b", text, re.IGNORECASE | re.DOTALL):
        reasons.append(f"{field} contains nested <step>")
    if _has_unbalanced_known_boundary(text):
        reasons.append(f"{field} contains unbalanced boundary tag")
    if re.search(r"</?(div|span|section|article|xml|phase|step)\b", text, re.IGNORECASE):
        reasons.append(f"{field} contains XML/HTML-like markup")
    return reasons


def _has_unbalanced_known_boundary(text: str) -> bool:
    for tag in ("system_prompt", "user_prompt", "exit_contract", "phase", "step", "ref"):
        opens = len(re.findall(rf"<{tag}\b", text, re.IGNORECASE))
        closes = len(re.findall(rf"</{tag}>", text, re.IGNORECASE))
        if opens != closes:
            return True
    return False


def _review_comments(reasons: list[str]) -> str:
    return "".join(f"{_REVIEW_PREFIX} {reason}-->\n" for reason in _dedupe(reasons))


def _phase_name_from_config(config: str) -> str | None:
    match = re.search(r"^\s*name\s*:\s*(.+?)\s*$", config, re.MULTILINE)
    return match.group(1).strip() if match else None


def _tools_from_phase_config(config: str) -> list[str]:
    lines = config.splitlines()
    tools: list[str] = []
    in_tools = False
    for line in lines:
        stripped = line.strip()
        if stripped == "tools:":
            in_tools = True
            continue
        if in_tools and stripped.startswith("- "):
            tools.append(stripped[2:].strip())
            continue
        if in_tools and stripped and not line.startswith((" ", "\t")):
            break
    return tools


def _unique_slug(name: str, used: set[str]) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip()).strip("-").lower() or "phase"
    candidate = slug
    index = 2
    while candidate in used:
        candidate = f"{slug}-{index}"
        index += 1
    return candidate


def _write_markdown(path: Path, frontmatter: dict[str, Any], body: str, report: CodemodReport) -> None:
    text = "---\n" + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False) + "---\n" + body
    _write_text(path, text, report)


def _write_text(path: Path, text: str, report: CodemodReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    report.add_written(path)


def _write_report(report: CodemodReport) -> None:
    lines = [
        "# CODEMOD_REPORT",
        "",
        f"- source: `{report.source.name}`",
        "- out_dir: `<codemod-output>`",
        "",
        "## Written files",
        "",
    ]
    lines.extend(f"- `{path}`" for path in sorted(report.written_files))
    lines.extend(["", "## Review markers", ""])
    if report.review_markers:
        lines.extend(f"- `{marker.path}`: {marker.reason}" for marker in report.review_markers)
    else:
        lines.append("- none")
    lines.extend(["", "## Mapping decisions", ""])
    lines.extend(f"- {decision}" for decision in report.mapping_decisions)
    path = report.out_dir / "CODEMOD_REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report.add_written(path)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run migrate schema 2.0 SKILL.md to V2.1 candidates.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    out_dir = args.out_dir or default_candidate_dir(args.source)
    report = migrate_skill_md(args.source, out_dir, force=args.force)
    print(f"wrote {len(report.written_files)} files to {report.out_dir}")
    print(f"review markers: {len(report.review_markers)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
