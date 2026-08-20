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


#: How much of one collected message the report prints. The full text is in
#: `trace.jsonl`, which the report links to; a real protocol_violation message
#: has run to several thousand characters, and one printed whole hides every
#: other failure under it.
ERROR_MESSAGE_BUDGET = 200


@dataclass
class _Execution:
    """One time a node ran.

    A plain node has exactly one. An `iterate` node has one per item, and those
    are the rows that answer 「which item was slow」 and 「which item failed」 —
    questions a single summed node row cannot answer at all.
    """

    execution_id: str
    started_at: str | None = None
    ended_at: str | None = None
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    errors: list[str] = field(default_factory=list)
    interrupted: bool = False

    @property
    def wall_time_sec(self) -> float | None:
        return _elapsed(self.started_at, self.ended_at)

    @property
    def status(self) -> str:
        if self.errors:
            return "failed"
        if self.interrupted:
            return "interrupted"
        if self.ended_at is None:
            # The run ended with this execution still open. Neither success nor
            # failure — and calling it either would be inventing a fact.
            return "unfinished"
        return "ok"


#: Worst first, so a node's status is the worst of its executions: forty items
#: of which one failed is a node that failed.
_STATUS_SEVERITY = ("failed", "interrupted", "unfinished", "ok")


@dataclass
class _NodeAccount:
    """What one node did across every execution of it, folded out of the stream."""

    node_id: str
    executions: list[_Execution] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    #: Turns of the ReAct loop INSIDE one execution — how many times the model
    #: thought, not how many times the node ran. The two were once printed under
    #: one heading that read as the second while meaning the first.
    agent_turns: int = 0
    #: Nudges and handled tool errors: the machinery changed the run's course
    #: without the run going wrong. Counted here, deliberately not in Failure.
    corrections: int = 0

    @property
    def started_at(self) -> str | None:
        return next((run.started_at for run in self.executions if run.started_at), None)

    @property
    def ended_at(self) -> str | None:
        return next((run.ended_at for run in reversed(self.executions) if run.ended_at), None)

    @property
    def llm_calls(self) -> int:
        return sum(run.llm_calls for run in self.executions)

    @property
    def input_tokens(self) -> int:
        return sum(run.input_tokens for run in self.executions)

    @property
    def output_tokens(self) -> int:
        return sum(run.output_tokens for run in self.executions)

    @property
    def tool_calls(self) -> int:
        return sum(run.tool_calls for run in self.executions)

    @property
    def errors(self) -> list[str]:
        return [line for run in self.executions for line in run.errors]

    @property
    def status(self) -> str:
        statuses = {run.status for run in self.executions}
        return next((name for name in _STATUS_SEVERITY if name in statuses), "ok")

    @property
    def wall_time_sec(self) -> float | None:
        return _elapsed(self.started_at, self.ended_at)


@dataclass
class _FanOut:
    """One `parallel_map` group. The engine announces these; nothing read them."""

    group_key: str
    skill_path: str = "—"
    item_count: int = 0
    max_concurrent: int = 0
    item_as: str = ""
    succeeded: int | None = None
    failed: int | None = None
    wall_time_seconds: float | None = None


def _elapsed(started_at: str | None, ended_at: str | None) -> float | None:
    if started_at is None or ended_at is None:
        return None
    try:
        started = datetime.fromisoformat(started_at)
        ended = datetime.fromisoformat(ended_at)
    except ValueError:
        return None
    return round((ended - started).total_seconds(), 2)


