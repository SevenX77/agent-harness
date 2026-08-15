#!/usr/bin/env bash
# Runtime resource blackboard for parallel worktrees on ONE machine.
#
# SCOPE — it tracks exactly one thing: which runtime resource is occupied RIGHT
# NOW and by which worktree. A TCP port, the CDP debug port, the main app.
#
# NOT A TASK LEDGER. Task progress, PR state and TODOs live in
# docs/development/DELIVERY_LEDGER.md, which is their single owner (AGENTS.md
# "文档事实唯一所有权"). A second, half-maintained copy of that truth here would
# rot the moment the two disagree, so this board refuses to carry it.
#
# STORAGE — <repo-root>/.worktrees/.board/ : machine-local and volatile.
# .worktrees/ is gitignored, so nothing the board writes is ever committed.
# Losing the whole directory costs nothing but the current claims.
#
# LIVENESS — a claim dies of its TTL or of an explicit `release`, never of a PID
# probe. Under Git Bash the PIDs on the board come from MSYS shells while the
# processes actually holding a port are native Windows ones (node, uvicorn,
# WebView2); `kill -0` cannot see them, so PID-based liveness would report dead
# holders as alive and alive ones as dead. A number that lies is worse than no
# number, so no PID is recorded at all.
set -euo pipefail

readonly DEFAULT_TTL_SECONDS=3600
# The lock directory necessarily appears one syscall before the metadata written
# inside it. A reader landing in that window sees an owner-less lock, which is
# byte-for-byte the same thing a holder that died mid-claim leaves behind — so
# the reader waits the window out instead of guessing. Writing the metadata is
# seven printf's; a lock still empty after this long is a corpse, not a race.
# (Measured need: a two-shell claim race hits this window routinely, and the
# wrong guess told the loser to --force away a perfectly healthy claim.)
# The budget is counted in polls, not in wall-clock seconds: `date +%s` has
# one-second granularity, so a "2 second" deadline would really be anywhere
# between 1 and 2 seconds depending on where the call landed inside a tick.
readonly OWNER_SETTLE_POLLS=20
readonly OWNER_SETTLE_INTERVAL_SECONDS=0.1

usage() {
  cat <<'EOF'
scripts/wt-board.sh — runtime resource blackboard for parallel worktrees

USAGE
  scripts/wt-board.sh claim   <resource> [--ttl <seconds>] [--note "<one line>"]
  scripts/wt-board.sh release <resource> [--force]
  scripts/wt-board.sh renew   <resource> [--ttl <seconds>]
  scripts/wt-board.sh status
  scripts/wt-board.sh holds   <resource>          # exit 0 only if THIS caller holds it
  scripts/wt-board.sh note    "<one line>"
  scripts/wt-board.sh help

WHAT IT IS FOR
  Several agents work in parallel worktrees on ONE machine. They share ports and
  they share the single CDP debug port. The board is where a worktree announces
  "I am holding this right now" so the others pick something else instead of
  fighting over it.

WHAT IT IS NOT FOR
  It is NOT a second task ledger. Do not record task progress, PR numbers, TODO
  lists or "what I'm working on" here — that truth belongs to
  docs/development/DELIVERY_LEDGER.md and must have exactly one owner. `note` is
  for runtime facts a neighbour needs ("restarting the app on 9222"), one line,
  not a status report.

RESOURCE NAMES (conventional; letters, digits, '-' and '_' only)
  cdp-9222      the WebView2 debug port used for real-window verification.
                Globally exclusive: one machine, one debugged window, one port —
                two agents driving it at once send clicks into each other's run.
  main-app      the repo root's full app (Vite 5173 + sidecar 8787).
  port-<n>      a worktree's private Vite / sidecar port. scripts/wt-dev.sh
                claims these for you and releases them when it exits.

WHO IS HOLDING IT
  A claim records the worktree, the branch and WT_BOARD_AGENT — a stable id for
  the session doing the work. Set it once per session:
      export WT_BOARD_AGENT=<your session id>
  Two agents routinely work from the same tree (the repo root), so the worktree
  path alone cannot separate them. `holds` refuses to answer yes unless both the
  claim and the caller name themselves, which is what lets a tool guard itself:
      scripts/wt-board.sh holds cdp-9222 || exit 1

TTL
  Default 3600s. A claim expires on its own so a crashed holder cannot block the
  resource forever; `claim` on an expired claim takes it over and says so.
  Long job? `renew` it, or claim it with a bigger --ttl up front.
EOF
}

