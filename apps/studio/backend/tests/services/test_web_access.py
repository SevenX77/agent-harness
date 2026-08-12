"""Reading a page that only exists behind somebody's login.

The agent never logs in and never sees a credential. It borrows the browser the
person already logged into, through the OpenCLI Browser Bridge, and is allowed
exactly two things there: go to a URL, and read what is on the page.

Two facts measured against the real CLI (opencli v1.8.6, 2026-08-12) shape these
tests. `opencli doctor` exits 0 **even while the extension is disconnected**, so
the exit code says nothing about readiness and the output has to be read. And
every invocation prints a Node `UNDICI-EHPA` warning on stderr, so stderr is
noise, not failure.
"""

from __future__ import annotations

import json

import pytest
from app.services import web_access

EXTRACT_JSON = json.dumps(
    {
        "url": "https://platform.example.com/models",
        "title": "Models",
        "selector": None,
        "total_chars": 167,
        "chunk_size": 167,
        "start": 0,
        "end": 167,
        "next_start_char": None,
        "content": "# Models\n\nvision-pro accepts text and images.",
    }
)

DOCTOR_DISCONNECTED = (
    "opencli v1.8.6 doctor (node v24.18.0)\n"
    "\n"
    "[OK] Daemon: running on port 19825 (v1.8.6)\n"
    "[MISSING] Extension: not connected\n"
    "[FAIL] Connectivity: failed (Browser Bridge extension not connected)\n"
)

DOCTOR_CONNECTED = (
    "[OK] Daemon: running on port 19825 (v1.8.6)\n"
    "[OK] Extension: connected (v1.0.22)\n"
    "[OK] Connectivity: connected in 0.1s\n"
)

NODE_WARNING = (
    "(node:20648) [UNDICI-EHPA] Warning: EnvHttpProxyAgent is experimental.\n"
    "(Use `node --trace-warnings ...` to show where the warning was created)\n"
)


def _runner(replies: dict[str, str], *, stderr: str = ""):
    """A fake `opencli` that answers by verb and records what it was asked."""

    calls: list[list[str]] = []

    def run(args: list[str]) -> web_access.CliReply:
        calls.append(args)
        verb = next((a for a in args if a in replies), None)
        return web_access.CliReply(stdout=replies.get(verb or "", ""), stderr=stderr)

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_a_page_behind_a_login_comes_back_as_text() -> None:
    run = _runner({"open": '{"url": "x", "page": "P1"}', "extract": EXTRACT_JSON})

    page = web_access.fetch_page("https://platform.example.com/models", run=run)

    assert isinstance(page, web_access.WebPage)
    assert page.title == "Models"
    assert "vision-pro accepts text and images." in page.content
    assert page.continues_at is None


def test_a_long_page_says_where_to_continue() -> None:
    long_page = json.loads(EXTRACT_JSON)
    long_page["next_start_char"] = 20000
    run = _runner({"open": "{}", "extract": json.dumps(long_page)})

    page = web_access.fetch_page("https://example.com/long", run=run)

    assert isinstance(page, web_access.WebPage)
    assert page.continues_at == 20000


def test_a_disconnected_bridge_says_what_the_person_must_do() -> None:
    """The agent cannot fix this and must not pretend the page was empty."""

    run = _runner({"open": "not json", "doctor": DOCTOR_DISCONNECTED})

    outcome = web_access.fetch_page("https://platform.example.com/models", run=run)

    assert isinstance(outcome, web_access.BridgeNotReady)
    assert outcome.daemon_running is True
    assert outcome.extension_connected is False
    assert "Chrome" in outcome.what_the_person_must_do


def test_a_connected_bridge_that_still_failed_is_not_blamed_on_the_person() -> None:
    """Telling somebody to install what is already installed wastes their time."""

    run = _runner({"open": "not json", "doctor": DOCTOR_CONNECTED})

    outcome = web_access.fetch_page("https://example.com", run=run)

    assert isinstance(outcome, web_access.BridgeNotReady)
    assert outcome.extension_connected is True
    assert "Chrome" not in outcome.what_the_person_must_do


def test_the_node_warning_on_stderr_is_not_a_failure() -> None:
    run = _runner(
        {"open": '{"url": "x", "page": "P1"}', "extract": EXTRACT_JSON},
        stderr=NODE_WARNING,
    )

    page = web_access.fetch_page("https://example.com", run=run)

    assert isinstance(page, web_access.WebPage)


def test_reading_starts_where_the_previous_chunk_stopped() -> None:
    run = _runner({"open": "{}", "extract": EXTRACT_JSON})

    web_access.fetch_page("https://example.com/long", start=20000, run=run)

    extract_call = next(c for c in run.calls if "extract" in c)  # type: ignore[attr-defined]
    assert "--start" in extract_call
    assert extract_call[extract_call.index("--start") + 1] == "20000"


@pytest.mark.parametrize("verb", sorted(web_access.WRITE_VERBS))
def test_no_write_verb_can_be_issued(verb: str) -> None:
    """OpenCLI can click, fill, type and eval. This adapter must not reach them:
    the person's browser is logged into their real accounts, so a write verb
    there acts as them. Read-only is the whole reason the tool needs no
    approval, and a closed vocabulary is what keeps it true."""

    with pytest.raises(ValueError, match="read-only"):
        web_access.issue(verb, run=_runner({}))


@pytest.mark.parametrize("verb", sorted(web_access.READ_VERBS))
def test_every_read_verb_is_reachable(verb: str) -> None:
    web_access.issue(verb, run=_runner({verb: "{}"}))


def test_the_two_vocabularies_do_not_overlap() -> None:
    assert not (web_access.READ_VERBS & web_access.WRITE_VERBS)


def test_the_executable_is_resolved_before_it_is_launched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """npm installs `opencli` on Windows as `opencli.CMD`, and CreateProcess
    will not resolve an extensionless name — a live run failed with
    `FileNotFoundError: [WinError 2]` while every fake-runner test stayed green.
    `shutil.which` applies PATHEXT, so resolving first is what makes the same
    call work on all three platforms without a shell (and a shell would put a
    model-supplied URL on a command line, which is its own problem).
    """

    launched: list[list[str]] = []
    monkeypatch.setattr(web_access.shutil, "which", lambda name: rf"C:\bin\{name}.CMD")
    monkeypatch.setattr(
        web_access.subprocess,
        "run",
        lambda argv, **kwargs: launched.append(argv) or _completed(),
    )

    web_access._shell_out(["doctor"])

    assert launched[0][0] == r"C:\bin\opencli.CMD"


def test_a_machine_without_opencli_says_so_rather_than_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The state a brand-new machine is in. It must be reported as something a
    person can act on, not as a stack trace and not as an empty page."""

    monkeypatch.setattr(web_access.shutil, "which", lambda name: None)

    outcome = web_access.fetch_page("https://example.com")

    assert isinstance(outcome, web_access.BridgeNotReady)
    assert outcome.cli_installed is False
    assert "OpenCLI" in outcome.what_the_person_must_do


class _completed:
    returncode = 0
    stdout = ""
    stderr = ""
