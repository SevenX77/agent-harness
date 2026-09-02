#!/usr/bin/env bash
# Cross-review adjudication record for a PR: post one, read the latest one.
#
# WHY THIS IS A SCRIPT AND NOT A PARAGRAPH.
# docs/development/PARALLEL_ORCHESTRATION.md used to spell these two procedures
# out in prose. Four review rounds running found a branch the prose had not
# written down — a missing header line, an unvalidated verdict, page 2 of the
# comments, a hard-coded login. Prose cannot be executed and cannot be tested,
# so each round could only find the next hole by reading harder. A script can be
# run and has a self-test (scripts/tests/xreview-selftest.sh), which is this
# repo's own rule: core logic must be verifiable offline against fakes
# (AGENTS.md 通用工程原则 7 "离线可验证"). The document points here and states
# no steps of its own — one owner per fact (文档事实唯一所有权).
#
# WHAT IT IS FOR. The status marker a coordinator writes into
# docs/development/DELIVERY_LEDGER.md takes "the most recent cross-review
# adjudication" as an input. Cross review in this program runs on the command
# line and never becomes a GitHub review, so `gh pr view --json reviews` stays
# empty however many rounds a PR has had. A PR comment in a fixed shape is the
# record; this script writes it and reads it back.
#
# WHAT IT IS NOT FOR. It records the CROSS-REVIEW adjudication only — one PR,
# one round, approve or rework, dead once that PR is merged or closed. A
# COORDINATOR adjudication (a decision about principle, design or scope, which
# must outlive the conversation) belongs in the program's decision document,
# never here. They are different objects; the SOP's glossary defines both.
#
# WHY EVERY BYTE OF A COMMENT BODY IS HANDLED IN PYTHON, NEVER IN BASH.
# The bodies here are real review reports — tens of thousands of Chinese
# characters — and they arrive from a network API, so the shell's own habits
# corrupt them in ways that are invisible in a short fixture:
#   * `body | head -n 1` makes head exit after one line; with `pipefail` the
#     producer then dies of SIGPIPE and the whole command reports 141. Measured:
#     ~20k characters (~60 KB) still returned 0, ~30k (~90 KB) failed reliably —
#     well under GitHub's own comment limit, i.e. inside normal working range.
#   * A command substitution cannot carry a NUL. Bash drops it (with a warning
#     on stderr that nothing reads), so a body starting with NUL + "交叉审" —
#     which must NOT match the anchored first-line pattern — was silently
#     rewritten into one that did.
# So bash here only orchestrates: it calls gh, moves files, and passes exit
# codes through. Parsing, the invariant check and the comparison all happen in
# the embedded Python program below, on str/bytes that keep what the API sent.
#
# WHY THE READ SIDE AND THE WRITE SIDE SHARE ONE FUNCTION.
# `post` refused a file with two 裁决 lines while `latest` accepted a comment
# with two, reading only the last one — so a record that could never have been
# written by this script was still trusted when read back. The invariant now has
# exactly ONE implementation, verdict_of(), and both sides call it. A record
# that violates it is illegal, and an illegal record stops the program instead
# of resolving to whichever verdict happens to be last.
set -euo pipefail