repo_root="$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd)")"
# WT_BOARD_DIR exists so the self-test (scripts/tests/wt-board-selftest.sh) can
# run against a throwaway board instead of polluting the shared one.
board_dir="${WT_BOARD_DIR:-$repo_root/.worktrees/.board}"
locks_dir="$board_dir/locks"
log_file="$board_dir/log"

self_worktree="$(git rev-parse --show-toplevel)"
self_branch="$(git rev-parse --abbrev-ref HEAD)"
# Who is holding it, one level finer than the worktree. Two agents routinely work
# from the SAME tree — the repo root — so the worktree path alone cannot tell
# them apart, and on 2026-08-15 two of them drove the same debugged window while
# the board looked consistent to both. Same idea as a Kubernetes Lease's
# holderIdentity or a Terraform state lock's ID: a claim is worthless as a mutual
# exclusion unless the holder can be named. Empty when the caller never set one,
# which `holds` treats as "cannot prove it is mine".
self_agent="${WT_BOARD_AGENT:-}"

die() { echo "error: $*" >&2; exit 1; }

now_epoch() { date +%s; }
now_human() { date '+%Y-%m-%d %H:%M:%S'; }

# Resource names become directory names, so the character set is restricted at
# the boundary instead of being sanitised later: no '/', no '.', no traversal.
validate_resource() {
  case "$1" in
    '') die "missing <resource> — see: scripts/wt-board.sh help" ;;
    *[!A-Za-z0-9_-]*) die "invalid resource name '$1' — letters, digits, '-' and '_' only" ;;
  esac
}

validate_ttl() {
  case "$1" in
    ''|*[!0-9]*) die "--ttl wants whole seconds, got '$1'" ;;
    0) die "--ttl 0 would expire instantly" ;;
  esac
}

fmt_duration() { # fmt_duration <non-negative seconds> -> "2h05m" / "5m30s" / "42s"
  local s="$1"
  if [ "$s" -ge 3600 ]; then printf '%dh%02dm' "$((s / 3600))" "$(((s % 3600) / 60))"
  elif [ "$s" -ge 60 ]; then printf '%dm%02ds' "$((s / 60))" "$((s % 60))"
  else printf '%ds' "$s"; fi
}

# Metadata of the last lock read_owner() succeeded on.
owner_branch=""; owner_worktree=""; owner_agent=""; owner_note=""
owner_claimed_human=""; owner_expires_epoch=""; owner_expires_human=""

read_owner() { # read_owner <lock-dir> -> 1 when the metadata is missing/unusable
  local key value
  owner_branch=""; owner_worktree=""; owner_agent=""; owner_note=""
  owner_claimed_human=""; owner_expires_epoch=""; owner_expires_human=""
  [ -r "$1/owner" ] || return 1
  while IFS='=' read -r key value; do
    case "$key" in
      branch) owner_branch="$value" ;;
      worktree) owner_worktree="$value" ;;
      agent) owner_agent="$value" ;;
      claimed_at_human) owner_claimed_human="$value" ;;
      expires_at_epoch) owner_expires_epoch="$value" ;;
      expires_at_human) owner_expires_human="$value" ;;
      note) owner_note="$value" ;;
    esac
  done <"$1/owner"
  case "$owner_expires_epoch" in
    ''|*[!0-9]*) return 1 ;;
  esac
  return 0
}

read_owner_settled() { # read_owner_settled <lock-dir> -> 1 only if it never settles
  local poll=0
  while :; do
    read_owner "$1" && return 0
    [ "$poll" -lt "$OWNER_SETTLE_POLLS" ] || return 1
    poll=$((poll + 1))
    sleep "$OWNER_SETTLE_INTERVAL_SECONDS"
  done
}

