from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.adapters.engine import GoldenInputRef, RunResultSnapshot, calculate_score, diff_outputs
from app.core.exceptions import error_response
from app.models.compare import FieldDifference, NodeGoldenGroup

RUN_RESULT_FILENAME = "result.json"
STORE_RUN_RESULT_FILENAMES = (RUN_RESULT_FILENAME,)

GoldenHeadlessRequest = GoldenInputRef


class GoldenHeadlessResult(BaseModel):
    baseline_id: str
    source_run_id: str | None = None
    source_run_results_ref: str | None = None
    baseline_ref: str
    run_results_ref: str
    total_score: float
    node_groups: list[NodeGoldenGroup] = Field(default_factory=list)


def evaluate_golden_headless(request: GoldenInputRef) -> GoldenHeadlessResult:
    run_results_ref = request.run_results_ref.uri
    snapshot_payload = _read_current_run_results_ref(run_results_ref)
    snapshot = _snapshot_from_payload(snapshot_payload, ref=run_results_ref)
    _validate_snapshot_run_results_ref(snapshot, run_results_ref)
    current_nodes = _snapshot_node_outputs(snapshot, run_results_ref)
    baseline = _read_baseline_contract(request.baseline_ref)

    return _compare_node_outputs(
        current_nodes,
        baseline.cases,
        baseline_id=baseline.baseline_id,
        source_run_id=baseline.source_run_id,
        source_run_results_ref=baseline.source_run_results_ref,
        baseline_ref=request.baseline_ref,
        run_results_ref=run_results_ref,
    )


