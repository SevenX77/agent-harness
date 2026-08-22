"""Turn one turn's explicit mentions into the context that turn actually gets.

Design: `docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md`
F4 + decision COPILOT_ASSIST-8.

The split that runs through this module: a mention either points at something
the workspace can read out right now, or it points at something that only
existed during one run or one compile.

* ``file`` and ``phase`` are the first kind. The backend reads the bytes and
  injects them, because "the file at this path" has one answer and reading it
  here saves the copilot a round trip.
* ``dot``, ``error`` and ``trace`` are the second kind. The backend injects the
  reference and stops. It has tools to fetch those itself, and deciding WHICH
  run's value the user meant is a judgement — moving it into the shell is the
  same "the system decides what the context is" F4 ③ rules out.

Whichever it was, the echo says so, so nobody has to infer which they got.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import escape

from app.core.authored_text import read_authored_text
from app.models.copilot import CopilotMention

# F4 ①'s injection budget for one turn, across every mention in it. A budget
# per mention would let ten of them add up to ten times the cap.
MENTION_CONTENT_BUDGET = 150_000

# The kinds whose object the workspace can read out right now.
_CONTENT_KINDS = frozenset({"file", "phase"})

# Exactly one of these exists per phase directory — the engine rejects a
# directory with two as `[F-v3-graph-phase-mode-ambiguous]`.
_PHASE_NODE_FILENAMES = ("LOGIC.md", "SUBGRAPH.md", "SKILL.md")


# The four things one mention can turn into, named rather than inferred from
# which optional fields happen to be set. An outcome nobody can spell out is one
# every reader re-derives differently — and there are now four, not two.
MentionOutcome = Literal["injected", "reference_only", "repeat", "failed"]


@dataclass(frozen=True)
class ResolvedMention:
    """What one mention actually turned into for this turn."""

    kind: str
    ref: str
    label: str
    outcome: MentionOutcome
    # The object's text. Set only when `outcome` is "injected".
    content: str | None
    # Where the content was read from, skill-relative. Set only when injected.
    source_path: str | None
    truncated: bool
    # Why nothing was injected, in the user's terms. Set only when "failed".
    failure: str | None


def resolve_mentions(
    mentions: list[CopilotMention],
    *,
    skill_dir: Path,
    budget: int = MENTION_CONTENT_BUDGET,
) -> tuple[ResolvedMention, ...]:
    """Resolve every mention in order, spending one shared content budget.

    The same object named twice is read once (COPILOT_ASSIST-10 ②). The budget
    is a per-TURN allowance shared across every mention in it, so a second
    reading of the same bytes buys nothing and can push a later mention out of
    the allowance. Merging happens HERE rather than in the composer because the
    allowance is this module's rule; a client that forgot to de-duplicate must
    not be able to spend it twice.

    Every input mention still gets an entry, so the echo can keep one line per
    pill the user typed — a repeat is reported as a repeat, not dropped.
    """
    resolved: list[ResolvedMention] = []
    remaining = budget
    # Identity is the PAIR: `kind` decides how `ref` is read, so the same string
    # under two kinds is two objects (COPILOT_ASSIST-8).
    already_named: set[tuple[str, str]] = set()
    for mention in mentions:
        identity = (mention.kind, mention.ref)
        if identity in already_named:
            resolved.append(_repeat(mention))
            continue
        already_named.add(identity)
        if mention.kind not in _CONTENT_KINDS:
            resolved.append(_reference_only(mention))
            continue
        outcome = _read_mentioned_file(mention, skill_dir=skill_dir, remaining=remaining)
        resolved.append(outcome)
        remaining -= len(outcome.content or "")
    return tuple(resolved)


def render_mentions_xml(resolved: tuple[ResolvedMention, ...] | list[ResolvedMention]) -> str:
    """Render the resolved mentions as structured prompt context.

    Repeats contribute nothing: the object is already in the block above, under
    the same ref, and a second identical entry only spends the model's context.
    """
    blocks = [_mention_block(item) for item in resolved if item.outcome != "repeat"]
    if not blocks:
        return ""
    return "<mentions>\n" + "\n".join(blocks) + "\n</mentions>"


def mention_echo_lines(
    resolved: tuple[ResolvedMention, ...] | list[ResolvedMention],
) -> list[str]:
    """One line per mention for the context echo, saying what it actually became."""
    lines: list[str] = []
    for item in resolved:
        if item.outcome == "repeat":
            lines.append(f"@{item.kind} {item.ref} — already named above, injected once")
        elif item.failure is not None:
            lines.append(f"@{item.kind} {item.ref} — {item.failure} (nothing injected)")
        elif item.content is None:
            lines.append(f"@{item.kind} {item.ref} — reference only, not read here")
        elif item.truncated:
            lines.append(
                f"@{item.kind} {item.ref} — {item.source_path}, "
                f"truncated to {len(item.content)} chars (turn budget)"
            )
        else:
            lines.append(f"@{item.kind} {item.ref} — {item.source_path}, {len(item.content)} chars")
    return lines


def _repeat(mention: CopilotMention) -> ResolvedMention:
    """A second pill naming an object an earlier pill already named."""
    return ResolvedMention(
        kind=mention.kind,
        ref=mention.ref,
        label=mention.label,
        outcome="repeat",
        content=None,
        source_path=None,
        truncated=False,
        failure=None,
    )


def _reference_only(mention: CopilotMention) -> ResolvedMention:
    return ResolvedMention(
        kind=mention.kind,
        ref=mention.ref,
        label=mention.label,
        outcome="reference_only",
        content=None,
        source_path=None,
        truncated=False,
        failure=None,
    )


def _failed(mention: CopilotMention, reason: str) -> ResolvedMention:
    return ResolvedMention(
        kind=mention.kind,
        ref=mention.ref,
        label=mention.label,
        outcome="failed",
        content=None,
        source_path=None,
        truncated=False,
        failure=reason,
    )


def _read_mentioned_file(
    mention: CopilotMention,
    *,
    skill_dir: Path,
    remaining: int,
) -> ResolvedMention:
    located = (
        _phase_node_file(mention.ref, skill_dir=skill_dir)
        if mention.kind == "phase"
        else _workspace_file(mention.ref, skill_dir=skill_dir)
    )
    if isinstance(located, str):
        return _failed(mention, located)

    try:
        text = read_authored_text(located)
    except OSError as exc:
        return _failed(mention, f"could not be read ({exc.strerror or exc})")
    except UnicodeDecodeError:
        return _failed(mention, "is not UTF-8 text")

    budget = max(remaining, 0)
    truncated = len(text) > budget
    return ResolvedMention(
        kind=mention.kind,
        ref=mention.ref,
        label=mention.label,
        outcome="injected",
        content=text[:budget] if truncated else text,
        source_path=located.relative_to(skill_dir).as_posix(),
        truncated=truncated,
        failure=None,
    )


def _workspace_file(ref: str, *, skill_dir: Path) -> Path | str:
    """Locate a `file` ref, or say why it is not addressable."""
    candidate = (skill_dir / ref).resolve(strict=False)
    root = skill_dir.resolve(strict=False)
    if candidate != root and root not in candidate.parents:
        return "is outside this skill"
    if not candidate.is_file():
        return "was not found"
    return candidate


def _phase_node_file(ref: str, *, skill_dir: Path) -> Path | str:
    """Locate a `phase` ref's node file, or say why it is not addressable.

    A bare id is a phase of this skill; `<subgraph>/<phase>` is a phase of the
    subgraph named on the left, which is how the composer addresses one it
    showed inside an expanded subgraph.
    """
    parts = ref.split("/")
    if len(parts) == 1:
        phase_dir = skill_dir / "phases" / parts[0]
    elif len(parts) == 2:
        phase_dir = skill_dir / "subgraph" / parts[0] / "phases" / parts[1]
    else:
        return "is not a phase address"

    resolved_dir = phase_dir.resolve(strict=False)
    root = skill_dir.resolve(strict=False)
    if root not in resolved_dir.parents:
        return "is outside this skill"
    if not resolved_dir.is_dir():
        return "was not found"

    node_files = [resolved_dir / name for name in _PHASE_NODE_FILENAMES if (resolved_dir / name).is_file()]
    if not node_files:
        return "has no node file"
    if len(node_files) > 1:
        return "has more than one node file"
    return node_files[0]


def _mention_block(item: ResolvedMention) -> str:
    attributes = f'kind="{escape(item.kind, {chr(34): "&quot;"})}" ref="{escape(item.ref, {chr(34): "&quot;"})}"'
    label = f'label="{escape(item.label, {chr(34): "&quot;"})}"'
    if item.failure is not None:
        return f"  <mention {attributes} {label} unresolved={escape(item.failure, {chr(34): '&quot;'})!r} />"
    if item.content is None:
        return f"  <mention {attributes} {label} content=\"not-read-here\" />"
    body = escape(item.content)
    truncated = ' truncated="true"' if item.truncated else ""
    return (
        f'  <mention {attributes} {label} source="{escape(item.source_path or "", {chr(34): "&quot;"})}"{truncated}>\n'
        f"{body}\n"
        f"  </mention>"
    )