write_owner() { # write_owner <lock-dir> <ttl> <note>
  local lock="$1" ttl="$2" note="$3" start
  start="$(now_epoch)"
  # Both epoch and human forms are stored because converting one to the other at
  # read time needs `date -d @…` (GNU) or `date -r …` (BSD) — the board must
  # print the same thing on Windows, macOS and Linux.
  #
  # Written to a scratch name inside the same lock directory and renamed into
  # place, so `owner` goes from absent to complete in one step. Writing the
  # seven lines straight into `owner` let a concurrent reader see the first four
  # and print a holder with a blank expiry and a blank note — observed for real
  # in a two-shell claim race. A half-read holder is a half-true board.
  {
    printf 'branch=%s\n' "$self_branch"
    printf 'worktree=%s\n' "$self_worktree"
    printf 'agent=%s\n' "$self_agent"
    printf 'claimed_at_epoch=%s\n' "$start"
    printf 'claimed_at_human=%s\n' "$(now_human)"
    printf 'expires_at_epoch=%s\n' "$((start + ttl))"
    printf 'expires_at_human=%s\n' "$(date_at "$((start + ttl))")"
    printf 'note=%s\n' "$note"
  } >"$lock/.owner.pending"
  mv "$lock/.owner.pending" "$lock/owner"
}

# Expiry timestamps are rendered by adding the TTL to the *current* wall clock
# rather than formatting a future epoch, which no portable `date` can do.
date_at() { # date_at <epoch in the future>
  local delta=$(($1 - $(now_epoch)))
  if [ "$delta" -le 0 ]; then now_human; else
    # Both GNU and BSD date can do relative offsets, with different flags.
    date -d "+${delta} seconds" '+%Y-%m-%d %H:%M:%S' 2>/dev/null \
      || date -v "+${delta}S" '+%Y-%m-%d %H:%M:%S' 2>/dev/null \
      || now_human
  fi
}

one_line() { printf '%s' "$1" | tr '\n\t\r' '   '; }

print_holder() { # print_holder <resource> <remaining seconds, may be negative>
  local remaining="$2"
  printf '  holder:  %s  @ %s\n' "${owner_branch:-?}" "${owner_worktree:-?}"
  printf '  since:   %s\n' "${owner_claimed_human:-?}"
  if [ "$remaining" -ge 0 ]; then
    printf '  expires: %s  (%s left)\n' "${owner_expires_human:-?}" "$(fmt_duration "$remaining")"
  else
    printf '  expired: %s  (%s ago)\n' "${owner_expires_human:-?}" "$(fmt_duration "$((-remaining))")"
  fi
  [ -n "$owner_note" ] && printf '  note:    %s\n' "$owner_note"
  return 0
}

append_log() { # append_log <text>
  mkdir -p "$board_dir"
  # '>>' on a short line is the whole concurrency story: every writer opens in
  # append mode, so two simultaneous notes interleave as two lines, never as one
  # mangled line. No lock file, nothing to leak.
  printf '%s\t%s\t%s\n' "$(now_human)" "$self_branch" "$(one_line "$1")" >>"$log_file"
}