def persist_compare_result_for_golden(
    skill_id: str,
    result: GoldenHeadlessResult,
) -> str:
    """Persist a reusable compare fact under the Golden-owned workspace tree."""

    from app.services.skills import resolve_skill_dir, validate_run_id_segment

    parsed_run_ref = _parse_run_store_ref(result.run_results_ref)
    if parsed_run_ref is None or parsed_run_ref[0] != skill_id:
        _raise_golden_error(
            "golden.run_result_invalid",
            422,
            f"Run results ref does not belong to skill: {result.run_results_ref}",
            {"skill_id": skill_id, "ref": result.run_results_ref},
        )
    run_id = validate_run_id_segment(parsed_run_ref[1])
    baseline_id = validate_run_id_segment(result.baseline_id)
    compare_dir = resolve_skill_dir(skill_id) / ".workspace" / "golden" / baseline_id / "compare" / run_id
    compare_dir.mkdir(parents=True, exist_ok=True)
    (compare_dir / "compare_result.json").write_text(
        result.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return f"{skill_id}/golden/{baseline_id}/compare/{run_id}/compare_result.json"


def golden_headless_request_from_ref(run_results_ref: str, baseline_ref: str) -> GoldenInputRef:
    """Adapt a Studio artifact ref string into the Engine-owned golden input contract."""
    snapshot_payload = _read_current_run_results_ref(run_results_ref)
    snapshot = _snapshot_from_payload(snapshot_payload, ref=run_results_ref)
    _validate_snapshot_run_results_ref(snapshot, run_results_ref)
    return GoldenInputRef(
        run_results_ref=snapshot.run_results_ref,
        baseline_ref=baseline_ref,
    )


class _CurrentNodeOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    phase_id: str | None = None
    output: dict[str, Any]


class _BaselineCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    phase_id: str | None = None
    expected_output: dict[str, Any]


class _BaselineContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    baseline_id: str
    source_run_id: str | None = None
    source_run_results_ref: str | None = None
    cases: dict[str, _BaselineCase]


def _compare_node_outputs(
    current_nodes: dict[str, _CurrentNodeOutput],
    golden_nodes: dict[str, _BaselineCase],
    *,
    baseline_id: str,
    source_run_id: str | None,
    source_run_results_ref: str | None,
    baseline_ref: str,
    run_results_ref: str,
) -> GoldenHeadlessResult:
    node_groups: list[NodeGoldenGroup] = []
    ordered_node_ids = [*golden_nodes]
    ordered_node_ids.extend(node_id for node_id in current_nodes if node_id not in golden_nodes)

    for node_id in ordered_node_ids:
        current = current_nodes.get(node_id)
        golden = golden_nodes.get(node_id)
        current_value = current.output if current is not None else {}
        golden_value = golden.expected_output if golden is not None else {}
        node_diffs, node_score = _field_differences(
            current_value,
            golden_value,
            path_prefix=f"nodes.{node_id}",
        )
        stale_fields = [
            diff.field_path
            for diff in node_diffs
            if diff.current_value is None or diff.golden_value is None
        ]
        schema_status = "valid"
        if current is None:
            schema_status = "missing"
        elif golden is None or stale_fields:
            schema_status = "stale"
        node_groups.append(
            NodeGoldenGroup(
                node_id=node_id,
                phase_id=(golden.phase_id if golden is not None else current.phase_id if current is not None else None),
                status="pass" if not node_diffs and current is not None and golden is not None else "fail",
                score=node_score,
                field_differences=node_diffs,
                stale_fields=stale_fields,
                schema_status=cast(Any, schema_status),
                baseline_ref=baseline_ref,
                run_results_ref=run_results_ref,
            )
        )

    total_score = 100.0
    if node_groups:
        total_score = round(sum(node.score for node in node_groups) / len(node_groups) * 100, 2)
    return GoldenHeadlessResult(
        baseline_id=baseline_id,
        source_run_id=source_run_id,
        source_run_results_ref=source_run_results_ref,
        baseline_ref=baseline_ref,
        run_results_ref=run_results_ref,
        total_score=total_score,
        node_groups=node_groups,
    )


def _snapshot_from_payload(payload: Any, *, ref: str) -> RunResultSnapshot:
    try:
        snapshot = RunResultSnapshot.model_validate(payload)
    except Exception as exc:
        _raise_golden_error(
            "golden.run_result_invalid",
            422,
            f"Run result snapshot is invalid: {ref}",
            {"ref": ref, "error": str(exc)},
        )
    if not snapshot.node_results:
        _raise_golden_error(
            "golden.run_result_invalid",
            422,
            f"Run result snapshot has no node results: {ref}",
            {"ref": ref, "field": "node_results"},
        )
    return snapshot


def _snapshot_node_outputs(snapshot: RunResultSnapshot, run_results_ref: str) -> dict[str, _CurrentNodeOutput]:
    nodes: dict[str, _CurrentNodeOutput] = {}
    parsed_run_ref = _parse_run_store_ref(run_results_ref)
    if parsed_run_ref is None:
        _raise_golden_error(
            "golden.run_result_invalid",
            422,
            f"Run results must be read from sealed RunArtifactStore refs: {run_results_ref}",
            {"ref": run_results_ref},
        )
    default_skill_id, default_run_id, _object_path = parsed_run_ref
    for node in snapshot.node_results:
        node_id = node.agent_node_id
        output = _read_node_output_ref(
            node.outputs_ref,
            default_skill_id=default_skill_id,
            default_run_id=default_run_id,
            run_results_ref=run_results_ref,
        )
        nodes[node_id] = _CurrentNodeOutput(
            node_id=node_id,
            phase_id=node_id,
            output=output if isinstance(output, dict) else {"value": output},
        )
    return nodes


def _validate_snapshot_run_results_ref(snapshot: RunResultSnapshot, run_results_ref: str) -> None:
    parsed_run_ref = _parse_run_store_ref(run_results_ref)
    if parsed_run_ref is None:
        _raise_golden_error(
            "golden.run_result_invalid",
            422,
            f"Run results must be read from sealed RunArtifactStore refs: {run_results_ref}",
            {"ref": run_results_ref},
        )
    expected_skill_id, expected_run_id, _object_path = parsed_run_ref
    embedded_ref = snapshot.run_results_ref
    embedded_parsed = _parse_run_store_ref(embedded_ref.uri)
    if (
        embedded_ref.uri != run_results_ref
        or embedded_ref.run_id != expected_run_id
        or embedded_parsed is None
        or embedded_parsed[0] != expected_skill_id
        or embedded_parsed[1] != expected_run_id
    ):
        _raise_golden_error(
            "golden.run_result_invalid",
            422,
            f"Run result snapshot ref does not match sealed ref: {run_results_ref}",
            {
                "ref": run_results_ref,
                "embedded_ref": embedded_ref.uri,
                "field": "run_results_ref",
                "expected_run_id": expected_run_id,
                "embedded_run_id": embedded_ref.run_id,
            },
        )


def _read_node_output_ref(
    ref: str,
    *,
    default_skill_id: str,
    default_run_id: str,
    run_results_ref: str,
) -> Any:
    parsed_ref = _parse_run_store_ref(ref)
    if parsed_ref is None:
        parsed_ref = (
            default_skill_id,
            default_run_id,
            _safe_relative_run_object_path(ref, run_results_ref=run_results_ref),
        )
    elif parsed_ref[0] != default_skill_id or parsed_ref[1] != default_run_id:
        _raise_golden_error(
            "golden.run_result_invalid",
            422,
            f"Node output ref does not belong to sealed run: {ref}",
            {
                "ref": run_results_ref,
                "embedded_ref": ref,
                "field": "node_results.outputs_ref",
                "expected_skill_id": default_skill_id,
                "expected_run_id": default_run_id,
                "embedded_skill_id": parsed_ref[0],
                "embedded_run_id": parsed_ref[1],
            },
        )
    skill_id, run_id, object_path = parsed_ref
    return _read_run_store_json_ref(f"{skill_id}/runs/{run_id}/{object_path}")


def _safe_relative_run_object_path(ref: str, *, run_results_ref: str) -> str:
    if not ref or "\\" in ref:
        _raise_golden_error(
            "golden.run_result_invalid",
            422,
            f"Node output ref is invalid: {ref}",
            {"ref": run_results_ref, "embedded_ref": ref, "field": "node_results.outputs_ref"},
        )
    posix_path = PurePosixPath(ref)
    if posix_path.is_absolute() or any(part in {"", ".", ".."} for part in posix_path.parts):
        _raise_golden_error(
            "golden.run_result_invalid",
            422,
            f"Node output ref is invalid: {ref}",
            {"ref": run_results_ref, "embedded_ref": ref, "field": "node_results.outputs_ref"},
        )
    return "/".join(posix_path.parts)


def _read_baseline_contract(ref: str) -> _BaselineContract:
    payload = _read_baseline_json_ref(ref)
    if not isinstance(payload, dict):
        _raise_golden_error(
            "golden.baseline_invalid",
            422,
            f"Golden baseline is invalid: {ref}",
            {"ref": ref, "field": "baseline"},
        )
    expected_baseline_id = _baseline_id(ref)
    baseline_id = payload.get("baseline_id")
    if isinstance(baseline_id, str) and baseline_id:
        if baseline_id != expected_baseline_id:
            _raise_golden_error(
                "golden.baseline_invalid",
                422,
                f"Golden baseline id does not match ref: {ref}",
                {
                    "ref": ref,
                    "field": "baseline_id",
                    "expected_baseline_id": expected_baseline_id,
                    "embedded_baseline_id": baseline_id,
                },
            )
    else:
        baseline_id = expected_baseline_id
    source_run_id = payload.get("source_run_id")
    source_run_results_ref = payload.get("source_run_results_ref")
    cases_payload = payload.get("cases")
    if not isinstance(cases_payload, list):
        _raise_golden_error(
            "golden.baseline_invalid",
            422,
            f"Golden baseline cases are invalid: {ref}",
            {"ref": ref, "field": "cases"},
        )
    cases: dict[str, _BaselineCase] = {}
    for item in cases_payload:
        if not isinstance(item, dict):
            _raise_golden_error(
                "golden.baseline_invalid",
                422,
                f"Golden baseline case is invalid: {ref}",
                {"ref": ref, "field": "cases"},
            )
        case_ref = item.get("expected_output_ref") or item.get("case_ref")
        case_payload = item
        if isinstance(case_ref, str) and case_ref:
            case_payload = _read_baseline_json_ref(_join_baseline_ref(ref, case_ref))
        if not isinstance(case_payload, dict):
            _raise_golden_error(
                "golden.baseline_invalid",
                422,
                f"Golden baseline case is invalid: {ref}",
                {"ref": ref, "case_ref": case_ref},
            )
        node_id = case_payload.get("node_id") or item.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            _raise_golden_error(
                "golden.baseline_invalid",
                422,
                f"Golden baseline case missing node_id: {ref}",
                {"ref": ref, "case_ref": case_ref},
            )
        phase_id = case_payload.get("phase_id") or item.get("phase_id") or node_id
        expected_output = case_payload.get("expected_output", case_payload.get("outputs"))
        if not isinstance(expected_output, dict):
            _raise_golden_error(
                "golden.baseline_invalid",
                422,
                f"Golden baseline case missing expected output: {ref}",
                {"ref": ref, "case_ref": case_ref, "node_id": node_id},
            )
        cases[node_id] = _BaselineCase(
            node_id=node_id,
            phase_id=phase_id if isinstance(phase_id, str) else node_id,
            expected_output=expected_output,
        )
    return _BaselineContract(
        baseline_id=baseline_id,
        source_run_id=source_run_id if isinstance(source_run_id, str) else None,
        source_run_results_ref=source_run_results_ref if isinstance(source_run_results_ref, str) else None,
        cases=cases,
    )


def _join_baseline_ref(baseline_ref: str, child_ref: str) -> str:
    child_path = PurePosixPath(child_ref)
    if (
        not child_ref
        or "\\" in child_ref
        or child_path.is_absolute()
        or len(child_path.parts) != 2
        or child_path.parts[0] != "cases"
        or any(part in {"", ".", ".."} for part in child_path.parts)
        or child_path.suffix != ".json"
    ):
        _raise_golden_error(
            "golden.baseline_invalid",
            422,
            f"Golden baseline case ref is invalid: {child_ref}",
            {"ref": baseline_ref, "case_ref": child_ref},
        )

    baseline_dir = _find_file(baseline_ref).parent.resolve(strict=False)
    candidate = baseline_dir.joinpath(*child_path.parts).resolve(strict=False)
    try:
        candidate.relative_to(baseline_dir)
    except ValueError:
        _raise_golden_error(
            "golden.baseline_invalid",
            422,
            f"Golden baseline case ref escapes baseline directory: {child_ref}",
            {"ref": baseline_ref, "case_ref": child_ref, "baseline_dir": str(baseline_dir)},
        )
    return str(candidate)


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


def _read_current_run_results_ref(ref: str) -> Any:
    store_payload = _read_run_store_json_ref(ref)
    if store_payload is not None:
        return store_payload

    path = _find_file(ref)
    if path.exists() and _looks_like_mutable_run_result_path(path):
        _raise_golden_error(
            "golden.run_results_mutable_ref",
            422,
            f"Run results must be read from sealed RunArtifactStore refs: {ref}",
            {"ref": ref, "resolved_path": str(path)},
        )
    _raise_golden_error(
        "golden.run_result_invalid",
        422,
        f"Run results must be read from sealed RunArtifactStore refs: {ref}",
        {"ref": ref, "resolved_path": str(path)},
    )


def _read_baseline_json_ref(ref: str) -> Any:
    path = _find_file(ref)
    if not path.exists():
        _raise_golden_error(
            "golden.baseline_not_found",
            404,
            f"Golden baseline not found: {ref}",
            {"ref": ref, "resolved_path": str(path)},
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _raise_golden_error(
            "golden.baseline_invalid",
            422,
            f"Golden baseline JSON is invalid: {path}",
            {"ref": ref, "resolved_path": str(path), "error": str(exc)},
        )


def _read_run_store_json_ref(ref: str) -> Any | None:
    parsed = _parse_run_store_ref(ref)
    if parsed is None:
        return None
    skill_id, run_id, object_path = parsed
    try:
        from app.core.adapters.http_transport import StudioAdapterError
        from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
        from app.services.skills import resolve_skill_dir

        skill_dir = resolve_skill_dir(skill_id)
        raw = LocalRunArtifactStore(root=skill_dir / ".workspace").get_run_object(run_id, object_path)
    except StudioAdapterError as exc:
        _raise_artifact_error(exc, ref=ref, run_id=run_id, path=object_path)
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _raise_golden_error(
            "golden.run_result_invalid",
            422,
            f"Run result JSON is invalid: {ref}",
            {"ref": ref, "run_id": run_id, "path": object_path, "error": str(exc)},
        )
    return loaded


def read_run_result_payload_for_golden(skill_id: str, run_id: str) -> tuple[str, str]:
    """Read the golden source payload from sealed RunArtifactStore objects."""
    last_error: HTTPException | None = None
    for filename in STORE_RUN_RESULT_FILENAMES:
        ref = f"{skill_id}/runs/{run_id}/{filename}"
        try:
            payload = _read_run_store_json_ref(ref)
        except HTTPException as exc:
            last_error = exc
            if _is_missing_candidate_path(exc):
                continue
            raise
        if payload is not None:
            return ref, json.dumps(payload, ensure_ascii=False, default=str)

    if last_error is not None:
        raise last_error
    _raise_golden_error(
        "golden.run_results_not_found",
        404,
        f"Run results not found: {run_id}",
        {"skill_id": skill_id, "run_id": run_id},
    )


def read_run_result_snapshot_for_golden(
    skill_id: str,
    run_id: str,
) -> tuple[str, RunResultSnapshot, dict[str, dict[str, Any]]]:
    """Read a sealed RunResultSnapshot and dereference its per-node outputs."""
    ref, result_content = read_run_result_payload_for_golden(skill_id, run_id)
    try:
        payload = json.loads(result_content)
    except json.JSONDecodeError as exc:
        _raise_golden_error(
            "golden.run_result_invalid",
            422,
            f"Run result JSON is invalid: {ref}",
            {"ref": ref, "run_id": run_id, "path": RUN_RESULT_FILENAME, "error": str(exc)},
        )
    snapshot = _snapshot_from_payload(payload, ref=ref)
    nodes = _snapshot_node_outputs(snapshot, ref)
    return ref, snapshot, {node_id: node.output for node_id, node in nodes.items()}


def _parse_run_store_ref(ref: str) -> tuple[str, str, str] | None:
    if not ref or "\\" in ref:
        return None
    posix_path = PurePosixPath(ref)
    if posix_path.is_absolute() or any(part in {"", ".", ".."} for part in posix_path.parts):
        return None
    parts = posix_path.parts
    if len(parts) < 4 or parts[1] != "runs":
        return None
    return parts[0], parts[2], "/".join(parts[3:])


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
        # Workspace skills (the writable ones you actually run/promote) keep their
        # run/golden artifacts under WORKSPACES_DIR, not SKILLS_DIR. Resolve the
        # real skill dir so compare finds them there too — otherwise golden
        # compare fails for every runnable skill.
        try:
            from app.services.skills import resolve_skill_dir

            resolved_skill_dir: Path | None = resolve_skill_dir(skill_id)
        except Exception:  # noqa: BLE001 — fall back to the SKILLS_DIR candidates below
            resolved_skill_dir = None
        if resolved_skill_dir is not None:
            candidates.append(_safe_join(resolved_skill_dir / ".workspace", suffix))
            candidates.append(_safe_join(resolved_skill_dir, suffix))

    for candidate in candidates:
        if candidate.exists():
            return candidate
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


def _looks_like_mutable_run_result_path(path: Path) -> bool:
    parts = path.parts
    return path.name in STORE_RUN_RESULT_FILENAMES and "runs" in parts


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
    for filename in STORE_RUN_RESULT_FILENAMES:
        # codeql[py/path-injection] run_dir is produced by run_dir_for, which validates the run id segment.
        path = run_dir / filename
        if path.exists():
            return path
    return run_dir / RUN_RESULT_FILENAME


def _raise_golden_error(
    error_code: str,
    http_status: int,
    message: str,
    details: dict[str, Any],
) -> None:
    response = error_response(
        error_code=error_code,
        http_status=http_status,
        message=message,
        details=details,
        retry_strategy="not_retryable",
    )
    raise HTTPException(status_code=http_status, detail=response.model_dump())


def _raise_artifact_error(
    exc: Exception,
    *,
    ref: str,
    run_id: str,
    path: str,
) -> None:
    error_code = getattr(exc, "error_code", "artifact.read_failed")
    payload = getattr(exc, "error_payload", {})
    details = payload if isinstance(payload, dict) else {"detail": str(payload)}
    details = {"ref": ref, "run_id": run_id, "path": path, **details}
    mapped_code = {
        "artifact.not_found": "golden.run_results_not_found",
        "artifact.hash_mismatch": "golden.hash_mismatch",
        "artifact.run_not_sealed": "golden.run_results_unsealed",
        "artifact.corrupt_manifest": "golden.run_result_invalid",
        "artifact.invalid_hash": "golden.run_result_invalid",
        "artifact.invalid_run_id": "golden.run_result_invalid",
    }.get(str(error_code), f"golden.{error_code}")
    status = 404 if error_code == "artifact.not_found" else 422
    if error_code == "artifact.run_not_sealed":
        status = 409
    _raise_golden_error(
        mapped_code,
        status,
        f"Golden run artifact read failed: {error_code}",
        details,
    )


def _http_error_code(exc: HTTPException) -> str | None:
    detail = exc.detail
    if isinstance(detail, dict):
        value = detail.get("error_code")
        return value if isinstance(value, str) else None
    return None


def _http_error_details(exc: HTTPException) -> dict[str, Any]:
    detail = exc.detail
    if not isinstance(detail, dict):
        return {}
    details = detail.get("details")
    return details if isinstance(details, dict) else {}


def _is_missing_candidate_path(exc: HTTPException) -> bool:
    if _http_error_code(exc) != "golden.run_results_not_found":
        return False
    details = _http_error_details(exc)
    return "hash" not in details
