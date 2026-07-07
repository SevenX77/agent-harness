from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

_SCHEMA_VERSION = "studio.runtime_config.v1"
_ARCHIVE_DIR_NAMES = {"history", ".history"}
_STRUCTURED_SUFFIXES = {".json", ".jsonl", ".ndjson", ".csv", ".tsv"}
_TEXT_SUFFIXES = {".txt", ".md"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg"}
_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
_DOC_SUFFIXES = {".pdf", ".doc", ".docx"}
_VERSION_RE = re.compile(r"_(?:latest(?:_\d{8}_\d{6})?|v\d{8}_\d{6})", re.IGNORECASE)
_NUMBER_RE = re.compile(r"_(\d{1,6})(?=_|$)")


def workspace_dir_for_runtime(skill_dir: Path) -> Path:
    return skill_dir / ".workspace"


def runtime_config_path_for(skill_dir: Path) -> Path:
    return workspace_dir_for_runtime(skill_dir) / "runtime_config.json"


def default_runtime_config() -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "inputs": {
            "import_root": "import_files",
            "manifest": {"root": [], "phases": {}},
            "root": {},
            "phases": {},
            "conflicts": {"root": [], "phases": {}},
        },
        "llm": {
            "node_params": {"nodes": {}},
            "compare_candidates": {"nodes": {}},
            "custom_params": {"nodes": {}},
        },
        "artifacts": [],
    }


def read_runtime_config(skill_dir: Path) -> dict[str, Any]:
    path = runtime_config_path_for(skill_dir)
    if not path.exists():
        return _with_fingerprint(default_runtime_config())
    raw = json.loads(path.read_text(encoding="utf-8"))
    config = default_runtime_config()
    if isinstance(raw, dict):
        _deep_update(config, raw)
    config["schema_version"] = _SCHEMA_VERSION
    return _with_fingerprint(config)