def build_run_report(run_dir: Path) -> str:
    """Render one run's report markdown from its sealed artifacts."""
    events = _read_events(run_dir / "trace.jsonl")
    metadata = _read_json(run_dir / "run_metadata.json")
    runtime_config = _read_json(run_dir / "runtime_config.snapshot.json")
    nodes = _account_nodes(events)
    fan_outs = _account_fan_outs(events)

    sections = [
        _summary_section(run_dir, metadata, events, nodes),
        _failure_section(metadata, nodes),
        _inputs_section(run_dir, runtime_config, events),
        _nodes_section(nodes),
        _repeats_section(nodes, fan_outs),
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


#: A run went WRONG here, and the report has to say so. The common thread: each
#: of these is the machinery refusing or abandoning what was asked, rather than
#: correcting it. `tool_error_handled` is deliberately absent — the engine turns
#: that exception into feedback the model reads and the run carries on, which
#: makes it a correction (counted below), not a failure.
_FAILURE_EVENTS = frozenset(
    {
        # The state broke a framework contract; the agent loop is about to be cut.
        "protocol_violation",
        # The run was cut short for going in circles.
        "loop_detected",
        # It finished — on a lesser path than the one it was configured for.
        # Nothing else in the report would show that it had.
        "builtin_subagent_fallback",
    }
)

#: The machinery changed the run's course and the run carried on. Worth counting
#: — a node that needed six nudges is worth a look — but not worth listing among
#: the things that went wrong.
_CORRECTION_EVENTS = frozenset({"nudge", "tool_error_handled", "tool_history_repaired"})

#: Events that open one execution of a node, and the field naming that execution.
#: Everything charged to a node in between belongs to whichever execution is open
#: at that moment: an `llm_call` carries no execution id of its own, and the
#: trace is ordered.
_EXECUTION_OPENS = {"phase_start": "phase_execution_id", "edge_start": "edge_transition_id"}
_EXECUTION_CLOSES = frozenset({"phase_end", "edge_end"})


def _account_nodes(events: Iterable[dict[str, Any]]) -> list[_NodeAccount]:
    accounts: dict[str, _NodeAccount] = {}
    open_execution: dict[str, _Execution] = {}

    def account_for(node_id: str) -> _NodeAccount:
        if node_id not in accounts:
            accounts[node_id] = _NodeAccount(node_id=node_id)
        return accounts[node_id]

    def execution_for(node_id: str) -> _Execution:
        """The execution currently charged for this node, opening one if needed.

        An implicit execution covers events that arrive with nothing open — a
        truncated trace, or a node seen only through events that carry no
        lifecycle of their own. Charging them somewhere beats dropping them.
        """
        current = open_execution.get(node_id)
        if current is None:
            account = account_for(node_id)
            current = _Execution(execution_id=f"{node_id}#{len(account.executions) + 1}")
            account.executions.append(current)
            open_execution[node_id] = current
        return current

    for event in events:
        node_id = _event_node(event)
        if node_id is None:
            continue
        account = account_for(node_id)
        timestamp = event.get("timestamp")
        event_type = str(event.get("event_type", ""))

        if event_type in _EXECUTION_OPENS:
            identifier = event.get(_EXECUTION_OPENS[event_type])
            execution = _Execution(
                execution_id=str(identifier)
                if isinstance(identifier, str) and identifier
                else f"{node_id}#{len(account.executions) + 1}",
                started_at=timestamp if isinstance(timestamp, str) else None,
            )
            account.executions.append(execution)
            open_execution[node_id] = execution
        elif event_type in _EXECUTION_CLOSES:
            execution = execution_for(node_id)
            if isinstance(timestamp, str):
                execution.ended_at = timestamp
            open_execution.pop(node_id, None)
        elif event_type == "llm_call":
            execution = execution_for(node_id)
            execution.llm_calls += 1
            execution.input_tokens += _as_int(event.get("input_tokens"))
            execution.output_tokens += _as_int(event.get("output_tokens"))
            model = event.get("resolved_model")
            if isinstance(model, str) and model and model not in account.models:
                account.models.append(model)
        elif event_type == "tool_call":
            execution_for(node_id).tool_calls += 1
        elif event_type == "agent_loop_iteration":
            account.agent_turns = max(account.agent_turns, _as_int(event.get("iteration")))
        elif event_type == "interrupted":
            execution_for(node_id).interrupted = True
        elif event_type in _CORRECTION_EVENTS:
            account.corrections += 1
        elif event_type == "finish_task_verdict":
            # A rejected submission is the live successor of the removed
            # validation_fail event: the attempt failed its checks and the
            # model was sent back to fix it.
            if event.get("verdict") == "rejected":
                execution_for(node_id).errors.append(_error_line(event))
        elif event_type in _FAILURE_EVENTS:
            execution_for(node_id).errors.append(_error_line(event))

    return list(accounts.values())


def _account_fan_outs(events: Iterable[dict[str, Any]]) -> list[_FanOut]:
    groups: dict[str, _FanOut] = {}
    for event in events:
        key = event.get("group_key")
        if not isinstance(key, str) or not key:
            continue
        event_type = event.get("event_type")
        if event_type == "parallel_map_group_started":
            group = groups.setdefault(key, _FanOut(group_key=key))
            skill_path = event.get("skill_path")
            group.skill_path = skill_path if isinstance(skill_path, str) and skill_path else "—"
            group.item_count = _as_int(event.get("item_count"))
            group.max_concurrent = _as_int(event.get("max_concurrent"))
            item_as = event.get("item_as")
            group.item_as = item_as if isinstance(item_as, str) else ""
        elif event_type == "parallel_map_group_ended":
            group = groups.setdefault(key, _FanOut(group_key=key))
            group.succeeded = _as_int(event.get("succeeded"))
            group.failed = _as_int(event.get("failed"))
            wall = event.get("wall_time_seconds")
            group.wall_time_seconds = float(wall) if isinstance(wall, (int, float)) else None
    return list(groups.values())


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
    return f"{event_type}: {_clipped(str(message))}" if message else event_type


def _clipped(text: str) -> str:
    """Enough of a message to recognise it, with the full text one link away."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= ERROR_MESSAGE_BUDGET:
        return collapsed
    return collapsed[:ERROR_MESSAGE_BUDGET].rstrip() + "…"


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


def _workspace_relative_link(run_dir: Path, path: str) -> str | None:
    """A link from the report to a workspace file, or None when there isn't one.

    Binding paths are relative to the skill's `.workspace` (that is where
    `_scan_import_files` roots them), and a run directory lives at
    `<workspace>/runs/<run id>` — so the file is exactly two levels up. Deriving
    it from the actual directory rather than hard-coding `../..` means a report
    written somewhere else gets no link instead of a broken one: a link that
    resolves to nothing invites a click that fails, which is worse than plain
    text.
    """
    if run_dir.parent.name != "runs" or run_dir.parent.parent.name != ".workspace":
        return None
    if path.startswith(("/", "\\")) or ".." in Path(path).parts:
        return None
    return f"../../{path}"


def _injected_files(events: Sequence[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """(file, node it was handed to, field) for every file the ENGINE injected.

    The runtime snapshot says what the run was configured to read; these say what
    actually arrived, and mid-run injection happens on an edge transition into
    one node — so the node is part of the fact, not decoration.
    """
    seen: list[tuple[str, str, str]] = []
    for event in events:
        if event.get("event_type") != "input_file_injected":
            continue
        file_ref = event.get("file_ref")
        target = event.get("target_field")
        to_phase = event.get("to_phase")
        if not isinstance(file_ref, str) or not file_ref:
            continue
        entry = (
            file_ref,
            to_phase if isinstance(to_phase, str) else "—",
            target if isinstance(target, str) else "—",
        )
        if entry not in seen:
            seen.append(entry)
    return seen


def _file_line(run_dir: Path, path: str, tail: str) -> str:
    link = _workspace_relative_link(run_dir, path)
    named = f"[{path}]({link})" if link else f"`{path}`"
    return f"- {named}{tail}"


def _inputs_section(
    run_dir: Path,
    runtime_config: dict[str, Any],
    events: Sequence[dict[str, Any]],
) -> str:
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

    injected = _injected_files(events)
    if by_file:
        for (path, sha), fields in sorted(by_file.items()):
            supplied = ", ".join(f"`{name}`" for name in sorted(fields))
            sha_note = f" · `{sha}`" if sha else ""
            lines.append(_file_line(run_dir, path, f"{sha_note} → {supplied}"))
    elif not injected:
        lines.append("- no input file was pinned for this run")

    for path, node_id, field_name in injected:
        lines.append(
            _file_line(run_dir, path, f" → `{field_name}`, handed to `{node_id}` mid-run")
        )

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
        "| node | status | wall | ran | LLM calls | tokens in/out | tools "
        "| agent turns | corrections | model |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for node in nodes:
        wall = f"{node.wall_time_sec:.2f}s" if node.wall_time_sec is not None else "—"
        models = ", ".join(f"`{model}`" for model in node.models) if node.models else "—"
        ran = len(node.executions)
        lines.append(
            f"| `{node.node_id}` | {node.status} | {wall} | {ran}× | {node.llm_calls} | "
            f"{node.input_tokens}/{node.output_tokens} | {node.tool_calls} | "
            f"{node.agent_turns or '—'} | {node.corrections or '—'} | {models} |"
        )
    lines.append("")
    return "\n".join(lines)


def _repeats_section(nodes: Sequence[_NodeAccount], fan_outs: Sequence[_FanOut]) -> str:
    """Every node that ran more than once, and every fan-out, itemized.

    The summed row in Nodes answers 「what did this node cost」. It cannot answer
    「which item was slow」 or 「which item failed」, and for an `iterate` over
    forty chapters those are the only questions worth asking.
    """
    repeated = [node for node in nodes if len(node.executions) > 1]
    if not repeated and not fan_outs:
        return ""

    lines = ["## Repeats", ""]
    for node in repeated:
        lines += [
            f"### `{node.node_id}` — {len(node.executions)} executions",
            "",
            "| # | wall | LLM calls | tokens in/out | tools | outcome |",
            "|---|---|---|---|---|---|",
        ]
        for index, run in enumerate(node.executions, start=1):
            wall = f"{run.wall_time_sec:.2f}s" if run.wall_time_sec is not None else "—"
            lines.append(
                f"| {index} | {wall} | {run.llm_calls} | "
                f"{run.input_tokens}/{run.output_tokens} | {run.tool_calls} | {run.status} |"
            )
        lines.append("")

    for group in fan_outs:
        item_as = f" as `{group.item_as}`" if group.item_as else ""
        wall = (
            f"{group.wall_time_seconds:.2f}s" if group.wall_time_seconds is not None else "—"
        )
        lines += [
            f"### parallel_map `{group.skill_path}`{item_as}",
            "",
            "| items | concurrent | succeeded | failed | wall |",
            "|---|---|---|---|---|",
            f"| {group.item_count} | {group.max_concurrent} | "
            f"{group.succeeded if group.succeeded is not None else '—'} | "
            f"{group.failed if group.failed is not None else '—'} | {wall} |",
            "",
        ]
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
    """What this run is a candidate IN, and where the run it answers to lives.

    A candidate side-run is only meaningful next to the run it is measured
    against, so the report links to that run's report — a sibling directory, one
    level up. Without a recorded base run there is no link to make, and the
    section says what it knows rather than guessing at a run id.
    """
    group_id = metadata.get("compare_group_id")
    if not isinstance(group_id, str) or not group_id:
        return ""
    label = metadata.get("candidate_label") or metadata.get("candidate_id") or "—"
    base_run_id = metadata.get("compare_base_run_id")
    lines = [
        "## Model compare",
        "",
        f"- candidate `{label}` for node `{metadata.get('compare_node_id', '—')}`",
        f"- group `{group_id}`",
    ]
    if isinstance(base_run_id, str) and base_run_id:
        lines.append(f"- measured against [{base_run_id}](../{base_run_id}/report.md)")
    else:
        lines.append("- the run this was measured against was not recorded")
    lines.append("")
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
