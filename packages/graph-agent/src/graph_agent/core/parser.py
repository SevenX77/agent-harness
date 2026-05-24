"""Pure parsing utilities for V0.3.0 Markdown/YAML documents."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, NoReturn

try:  # pragma: no cover - exercised indirectly depending on env deps
    from ruamel.yaml import YAML as _RuamelYAML
    from ruamel.yaml.error import YAMLError as _RuamelYAMLError

    RuamelYAML: Any = _RuamelYAML
    YAMLError: Any = _RuamelYAMLError
except ModuleNotFoundError:  # pragma: no cover
    import yaml

    RuamelYAML = None
    YAMLError = yaml.YAMLError

from graph_agent.core.exceptions import SkillLoadError


def _make_yaml() -> Any:
    """Build a configured ruamel YAML loader."""
    if RuamelYAML is None:
        raise SkillLoadError("ruamel.yaml is not available")
    yaml = RuamelYAML(typ="rt")
    yaml.preserve_quotes = True
    return yaml


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        raise SkillLoadError("No YAML frontmatter found (file must start with ---)")

    # Cohesion plan 方针 3.4 (2026-04-26): accept both ``\n`` and
    # ``\r\n``. ``read_text(...)`` normalises CRLF→LF, but Studio /
    # programmatic callers may hand us the raw bytes; the regex must
    # not depend on universal-newline normalisation.
    match = re.match(r"^---\r?\n(.*?)\r?\n---", content, re.DOTALL)
    if not match:
        raise SkillLoadError("Invalid frontmatter format")

    yaml_body = match.group(1)
    try:
        if RuamelYAML is None:
            import yaml as pyyaml

            data = pyyaml.safe_load(yaml_body)
        else:
            yaml = _make_yaml()
            data = yaml.load(yaml_body)
    except YAMLError as exc:
        raise SkillLoadError(f"Invalid YAML in frontmatter: {exc}") from exc

    if not isinstance(data, dict):
        raise SkillLoadError("Frontmatter must be a YAML dictionary")

    return data


def _strip_frontmatter(content: str) -> str:
    """Return content after YAML frontmatter."""
    match = re.match(r"^---\r?\n.*?\r?\n---", content, re.DOTALL)
    if match:
        return content[match.end() :].lstrip("\r\n")
    return content


def _fatal(path: Path, line: int, message: str) -> NoReturn:
    raise SkillLoadError(f"[F-v3-route] {path}:{line} {message}")


def parse_markdown_parts(path: Path | str) -> tuple[dict[str, Any], str, dict[str, int]]:
    """Read a V0.3.0 markdown document into YAML frontmatter and raw body."""
    p = Path(path)
    content = p.read_text(encoding="utf-8")

    frontmatter = _parse_frontmatter(content)
    if "schema_version" in frontmatter:
        frontmatter["schema_version"] = str(frontmatter["schema_version"]).strip()
    body = _strip_frontmatter(content)
    frontmatter_end_line = 1
    match = re.match(r"^---\r?\n.*?\r?\n---", content, re.DOTALL)
    if match:
        frontmatter_end_line = content[: match.end()].count("\n") + 1

    return frontmatter, body, {"body_start": frontmatter_end_line + 1}


def extract_raw_blocks(body: str, allowed_tags: list[str]) -> dict[str, str]:
    """Extract top-level ``<tag>...</tag>`` blocks as raw strings.

    The inside of each block is intentionally not parsed as XML.  Natural
    language angle brackets, HTML snippets, and malformed inner markup remain
    untouched.
    """
    blocks: dict[str, str] = {}
    for tag in allowed_tags:
        pattern = re.compile(
            rf"<{re.escape(tag)}(?:\s[^>]*)?>(.*?)</{re.escape(tag)}>",
            re.DOTALL | re.IGNORECASE,
        )
        match = pattern.search(body)
        if match:
            blocks[tag] = match.group(1).strip()
    return blocks


_FORBIDDEN_TOPOLOGY_TAG_RE = re.compile(
    r"</?\s*(phase|depends_on|edge)\b",
    re.IGNORECASE,
)


def scan_forbidden_topology_tags(path: Path, body: str) -> None:
    """Reject graph-topology tags inside phase XML bodies."""
    match = _FORBIDDEN_TOPOLOGY_TAG_RE.search(body)
    if match is None:
        return
    line = body[: match.start()].count("\n") + 1
    tag = match.group(0).replace(" ", "")
    if not tag.endswith(">"):
        tag += ">"
    _fatal(
        path,
        line,
        f"topology tag '{tag}' is forbidden in phase body (整图拓扑只能在 GRAPH.md)",
    )


__all__ = [
    "_parse_frontmatter",
    "_strip_frontmatter",
    "extract_raw_blocks",
    "parse_markdown_parts",
    "scan_forbidden_topology_tags",
]