def write_runtime_config(skill_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
    workspace = workspace_dir_for_runtime(skill_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    payload = _with_fingerprint(config)
    path = runtime_config_path_for(skill_dir)
    from app.services.file_watcher import record_api_write

    record_api_write(path, match_current_mtime=False)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    record_api_write(path)
    return payload


def refresh_runtime_config(skill_dir: Path) -> dict[str, Any]:
    config = read_runtime_config(skill_dir)
    inputs = _dict_slot(config, "inputs")
    phase_ids = ensure_import_layout(skill_dir)
    manifest, root_bindings, phase_bindings, conflicts = _scan_import_files(
        workspace_dir_for_runtime(skill_dir),
        phase_ids=phase_ids,
    )
    inputs["import_root"] = "import_files"
    inputs["manifest"] = manifest
    inputs["root"] = root_bindings
    inputs["phases"] = phase_bindings
    inputs["conflicts"] = conflicts
    return write_runtime_config(skill_dir, config)


def runtime_input_fields_for_engine(config: dict[str, Any]) -> dict[str, set[str]]:
    inputs = config.get("inputs")
    phases = inputs.get("phases") if isinstance(inputs, dict) else None
    if not isinstance(phases, dict):
        return {}
    result: dict[str, set[str]] = {}
    for phase_id, bindings in phases.items():
        if not isinstance(phase_id, str) or not isinstance(bindings, dict):
            continue
        fields = {field for field, binding in bindings.items() if isinstance(field, str) and isinstance(binding, dict)}
        if fields:
            result[phase_id] = fields
    return result


def runtime_config_fingerprint(config: dict[str, Any]) -> str:
    return str(_with_fingerprint(config)["fingerprint"])


def update_node_llm_params_payload(
    skill_dir: Path,
    nodes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    config = read_runtime_config(skill_dir)
    llm = _dict_slot(config, "llm")
    llm["node_params"] = {"nodes": {node: payload for node, payload in sorted(nodes.items())}}
    return write_runtime_config(skill_dir, config)


def update_compare_candidates_payload(
    skill_dir: Path,
    nodes: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    config = read_runtime_config(skill_dir)
    llm = _dict_slot(config, "llm")
    llm["compare_candidates"] = {"nodes": {node: payload for node, payload in sorted(nodes.items())}}
    return write_runtime_config(skill_dir, config)


def update_artifacts_payload(skill_dir: Path, artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    config = read_runtime_config(skill_dir)
    config["artifacts"] = artifacts
    return write_runtime_config(skill_dir, config)


def write_runtime_snapshot(run_dir: Path, config: dict[str, Any]) -> Path:
    path = run_dir / "runtime_config.snapshot.json"
    payload = _with_fingerprint(config)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def ensure_import_layout(skill_dir: Path, phase_ids: list[str] | None = None) -> list[str]:
    workspace = workspace_dir_for_runtime(skill_dir)
    import_root = workspace / "import_files"
    phase_root = import_root / ".phase"
    phase_root.mkdir(parents=True, exist_ok=True)
    current_phase_ids = phase_ids if phase_ids is not None else _graph_phase_ids(skill_dir)
    current = {phase_id for phase_id in current_phase_ids if _is_safe_phase_id(phase_id)}
    for phase_id in sorted(current):
        (phase_root / phase_id).mkdir(parents=True, exist_ok=True)
    for child in list(phase_root.iterdir()):
        if child.is_dir() and child.name not in current:
            shutil.rmtree(child)
    return sorted(current)


def _dict_slot(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if key in {"golden", "ui"}:
            continue
        existing = target.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            _deep_update(existing, value)
        else:
            target[key] = value


def _with_fingerprint(config: dict[str, Any]) -> dict[str, Any]:
    payload = _strip_non_runtime_keys(config)
    payload["schema_version"] = _SCHEMA_VERSION
    payload["updated_at"] = datetime.now(UTC).isoformat()
    stable = _strip_fingerprint_fields(payload)
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["fingerprint"] = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    return payload


def _strip_non_runtime_keys(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key not in {"golden", "ui"}}


def _strip_fingerprint_fields(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key not in {"updated_at", "fingerprint"}}


def _scan_import_files(
    workspace_dir: Path,
    *,
    phase_ids: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    import_root = workspace_dir / "import_files"
    if not import_root.exists():
        return {"root": [], "phases": {}}, {}, {}, {"root": [], "phases": {}}
    root_entries = _scan_import_dir(import_root, workspace_dir, depth=1, skip_phase=True)
    root_bindings, root_conflicts = _bindings_from_entries(root_entries, scope="root")
    phase_entries: dict[str, list[dict[str, Any]]] = {}
    phase_bindings: dict[str, dict[str, Any]] = {}
    phase_conflicts: dict[str, list[dict[str, Any]]] = {}
    phase_root = import_root / ".phase"
    current_phase_ids = phase_ids
    if current_phase_ids is None and phase_root.is_dir():
        current_phase_ids = sorted(path.name for path in phase_root.iterdir() if path.is_dir())
    if phase_root.is_dir():
        for phase_id in sorted(current_phase_ids or []):
            phase_dir = phase_root / phase_id
            if not phase_dir.is_dir():
                continue
            entries = _scan_import_dir(phase_dir, workspace_dir, depth=1)
            phase_entries[phase_id] = entries
            bindings, conflicts = _bindings_from_entries(entries, scope=f"phase:{phase_id}")
            phase_bindings[phase_id] = bindings
            phase_conflicts[phase_id] = conflicts
    return (
        {"root": root_entries, "phases": phase_entries},
        root_bindings,
        phase_bindings,
        {"root": root_conflicts, "phases": phase_conflicts},
    )


def _scan_import_dir(
    path: Path,
    workspace_dir: Path,
    *,
    depth: int,
    skip_phase: bool = False,
) -> list[dict[str, Any]]:
    files: list[Path] = []
    subdirs: list[Path] = []
    for child in sorted(path.iterdir()):
        if child.is_dir():
            if _is_archive_dir(child):
                continue
            if skip_phase and child.name == ".phase":
                continue
            subdirs.append(child)
        elif child.is_file():
            files.append(child)

    entries = _fold_batches(files, workspace_dir)
    if depth <= 0:
        return entries
    for subdir in subdirs:
        entries.append(
            {
                "kind": "dir",
                "name": subdir.name,
                "path": subdir.relative_to(workspace_dir).as_posix(),
                "entries": _scan_import_dir(subdir, workspace_dir, depth=depth - 1),
            }
        )
    return entries


def _file_entry(path: Path, workspace_dir: Path) -> dict[str, Any]:
    rel = path.relative_to(workspace_dir).as_posix()
    suffix = path.suffix.lower()
    stat = path.stat()
    entry = {
        "kind": "file",
        "path": rel,
        "name": path.name,
        "stem": _strip_version(path.stem),
        "format": _format_for_suffix(suffix),
        "content_type": _content_type_for(path),
        "size": stat.st_size,
        "sha256": _sha256_file(path),
        "fields": _fields_for_file(path),
    }
    return entry


def _format_for_suffix(suffix: str) -> str:
    if suffix in _STRUCTURED_SUFFIXES:
        return suffix.removeprefix(".") or "structured"
    if suffix in _TEXT_SUFFIXES:
        return "text"
    if suffix in _DOC_SUFFIXES:
        return "document"
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in _AUDIO_SUFFIXES:
        return "audio"
    if suffix in _VIDEO_SUFFIXES:
        return "video"
    return "binary"


def _content_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "text/markdown"
    if suffix == ".txt":
        return "text/plain"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def _strip_version(stem: str) -> str:
    return _VERSION_RE.sub("", stem)


def _batch_key(stem: str) -> tuple[str, int] | None:
    bare = _strip_version(stem)
    match = _NUMBER_RE.search(bare)
    if match is None:
        return None
    return bare[: match.start()] + "_{n}" + bare[match.end() :], int(match.group(1))


def _fold_batches(files: list[Path], workspace_dir: Path) -> list[dict[str, Any]]:
    groups: dict[str, list[tuple[int, Path]]] = {}
    singles: list[Path] = []
    for path in files:
        key = _batch_key(path.stem)
        if key is None:
            singles.append(path)
            continue
        pattern_stem, number = key
        groups.setdefault(f"{pattern_stem}{path.suffix}", []).append((number, path))

    entries: list[dict[str, Any]] = []
    for pattern, members in sorted(groups.items()):
        if len(members) < 2:
            singles.extend(path for _, path in members)
            continue
        members.sort(key=lambda item: item[0])
        numbers = [number for number, _ in members]
        first = members[0][1]
        first_entry = _file_entry(first, workspace_dir)
        field_name = _batch_field_name(pattern)
        entries.append(
            {
                "kind": "batch",
                "name": pattern,
                "stem": field_name,
                "dir": first.parent.relative_to(workspace_dir).as_posix(),
                "pattern": pattern,
                "numbers": numbers,
                "count": len(members),
                "format": first_entry["format"],
                "content_type": first_entry["content_type"],
                "fields": _batch_fields(first_entry, field_name=field_name),
            }
        )
    entries.extend(_file_entry(path, workspace_dir) for path in sorted(singles))
    return entries


def _batch_field_name(pattern: str) -> str:
    stem = Path(pattern).stem
    prefix = stem.split("{n}", 1)[0]
    return prefix.rstrip("._-") or stem


def _batch_fields(first_entry: dict[str, Any], *, field_name: str) -> list[dict[str, Any]]:
    items = first_entry.get("fields")
    item_fields = items if isinstance(items, list) else []
    return [
        {
            "name": field_name,
            "type": "array",
            "value_type": _value_type_for_entry(first_entry),
            "items": item_fields,
        }
    ]


def _fields_for_file(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, UnicodeDecodeError):
            return []
        if isinstance(data, dict):
            return [
                {"name": str(key), "type": _json_type(value), "value_type": "json", "json_path": [str(key)]}
                for key, value in data.items()
            ]
        return [{"name": _strip_version(path.stem), "type": _json_type(data), "value_type": "json"}]
    if suffix in {".jsonl", ".ndjson"}:
        return [
            {
                "name": _strip_version(path.stem),
                "type": "array",
                "value_type": "jsonl",
                "items": _jsonl_item_fields(path),
            }
        ]
    if suffix in {".csv", ".tsv"}:
        return [
            {
                "name": _strip_version(path.stem),
                "type": "array",
                "value_type": suffix.removeprefix("."),
                "items": _tabular_item_fields(path, delimiter="\t" if suffix == ".tsv" else ","),
            }
        ]
    if suffix in _TEXT_SUFFIXES:
        return [{"name": _strip_version(path.stem), "type": "string", "value_type": "string"}]
    return [{"name": _strip_version(path.stem), "type": "object", "value_type": "file_ref"}]


def _jsonl_item_fields(path: Path) -> list[dict[str, Any]]:
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            if isinstance(data, dict):
                return [
                    {"name": str(key), "type": _json_type(value)}
                    for key, value in data.items()
                ]
            return [{"name": "value", "type": _json_type(data)}]
    except (OSError, ValueError, UnicodeDecodeError):
        return []
    return []


def _tabular_item_fields(path: Path, *, delimiter: str) -> list[dict[str, Any]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh, delimiter=delimiter)
            header = next(reader, [])
    except (OSError, UnicodeDecodeError, csv.Error):
        return []
    return [{"name": str(column), "type": "string"} for column in header if str(column)]


def _json_type(value: Any) -> str:
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


def _bindings_from_entries(entries: list[dict[str, Any]], *, scope: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    candidates = _binding_candidates_from_entries(entries)
    by_normalized: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        normalized = _normalize_field_name(candidate["field"])
        by_normalized.setdefault(normalized, []).append(candidate)
    bindings: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []
    for normalized, field_candidates in sorted(by_normalized.items()):
        if len(field_candidates) == 1:
            candidate = field_candidates[0]
            bindings[candidate["field"]] = candidate["binding"]
            continue
        first = field_candidates[0]
        conflicts.append(
            {
                "field": first["field"],
                "normalized_field": normalized,
                "scope": scope,
                "candidates": [candidate["diagnostic"] for candidate in field_candidates],
            }
        )
    return bindings, conflicts


def _binding_candidates_from_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for entry in entries:
        kind = entry.get("kind")
        if kind == "dir":
            nested = entry.get("entries")
            if isinstance(nested, list):
                candidates.extend(_binding_candidates_from_entries(nested))
            continue
        if kind == "batch":
            field_name = entry.get("stem")
            if isinstance(field_name, str) and field_name:
                binding = {
                    "dir": entry.get("dir") if isinstance(entry.get("dir"), str) else None,
                    "pattern": entry.get("pattern") if isinstance(entry.get("pattern"), str) else None,
                    "numbers": entry.get("numbers") if isinstance(entry.get("numbers"), list) else None,
                    "value_type": _value_type_for_entry(entry),
                    "content_type": entry.get("content_type") if isinstance(entry.get("content_type"), str) else None,
                    "type": "array",
                }
                diagnostic = {
                    "dir": entry.get("dir") if isinstance(entry.get("dir"), str) else None,
                    "pattern": entry.get("pattern") if isinstance(entry.get("pattern"), str) else None,
                    "type": "array",
                    "value_type": _value_type_for_entry(entry),
                    "content_type": entry.get("content_type") if isinstance(entry.get("content_type"), str) else None,
                }
                candidates.append(
                    {
                        "field": field_name,
                        "binding": {key: value for key, value in binding.items() if value is not None},
                        "diagnostic": {key: value for key, value in diagnostic.items() if value is not None},
                    }
                )
            continue
        path = entry.get("path")
        fields = entry.get("fields")
        if not isinstance(path, str) or not isinstance(fields, list):
            continue
        for field in fields:
            if not isinstance(field, dict) or not isinstance(field.get("name"), str):
                continue
            binding = {
                "path": path,
                "value_type": field.get("value_type") if isinstance(field.get("value_type"), str) else "string",
                "content_type": entry.get("content_type") if isinstance(entry.get("content_type"), str) else None,
                "sha256": entry.get("sha256") if isinstance(entry.get("sha256"), str) else None,
                "type": field.get("type") if isinstance(field.get("type"), str) else None,
            }
            json_path = field.get("json_path")
            if isinstance(json_path, list) and all(isinstance(part, str) for part in json_path):
                binding["json_path"] = json_path
            diagnostic = {
                "path": path,
                "type": field.get("type") if isinstance(field.get("type"), str) else None,
                "value_type": field.get("value_type") if isinstance(field.get("value_type"), str) else "string",
                "content_type": entry.get("content_type") if isinstance(entry.get("content_type"), str) else None,
            }
            if isinstance(json_path, list) and all(isinstance(part, str) for part in json_path):
                diagnostic["json_path"] = json_path
            candidates.append(
                {
                    "field": field["name"],
                    "binding": {key: value for key, value in binding.items() if value is not None},
                    "diagnostic": {key: value for key, value in diagnostic.items() if value is not None},
                }
            )
    return candidates


def _value_type_for_entry(entry: dict[str, Any]) -> str:
    fmt = entry.get("format")
    if fmt in {"json", "jsonl", "csv", "tsv", "text"}:
        return "string" if fmt == "text" else str(fmt)
    return "file_ref"


def _is_archive_dir(path: Path) -> bool:
    return path.name.lower() in _ARCHIVE_DIR_NAMES


def _normalize_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _is_safe_phase_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value))


def _graph_phase_ids(skill_dir: Path) -> list[str]:
    graph_path = skill_dir / "GRAPH.md"
    try:
        text = graph_path.read_text(encoding="utf-8")
    except OSError:
        return []
    frontmatter = _frontmatter_block(text)
    if frontmatter is None:
        return []
    try:
        loaded = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        return []
    if not isinstance(loaded, dict):
        return []
    phases = loaded.get("phases")
    if not isinstance(phases, list):
        return []
    result: list[str] = []
    for phase in phases:
        if isinstance(phase, str):
            result.append(phase)
        elif isinstance(phase, dict):
            phase_id = phase.get("id") or phase.get("name") or phase.get("phase")
            if isinstance(phase_id, str):
                result.append(phase_id)
    return result


def _frontmatter_block(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    marker = "\n---"
    end = text.find(marker, 3)
    if end < 0:
        return None
    return text[3:end].strip()