cmd_claim() {
  local resource="" ttl="$DEFAULT_TTL_SECONDS" note=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --ttl) [ $# -ge 2 ] || die "--ttl needs a value in seconds"; ttl="$2"; shift 2 ;;
      --note) [ $# -ge 2 ] || die "--note needs a quoted line"; note="$(one_line "$2")"; shift 2 ;;
      -*) die "unknown flag '$1' for claim" ;;
      *) [ -z "$resource" ] || die "claim takes one resource, got '$resource' and '$1'"
         resource="$1"; shift ;;
    esac
  done
  validate_resource "$resource"
  validate_ttl "$ttl"
  mkdir -p "$locks_dir"

  local lock="$locks_dir/$resource" reclaimed="" attempt remaining stale
  # Two attempts: the second one exists only for the reclaim path below, where
  # this process has just cleared an expired claim and races the neighbour who
  # noticed the same expiry. Whoever loses that race reports the winner.
  for attempt in 1 2; do
    if mkdir "$lock" 2>/dev/null; then
      write_owner "$lock" "$ttl" "$note"
      # Print what was actually stored, so the message can never describe an
      # expiry the file does not carry.
      read_owner "$lock"
      printf '✓ claimed %s  (%s, expires %s)\n' \
        "$resource" "$(fmt_duration "$ttl")" "$owner_expires_human"
      [ -n "$note" ] && printf '  note: %s\n' "$note"
      [ -n "$reclaimed" ] && printf '  ↻ %s\n' "$reclaimed"
      append_log "claim $resource${note:+ — $note}${reclaimed:+ ($reclaimed)}"
      return 0
    fi

    if ! read_owner_settled "$lock"; then
      echo "✗ $resource is occupied but never described itself" \
           "(waited ${OWNER_SETTLE_POLLS}×${OWNER_SETTLE_INTERVAL_SECONDS}s)" >&2
      echo "  a claim died between creating the lock and writing its metadata." >&2
      echo "  clear it deliberately: scripts/wt-board.sh release $resource --force" >&2
      return 1
    fi

    remaining=$((owner_expires_epoch - $(now_epoch)))
    if [ "$remaining" -ge 0 ]; then
      echo "✗ $resource is already claimed" >&2
      print_holder "$resource" "$remaining" >&2
      echo "  wait, or have that worktree run: scripts/wt-board.sh release $resource" >&2
      return 1
    fi

    # Expired. `mv` of the lock directory is the atomic step: exactly one racer
    # can rename it away, the other gets ENOENT and loops back into mkdir.
    stale="$locks_dir/.stale-$resource-$$-${RANDOM}"
    if mv "$lock" "$stale" 2>/dev/null; then
      rm -rf "$stale"
      reclaimed="reclaimed an expired claim (was ${owner_branch:-?}, expired ${owner_expires_human:-?})"
    fi
  done

  echo "✗ $resource was taken by another worktree while its expired claim was being reclaimed" >&2
  if read_owner_settled "$lock"; then
    print_holder "$resource" "$((owner_expires_epoch - $(now_epoch)))" >&2
  fi
  return 1
}

cmd_release() {
  local resource="" force=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --force) force=1; shift ;;
      -*) die "unknown flag '$1' for release" ;;
      *) [ -z "$resource" ] || die "release takes one resource, got '$resource' and '$1'"
         resource="$1"; shift ;;
    esac
  done
  validate_resource "$resource"

  local lock="$locks_dir/$resource"
  if [ ! -d "$lock" ]; then
    # Idempotent on purpose: release runs from an EXIT trap, and a trap that
    # fails because the work was already done is a trap people stop trusting.
    printf 'nothing to release — %s is not claimed\n' "$resource"
    return 0
  fi

  if [ "$force" -eq 0 ] && read_owner_settled "$lock" \
     && [ "$owner_worktree" != "$self_worktree" ] \
     && [ "$((owner_expires_epoch - $(now_epoch)))" -ge 0 ]; then
    echo "✗ refusing to release $resource — it is held by another worktree" >&2
    print_holder "$resource" "$((owner_expires_epoch - $(now_epoch)))" >&2
    echo "  if you are sure that holder is gone: scripts/wt-board.sh release $resource --force" >&2
    return 1
  fi

  rm -rf "$lock"
  printf '✓ released %s\n' "$resource"
  append_log "release $resource"
}

cmd_renew() {
  local resource="" ttl="$DEFAULT_TTL_SECONDS"
  while [ $# -gt 0 ]; do
    case "$1" in
      --ttl) [ $# -ge 2 ] || die "--ttl needs a value in seconds"; ttl="$2"; shift 2 ;;
      -*) die "unknown flag '$1' for renew" ;;
      *) [ -z "$resource" ] || die "renew takes one resource, got '$resource' and '$1'"
         resource="$1"; shift ;;
    esac
  done
  validate_resource "$resource"
  validate_ttl "$ttl"

  local lock="$locks_dir/$resource"
  [ -d "$lock" ] || die "$resource is not claimed — use: scripts/wt-board.sh claim $resource"
  read_owner_settled "$lock" || die "$resource never described itself — release --force it and claim again"
  [ "$owner_worktree" = "$self_worktree" ] \
    || die "$resource is held by ${owner_branch:-?} @ $owner_worktree, not by this worktree"

  local was_expired=""
  [ "$((owner_expires_epoch - $(now_epoch)))" -lt 0 ] && was_expired=" (it had already expired)"
  write_owner "$lock" "$ttl" "$owner_note"
  read_owner "$lock"
  printf '✓ renewed %s  (%s, expires %s)%s\n' \
    "$resource" "$(fmt_duration "$ttl")" "$owner_expires_human" "$was_expired"
  append_log "renew $resource"
}

