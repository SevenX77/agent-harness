"""Fixed-format artifact manifest writer (MVP1 r3 design).

The host runtime_config ``artifacts`` manifest declares which files to persist and which
blackboard fields each file carries. This module owns the fixed on-disk
naming so downstream imports can recognize engine-produced artifacts at a
glance (design: engine mvp1 physical-layout §2.2.2, skill-syntax §3.4.1):

- single:   ``<stem>_latest_<YYYYMMDD_HHMMSS>.json``; previous ``latest``
            versions are archived to ``history/<stem>_v<ts>.json``.
- per-item: ``<stem>/<stem>_<NNN>_latest_<ts>.json`` — one file per element
            of the (list-valued) declared fields; NNN inherits the element's
            ``chapter_number`` when present, else its 1-based position.
            Superseded numbers archive to ``<stem>/history/``.

This manifest wholly replaces the former per-field ``target: 'artifact'``
declarations (no dual support).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from graph_agent.core.exceptions import GraphAgentFatalError, make_error_payload

_LATEST_RE_TEMPLATE = r"^{stem}_latest_(\d{{8}}_\d{{6}})\.{ext}$"


def _now_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _write_payload(path: Path, payload: Any, fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "md":
        path.write_text(str(payload), encoding="utf-8")
    else:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def _archive_previous_latest(directory: Path, stem: str, ext: str) -> None:
    if not directory.is_dir():
        return
    pattern = re.compile(_LATEST_RE_TEMPLATE.format(stem=re.escape(stem), ext=re.escape(ext)))
    for entry in directory.iterdir():
        match = pattern.match(entry.name)
        if match is None or not entry.is_file():
            continue
        history = directory / "history"
        history.mkdir(parents=True, exist_ok=True)
        entry.replace(history / f"{stem}_v{match.group(1)}.{ext}")


def _item_number(element: Any, position: int) -> int:
    if isinstance(element, Mapping):
        number = element.get("chapter_number")
        if isinstance(number, int) and number >= 0:
            return number
    return position + 1


def _per_item_rows(
    stem: str, fields: Sequence[str], blackboard: Mapping[str, Any]
) -> list[tuple[int, dict[str, Any]]]:
    lists: dict[str, list[Any]] = {}
    for field in fields:
        if field not in blackboard:
            continue
        value = blackboard[field]
        if not isinstance(value, list):
            detail = (
                f"artifact '{stem}' declares mode per-item but blackboard field "
                f"'{field}' is {type(value).__name__}, not a list"
            )
            raise GraphAgentFatalError(
                detail,
                payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", detail),
            )
        lists[field] = value
    if not lists:
        return []
    length = max(len(v) for v in lists.values())
    rows: list[tuple[int, dict[str, Any]]] = []
    for i in range(length):
        payload = {f: v[i] for f, v in lists.items() if i < len(v)}
        first = next(iter(payload.values()))
        rows.append((_item_number(first, i), payload))
    return rows


def write_manifest_artifacts(
    artifacts: Sequence[Mapping[str, Any]],
    blackboard: Mapping[str, Any],
    artifacts_dir: Path,
    *,
    timestamp: str | None = None,
) -> list[Path]:
    """Persist declared artifacts from the blackboard; returns written paths."""
    ts = timestamp or _now_timestamp()
    written: list[Path] = []
    for spec in artifacts:
        stem = spec["stem"]
        fields = spec["fields"]
        mode = spec.get("mode", "single")
        fmt = spec.get("format", "json")
        ext = "md" if fmt == "md" else "json"
        if mode == "per-item":
            rows = _per_item_rows(stem, fields, blackboard)
            item_dir = artifacts_dir / stem
            for number, row in rows:
                payload: Any = row
                if fmt == "md":
                    payload = next(iter(row.values()))
                item_stem = f"{stem}_{number:03d}"
                _archive_previous_latest(item_dir, item_stem, ext)
                target = item_dir / f"{item_stem}_latest_{ts}.{ext}"
                _write_payload(target, payload, fmt)
                written.append(target)
        else:
            field_map = {f: blackboard[f] for f in fields if f in blackboard}
            if not field_map:
                continue
            payload = next(iter(field_map.values())) if fmt == "md" else field_map
            _archive_previous_latest(artifacts_dir, stem, ext)
            target = artifacts_dir / f"{stem}_latest_{ts}.{ext}"
            _write_payload(target, payload, fmt)
            written.append(target)
    return written
