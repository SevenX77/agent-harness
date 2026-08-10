"""The run report's account of which routes ran it, and how their settings fared.

The trace answers "what happened on this call". Nobody reading a finished run
wants to answer "did this run get what it asked for" by scrolling through
twenty calls that each say the same thing, so this converges them: one block
per route the run touched, one line per setting with how many calls carried it,
and — collected at the end where a reader will actually reach them — the
settings that did not run as asked.

It adds no facts. Everything printed here is read back out of the run's own
trace, which is what lets the report be regenerated at any time and lets
deleting it lose nothing.

Design: docs/design/2026-08-10-runtime-settings-are-preferences-decision.md D7
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

# The verdicts that mean the caller did not get what they asked for. Kept in
# step with the gateway's closed set by hand, the same way the event itself is.
UNMET_VERDICTS: frozenset[str] = frozenset({"adjusted", "unsupported", "rejected", "ignored"})


@dataclass(frozen=True)
class _SettingLine:
    """One setting on one route, folded across every call that carried it."""

    setting: str
    requested: str
    verdict: str
    reason: str
    calls: int = 1

    def counted_again(self) -> _SettingLine:
        return _SettingLine(self.setting, self.requested, self.verdict, self.reason, self.calls + 1)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.setting, self.requested, self.verdict)


@dataclass
class _RouteAccount:
    """Everything one run learned about one route."""

    route_id: str
    provider_model_id: str | None = None
    decisions: dict[str, int] = field(default_factory=dict)
    settings: dict[tuple[str, str, str], _SettingLine] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)


def routes_section(events: Sequence[dict[str, Any]]) -> str:
    """The report's ``## Routes`` block, or nothing when no route was touched."""
    accounts = _account_routes(events)
    if not accounts:
        return ""
    lines = ["## Routes", ""]
    for account in accounts:
        lines += _route_block(account)
    lines += _unmet_block(accounts)
    return "\n".join(lines)


def _account_routes(events: Iterable[dict[str, Any]]) -> list[_RouteAccount]:
    accounts: dict[str, _RouteAccount] = {}

    def account_for(event: dict[str, Any]) -> _RouteAccount | None:
        route_id = event.get("route_id")
        if not isinstance(route_id, str) or not route_id:
            return None
        account = accounts.setdefault(route_id, _RouteAccount(route_id=route_id))
        model = event.get("provider_model_id")
        if account.provider_model_id is None and isinstance(model, str) and model:
            account.provider_model_id = model
        return account

    for event in events:
        event_type = event.get("event_type")
        if event_type == "llm_route_decision":
            account = account_for(event)
            if account is not None:
                _record_decision(account, event)
        elif event_type == "llm_call_settings":
            account = account_for(event)
            if account is not None:
                _record_settings(account, event)
    return list(accounts.values())


def _record_decision(account: _RouteAccount, event: dict[str, Any]) -> None:
    decision = event.get("decision")
    if not isinstance(decision, str) or not decision:
        return
    account.decisions[decision] = account.decisions.get(decision, 0) + 1
    reason = event.get("reason")
    # First reason per outcome: later calls repeat it, and a table of twenty
    # identical sentences hides the one outcome that differs.
    if isinstance(reason, str) and reason and decision not in account.reasons:
        account.reasons[decision] = reason


def _record_settings(account: _RouteAccount, event: dict[str, Any]) -> None:
    raw = event.get("settings")
    if not isinstance(raw, list):
        return
    for entry in raw:
        line = _setting_line(entry)
        if line is None:
            continue
        existing = account.settings.get(line.key)
        account.settings[line.key] = existing.counted_again() if existing else line


def _setting_line(entry: Any) -> _SettingLine | None:
    if not isinstance(entry, dict):
        return None
    setting = entry.get("setting")
    verdict = entry.get("verdict")
    if not isinstance(setting, str) or not isinstance(verdict, str):
        return None
    reason = entry.get("reason")
    return _SettingLine(
        setting=setting,
        requested=_rendered(entry.get("requested")),
        verdict=verdict,
        reason=reason if isinstance(reason, str) else "",
    )


def _rendered(value: Any) -> str:
    """A setting's value as the report prints it, with nothing invented for absence."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _route_block(account: _RouteAccount) -> list[str]:
    lines = [f"### `{account.route_id}`", ""]
    if account.provider_model_id:
        lines += [f"Model: `{account.provider_model_id}`", ""]
    if account.decisions:
        lines += ["| outcome | times | first reason |", "|---|---|---|"]
        lines += [
            f"| {decision} | {count} | {account.reasons.get(decision, '')} |"
            for decision, count in sorted(account.decisions.items())
        ]
        lines.append("")
    if account.settings:
        lines += ["| setting | requested | outcome | calls |", "|---|---|---|---|"]
        lines += [
            f"| `{line.setting}` | {line.requested} | {line.verdict} | {line.calls} |"
            for line in sorted(account.settings.values(), key=lambda item: item.setting)
        ]
        lines.append("")
    return lines


def _unmet_block(accounts: Sequence[_RouteAccount]) -> list[str]:
    """The settings that did not run as asked, gathered out of the per-route tables.

    They are already above, one route at a time. They are repeated here because
    a warning spread across five tables is a warning nobody adds up.
    """
    unmet = [
        (account, line)
        for account in accounts
        for line in sorted(account.settings.values(), key=lambda item: item.setting)
        if line.verdict in UNMET_VERDICTS
    ]
    if not unmet:
        return []
    lines = [
        "### Settings that did not run as asked",
        "",
        "| route | setting | requested | outcome | why |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| `{account.route_id}` | `{line.setting}` | {line.requested} | {line.verdict} | {line.reason} |"
        for account, line in unmet
    ]
    lines.append("")
    return lines


__all__ = ["UNMET_VERDICTS", "routes_section"]
