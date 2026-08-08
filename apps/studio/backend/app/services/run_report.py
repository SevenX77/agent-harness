"""One readable page per run, projected from that run's sealed artifacts.

Design: `docs/studio/mvp1/02_capabilities/run-execution/mvp1-alignment.md` F6.
The report adds no facts. Every number in it is read back out of the run
directory — `trace.jsonl` for what happened, `run_metadata.json` for the
outcome, `runtime_config.snapshot.json` for which inputs were active — so the
file can be regenerated at any time and deleting it loses nothing (RUN_EXECUTION-5).

Token totals and model names come from the `llm_call` events rather than from
`metrics.json`, because a role resolves through a fallback chain: which model
answered is only true per call (RUN_EXECUTION-6).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = ["build_run_report", "write_run_report"]

REPORT_FILENAME = "report.md"

# Files a reader may want to open from the report. Listed here rather than
# globbed so the report's "raw records" section stays a stable, named set.
RAW_RECORD_FILES = (
    ("trace.jsonl", "every event this run emitted"),
    ("final_state.json", "the blackboard as the run left it"),
    ("result.json", "the run result envelope"),
    ("metrics.json", "the engine's own metrics summary"),
    ("input_data.json", "the inputs the run was started with"),
    ("runtime_config.snapshot.json", "the runtime config this run was pinned to"),
)


@dataclass
class _NodeAccount:
    """What one node did, folded out of the event stream."""

    node_id: str
    started_at: str | None = None
    ended_at: str | None = None
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    iterations: int = 0
    models: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def wall_time_sec(self) -> float | None:
        if self.started_at is None or self.ended_at is None:
            return None
        try:
            started = datetime.fromisoformat(self.started_at)
            ended = datetime.fromisoformat(self.ended_at)
        except ValueError:
            return None
        return round((ended - started).total_seconds(), 2)


def build_run_report(run_dir: Path) -> str:
    """Render one run's report markdown from its sealed artifacts."""
    events = _read_events(run_dir / "trace.jsonl")
    metadata = _read_json(run_dir / "run_metadata.json")
    runtime_config = _read_json(run_dir / "runtime_config.snapshot.json")
    nodes = _account_nodes(events)

    sections = [
        _summary_section(run_dir, metadata, events, nodes),
        _failure_section(metadata, nodes),
        _inputs_section(run_dir, runtime_config),
        _nodes_section(nodes),
        _tools_section(events),
        _artifacts_section(run_dir),
        _compare_section(metadata),
        _raw_records_section(run_dir),
    ]
    return "\n".join(section for section in sections if section) + "\n"