usage() {
  cat <<'EOF'
scripts/xreview.sh — the cross-review adjudication record of a PR

USAGE
  scripts/xreview.sh post   <pr> <round> <verdict-file>
  scripts/xreview.sh latest <pr> [--with-url]
  scripts/xreview.sh help

post
  Reads <verdict-file> — the cross-review seat's raw output, e.g. codex's
  --output-last-message file. It must contain EXACTLY ONE line starting with
  裁决: , that line must be the last non-blank line, and it must read
  裁决:approve or 裁决:rework. Anything else is refused: a file carrying two
  verdicts has no single answer to record. The comment is built as a header
  line carrying THAT verdict, a blank line, then the file verbatim; the built
  comment is re-checked with the reader's own function before it is posted;
  then it is read back to prove the record just written is the one latest sees.

latest
  Prints the most recent cross-review adjudication of <pr>: approve, rework, or
  尚未审 when the PR has no record yet. Exits non-zero, naming the offending
  comment URL, when a comment looks like a record but breaks the record's
  invariant, and exits non-zero when the GitHub API call fails — an unreadable
  record and an unreachable API are never reported as "no record", because
  either would hand the ledger a marker that nothing supports.
  --with-url also prints the winning comment URL (tab-separated).

COORDINATOR ACCOUNT
  Only comments authored by the coordinator account count; nobody else posting
  the same shape may overwrite the record. The account comes from
  XREVIEW_COORDINATOR, else from <repo-root>/.xreview-coordinator. The script
  validates it and refuses anything it cannot read as exactly one GitHub login
  — appending a second line during a handover is an error, not a silent no-op.
  Comparison is case-insensitive, because GitHub logins are: the API answers
  /users/sevenx77 and /users/SEVENX77 with the canonical SevenX77, and a
  handover file written in lower case must not silently stop matching.
  Handing coordination to another account is a PR editing that file.

PYTHON
  XREVIEW_PYTHON overrides the interpreter. Otherwise: `uv run python`, then
  python3, then python — and any candidate whose path is under WindowsApps is
  skipped, because that is the Windows Store placeholder, which pops the Store
  GUI instead of running code.

SELF-TEST
  CI's pytest testpaths do not reach scripts/, so after changing this script run
      bash scripts/tests/xreview-selftest.sh
EOF
}

die() { echo "error: $*" >&2; exit 1; }

repo_root="$(git rev-parse --show-toplevel)"
readonly repo_root

tmpdir="$(mktemp -d)"
readonly tmpdir
trap 'rm -rf "$tmpdir"' EXIT

# Resolved lazily: `latest` needs Python, `help` does not.
PYTHON_BIN=()

# The Windows Store ships a stub named python.exe on PATH for machines with no
# Python installed. Running it opens the Store instead of executing anything, so
# a plain "does `python` exist" probe picks a GUI. Nothing under WindowsApps is
# ever the interpreter we want.
is_store_placeholder() {
  local path_lower
  path_lower="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$path_lower" in *windowsapps*) return 0 ;; *) return 1 ;; esac
}

resolve_python() {
  [ "${#PYTHON_BIN[@]}" -gt 0 ] && return 0
  if [ -n "${XREVIEW_PYTHON:-}" ]; then
    read -r -a PYTHON_BIN <<<"$XREVIEW_PYTHON"
    return 0
  fi
  # uv first: this repo pins its interpreter through uv, and a machine that has
  # uv has a working Python by construction. python3/python are the fallback for
  # a checkout used outside the uv workspace.
  local uv_path
  if uv_path="$(command -v uv 2>/dev/null)" && ! is_store_placeholder "$uv_path" \
     && uv run python -c 'import sys' >/dev/null 2>&1; then
    PYTHON_BIN=(uv run python)
    return 0
  fi
  local cand cand_path
  for cand in python3 python; do
    if cand_path="$(command -v "$cand" 2>/dev/null)" && ! is_store_placeholder "$cand_path" \
       && "$cand" -c 'import sys' >/dev/null 2>&1; then
      PYTHON_BIN=("$cand")
      return 0
    fi
  done
  die 'no usable Python interpreter (tried $XREVIEW_PYTHON, uv run python, python3, python; WindowsApps placeholders are skipped)'
}

