from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from app.core.adapters.engine import calculate_score, diff_outputs
from app.models.compare import FieldDifference, NodeGoldenResult

RUN_RESULT_FILENAME = "result.json"
LEGACY_RUN_RESULT_FILENAME = "final_state.json"


class GoldenHeadlessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_results_ref: str
    baseline_ref: str


class GoldenHeadlessResult(BaseModel):
    differences: list[FieldDifference]
    total_score: float
    golden_run_id: str
    node_results: list[NodeGoldenResult] = Field(default_factory=list)


def evaluate_golden_headless(request: GoldenHeadlessRequest) -> GoldenHeadlessResult:
    baseline_id = _baseline_id(request.baseline_ref)
    current_data = _read_json_ref(request.run_results_ref)
    golden_data = _read_json_ref(request.baseline_ref)

    current_nodes = _node_outputs(current_data)
    golden_nodes = _node_outputs(golden_data)
    if current_nodes or golden_nodes:
        return _compare_node_outputs(current_nodes, golden_nodes, golden_run_id=baseline_id)

    differences, score = _field_differences(
        current_data,
        golden_data,
        path_prefix="output",
    )
    node_result = NodeGoldenResult(
        node_id="output",
        verdict="pass" if not differences else "fail",
        score=score,
        differences=differences,
    )
    return GoldenHeadlessResult(
        differences=differences,
        total_score=round(score * 100, 2),
        golden_run_id=baseline_id,
        node_results=[node_result],
    )


def _compare_node_outputs(
    current_nodes: dict[str, dict[str, Any]],
    golden_nodes: dict[str, dict[str, Any]],
    *,
    golden_run_id: str,
) -> GoldenHeadlessResult:
    node_results: list[NodeGoldenResult] = []
    differences: list[FieldDifference] = []
    ordered_node_ids = [*current_nodes]
    ordered_node_ids.extend(node_id for node_id in golden_nodes if node_id not in current_nodes)

    for node_id in ordered_node_ids:
        node_diffs, node_score = _field_differences(
            current_nodes.get(node_id, {}),
            golden_nodes.get(node_id, {}),
            path_prefix=f"nodes.{node_id}",
        )
        differences.extend(node_diffs)
        node_results.append(
            NodeGoldenResult(
                node_id=node_id,
                verdict="pass" if not node_diffs else "fail",
                score=node_score,
                differences=node_diffs,
            )
        )

    total_score = 100.0
    if node_results:
        total_score = round(sum(node.score for node in node_results) / len(node_results) * 100, 2)
    return GoldenHeadlessResult(
        differences=differences,
        total_score=total_score,
        golden_run_id=golden_run_id,
        node_results=node_results,
    )


def _node_outputs(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    phases = payload.get("phases")
    if not isinstance(phases, list):
        return {}
    nodes: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(phases):
        if not isinstance(item, dict):
            continue
        node_id = item.get("phase_name") or item.get("name") or item.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            node_id = f"node_{index}"
        outputs: Any = item.get("outputs")
        if not isinstance(outputs, dict):
            outputs = item.get("context") if isinstance(item.get("context"), dict) else {}
        nodes[node_id] = cast(dict[str, Any], outputs)
    return nodes


def _field_differences(
    current_value: Any,
    golden_value: Any,
    *,
    path_prefix: str,
) -> tuple[list[FieldDifference], float]:
    score = calculate_score(current_value, golden_value)
    differences: list[FieldDifference] = []
    for item in diff_outputs(current_value, golden_value, path_prefix):
        actual = item.get("actual")
        expected = item.get("expected")
        value = actual if actual is not None else expected
        differences.append(
            FieldDifference(
                field_path=str(item.get("path") or path_prefix),
                type=_diff_type(value),
                current_value=actual,
                golden_value=expected,
                score=score,
                changed=True,
            )
        )
    return differences, score


def _diff_type(value: Any) -> Literal["text", "number", "bool", "list", "dict", "null", "unknown"]:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "text"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    if value is None:
        return "null"
    return "unknown"


def _read_json_ref(ref: str) -> Any:
    path = _find_file(ref)
    if not path.exists():
        raise FileNotFoundError(f"Run results file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _find_file(ref: str) -> Path:
    ref_path = _safe_ref_path(ref)
    if ref_path.exists():
        return ref_path

    from app.core import config

    candidates: list[Path] = []
    storage_root = _storage_root()
    candidates.append(_safe_join(storage_root, ref_path))
    candidates.append(_safe_join(Path("."), ref_path))

    parts = ref_path.parts
    skill_id = parts[0] if len(parts) >= 3 and parts[0] not in {"runs", "golden"} else None
    if skill_id:
        suffix = Path(*parts[1:])
        candidates.append(_safe_join(config.SKILLS_DIR / skill_id / ".workspace", suffix))
        candidates.append(_safe_join(config.SKILLS_DIR / skill_id, suffix))

    for candidate in candidates:
        if candidate.exists():
            return candidate
        if candidate.name == RUN_RESULT_FILENAME:
            legacy_candidate = candidate.with_name(LEGACY_RUN_RESULT_FILENAME)
            if legacy_candidate.exists():
                return legacy_candidate
    return ref_path


def _safe_ref_path(ref: str) -> Path:
    if not ref or "\\" in ref:
        raise ValueError(f"Invalid artifact ref: {ref}")
    ref_path = Path(ref)
    if ref_path.is_absolute():
        return ref_path.resolve(strict=False)
    posix_path = PurePosixPath(ref)
    if posix_path.is_absolute() or any(part in {"", ".", ".."} for part in posix_path.parts):
        raise ValueError(f"Invalid artifact ref: {ref}")
    return Path(*posix_path.parts)


def _safe_join(root: Path, relative_path: Path) -> Path:
    if relative_path.is_absolute():
        return relative_path
    root_resolved = root.resolve(strict=False)
    candidate = root_resolved.joinpath(relative_path).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Invalid artifact ref: {relative_path}") from exc
    return candidate


def _storage_root() -> Path:
    from app.core import config

    if hasattr(config, "settings") and hasattr(config.settings, "storage_root"):
        return Path(config.settings.storage_root)
    return config.WORKSPACES_DIR / "default"


def _baseline_id(baseline_ref: str) -> str:
    match = re.search(r"golden/([^/]+)", baseline_ref)
    if match:
        return match.group(1)
    path = Path(baseline_ref)
    if path.parent.name:
        return path.parent.name
    return "unknown"


def resolve_existing_run_result_file(run_dir: Path) -> Path:
    for filename in (RUN_RESULT_FILENAME, LEGACY_RUN_RESULT_FILENAME):
        # codeql[py/path-injection] run_dir is produced by run_dir_for, which validates the run id segment.
        path = run_dir / filename
        if path.exists():
            return path
    return run_dir / RUN_RESULT_FILENAME
