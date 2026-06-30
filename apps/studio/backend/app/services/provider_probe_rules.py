"""Data-driven DYNAMIC probe-candidate rules (W3-A / T2).

Some backends pick their official language-model probe candidates from the *model id*
(openai branches on `gpt-3.5-turbo-instruct` / `gpt-5-pro` and expands a reasoning-effort
ladder; gemini splits on a thinking-capable model list). That is still DATA, not code:
this module reads `app/data/probe_candidates_dynamic.json` and applies a tiny generic
interpreter (model-class matchers -> the first matching rule -> candidate specs, with a
reasoning-ladder expander) so a new rule is a config edit, not a code change.

Each produced spec is kwargs for `routers/llm.py::_candidate(...)` — identical shape to
the static `probe_candidates.json`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DYNAMIC_PATH = Path(__file__).resolve().parents[1] / "data" / "probe_candidates_dynamic.json"


@lru_cache(maxsize=1)
def _dynamic_table() -> dict[str, dict[str, Any]]:
    raw = json.loads(_DYNAMIC_PATH.read_text(encoding="utf-8"))
    return {str(backend): cfg for backend, cfg in raw.get("dynamic_probe_candidates", {}).items()}


def _matcher_matches(model: str, matcher: dict[str, Any]) -> bool:
    """A matcher is a conjunction: every present condition must hold."""
    prefix = matcher.get("prefix")
    if prefix is not None and not model.startswith(str(prefix)):
        return False
    contains = matcher.get("contains")
    if contains is not None and str(contains) not in model:
        return False
    equals = matcher.get("equals")
    if equals is not None and model != str(equals):
        return False
    return True


def _in_class(model: str, class_def: dict[str, Any]) -> bool:
    """A class is a disjunction of matchers (any_of)."""
    return any(_matcher_matches(model, matcher) for matcher in class_def.get("any_of", []))


def _reasoning_runtime(reasoning: dict[str, Any], classes: dict[str, bool], effort: str) -> dict[str, Any]:
    max_tokens = (
        reasoning["max_tokens_when_pro"]
        if classes.get(reasoning["pro_class"], False)
        else reasoning["max_tokens_default"]
    )
    return {"max_output_tokens": max_tokens, "reasoning": {"enabled": True, "effort": effort}}


def _expand_reasoning(
    reasoning: dict[str, Any],
    method_id: str,
    default_rank: int,
    fallback_rank: int,
    classes: dict[str, bool],
    model: str,
) -> list[dict[str, Any]]:
    efforts = (
        reasoning["efforts_when_high"]
        if classes.get(reasoning["high_class"], False)
        else reasoning["efforts_default"]
    )
    request_mapper_id = reasoning["request_mappers"][method_id]
    retry_group = str(reasoning["retry_group"]).replace("{model}", model)
    return [
        {
            "method_id": method_id,
            "profile_id": f"reasoning:{method_id}:{effort}",
            "capability": "reasoning",
            "request_mapper_id": request_mapper_id,
            "default_rank": default_rank + index,
            "fallback_rank": fallback_rank,
            "runtime_settings": _reasoning_runtime(reasoning, classes, effort),
            "retry_group": retry_group,
        }
        for index, effort in enumerate(efforts)
    ]


def dynamic_probe_candidate_specs(backend: str, model_id: str) -> list[dict[str, Any]] | None:
    """Return the `_candidate(**spec)` kwargs for a model-dependent backend, or ``None``
    if the backend's candidates are static / not configured here."""
    cfg = _dynamic_table().get(backend)
    if cfg is None:
        return None
    model = model_id.lower()
    classes = {name: _in_class(model, class_def) for name, class_def in cfg.get("classes", {}).items()}
    rule = next(
        (r for r in cfg.get("rules", []) if r.get("default") or classes.get(str(r.get("when")), False)),
        None,
    )
    if rule is None:
        return []
    reasoning = cfg.get("reasoning", {})
    specs: list[dict[str, Any]] = []
    for cand in rule.get("candidates", []):
        reasoning_for = cand.get("reasoning")
        if reasoning_for is not None:
            default_rank, fallback_rank = cand["rank"]
            specs.extend(
                _expand_reasoning(reasoning, str(reasoning_for), default_rank, fallback_rank, classes, model)
            )
            continue
        default_rank, fallback_rank = cand["rank"]
        spec: dict[str, Any] = {
            "method_id": cand["method_id"],
            "profile_id": cand["profile_id"],
            "capability": cand["capability"],
            "request_mapper_id": cand["request_mapper_id"],
            "default_rank": default_rank,
            "fallback_rank": fallback_rank,
        }
        runtime = cand.get("runtime")
        if runtime == "reasoning_if_high":
            # openai responses-only path: high-reasoning models carry the reasoning
            # runtime; everyone else uses _candidate's default.
            if classes.get(reasoning["high_class"], False):
                spec["runtime_settings"] = _reasoning_runtime(reasoning, classes, "high")
        elif isinstance(runtime, dict):
            spec["runtime_settings"] = runtime
        specs.append(spec)
    return specs
