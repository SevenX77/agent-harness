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
# WHY THE PROJECTION IS PYTHON AND NOT `gh --jq`.
# Selecting the winning comment depends on ONE field choice: order by
# `created_at`, never by `updated_at`, so that editing an old comment cannot
# turn it into the newest record. While that choice lived inside a `--jq`
# expression handed to gh, no test could reach it: the self-test's fake `gh`
# replaced gh entirely, so mutating `.created_at` to `.updated_at` left the
# suite green — a contract with no regression protection at all. The projection
# now runs in this script, on the raw JSON gh returns, so the fake `gh` feeds
# real GitHub payloads and the mutation turns the suite red.
set -euo pipefail

# The record's shape. Both regexes are anchored: a line either is a record or it
# is not, with nothing in between for a reader to interpret.
readonly FIRST_LINE_RE='^交叉审 r([0-9]+):(approve|rework)$'
readonly VERDICT_LINE_RE='^裁决:(approve|rework)$'
readonly VERDICT_LINE_PREFIX='裁决:'
# GitHub login: alphanumerics, single hyphens inside, 39 characters at most.
# Bash uses POSIX ERE, which has no lookahead, so the canonical
# `[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}` is expressed as
# "alnum runs joined by single hyphens" plus an explicit length check — the two
# accept exactly the same strings.
readonly LOGIN_RE='^[A-Za-z0-9]+(-[A-Za-z0-9]+)*$'
readonly LOGIN_MAX_LEN=39

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
  line carrying THAT verdict, a blank line, then the file verbatim; posted; then
  read back to prove the record just written is the one latest sees.

latest
  Prints the most recent cross-review adjudication of <pr>: approve, rework, or
  尚未审 when the PR has no record yet. Exits non-zero, naming the offending
  comment URL, when a comment looks like a record but is not a valid one, and
  exits non-zero when the GitHub API call fails — an unreadable record and an
  unreachable API are never reported as "no record", because either would hand
  the ledger a marker that nothing supports.
  --with-url also prints the winning comment URL (tab-separated).

COORDINATOR ACCOUNT
  Only comments authored by the coordinator account count; nobody else posting
  the same shape may overwrite the record. The account comes from
  XREVIEW_COORDINATOR, else from <repo-root>/.xreview-coordinator. That file
  must hold exactly one non-blank line holding exactly one GitHub login, and
  this script enforces it — appending a second line during a handover is an
  error, not a silent no-op. Handing coordination to another account is a PR
  editing that file.

SELF-TEST
  CI's pytest testpaths do not reach scripts/, so after changing this script run
      bash scripts/tests/xreview-selftest.sh
EOF
}

die() { echo "error: $*" >&2; exit 1; }

repo_root="$(git rev-parse --show-toplevel)"
readonly repo_root

# Resolved lazily: `latest` needs it, `help` does not.
PYTHON_BIN=()
resolve_python() {
  [ "${#PYTHON_BIN[@]}" -gt 0 ] && return 0
  if [ -n "${XREVIEW_PYTHON:-}" ]; then
    read -r -a PYTHON_BIN <<<"$XREVIEW_PYTHON"
    return 0
  fi
  local cand
  for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys' >/dev/null 2>&1; then
      PYTHON_BIN=("$cand")
      return 0
    fi
  done
  if command -v uv >/dev/null 2>&1 && uv run python -c 'import sys' >/dev/null 2>&1; then
    PYTHON_BIN=(uv run python)
    return 0
  fi
  die 'no usable Python interpreter (tried $XREVIEW_PYTHON, python3, python, uv run python)'
}