# The one place any comment body, verdict file or coordinator login is parsed.
# Written out on first use and run by path — never piped in, so nothing about
# the program or its input passes through a shell variable.
write_python_program() {
  cat >"$1" <<'PYTHON_PROGRAM'
"""Parsing, validation and selection for xreview.sh.

Everything that reads a comment body, a verdict file or the coordinator account
lives here. The shell above only calls gh and passes exit codes through: a body
that goes through a bash variable loses NUL bytes, and a body that goes through
a pipe into `head` kills its producer with SIGPIPE once the body gets long.

Subcommands
  latest  <comments.json> <coordinator-file> [--with-url]
  compose <round> <verdict-file> <out-file>

Exit codes
  0 fine · 2 wrong usage · 3 illegal record / invalid input
"""

import json
import os
import re
import sys

# Anchored with \Z, not $: Python's $ also matches just BEFORE a trailing
# newline, so a value of "file-login" plus a newline satisfied a pattern written
# to accept exactly "file-login" — which is how a coordinator file with a stray
# blank line passed the check whose whole job was to reject it.
FIRST_LINE_RE = re.compile(r"^交叉审 r([0-9]+):(approve|rework)\Z")
VERDICT_LINE_RE = re.compile(r"^裁决:(approve|rework)\Z")
VERDICT_PREFIX = "裁决:"
RECORD_PREFIX = "交叉审 r"
# Written out for humans: an error message that dumps a regex tells a
# coordinator less than the shape itself does.
FIRST_LINE_SHAPE = "交叉审 r<round>:approve or 交叉审 r<round>:rework"
VERDICT_LINE_SHAPE = "裁决:approve or 裁决:rework"
# A GitHub login: alphanumerics joined by single hyphens, 39 characters at most.
LOGIN_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\Z")
LOGIN_MAX_LEN = 39

EXIT_USAGE = 2
EXIT_ILLEGAL = 3


class Illegal(Exception):
    """Input that must stop the program rather than be interpreted."""


def out(text):
    # Bytes, not text: the Windows console encoding is cp936 here, and the text
    # layer would both fail on 尚未审 and translate \n into \r\n.
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def err(text):
    sys.stderr.buffer.write(text.encode("utf-8"))
    sys.stderr.buffer.flush()


def lines_of(text):
    """Split a body into lines under one rule for every caller.

    Comment bodies come back from GitHub with CRLF whenever a human typed them
    in the web UI, so a trailing CR is punctuation, not content. Nothing else is
    stripped: a NUL is content, and a line that is only a NUL is not blank.
    """
    return [line[:-1] if line.endswith("\r") else line for line in text.split("\n")]


def verdict_of(text, what):
    """THE record invariant — one implementation, called by both sides.

    Exactly one line starts with 裁决: , that line matches the anchored pattern,
    and it is the last non-blank line. `post` applies it to the verdict file and
    again to the comment it just built; `latest` applies it to every comment it
    treats as a record. A body that fails it is illegal in both directions, so a
    record this script would refuse to write can never be trusted when read.
    """
    lines = lines_of(text)
    hits = [line for line in lines if line.startswith(VERDICT_PREFIX)]
    if len(hits) != 1:
        raise Illegal(
            "%s must contain exactly one line starting with '%s', found %d"
            % (what, VERDICT_PREFIX, len(hits))
        )
    match = VERDICT_LINE_RE.match(hits[0])
    if not match:
        raise Illegal(
            "%s: the 裁决 line must read %s, got '%s'"
            % (what, VERDICT_LINE_SHAPE, hits[0])
        )
    non_blank = [line for line in lines if line.strip()]
    if not non_blank or non_blank[-1] != hits[0]:
        raise Illegal("%s: the 裁决 line must be the last non-blank line" % what)
    return match.group(1)


def validate_login(value, source):
    if value == "":
        raise Illegal("%s holds an empty GitHub login" % source)
    if "\r" in value:
        raise Illegal(
            "%s: the value ends with a CR — the file must use LF line endings" % source
        )
    if len(value) > LOGIN_MAX_LEN:
        raise Illegal(
            "%s: '%s' is longer than %d characters, so it is not a GitHub login"
            % (source, value, LOGIN_MAX_LEN)
        )
    if not LOGIN_RE.match(value):
        raise Illegal(
            "%s: '%s' is not a GitHub login (letters, digits and single inner hyphens only)"
            % (source, value)
        )
    return value


def one_login(raw, source):
    """The whole value, minus at most one trailing newline, IS the login.

    Not "the first non-blank line", not "the one non-blank line": exactly the
    content. A handover that appends an account, or an editor that leaves a
    second blank line, changes the file's meaning, and this is the check that
    notices. One trailing newline is allowed, and only one, because every text
    editor writes exactly one at the end of a file.
    """
    if raw.endswith("\n"):
        raw = raw[:-1]
    return validate_login(raw, source)


def coordinator_login(coord_file):
    env_value = os.environ.get("XREVIEW_COORDINATOR", "")
    if env_value:
        return one_login(env_value, "XREVIEW_COORDINATOR")
    if not os.path.isfile(coord_file):
        raise Illegal(
            "no coordinator account: set XREVIEW_COORDINATOR, or create %s with one GitHub login"
            % coord_file
        )
    with open(coord_file, "rb") as handle:
        raw = handle.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Illegal("%s is not valid UTF-8: %s" % (coord_file, exc))
    return one_login(text, coord_file)


def read_comments(path):
    """The comments of one PR, as gh --paginate really prints them.

    `gh api --paginate` writes one JSON array PER PAGE, back to back, so this
    decodes a stream of arrays rather than one document.
    """
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8")
    decoder = json.JSONDecoder()
    position = 0
    comments = []
    while True:
        while position < len(text) and text[position] in " \t\r\n":
            position += 1
        if position >= len(text):
            break
        page, position = decoder.raw_decode(text, position)
        comments.extend(page)
    return comments


def cmd_latest(argv):
    if len(argv) < 2:
        raise SystemExit(EXIT_USAGE)
    comments_path, coord_file = argv[0], argv[1]
    with_url = "--with-url" in argv[2:]
    coordinator = coordinator_login(coord_file).lower()

    best_key = None
    best = None
    for comment in read_comments(comments_path):
        login = (comment.get("user") or {}).get("login") or ""
        # GitHub logins are case-insensitive; comparing them case-sensitively
        # turned a real rework into 尚未审 when the account file said sevenx77.
        if login.lower() != coordinator:
            continue
        body = comment.get("body") or ""
        url = comment.get("html_url") or ""
        first = lines_of(body)[0] if body else ""
        if not first.startswith(RECORD_PREFIX):
            continue
        match = FIRST_LINE_RE.match(first)
        if not match:
            raise Illegal(
                "illegal cross-review record — the first line must read %s: %s"
                % (FIRST_LINE_SHAPE, url)
            )
        header_verdict = match.group(2)
        body_verdict = verdict_of(body, "illegal cross-review record %s" % url)
        if body_verdict != header_verdict:
            raise Illegal(
                "cross-review record contradicts itself — header says %s, 裁决 line says %s: %s"
                % (header_verdict, body_verdict, url)
            )
        # created_at, never updated_at: editing an old comment must not turn it
        # into the newest record. GitHub returns a fixed-width UTC stamp
        # (YYYY-MM-DDTHH:MM:SSZ), so string order is chronological order; it is
        # accurate to the second, and the monotonically increasing comment id
        # breaks a same-second tie the same way for every reader.
        key = (comment["created_at"], int(comment["id"]))
        if best_key is None or key > best_key:
            best_key = key
            best = (header_verdict, url)

    if best is None:
        out("尚未审\n")
        return 0
    verdict, url = best
    out("%s\t%s\n" % (verdict, url) if with_url else "%s\n" % verdict)
    return 0


def cmd_compose(argv):
    if len(argv) != 3:
        raise SystemExit(EXIT_USAGE)
    round_number, verdict_path, out_path = argv
    if not re.match(r"^[0-9]+\Z", round_number):
        raise Illegal("round must be a decimal number, got '%s'" % round_number)
    if not os.path.isfile(verdict_path):
        raise Illegal("verdict file not found: %s" % verdict_path)
    with open(verdict_path, "rb") as handle:
        raw = handle.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Illegal("%s is not valid UTF-8: %s" % (verdict_path, exc))

    verdict = verdict_of(text, "the verdict file %s" % verdict_path)
    # The header is CONSTRUCTED from the file's own verdict, never typed by
    # hand. That is what stops a header saying approve from sitting on a body
    # that says rework.
    body = "交叉审 r%s:%s\n\n%s" % (round_number, verdict, text)

    # Read the composed comment back with the reader's own checks before it is
    # posted: whatever this writes, latest must be able to read.
    first = lines_of(body)[0]
    if not FIRST_LINE_RE.match(first):
        raise Illegal("the composed first line must read %s, got '%s'" % (FIRST_LINE_SHAPE, first))
    if verdict_of(body, "the composed comment") != verdict:
        raise Illegal("the composed comment does not read back as %s" % verdict)

    with open(out_path, "wb") as handle:
        handle.write(body.encode("utf-8"))
    out("%s\n" % verdict)
    return 0


def main(argv):
    if not argv:
        err("error: xreview.py needs a subcommand\n")
        return EXIT_USAGE
    command, rest = argv[0], argv[1:]
    handlers = {"latest": cmd_latest, "compose": cmd_compose}
    if command not in handlers:
        err("error: unknown subcommand '%s'\n" % command)
        return EXIT_USAGE
    try:
        return handlers[command](rest)
    except Illegal as exc:
        err("error: %s\n" % exc)
        return EXIT_ILLEGAL
    except (OSError, ValueError, KeyError) as exc:
        err("error: could not read the comment payload: %s\n" % exc)
        return EXIT_ILLEGAL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
PYTHON_PROGRAM
}