def write_run_report(run_dir: Path) -> Path:
    """Write the run's report next to the artifacts it summarizes."""
    path = run_dir / REPORT_FILENAME
    path.write_text(build_run_report(run_dir), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# reading


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


# --------------------------------------------------------------------------
# folding


def _event_node(event: dict[str, Any]) -> str | None:
    for key in ("phase_name", "current_phase", "to_phase"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _account_nodes(events: Iterable[dict[str, Any]]) -> list[_NodeAccount]:
    accounts: dict[str, _NodeAccount] = {}

    def account_for(node_id: str) -> _NodeAccount:
        if node_id not in accounts:
            accounts[node_id] = _NodeAccount(node_id=node_id)
        return accounts[node_id]

    for event in events:
        node_id = _event_node(event)
        if node_id is None:
            continue
        account = account_for(node_id)
        timestamp = event.get("timestamp")
        event_type = event.get("event_type")
        if event_type == "phase_start" and isinstance(timestamp, str):
            account.started_at = timestamp
        elif event_type == "phase_end" and isinstance(timestamp, str):
            account.ended_at = timestamp
        elif event_type == "llm_call":
            account.llm_calls += 1
            account.input_tokens += _as_int(event.get("input_tokens"))
            account.output_tokens += _as_int(event.get("output_tokens"))
            model = event.get("resolved_model")
            if isinstance(model, str) and model and model not in account.models:
                account.models.append(model)
        elif event_type == "tool_call":
            account.tool_calls += 1
        elif event_type == "agent_loop_iteration":
            account.iterations = max(account.iterations, _as_int(event.get("iteration")))
        elif event_type in {"validation_fail", "retry_exhausted", "internal_error"}:
            account.errors.append(_error_line(event))

    return list(accounts.values())


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _error_line(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type", "error"))
    errors = event.get("errors")
    if isinstance(errors, list) and errors:
        return f"{event_type}: " + "; ".join(str(item) for item in errors)
    final_errors = event.get("final_errors")
    if isinstance(final_errors, list) and final_errors:
        return f"{event_type}: " + "; ".join(str(item) for item in final_errors)
    message = event.get("message")
    return f"{event_type}: {message}" if message else event_type


# --------------------------------------------------------------------------
# rendering


def _summary_section(
    run_dir: Path,
    metadata: dict[str, Any],
    events: Sequence[dict[str, Any]],
    nodes: Sequence[_NodeAccount],
) -> str:
    input_tokens = sum(node.input_tokens for node in nodes)
    output_tokens = sum(node.output_tokens for node in nodes)
    llm_calls = sum(node.llm_calls for node in nodes)
    tool_calls = sum(node.tool_calls for node in nodes)
    ended = next((event for event in reversed(events) if event.get("event_type") == "run_ended"), {})
    wall_time = ended.get("wall_time_seconds")
    if not isinstance(wall_time, (int, float)):
        metrics = metadata.get("metrics")
        wall_time = metrics.get("wall_time_sec") if isinstance(metrics, dict) else None

    rows = [
        ("Run", f"`{run_dir.name}`"),
        ("Status", str(metadata.get("status", "unknown"))),
        ("Kind", str(metadata.get("kind", "run"))),
        ("Started", str(metadata.get("started_at", "—"))),
        ("Wall time", f"{float(wall_time):.2f}s" if isinstance(wall_time, (int, float)) else "—"),
        ("Tokens", f"{input_tokens} in / {output_tokens} out / {input_tokens + output_tokens} total"),
        ("LLM calls", str(llm_calls)),
        ("Tool calls", str(tool_calls)),
        ("Nodes", str(len(nodes))),
        ("Events", str(len(events))),
        ("Git archive", str(metadata.get("git_status") or "—")),
    ]
    lines = ["# Run report", "", "| | |", "|---|---|"]
    lines += [f"| {label} | {value} |" for label, value in rows]
    lines.append("")
    return "\n".join(lines)


def _failure_section(metadata: dict[str, Any], nodes: Sequence[_NodeAccount]) -> str:
    error = metadata.get("error")
    node_errors = [(node.node_id, line) for node in nodes for line in node.errors]
    if not isinstance(error, dict) and not node_errors:
        return ""

    lines = ["## Failure", ""]
    if isinstance(error, dict):
        lines += [
            f"- **{error.get('code', 'run.failed')}** — {error.get('message', '')}".rstrip(),
        ]
        details = error.get("details")
        if isinstance(details, dict) and details:
            lines.append(f"  - details: `{json.dumps(details, ensure_ascii=False)}`")
    for node_id, line in node_errors:
        lines.append(f"- `{node_id}` — {line}")
    lines.append("")
    return "\n".join(lines)


def _input_bindings(active: Any) -> Iterable[tuple[str, dict[str, Any]]]:
    """Yield (field name, binding) for every declared input field.

    The runtime config keys bindings by FIELD, under `root` for graph-level
    inputs and under `phases.<phase>` for per-node ones.
    """
    if not isinstance(active, dict):
        return
    for field_name, binding in (active.get("root") or {}).items():
        if isinstance(binding, dict):
            yield str(field_name), binding
    phases = active.get("phases")
    if isinstance(phases, dict):
        for phase_name, fields in phases.items():
            if not isinstance(fields, dict):
                continue
            for field_name, binding in fields.items():
                if isinstance(binding, dict):
                    yield f"{phase_name}.{field_name}", binding


def _inputs_section(run_dir: Path, runtime_config: dict[str, Any]) -> str:
    lines = ["## Inputs", ""]
    inputs = runtime_config.get("inputs")
    active = inputs.get("active") if isinstance(inputs, dict) else None

    # Several fields usually read the same file, so the report is per FILE and
    # names the fields it supplied — that is the question a reader has.
    by_file: dict[tuple[str, str], list[str]] = {}
    for field_name, binding in _input_bindings(active):
        path = binding.get("path")
        if not isinstance(path, str) or not path:
            continue
        sha = binding.get("sha256")
        by_file.setdefault((path, str(sha) if isinstance(sha, str) else ""), []).append(field_name)

    if by_file:
        for (path, sha), fields in sorted(by_file.items()):
            supplied = ", ".join(f"`{name}`" for name in sorted(fields))
            sha_note = f" · `{sha}`" if sha else ""
            lines.append(f"- `{path}`{sha_note} → {supplied}")
    else:
        lines.append("- no input file was pinned for this run")

    if (run_dir / "input_data.json").exists():
        lines.append("- run inputs as delivered: [input_data.json](input_data.json)")
    lines.append("")
    return "\n".join(lines)


def _nodes_section(nodes: Sequence[_NodeAccount]) -> str:
    if not nodes:
        return ""
    lines = [
        "## Nodes",
        "",
        "| node | wall | LLM calls | tokens in/out | tools | loop iterations | model |",
        "|---|---|---|---|---|---|---|",
    ]
    for node in nodes:
        wall = f"{node.wall_time_sec:.2f}s" if node.wall_time_sec is not None else "—"
        models = ", ".join(f"`{model}`" for model in node.models) if node.models else "—"
        lines.append(
            f"| `{node.node_id}` | {wall} | {node.llm_calls} | "
            f"{node.input_tokens}/{node.output_tokens} | {node.tool_calls} | "
            f"{node.iterations or '—'} | {models} |"
        )
    lines.append("")
    return "\n".join(lines)


def _tools_section(events: Sequence[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for event in events:
        if event.get("event_type") != "tool_call":
            continue
        name = event.get("tool_name")
        key = name if isinstance(name, str) and name else "(unnamed)"
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return ""
    lines = ["## Tools", "", "| tool | calls |", "|---|---|"]
    lines += [f"| `{name}` | {count} |" for name, count in sorted(counts.items())]
    lines.append("")
    return "\n".join(lines)


def _artifacts_section(run_dir: Path) -> str:
    artifacts_dir = run_dir / "artifacts"
    if not artifacts_dir.is_dir():
        return ""
    files = sorted(path for path in artifacts_dir.rglob("*") if path.is_file())
    if not files:
        return ""
    lines = ["## Artifacts", ""]
    for path in files:
        rel = path.relative_to(run_dir).as_posix()
        lines.append(f"- [{rel}]({rel}) — {path.stat().st_size} bytes")
    lines.append("")
    return "\n".join(lines)


def _compare_section(metadata: dict[str, Any]) -> str:
    group_id = metadata.get("compare_group_id")
    if not isinstance(group_id, str) or not group_id:
        return ""
    lines = [
        "## Model compare",
        "",
        f"- group `{group_id}`, node `{metadata.get('compare_node_id', '—')}`",
        f"- candidate `{metadata.get('candidate_label') or metadata.get('candidate_id') or '—'}`",
        "",
    ]
    return "\n".join(lines)


def _raw_records_section(run_dir: Path) -> str:
    lines = ["## Raw records", ""]
    present = [
        f"- [{name}]({name}) — {description}"
        for name, description in RAW_RECORD_FILES
        if (run_dir / name).exists()
    ]
    if not present:
        return ""
    lines += present
    lines.append("")
    return "\n".join(lines)
