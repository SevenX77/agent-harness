"""SKILL.md reverse-serialisation (Studio Phase 0 Task 0.2).

Given a validated ``SkillManifest`` (from ``core.manifest``), produce a
byte-stable ``SKILL.md`` string. The output is the authoritative shape
that the forthcoming parser (Task 0.3) will consume, so this module
effectively *defines* the on-disk format.

Format decision (2026-04-24 Claude/Gemini converged):
pure YAML frontmatter, no structured XML/Markdown body.

Why pure YAML
=============

* **Parser determinism** — a single YAML tree is unambiguous; mixing
  YAML frontmatter with an XML/Markdown body requires maintaining two
  ASTs in sync, and any parser regex over Markdown body is fragile
  under minor user edits.
* **Round-trip idempotency** — Studio UI ↔ Git repo double-sync
  demands that ``serialize(parse(f)) == f`` byte-for-byte. Only pure
  YAML with fixed dumper options (``sort_keys=False``, explicit block
  scalar style for multiline strings) meets that bar.
* **Long-string habitat** — YAML Block Scalar (``|``) is the
  GitHub-Actions / Kubernetes-manifest / Ansible idiom for multi-line
  prompts and persona profiles. Git diffs stay clean, no quote
  escaping needed.

Body (any text after the closing ``---``) is treated as non-structured
human notes — rationale, changelogs, design discussion — and is
ignored by the parser. The parser (Task 0.3) will optionally stash it
into a transient ``_human_body_content`` attribute so that serialising
again preserves it verbatim. That preservation path ships with Task 0.3;
this module's ``serialize_skill()`` only emits frontmatter + an empty
body for now.

Dumper configuration
====================

* ``sort_keys=False`` — preserves the field order Pydantic derives
  from the class declarations, which is author-friendly.
* ``default_flow_style=False`` — force block-style dicts/lists. Flow
  style (``{a: 1, b: 2}``) would collapse under long values and
  destabilise diffs.
* ``allow_unicode=True`` — SKILL.md files routinely carry Chinese
  descriptions; escape-encoding would destroy readability.
* ``CustomDumper.represent_str`` — any string containing ``\\n`` is
  emitted as a Literal Block Scalar (``|``). This keeps LLM prompts,
  persona ``role_profile``s, and multi-line few-shot examples legible.
"""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from graph_agent.core.manifest import SkillManifest


class _BlockScalarDumper(yaml.SafeDumper):  # type: ignore[misc]  # PyYAML SafeDumper is Any without local stubs.
    """PyYAML dumper that forces multi-line strings to Block Scalar style.

    Strings without newlines fall through to default plain/quoted
    behaviour; only genuine multi-line text (LLM prompts, role
    profiles, few-shot examples) is rendered with ``|``.
    """


def _represent_str(dumper: _BlockScalarDumper, data: str) -> Any:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_BlockScalarDumper.add_representer(str, _represent_str)


def serialize_skill(manifest: SkillManifest) -> str:
    """Serialise a ``SkillManifest`` to a ``SKILL.md`` string.

    Args:
        manifest: A validated ``SkillManifest`` instance (any of the
            three artifact types — agent/graph/persona).

    Returns:
        The full file contents as a string: ``---\\n<yaml>---\\n``.
        Callers that care about preserving an existing human-notes
        body must re-attach it themselves until Task 0.3 lands the
        parser-side preservation path.
    """
    if hasattr(manifest, "model_dump"):
        data = manifest.model_dump(exclude_none=True)
    else:
        msg = "serialize_skill requires a Pydantic v2 model with .model_dump"
        raise TypeError(msg)

    buf = StringIO()
    yaml.dump(
        data,
        buf,
        Dumper=_BlockScalarDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=1000,
    )
    yaml_str = buf.getvalue()
    if not yaml_str.endswith("\n"):
        yaml_str += "\n"

    return f"---\n{yaml_str}---\n"


__all__ = ["serialize_skill"]
