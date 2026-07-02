"""IO scan — file/folder field recognition for the input config tree.

Design: docs/studio/mvp1/03_regions/input/mvp1-alignment.md F5 (PM 2026-07-02).
Read-only: parses JSON/JSONL top-level fields, treats md/txt as one text
candidate field (never inlining content), folds numbered batch file groups
(``chapter_001…chapter_060``) into one entry with the extracted number list,
recognizes ``latest``/``_v<ts>`` version modifiers (keep latest, skip
``history/``), and recurses one level into subfolders. Recognition is
regex-robust — it must NOT assume the engine's own fixed artifact format.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/io", tags=["io"])

_TEXT_SUFFIXES = {".md", ".txt"}
_SAMPLE_MAX_CHARS = 200
_VERSION_RE = re.compile(r"_(?:latest(?:_\d{8}_\d{6})?|v\d{8}_\d{6})", re.IGNORECASE)
_NUMBER_RE = re.compile(r"_(\d{1,6})(?=_|$)")


class ScanRequest(BaseModel):
    path: str


def _sample(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= _SAMPLE_MAX_CHARS else None
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return None


def _type_of(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "null"


def _fields_of_mapping(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        return [
            {"name": str(k), "type": _type_of(v), "sample": _sample(v)}
            for k, v in data.items()
        ]
    return [{"name": "root", "type": _type_of(data), "sample": _sample(data)}]


def _strip_version(stem: str) -> str:
    return _VERSION_RE.sub("", stem)


def _batch_key(stem: str) -> tuple[str, int] | None:
    """Return (pattern-stem, number) when the stem carries a numeric segment."""
    bare = _strip_version(stem)
    match = _NUMBER_RE.search(bare)
    if match is None:
        return None
    pattern_stem = bare[: match.start()] + "_{n}" + bare[match.end() :]
    return pattern_stem, int(match.group(1))


def _scan_json_file(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, list):
        inner = _fields_of_mapping(data[0]) if data else []
        return [
            {
                "name": path.stem,
                "type": "array",
                "sample": None,
                "items": inner,
            }
        ]
    return _fields_of_mapping(data)


def _scan_jsonl_file(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open(encoding="utf-8") as fh:
            first = fh.readline()
        return _fields_of_mapping(json.loads(first))
    except (OSError, ValueError):
        return []


def _file_entry(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    size = path.stat().st_size
    if suffix == ".json":
        fmt, fields = "json", _scan_json_file(path)
    elif suffix == ".jsonl":
        fmt, fields = "jsonl", _scan_jsonl_file(path)
    elif suffix in _TEXT_SUFFIXES or suffix == "":
        fmt = "text"
        fields = [{"name": _strip_version(path.stem), "type": "string", "sample": None}]
    else:
        fmt, fields = "binary", []
    return {
        "kind": "file",
        "name": path.name,
        "stem": _strip_version(path.stem),
        "path": str(path),
        "format": fmt,
        "size": size,
        "fields": fields,
    }


def _fold_batches(files: list[Path]) -> list[dict[str, Any]]:
    groups: dict[str, list[tuple[int, Path]]] = {}
    singles: list[Path] = []
    for f in files:
        key = _batch_key(f.stem)
        if key is None:
            singles.append(f)
        else:
            groups.setdefault(f"{key[0]}{f.suffix}", []).append((key[1], f))

    entries: list[dict[str, Any]] = []
    for pattern, members in sorted(groups.items()):
        if len(members) < 2:
            singles.extend(path for _, path in members)
            continue
        members.sort(key=lambda item: item[0])
        numbers = [n for n, _ in members]
        first = members[0][1]
        entries.append(
            {
                "kind": "batch",
                "name": pattern,
                "dir": str(first.parent),
                "pattern": pattern,
                "numbers": numbers,
                "count": len(members),
                "fields": _file_entry(first)["fields"],
            }
        )
    entries.extend(_file_entry(f) for f in sorted(singles))
    return entries


def _scan_dir(path: Path, *, depth: int) -> list[dict[str, Any]]:
    files: list[Path] = []
    subdirs: list[Path] = []
    for child in sorted(path.iterdir()):
        if child.is_dir():
            if child.name.lower() == "history":
                continue
            subdirs.append(child)
        elif child.is_file():
            files.append(child)

    entries = _fold_batches(files)
    if depth > 0:
        for sub in subdirs:
            entries.append(
                {
                    "kind": "dir",
                    "name": sub.name,
                    "path": str(sub),
                    "entries": _scan_dir(sub, depth=depth - 1),
                }
            )
    return entries


@router.post("/scan")
def scan_path(request: ScanRequest) -> dict[str, Any]:
    target = Path(request.path)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"path not found: {request.path}")
    if target.is_file():
        return {"entries": [_file_entry(target)]}
    return {"entries": _scan_dir(target, depth=1)}
