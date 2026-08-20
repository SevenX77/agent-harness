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

from app.core.adapters.atomic_file import read_published_text
from app.services.run_report_routes import routes_section

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
        routes_section(events),
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
        loaded = json.loads(read_published_text(path))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


# --------------------------------------------------------------------------
# folding


def _event_node(event: dict[str, Any]) -> str | None:
    """Which run segment an event is charged to.

    An event carrying `edge_transition_id` happened in the TRANSITION between
    two node executions, not inside the node that follows it (decision
    2026-08-15 edge-as-run-segment, D8). Charging it to the downstream node —
    which is what the `to_phase` fallback below did for every edge operation —
    made a node look responsible for work and failures that happened before it
    started. Transitions are accounted as their own rows, peer to nodes.
    """
    transition = event.get("edge_transition_id")
    if isinstance(transition, str) and transition:
        return _scoped(event, _transition_label(event))
    for key in ("phase_name", "current_phase", "to_phase"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return _scoped(event, value)
    return None


def _scoped(event: dict[str, Any], label: str) -> str:
    """Prefix the label with the subgraph chain the event ran inside.

    A phase name is only unique within one skill: run
    2026-08-19T01-56-15_d0733362 had a `review` in the text-segmentation
    subgraph AND a `review` in the event-extraction subgraph, and keying rows
    on the bare name folded them into one (13 llm_calls) while
    event-extraction's `setup` row vanished into segmentation's. The engine
    now stamps `subgraph_path` on every event; two same-named phases from
    different subgraphs get different rows, and a subgraph's own iterate
    executions still aggregate into one row as before.
    """
    scope = event.get("subgraph_path")
    if isinstance(scope, str) and scope:
        return f"{scope}/{label}"
    return label


def _transition_label(event: dict[str, Any]) -> str:
    """How a transition row reads: the phases it joins, in the direction it ran."""
    raw_from = event.get("from_phases")
    from_phases = [item for item in raw_from if isinstance(item, str)] if isinstance(
        raw_from, list
    ) else []
    to_phase = event.get("to_phase")
    target = to_phase if isinstance(to_phase, str) and to_phase else "?"
    return f"{' + '.join(from_phases) if from_phases else 'input'} -> {target}"


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
        if event_type in ("phase_start", "edge_start") and isinstance(timestamp, str):
            account.started_at = timestamp
        elif event_type in ("phase_end", "edge_end") and isinstance(timestamp, str):
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
        elif event_type == "finish_task_verdict":
            # A rejected submission is the live successor of the removed
            # validation_fail event: the attempt failed its checks and the
            # model was sent back to fix it.
            if event.get("verdict") == "rejected":
                account.errors.append(_error_line(event))
        elif event_type == "protocol_violation":
            # The hard failure: the state broke a framework contract and the
            # agent loop is about to be cut. tool_error_handled is deliberately
            # NOT counted — the engine turned that exception into feedback the
            # model reads, and the run carries on.
            account.errors.append(_error_line(event))

    return list(accounts.values())


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _error_line(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type", "error"))
    errors = event.get("errors")
    if isinstance(errors, list) and errors:
        return f"{event_type}: " + "; ".join(str(item) for item in errors)
    violations = event.get("violations")
    if isinstance(violations, list) and violations:
        return f"{event_type}: " + "; ".join(str(item) for item in violations)
    message = event.get("message")
    return f"{event_type}: {message}" if message else event_type


# --------------------------------------------------------------------------
# rendering


def _wall_clock(value: Any) -> str:
    """One stored instant, read on the clock of the person reading the report.

    Decision D13 (`run-execution/mvp1-alignment.md` F1b) already settled this for
    the run id — a UTC stamp reads as the wrong time to the person looking at it
    — and the report is the same person looking at the same run. Printing the
    stored value verbatim put both readings on one page seven hours apart.

    Storage stays aware UTC: an instant is what everything computes with, and a
    local stamp on disk is ambiguous the moment the machine's zone changes. The
    conversion belongs here, at the edge where a value becomes text for a human.

    The offset rides along because a bare local stamp cannot say which zone it
    is. Borrowed from `git log`, which prints the author's local time with its
    offset for that reason; spelled `-07:00` rather than git's `-0700` so the
    offset reads the same here as everywhere else this product writes one. The
    run id carries no offset at all — a filename has no room for one — which is
    why the two readings are formatted differently on purpose.
    """
    if not isinstance(value, str) or not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        # Already a local wall clock — shifting it would name a moment the run
        # never had. Stamped without an offset because inventing one would
        # claim a zone the value never carried.
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    local = parsed.astimezone()
    offset = local.strftime("%z")
    return f"{local.strftime('%Y-%m-%d %H:%M:%S')} {offset[:3]}:{offset[3:]}"


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
        ("Started", _wall_clock(metadata.get("started_at"))),
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