# Raw GitHub comment JSON on stdin -> one TSV row per comment on stdout:
#   id <TAB> created_at <TAB> login <TAB> html_url <TAB> base64(body)
# base64 keeps a multi-line body inside one field. `gh api --paginate` prints
# one JSON array PER PAGE, back to back, so this decodes a stream of arrays
# rather than a single document.
project_comments() {
  resolve_python
  "${PYTHON_BIN[@]}" -c '
import base64, json, sys

text = sys.stdin.buffer.read().decode("utf-8")
decoder = json.JSONDecoder()
pos = 0
out = []
while True:
    while pos < len(text) and text[pos] in " \t\r\n":
        pos += 1
    if pos >= len(text):
        break
    page, pos = decoder.raw_decode(text, pos)
    for c in page:
        body = c.get("body") or ""
        out.append("\t".join([
            str(c["id"]),
            # created_at, never updated_at: editing an old comment must not make
            # it the newest record.
            c["created_at"],
            c["user"]["login"],
            c["html_url"],
            base64.b64encode(body.encode("utf-8")).decode("ascii"),
        ]))
# Bytes, not text: on Windows the text layer translates every newline into
# CRLF, and that stray CR would ride along inside the last TSV field and
# break the base64 decode on the other side.
sys.stdout.buffer.write("".join(line + chr(10) for line in out).encode("utf-8"))
'
}

validate_login() {
  local value="$1" source="$2"
  [ -n "$value" ] || die "$source holds an empty GitHub login"
  [ "${#value}" -le "$LOGIN_MAX_LEN" ] \
    || die "$source: '${value}' is longer than ${LOGIN_MAX_LEN} characters, so it is not a GitHub login"
  [[ $value =~ $LOGIN_RE ]] \
    || die "$source: '${value}' is not a GitHub login (letters, digits and single inner hyphens only)"
}

coordinator_login() {
  if [ -n "${XREVIEW_COORDINATOR:-}" ]; then
    validate_login "$XREVIEW_COORDINATOR" 'XREVIEW_COORDINATOR'
    printf '%s\n' "$XREVIEW_COORDINATOR"
    return 0
  fi
  local file="$repo_root/.xreview-coordinator"
  [ -f "$file" ] || die "no coordinator account: set XREVIEW_COORDINATOR, or create $file with one GitHub login"
  local raw login='' count=0
  while IFS= read -r raw || [ -n "$raw" ]; do
    raw="${raw%$'\r'}"
    if [ -n "${raw//[[:space:]]/}" ]; then
      count=$((count + 1))
      login="$raw"
    fi
  done <"$file"
  # Exactly one line, checked rather than assumed: a handover that APPENDS the
  # new account leaves two, and picking the first would silently keep ignoring
  # the new coordinator's records.
  [ "$count" -eq 1 ] \
    || die "$file must hold exactly one non-blank line with one GitHub login, found ${count}"
  validate_login "$login" "$file"
  printf '%s\n' "$login"
}

# Last non-blank line of stdin, stripped of a trailing CR.
last_nonblank_line() {
  local line last=''
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    if [ -n "${line//[[:space:]]/}" ]; then last="$line"; fi
  done
  printf '%s\n' "$last"
}

# Number of lines starting with the verdict prefix, CR-tolerant.
count_verdict_lines() {
  local line count=0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in "${VERDICT_LINE_PREFIX}"*) count=$((count + 1)) ;; esac
  done
  printf '%s\n' "$count"
}

# TSV rows for <pr> into the file named by $2. Dies on API failure: an API that
# did not answer is not a PR without records, and the difference decides whether
# a stale marker goes into the ledger.
fetch_comments_into() {
  local pr="$1" dest="$2"
  local raw err rc
  raw="$(mktemp)"
  err="$(mktemp)"
  set +e
  env -u GITHUB_TOKEN gh api --paginate "repos/{owner}/{repo}/issues/${pr}/comments" >"$raw" 2>"$err"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "error: gh api failed (exit ${rc}) listing comments of PR ${pr}; refusing to report '尚未审'" >&2
    sed 's/^/  gh: /' "$err" >&2
    rm -f "$raw" "$err"
    exit 1
  fi
  set +e
  project_comments <"$raw" >"$dest" 2>"$err"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "error: could not read the comment payload of PR ${pr} (exit ${rc})" >&2
    sed 's/^/  /' "$err" >&2
    rm -f "$raw" "$err"
    exit 1
  fi
  rm -f "$raw" "$err"
}

