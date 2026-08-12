"""Reading a page that only exists behind somebody's login.

Provider documentation, console pages and model catalogues are routinely gated
behind an account. The agent cannot get past that gate and must not try: it
never sees a password, never holds a cookie, never signs in. What it does
instead is borrow the browser the person is *already* signed into, through the
OpenCLI Browser Bridge — a Chrome extension the person installs themselves,
driven by a local daemon.

That borrowing is why this adapter is deliberately tiny. OpenCLI can click,
fill, type and eval; inside somebody's logged-in browser those verbs act **as
them**. So the vocabulary here is closed to two: go to a URL, read what is
there. `READ_VERBS` is the allowlist that enforces it and `WRITE_VERBS` names
what is being refused, so a later reader can see the refusal was a decision.
Being read-only is also what earns the tool its place on the no-approval list —
a single navigation plus a read is a side effect that can be stated in full.

Two behaviours were measured against opencli v1.8.6 on 2026-08-12 and are the
reason this file looks the way it does:

- ``opencli doctor`` exits **0 while the extension is disconnected**, so the
  exit code carries no readiness information and the output must be read.
- Every invocation prints a Node ``UNDICI-EHPA`` warning on stderr, so stderr
  is noise. Only stdout is evidence, and the two streams stay separate.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

# The browser session this app leases. OpenCLI keys tab leases by session name,
# so a fixed one keeps Studio's reading out of any other tool's tabs.
SESSION: Final = "studio"

EXECUTABLE: Final = "opencli"

READ_VERBS: Final[frozenset[str]] = frozenset({"open", "extract"})

# Verbs that would act as the signed-in person. Never reachable from here; the
# allowlist above is the enforcement, this is the record of what it excludes.
WRITE_VERBS: Final[frozenset[str]] = frozenset(
    {
        "check",
        "click",
        "dblclick",
        "dialog",
        "drag",
        "eval",
        "fill",
        "keys",
        "select",
        "type",
        "uncheck",
        "upload",
    }
)


@dataclass(frozen=True)
class CliReply:
    stdout: str
    stderr: str


Runner = Callable[[list[str]], CliReply]


@dataclass(frozen=True)
class WebPage:
    """A page the person's browser could see, as markdown."""

    url: str
    title: str
    content: str
    # Where a following read should start, when the page was too long for one
    # chunk. ``None`` means the whole page is here.
    continues_at: int | None


class OpenCliMissing(RuntimeError):
    """`opencli` is not on PATH — nothing can be read until it is installed."""


@dataclass(frozen=True)
class BridgeNotReady:
    """The page was not read, and why — in terms of what a person can act on.

    Kept distinct from an empty page on purpose: an agent that cannot tell the
    two apart reports "this provider documents nothing" when the truth is
    "nobody opened Chrome".
    """

    cli_installed: bool
    daemon_running: bool
    extension_connected: bool
    what_the_person_must_do: str


FetchOutcome = WebPage | BridgeNotReady


def _shell_out(args: list[str]) -> CliReply:
    # npm installs this as `opencli.CMD` on Windows, and CreateProcess does not
    # apply PATHEXT to an extensionless name — a live run died with
    # `FileNotFoundError: [WinError 2]`. `shutil.which` does apply it, so
    # resolving first makes one code path work on all three platforms. Doing it
    # this way instead of `shell=True` also keeps a model-supplied URL off a
    # command line.
    executable = shutil.which(EXECUTABLE)
    if executable is None:
        raise OpenCliMissing(EXECUTABLE)
    completed = subprocess.run(  # noqa: S603 — resolved executable, closed verb vocabulary
        [executable, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return CliReply(stdout=completed.stdout or "", stderr=completed.stderr or "")


def issue(verb: str, *arguments: str, run: Runner | None = None) -> CliReply:
    """Run one browser verb. Anything outside the read vocabulary is refused."""

    if verb not in READ_VERBS:
        raise ValueError(
            f"{verb!r} is not a read-only browser verb; this adapter borrows a "
            f"signed-in browser and may only {sorted(READ_VERBS)}"
        )
    runner = run or _shell_out
    return runner(["browser", SESSION, verb, *arguments])


def _as_json(stdout: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(stdout.strip())
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def read_bridge_status(run: Runner | None = None) -> tuple[bool, bool]:
    """(daemon running, extension connected), read off ``opencli doctor``.

    Parsed from the output rather than the exit code, which is 0 either way.
    """

    runner = run or _shell_out
    report = runner(["doctor"]).stdout
    daemon = extension = False
    for line in report.splitlines():
        marker_ok = line.startswith("[OK]")
        if "Daemon:" in line:
            daemon = marker_ok
        elif "Extension:" in line:
            extension = marker_ok
    return daemon, extension


_CLI_MISSING = BridgeNotReady(
    cli_installed=False,
    daemon_running=False,
    extension_connected=False,
    what_the_person_must_do=(
        "这台机器上没有 OpenCLI,所以读不了网页。装好它之后再重试;"
        "装完还要在 Chrome 里启用它的扩展并登录目标站点。"
    ),
)


def _diagnose(failure: str, run: Runner | None) -> BridgeNotReady:
    try:
        daemon, extension = read_bridge_status(run)
    except OpenCliMissing:
        return _CLI_MISSING
    if not daemon:
        todo = "OpenCLI 的本地后台没在运行,先启动它,再重试这次读取。"
    elif not extension:
        todo = (
            "打开 Chrome,启用 OpenCLI 扩展,并在浏览器里登录目标站点,然后重试。"
            "登录只有你能做——这里不会索取密码,也不会读取导出的 cookie。"
        )
    else:
        todo = f"浏览器桥是通的,但这一页没读到。OpenCLI 的原话:{failure.strip() or '(无输出)'}"
    return BridgeNotReady(
        cli_installed=True,
        daemon_running=daemon,
        extension_connected=extension,
        what_the_person_must_do=todo,
    )


def fetch_page(url: str, *, start: int = 0, run: Runner | None = None) -> FetchOutcome:
    """Go to ``url`` in the person's browser and read the page as markdown.

    ``start`` continues a long page from a previous read's ``continues_at``.
    """

    try:
        opened = issue("open", url, run=run)
    except OpenCliMissing:
        return _CLI_MISSING
    if _as_json(opened.stdout) is None:
        return _diagnose(opened.stdout, run)

    read = issue("extract", "--start", str(start), run=run)
    payload = _as_json(read.stdout)
    if payload is None:
        return _diagnose(read.stdout, run)

    return WebPage(
        url=str(payload.get("url") or url),
        title=str(payload.get("title") or ""),
        content=str(payload.get("content") or ""),
        continues_at=payload.get("next_start_char"),
    )
