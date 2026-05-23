"""Static @-mention scanning and reachability validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

MENTION_RE = re.compile(
    r"@(subagent|tool|subgraph|protocol|step|reference|example):([A-Za-z0-9_-]+)"
)
BROKEN_MENTION_RE = re.compile(r"@(subagent|tool|subgraph|protocol|step|reference|example)(?!:)")
UNKNOWN_MENTION_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_-]*):")
MENTION_KINDS = frozenset(
    {"subagent", "tool", "subgraph", "protocol", "step", "reference", "example"}
)


@dataclass(frozen=True)
class Mention:
    kind: str
    name: str
    start: int


def scan_mentions(text: str) -> list[Mention]:
    return [
        Mention(kind=match.group(1), name=match.group(2), start=match.start())
        for match in MENTION_RE.finditer(text)
    ]


def first_broken_mention(text: str) -> re.Match[str] | None:
    broken = BROKEN_MENTION_RE.search(text)
    if broken is not None:
        return broken
    for match in UNKNOWN_MENTION_RE.finditer(text):
        if match.group(1) not in MENTION_KINDS:
            return match
    return None


__all__ = ["Mention", "first_broken_mention", "scan_mentions"]