run_python() {
  resolve_python
  local program="$tmpdir/xreview.py"
  [ -f "$program" ] || write_python_program "$program"
  "${PYTHON_BIN[@]}" "$program" "$@"
}

# The comments of <pr> as raw JSON in $tmpdir/comments.json. Dies on API
# failure: an API that did not answer is not a PR without records, and the
# difference decides whether a stale marker goes into the ledger.
fetch_comments() {
  local pr="$1"
  local raw="$tmpdir/comments.json" errfile="$tmpdir/gh.err" rc=0
  set +e
  env -u GITHUB_TOKEN gh api --paginate "repos/{owner}/{repo}/issues/${pr}/comments" \
    >"$raw" 2>"$errfile"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "error: gh api failed (exit ${rc}) listing comments of PR ${pr}; refusing to report '尚未审'" >&2
    sed 's/^/  gh: /' "$errfile" >&2
    exit 1
  fi
  printf '%s' "$raw"
}

cmd_latest() {
  local pr="${1:-}" with_url=()
  [ -n "$pr" ] || die 'latest needs a PR number: scripts/xreview.sh latest <pr>'
  case "${2:-}" in
    --with-url) with_url=(--with-url) ;;
    '') ;;
    *) die "unknown option '${2}'" ;;
  esac
  local raw
  raw="$(fetch_comments "$pr")"
  # Python writes the verdict straight to this script's stdout and its own exit
  # code straight through: nothing is captured, so nothing can be laundered.
  run_python latest "$raw" "$repo_root/.xreview-coordinator" ${with_url[@]+"${with_url[@]}"}
}

