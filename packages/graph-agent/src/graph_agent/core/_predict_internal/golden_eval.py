"""Engine-local helper for Golden baseline evaluation."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from graph_agent.core.compiler import compile_skill
from graph_agent.core.runner import run_skill
from graph_agent.core.skill_resolver_protocol import SkillResolverProtocol


def diff_outputs(actual: Any, expected: Any, path_prefix: str = "") -> list[dict[str, Any]]:
    if actual == expected:
        return []

    if isinstance(actual, dict) and isinstance(expected, dict):
        diffs = []
        all_keys = sorted(set(actual.keys()) | set(expected.keys()))
        for k in all_keys:
            current_path = f"{path_prefix}.{k}" if path_prefix else k
            if k not in expected:
                diffs.append({
                    "path": current_path,
                    "expected": None,
                    "actual": actual[k],
                    "status": "changed"
                })
            elif k not in actual:
                diffs.append({
                    "path": current_path,
                    "expected": expected[k],
                    "actual": None,
                    "status": "changed"
                })
            else:
                diffs.extend(diff_outputs(actual[k], expected[k], current_path))
        return diffs

    if isinstance(actual, list) and isinstance(expected, list):
        diffs = []
        for i in range(max(len(actual), len(expected))):
            current_path = f"{path_prefix}[{i}]"
            act_val = actual[i] if i < len(actual) else None
            exp_val = expected[i] if i < len(expected) else None
            diffs.extend(diff_outputs(act_val, exp_val, current_path))
        return diffs

    return [{
        "path": path_prefix,
        "expected": expected,
        "actual": actual,
        "status": "changed"
    }]


def calculate_score(actual: Any, expected: Any) -> float:
    if actual == expected:
        return 1.0
    if isinstance(actual, dict) and isinstance(expected, dict):
        all_keys = set(actual.keys()) | set(expected.keys())
        if not all_keys:
            return 1.0
        scores = []
        for k in all_keys:
            scores.append(calculate_score(actual.get(k), expected.get(k)))
        return sum(scores) / len(scores)
    if isinstance(actual, list) and isinstance(expected, list):
        if not actual and not expected:
            return 1.0
        scores = []
        for i in range(max(len(actual), len(expected))):
            act_val = actual[i] if i < len(actual) else None
            exp_val = expected[i] if i < len(expected) else None
            scores.append(calculate_score(act_val, exp_val))
        return sum(scores) / len(scores)
    if isinstance(actual, str) and isinstance(expected, str):
        return SequenceMatcher(None, expected, actual).ratio()
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        denominator = max(abs(actual), abs(expected), 1.0)
        return max(0.0, 1.0 - (abs(actual - expected) / denominator))
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
            cases.append(json.load(f))

    # Compile the skill using compiler
    compiled_skill = compile_skill(skill_path, skill_resolver=skill_resolver)

    evaluated_cases = []
    passed_count = 0
    failed_count = 0
    stale_count = 0

    for case in cases:
        case_id = case["case_id"]
        phase_id = case["phase_id"]
        inputs = case["inputs"]
        expected_output = case.get("expected_output") or {}

        # 检查是否过期(stale)
        required_outputs = get_required_outputs(compiled_skill, phase_id)
        stale_fields = [f for f in required_outputs if f not in expected_output]

        if stale_fields:
            status = "stale"
            score = 0.0
            diff = []
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

            actual_output = extract_actual_output(res.context, phase_id, list(expected_output.keys()))
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
