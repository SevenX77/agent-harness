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
# (AGENTS.md 通用工程原则 7 "离线可验证"). The document now points here and
# states no steps of its own — one owner per fact (文档事实唯一所有权).
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
# TEST BOUNDARY. The self-test drives this script against a fake `gh` and covers
# everything below the API: pagination, author filtering, both fail-fast paths,
# tie-breaking, header construction. What it cannot cover is the projection
# string handed to gh's built-in jq — verify that against a real PR whenever you
# change it (`scripts/xreview.sh latest <pr>` on a PR whose records you know).
set -euo pipefail

# The record's shape. Both regexes are anchored: a line either is a record or it
# is not, with nothing in between for a reader to interpret.
readonly FIRST_LINE_RE='^交叉审 r([0-9]+):(approve|rework)$'
readonly VERDICT_LINE_RE='^裁决:(approve|rework)$'
# One line per comment, projected by gh's built-in jq. Field order is fixed;
# base64 keeps a multi-line body inside a single TSV field.
readonly COMMENT_PROJECTION='.[] | [(.id|tostring), .created_at, .user.login, .html_url, (.body|@base64)] | @tsv'

usage() {
  cat <<'EOF'
scripts/xreview.sh — the cross-review adjudication record of a PR

USAGE
  scripts/xreview.sh post   <pr> <round> <verdict-file>
  scripts/xreview.sh latest <pr> [--with-url]
  scripts/xreview.sh help

post
  Reads <verdict-file> — the cross-review seat's raw output, e.g. codex's
  --output-last-message file. Its LAST non-blank line must be 裁决:approve or
  裁决:rework, otherwise post refuses. Builds the comment as a header line
  carrying THAT verdict, a blank line, then the file verbatim; posts it; then
  reads it back to prove the record it just wrote is the one latest sees.

latest
  Prints the most recent cross-review adjudication of <pr>: approve, rework, or
  尚未审 when the PR has no record yet. Exits non-zero, naming the offending
  comment URL, when a comment looks like a record but is not a valid one — an
  unreadable record is never silently skipped and never falls back to an older
  one, because that hands the ledger a stale marker.
  --with-url also prints the winning comment URL (tab-separated).

COORDINATOR ACCOUNT
  Only comments authored by the coordinator account count; nobody else posting
  the same shape may overwrite the record. The account is read from
  XREVIEW_COORDINATOR, else from <repo-root>/.xreview-coordinator (one login,
  checked in). Handing coordination to another account is a PR editing that file.

SELF-TEST
  CI's pytest testpaths do not reach scripts/, so after changing this script run
      bash scripts/tests/xreview-selftest.sh
EOF
}

die() { echo "error: $*" >&2; exit 1; }

# --show-toplevel, not --git-common-dir: .xreview-coordinator is a CHECKED-IN
# file, so it must come from the working tree being used (a worktree has its own
# copy), not from wherever the shared .git lives.
repo_root="$(git rev-parse --show-toplevel)"
readonly repo_root

coordinator_login() {
  if [ -n "${XREVIEW_COORDINATOR:-}" ]; then
    printf '%s\n' "$XREVIEW_COORDINATOR"
    return 0
  fi
  local file="$repo_root/.xreview-coordinator"
  [ -f "$file" ] || die "no coordinator account: set XREVIEW_COORDINATOR, or create $file with one GitHub login"
  local login
  login="$(head -n 1 "$file" | tr -d '[:space:]')"
  [ -n "$login" ] || die "$file is empty; it must hold exactly one GitHub login"
  printf '%s\n' "$login"
}

# --paginate is not optional: GitHub returns 30 comments per page, so without it
# a PR with 31 comments hides its newest record, and an illegal record on a
# later page never trips the fail-fast either.
fetch_comments() {
  local pr="$1"
  env -u GITHUB_TOKEN gh api --paginate \
    "repos/{owner}/{repo}/issues/${pr}/comments" \
    --jq "$COMMENT_PROJECTION"
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
    [[ $first =~ $FIRST_LINE_RE ]] \
      || die "illegal cross-review record — first line does not match ${FIRST_LINE_RE}: $url"
    verdict="${BASH_REMATCH[2]}"
    body_verdict="$(printf '%s\n' "$body" | last_nonblank_line)"
    [[ $body_verdict =~ $VERDICT_LINE_RE ]] \
      || die "illegal cross-review record — last line is not the 裁决 line: $url"
    [ "${BASH_REMATCH[1]}" = "$verdict" ] \
      || die "cross-review record contradicts itself — header says ${verdict}, last line says ${BASH_REMATCH[1]}: $url"
    # created_at is ISO-8601 UTC accurate only to the second, so equal stamps are
    # ordinary; comment ids increase monotonically and break the tie the same way
    # for every reader.
    if [ "$created" \> "$best_created" ] || { [ "$created" = "$best_created" ] && [ "$id" -gt "$best_id" ]; }; then
      best_created="$created"
      best_id="$id"
      best_verdict="$verdict"
      best_url="$url"
    fi
  done < <(fetch_comments "$pr")

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

  local tail_line verdict
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