cmd_post() {
  local pr="${1:-}" round="${2:-}" file="${3:-}"
  [ -n "$pr" ] && [ -n "$round" ] && [ -n "$file" ] \
    || die 'post needs three arguments: scripts/xreview.sh post <pr> <round> <verdict-file>'

  local composed="$tmpdir/comment.md" verdict
  verdict="$(run_python compose "$round" "$file" "$composed")"

  local posted_url
  posted_url="$(env -u GITHUB_TOKEN gh pr comment "$pr" --body-file "$composed" | tr -d '\r' | tail -n 1)"

  # Read back: a post that latest cannot find did not establish the record,
  # whatever the API answered.
  local seen seen_verdict seen_url
  seen="$(cmd_latest "$pr" --with-url)"
  seen_verdict="${seen%%$'\t'*}"
  seen_url="${seen#*$'\t'}"
  [ "$seen_verdict" = "$verdict" ] \
    || die "posted ${verdict} but latest now reads ${seen_verdict} (${seen_url})"
  if [ -n "$posted_url" ] && [ "$seen_url" != "$posted_url" ]; then
    die "posted ${posted_url} but latest points at ${seen_url} — a newer record already exists"
  fi
  printf '%s\n' "OK 交叉审 r${round}:${verdict} recorded  ${seen_url}"
}

subcommand="${1:-help}"
[ $# -gt 0 ] && shift
case "$subcommand" in
  post) cmd_post "$@" ;;
  latest) cmd_latest "$@" ;;
  help|-h|--help) usage ;;
  *) usage >&2; echo >&2; die "unknown command '$subcommand'" ;;
esac