cmd_latest() {
  local pr="${1:-}" with_url=0
  [ -n "$pr" ] || die 'latest needs a PR number: scripts/xreview.sh latest <pr>'
  case "${2:-}" in
    --with-url) with_url=1 ;;
    '') ;;
    *) die "unknown option '${2}'" ;;
  esac
  local coordinator
  coordinator="$(coordinator_login)"

  # Into a file, not a process substitution: a pipeline's or substitution's exit
  # status is invisible to the loop that consumes it, which is exactly how an
  # API failure used to be laundered into "no record".
  local rows
  rows="$(mktemp)"
  fetch_comments_into "$pr" "$rows"

  local best_created='' best_id=0 best_verdict='' best_url=''
  local id created login url body_b64 body first verdict body_verdict
  while IFS=$'\t' read -r id created login url body_b64; do
    [ -n "${id:-}" ] || continue
    [ "$login" = "$coordinator" ] || continue
    body="$(printf '%s' "$body_b64" | base64 -d)"
    first="$(printf '%s\n' "$body" | head -n 1)"
    first="${first%$'\r'}"
    case "$first" in
      '交叉审 r'*) ;;
      *) continue ;;
    esac
    if ! [[ $first =~ $FIRST_LINE_RE ]]; then
      rm -f "$rows"
      die "illegal cross-review record — first line does not match ${FIRST_LINE_RE}: $url"
    fi
    verdict="${BASH_REMATCH[2]}"
    body_verdict="$(printf '%s\n' "$body" | last_nonblank_line)"
    if ! [[ $body_verdict =~ $VERDICT_LINE_RE ]]; then
      rm -f "$rows"
      die "illegal cross-review record — last line is not the 裁决 line: $url"
    fi
    if [ "${BASH_REMATCH[1]}" != "$verdict" ]; then
      rm -f "$rows"
      die "cross-review record contradicts itself — header says ${verdict}, last line says ${BASH_REMATCH[1]}: $url"
    fi
    # created_at is ISO-8601 UTC accurate only to the second, so equal stamps are
    # ordinary; comment ids increase monotonically and break the tie the same way
    # for every reader.
    if [ "$created" \> "$best_created" ] || { [ "$created" = "$best_created" ] && [ "$id" -gt "$best_id" ]; }; then
      best_created="$created"
      best_id="$id"
      best_verdict="$verdict"
      best_url="$url"
    fi
  done <"$rows"
  rm -f "$rows"

  if [ -z "$best_verdict" ]; then
    printf '尚未审\n'
    return 0
  fi
  if [ "$with_url" -eq 1 ]; then
    printf '%s\t%s\n' "$best_verdict" "$best_url"
  else
    printf '%s\n' "$best_verdict"
  fi
}

cmd_post() {
  local pr="${1:-}" round="${2:-}" file="${3:-}"
  [ -n "$pr" ] && [ -n "$round" ] && [ -n "$file" ] \
    || die 'post needs three arguments: scripts/xreview.sh post <pr> <round> <verdict-file>'
  [[ $round =~ ^[0-9]+$ ]] || die "round must be a decimal number, got '$round'"
  [ -f "$file" ] || die "verdict file not found: $file"

  # Exactly one verdict line, and it must be the last non-blank one. A file that
  # says rework and then says approve has no single answer to record, so it is
  # refused at the boundary instead of being resolved by a rule nobody agreed on.
  local verdict_count tail_line verdict
  verdict_count="$(count_verdict_lines <"$file")"
  [ "$verdict_count" -eq 1 ] \
    || die "the verdict file must contain exactly one line starting with '${VERDICT_LINE_PREFIX}', found ${verdict_count}: $file"
  tail_line="$(last_nonblank_line <"$file")"
  [[ $tail_line =~ $VERDICT_LINE_RE ]] \
    || die "the verdict file's last non-blank line must match ${VERDICT_LINE_RE}, got '${tail_line}'"
  verdict="${BASH_REMATCH[1]}"

  # The header is CONSTRUCTED from the file's own verdict, never typed by hand.
  # That is what stops a header saying approve from ever sitting on a body that
  # says rework.
  local tmp
  tmp="$(mktemp)"
  { printf '交叉审 r%s:%s\n\n' "$round" "$verdict"; cat "$file"; } >"$tmp"

  local posted_url
  posted_url="$(env -u GITHUB_TOKEN gh pr comment "$pr" --body-file "$tmp" | tr -d '\r' | tail -n 1)"
  rm -f "$tmp"

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
