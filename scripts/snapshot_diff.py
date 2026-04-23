#!/usr/bin/env python3
"""Snapshot-regression helper for graph_agent tracing.jsonl (I-2).

Gemini's "golden data" safety net for the upcoming harness split
(deferred-items.md, Task 7.1-7.4). Two modes:

* ``record`` — run a skill and save its normalised trace as a baseline.
* ``diff`` — run the same skill after a refactor and byte-diff the
  normalised trace against the baseline.

Normalisation
=============

Gemini Q3's rules are enforced here:

1. Drop the ``timestamp`` field from every event (absolute and relative
   times both drift under concurrency / parallel_map so keeping them
   guarantees false negatives).
2. Replace UUID-like strings (``sub_run_id`` / ``group_key`` /
   ``tool_call_id`` / ``thread_id`` / ``run_id`` / any value matching a
   UUID regex) with sequentially numbered placeholders
   (``normalized_uuid_1``, ``normalized_uuid_2``, ...). The placeholder
   table is rebuilt from scratch for every run so ordering is
   deterministic.

Exit codes
==========

* ``0`` — diff mode found no differences, or record mode succeeded.
* ``1`` — diff mode found differences (the diff is printed to stdout).
* ``2`` — usage / file-not-found errors.

Usage
=====

Record a baseline::

    python scripts/snapshot_diff.py record \\
        --skill skills/text-segmentation/SKILL.md \\
        --out tests/golden/text-segmentation.json

Compare a new run against the baseline::

    python scripts/snapshot_diff.py diff \\
        --run tracing.jsonl \\
        --baseline tests/golden/text-segmentation.json

No assumption is made about how the tracing.jsonl itself is produced;
the script consumes existing JSONL files.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


_UUID_RE = re.compile(
    # Canonical 8-4-4-4-12 plus the common 12-char hex used by parallel_map
    # (uuid4.hex[:12]). If we ever change that truncation length this
    # regex should be updated.
    r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"|[0-9a-f]{12}(?:-\d+)?)$",
    re.IGNORECASE,
)

# Fields whose values are ID-like regardless of format. `_UUID_RE` catches
# most values, but some IDs (e.g. the run-prefixed ``<group>-0001``
# sub_run_id format that parallel_map emits) need a by-name override.
_ID_FIELD_NAMES = frozenset({
    "run_id",
    "thread_id",
    "sub_run_id",
    "group_key",
    "tool_call_id",
    "child_thread_id",
})


def _looks_like_id(value: str) -> bool:
    if _UUID_RE.match(value):
        return True
    # parallel_map shape: <12hex>-<idx>
    if re.match(r"^[0-9a-f]{12}-\d+$", value, re.IGNORECASE):
        return True
    return False


def _normalise(obj: Any, uuid_map: dict[str, str], *, in_id_field: bool = False) -> Any:
    """Recursively return a normalised copy of ``obj``.

    ``in_id_field`` is True when we're recursing into a value whose *field
    name* (via the dict key) is in ``_ID_FIELD_NAMES``; this forces any
    string value at that spot to be treated as an identifier even if it
    doesn't match the UUID regex.
    """
    if isinstance(obj, str):
        if in_id_field or _looks_like_id(obj):
            return uuid_map.setdefault(obj, f"normalized_uuid_{len(uuid_map) + 1}")
        return obj

    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if key == "timestamp":
                # Rule 1 — drop timestamp.
                continue
            out[key] = _normalise(
                value, uuid_map, in_id_field=(key in _ID_FIELD_NAMES)
            )
        return out

    if isinstance(obj, list):
        return [_normalise(item, uuid_map) for item in obj]

    return obj


def _load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{idx}: invalid JSON — {exc}")
    return events


def _normalise_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    uuid_map: dict[str, str] = {}
    return [_normalise(event, uuid_map) for event in events]


def _record(run_path: Path, out_path: Path) -> int:
    if not run_path.exists():
        print(f"[snapshot_diff] not found: {run_path}", file=sys.stderr)
        return 2
    events = _load_events(run_path)
    normalised = _normalise_events(events)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(normalised, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[snapshot_diff] recorded {len(normalised)} events → {out_path}")
    return 0


def _diff(run_path: Path, baseline_path: Path) -> int:
    if not run_path.exists():
        print(f"[snapshot_diff] not found: {run_path}", file=sys.stderr)
        return 2
    if not baseline_path.exists():
        print(f"[snapshot_diff] not found: {baseline_path}", file=sys.stderr)
        return 2

    baseline_events = json.loads(baseline_path.read_text(encoding="utf-8"))
    run_events = _normalise_events(_load_events(run_path))

    if baseline_events == run_events:
        print(
            f"[snapshot_diff] OK — {len(run_events)} events match baseline "
            f"({baseline_path.name})"
        )
        return 0

    import difflib

    baseline_lines = json.dumps(baseline_events, indent=2, ensure_ascii=False).splitlines(
        keepends=True
    )
    run_lines = json.dumps(run_events, indent=2, ensure_ascii=False).splitlines(keepends=True)
    diff = difflib.unified_diff(
        baseline_lines,
        run_lines,
        fromfile=str(baseline_path),
        tofile=str(run_path),
        lineterm="",
    )
    sys.stdout.writelines(diff)
    sys.stdout.write("\n")
    print(
        f"[snapshot_diff] FAIL — baseline and run differ "
        f"(baseline={len(baseline_events)} events, run={len(run_events)})",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalise + diff graph_agent tracing.jsonl against a baseline.",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    record = sub.add_parser("record", help="Save a normalised tracing.jsonl as a baseline.")
    record.add_argument("--run", required=True, type=Path, help="Path to tracing.jsonl")
    record.add_argument("--out", required=True, type=Path, help="Output baseline JSON path")

    diff = sub.add_parser("diff", help="Diff a tracing.jsonl against a saved baseline.")
    diff.add_argument("--run", required=True, type=Path, help="Path to tracing.jsonl")
    diff.add_argument(
        "--baseline", required=True, type=Path, help="Path to baseline JSON"
    )

    args = parser.parse_args(argv)
    if args.mode == "record":
        return _record(args.run, args.out)
    if args.mode == "diff":
        return _diff(args.run, args.baseline)
    return 2


if __name__ == "__main__":
    sys.exit(main())
