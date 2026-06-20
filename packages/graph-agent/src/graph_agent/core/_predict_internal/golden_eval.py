"""Engine-local helper for Golden baseline evaluation."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import ErrorPayload
from graph_agent.core.runner import run_skill
from graph_agent.core.skill_resolver_protocol import SkillResolverProtocol

_GOLDEN_STALE_FIELDS_CODE = "[F-v3-golden-stale-fields]"


def _changed_diff(path: str, *, actual: Any, expected: Any) -> dict[str, Any]:
    return {
        "path": path,
        "expected": expected,
        "actual": actual,
        "status": "changed",
    }


def _field_path(path_prefix: str, key: str) -> str:
    return f"{path_prefix}.{key}" if path_prefix else key


def _diff_dict_outputs(
    actual: dict[Any, Any],
    expected: dict[Any, Any],
    path_prefix: str,
) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for key in sorted(set(actual.keys()) | set(expected.keys())):
        key_path = _field_path(path_prefix, str(key))
        if key not in expected:
            diffs.append(_changed_diff(key_path, actual=actual[key], expected=None))
            continue
        if key not in actual:
            diffs.append(_changed_diff(key_path, actual=None, expected=expected[key]))
            continue
        diffs.extend(diff_outputs(actual[key], expected[key], key_path))
    return diffs


def _diff_list_outputs(
    actual: list[Any],
    expected: list[Any],
    path_prefix: str,
) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for index in range(max(len(actual), len(expected))):
        current_path = f"{path_prefix}[{index}]"
        actual_value = actual[index] if index < len(actual) else None
        expected_value = expected[index] if index < len(expected) else None
        diffs.extend(diff_outputs(actual_value, expected_value, current_path))
    return diffs


def diff_outputs(actual: Any, expected: Any, path_prefix: str = "") -> list[dict[str, Any]]:
    if actual == expected:
        return []

    if isinstance(actual, dict) and isinstance(expected, dict):
        return _diff_dict_outputs(actual, expected, path_prefix)

    if isinstance(actual, list) and isinstance(expected, list):
        return _diff_list_outputs(actual, expected, path_prefix)

    return [_changed_diff(path_prefix, actual=actual, expected=expected)]


def _mean_score(scores: list[float]) -> float:
    if not scores:
        return 1.0
    return sum(scores) / len(scores)


def _dict_score(actual: dict[Any, Any], expected: dict[Any, Any]) -> float:
    keys = set(actual.keys()) | set(expected.keys())
    return _mean_score([calculate_score(actual.get(key), expected.get(key)) for key in keys])


def _list_score(actual: list[Any], expected: list[Any]) -> float:
    scores = []
    for index in range(max(len(actual), len(expected))):
        actual_value = actual[index] if index < len(actual) else None
        expected_value = expected[index] if index < len(expected) else None
        scores.append(calculate_score(actual_value, expected_value))
    return _mean_score(scores)


def _numeric_score(actual: int | float, expected: int | float) -> float:
    denominator = max(abs(actual), abs(expected), 1.0)
    return max(0.0, 1.0 - (abs(actual - expected) / denominator))


def calculate_score(actual: Any, expected: Any) -> float:
    if actual == expected:
        return 1.0
    if isinstance(actual, dict) and isinstance(expected, dict):
        return _dict_score(actual, expected)
    if isinstance(actual, list) and isinstance(expected, list):
        return _list_score(actual, expected)
    if isinstance(actual, str) and isinstance(expected, str):
        return SequenceMatcher(None, expected, actual).ratio()
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return _numeric_score(actual, expected)
    return 0.0


def extract_actual_output(context: dict[str, Any], phase_id: str, expected_keys: list[str]) -> dict[str, Any]:
    phase_outputs = context.get("phase_outputs", {})
    if isinstance(phase_outputs, dict) and phase_id in phase_outputs:
        val = phase_outputs[phase_id]
        if isinstance(val, dict):
            return val

    try:
        from graph_agent.core.state import BusinessData
        bd = BusinessData.model_validate(context)
        val = bd["phase_outputs"].get(phase_id)
        if isinstance(val, dict) and val:
            return val
    except Exception:
        pass

    fallback = {}
    for k in expected_keys:
        if k in context:
            fallback[k] = context[k]
    return fallback


def get_required_outputs(compiled_skill: Any, phase_id: str) -> list[str]:
    for doc in compiled_skill.nodes:
        if doc.phase_name == phase_id:
            io = doc.frontmatter.get("io") or {}
            outputs = io.get("outputs") or {}
            required = outputs.get("required")
            if isinstance(required, list):
                return [str(x) for x in required]
            break
    return []


def _output_fields(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    return sorted(str(key) for key in payload)


def _stale_fields(expected_output: Any, required_outputs: list[str]) -> list[str]:
    if not isinstance(expected_output, dict):
        return list(required_outputs)
    return [field for field in required_outputs if field not in expected_output]


def _golden_stale_fields_error(
    *,
    baseline_id: str,
    case_id: str,
    phase_id: str,
    case_file: Path,
    expected_output: Any,
    required_outputs: list[str],
    stale_fields: list[str],
) -> dict[str, Any]:
    payload = ErrorPayload(
        code=_GOLDEN_STALE_FIELDS_CODE,
        message=(
            "Golden expected output is missing required output fields "
            f"for phase {phase_id!r}: {', '.join(stale_fields)}"
        ),
        phase_id=phase_id,
        field_path="expected_output",
        source_path=str(case_file),
        details={
            "baseline_id": baseline_id,
            "case_id": case_id,
            "phase_id": phase_id,
            "stale_fields": stale_fields,
            "required_output_fields": list(required_outputs),
            "expected_output_fields": _output_fields(expected_output),
        },
    )
    return payload.model_dump(mode="json")


def evaluate_golden_baseline_impl(
    skill_path: str | Path,
    *,
    workspace_dir: Path,
    baseline_id: str,
    skill_resolver: SkillResolverProtocol,
    model_resolver: Any | None = None,
) -> dict[str, Any]:
    baseline_dir = workspace_dir / "golden" / baseline_id
    baseline_file = baseline_dir / "baseline.json"
    if not baseline_file.is_file():
        raise FileNotFoundError(f"baseline file not found: {baseline_file}")

    with open(baseline_file, encoding="utf-8") as f:
        baseline_data = json.load(f)

    case_ids = baseline_data.get("case_ids", [])
    cases = []
    for case_id in case_ids:
        case_file = baseline_dir / "cases" / f"{case_id}.json"
        if not case_file.is_file():
            raise FileNotFoundError(f"case file not found: {case_file}")
        with open(case_file, encoding="utf-8") as f:
            cases.append((case_file, json.load(f)))

    # Compile the skill using compiler
    compiled_skill = compile_skill(skill_path, skill_resolver=skill_resolver)

    evaluated_cases = []
    passed_count = 0
    failed_count = 0
    stale_count = 0

    for case_file, case in cases:
        case_id = case["case_id"]
        phase_id = case["phase_id"]
        inputs = case["inputs"]
        expected_output = case.get("expected_output") or {}

        # 检查是否过期(stale)
        required_outputs = get_required_outputs(compiled_skill, phase_id)
        stale_fields = _stale_fields(expected_output, required_outputs)
        error = None

        if stale_fields:
            status = "stale"
            score = 0.0
            diff = []
            error = _golden_stale_fields_error(
                baseline_id=baseline_id,
                case_id=case_id,
                phase_id=phase_id,
                case_file=case_file,
                expected_output=expected_output,
                required_outputs=required_outputs,
                stale_fields=stale_fields,
            )
            stale_count += 1
        else:
            # 运行 skill 获得实际输出
            res = run_skill(
                skill_path,
                workspace_dir=workspace_dir,
                skill_resolver=skill_resolver,
                model_resolver=model_resolver,
                cleanup_checkpoints_on_finish=True,
                **inputs
            )

            actual_output = extract_actual_output(res.context, phase_id, _output_fields(expected_output))
            diff = diff_outputs(actual_output, expected_output)
            score = calculate_score(actual_output, expected_output)

            if diff:
                status = "failed"
                failed_count += 1
            else:
                status = "passed"
                passed_count += 1

        evaluated_cases.append({
            "case_id": case_id,
            "phase_id": phase_id,
            "status": status,
            "score": score,
            "diff": diff,
            "stale_fields": stale_fields,
            "error": error,
        })

    report = {
        "baseline_id": baseline_id,
        "summary": {
            "total_cases": len(cases),
            "passed": passed_count,
            "failed": failed_count,
            "stale": stale_count,
        },
        "cases": evaluated_cases,
    }

    # 写盘
    report_file = baseline_dir / "report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report
