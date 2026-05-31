#!/usr/bin/env python3
"""V2.1 dual-run shadow comparator.

The current V2.1 migration is a hard cutover, so this prep tool supports
mode ``idempotency``: compile, assemble, and invoke the same V2.1 skill twice
with deterministic fake inputs, then emit a field-level JSON diff.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from langchain_core.messages import AIMessage  # noqa: E402

from graph_agent import LocalWorkspaceResolver, assemble_graph, compile_skill  # noqa: E402


class FakeHelloWorldChatModel:
    """Deterministic fixture for ``skills/hello-world`` shadow checks."""

    def __init__(self) -> None:
        self.react_turns = 0

    def bind_tools(self, tools: list[Any]) -> FakeHelloWorldChatModel:
        del tools
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        del messages
        self.react_turns += 1
        if self.react_turns == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "generate_greeting",
                        "args": {"user_name": "Ada"},
                        "id": "shadow-greet-tool",
                    }
                ],
            )
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "finish_task",
                    "args": {"markdown": "## greeting\n\nHello, Ada!"},
                    "id": "shadow-greet-finish",
                }
            ],
        )


def compare_idempotency(
    skill_root: Path,
    input_data: dict[str, Any],
    *,
    chat_fixture: str = "none",
) -> dict[str, Any]:
    output_a = _run_v21(
        skill_root, input_data, run_id="dual-run-shadow-a", chat_fixture=chat_fixture
    )
    output_b = _run_v21(
        skill_root, input_data, run_id="dual-run-shadow-b", chat_fixture=chat_fixture
    )
    diff = diff_json(output_a, output_b)
    return {
        "mode": "idempotency",
        "shadow_reference": "v21_repeat_run",
        "skill_root": str(skill_root),
        "match": not diff["missing"] and not diff["extra"] and not diff["mismatch"],
        "diff": diff,
        "outputs": {
            "run_a": output_a,
            "run_b": output_b,
        },
    }


def diff_json(left: Any, right: Any, path: str = "$") -> dict[str, list[dict[str, Any]]]:
    diff: dict[str, list[dict[str, Any]]] = {"missing": [], "extra": [], "mismatch": []}
    _diff_into(_normalize(left), _normalize(right), path, diff)
    return diff


def _run_v21(
    skill_root: Path,
    input_data: dict[str, Any],
    *,
    run_id: str,
    chat_fixture: str,
) -> dict[str, Any]:
    resolver = LocalWorkspaceResolver(
        search_paths=[skill_root, skill_root.parent, skill_root.parent / "registry"]
    )
    compiled = compile_skill(skill_root, cache=False, skill_resolver=resolver)
    graph = assemble_graph(
        compiled,
        chat_model=_chat_model(chat_fixture),
        skill_resolver=resolver,
    ).graph
    result = graph.invoke({"data": dict(input_data), "flow": {}, "messages": [], "run_id": run_id})
    normalized = _normalize({"data": result.get("data", {}), "flow": result.get("flow", {})})
    return normalized if isinstance(normalized, dict) else {}


def _chat_model(chat_fixture: str) -> Any:
    if chat_fixture == "none":
        return None
    if chat_fixture == "hello-world":
        return FakeHelloWorldChatModel()
    raise ValueError(f"unknown chat fixture: {chat_fixture}")


def _diff_into(left: Any, right: Any, path: str, diff: dict[str, list[dict[str, Any]]]) -> None:
    if isinstance(left, dict) and isinstance(right, dict):
        left_keys = set(left)
        right_keys = set(right)
        for key in sorted(left_keys - right_keys):
            diff["missing"].append({"path": f"{path}.{key}", "expected": left[key]})
        for key in sorted(right_keys - left_keys):
            diff["extra"].append({"path": f"{path}.{key}", "actual": right[key]})
        for key in sorted(left_keys & right_keys):
            _diff_into(left[key], right[key], f"{path}.{key}", diff)
        return
    if isinstance(left, list) and isinstance(right, list):
        max_len = max(len(left), len(right))
        for index in range(max_len):
            item_path = f"{path}[{index}]"
            if index >= len(left):
                diff["extra"].append({"path": item_path, "actual": right[index]})
            elif index >= len(right):
                diff["missing"].append({"path": item_path, "expected": left[index]})
            else:
                _diff_into(left[index], right[index], item_path, diff)
        return
    if left != right:
        diff["mismatch"].append({"path": path, "expected": left, "actual": right})


def _normalize(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _load_input(raw: str | None, path: str | None) -> dict[str, Any]:
    if path:
        payload = Path(path).read_text(encoding="utf-8")
    else:
        payload = raw or "{}"
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("input payload must be a JSON object")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_root", type=Path)
    parser.add_argument("--mode", choices=["idempotency"], default="idempotency")
    parser.add_argument("--input-json")
    parser.add_argument("--input-file")
    parser.add_argument("--chat-fixture", choices=["none", "hello-world"], default="none")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    report = compare_idempotency(
        args.skill_root,
        _load_input(args.input_json, args.input_file),
        chat_fixture=args.chat_fixture,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 0 if report["match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