cmd_status() {
  printf '== runtime resource board ==  %s\n' "$board_dir"
  printf 'machine-local and volatile. Task progress / PR state belong to\n'
  printf 'docs/development/DELIVERY_LEDGER.md — not here.\n\n'

  printf -- '-- claims --\n'
  local found=0 lock resource remaining state
  if [ -d "$locks_dir" ]; then
    for lock in "$locks_dir"/*/; do
      [ -d "$lock" ] || continue
      resource="$(basename "$lock")"
      found=1
      if read_owner_settled "$lock"; then
        remaining=$((owner_expires_epoch - $(now_epoch)))
        if [ "$remaining" -ge 0 ]; then
          state="$(fmt_duration "$remaining") left"
        else
          state="EXPIRED $(fmt_duration "$((-remaining))") ago"
        fi
        printf '  %-12s %-28s %-14s %-18s %s\n' \
          "$resource" "${owner_branch:-?}" "${owner_agent:-<anon>}" "$state" "${owner_note:-}"
      else
        printf '  %-12s %-28s %-14s %-18s %s\n' \
          "$resource" "?" "?" "NEVER DESCRIBED" "dead claim — release --force to clear"
      fi
    done
  fi
  [ "$found" -eq 1 ] || printf '  无占用 / nothing claimed\n'

  printf '\n-- worktrees --\n'
  git worktree list | sed 's/^/  /'

  printf '\n-- recent notes (last 10) --\n'
  if [ -s "$log_file" ]; then
    tail -n 10 "$log_file" | sed 's/^/  /'
  else
    printf '  (none)\n'
  fi
}

# The question a tool asks before it touches the resource. Exit 0 means "this
# caller holds a live claim on it" and nothing else — so a guard can be a single
# line, and a wrong answer fails closed.
cmd_holds() {
  local resource="${1:-}"
  [ $# -le 1 ] || die "holds takes one resource"
  validate_resource "$resource"

  local lock="$locks_dir/$resource"
  if [ ! -d "$lock" ] || ! read_owner_settled "$lock"; then
    echo "✗ $resource is not claimed" >&2
    return 1
  fi

  local remaining=$((owner_expires_epoch - $(now_epoch)))
  if [ "$remaining" -lt 0 ]; then
    echo "✗ the claim on $resource expired $(fmt_duration "$((-remaining))") ago" >&2
    print_holder "$resource" "$remaining" >&2
    return 1
  fi

  # Both sides must be able to name themselves. An anonymous claim and an
  # anonymous caller would compare equal while being two different agents —
  # precisely the case this identity exists to separate — so an unnamed holder
  # is treated as unproven rather than as a match.
  if [ -z "$self_agent" ] || [ -z "$owner_agent" ]; then
    echo "✗ cannot prove the claim on $resource is yours" >&2
    [ -z "$self_agent" ] && echo "  this caller set no WT_BOARD_AGENT" >&2
    [ -z "$owner_agent" ] && echo "  the claim carries no agent identity" >&2
    echo "  export WT_BOARD_AGENT=<stable id for this session>, then re-claim" >&2
    print_holder "$resource" "$remaining" >&2
    return 1
  fi

  if [ "$owner_agent" != "$self_agent" ] || [ "$owner_worktree" != "$self_worktree" ]; then
    echo "✗ $resource is held by someone else" >&2
    print_holder "$resource" "$remaining" >&2
    return 1
  fi
  return 0
}

cmd_note() {
  [ $# -eq 1 ] || die 'note takes exactly one quoted line: scripts/wt-board.sh note "restarting app on 9222"'
  [ -n "$1" ] || die 'note text is empty'
  append_log "$1"
  printf '✓ noted\n'
}

subcommand="${1:-help}"
[ $# -gt 0 ] && shift
case "$subcommand" in
  claim) cmd_claim "$@" ;;
  release) cmd_release "$@" ;;
  renew) cmd_renew "$@" ;;
  status) cmd_status "$@" ;;
  holds) cmd_holds "$@" ;;
  note) cmd_note "$@" ;;
  help|-h|--help) usage ;;
  *) usage >&2; echo >&2; die "unknown command '$subcommand'" ;;
esac
