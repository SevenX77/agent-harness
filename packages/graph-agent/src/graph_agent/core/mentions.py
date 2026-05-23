"""Static @-mention scanning and reachability validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

MENTION_RE = re.compile(
    r"@(subagent|tool|subgraph|protocol|step|reference|example):([A-Za-z0-9_-]+)"
)
BROKEN_MENTION_RE = re.compile(r"@(subagent|tool|subgraph|protocol|step|reference|example)(?!:)")


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
    return BROKEN_MENTION_RE.search(text)


__all__ = ["Mention", "first_broken_mention", "scan_mentions"]
