#!/usr/bin/env bash
# Self-test for scripts/wt-board.sh — runs the real script, never asserts on its
# source text. A shell condition that is silently always-false survives every
# text assertion ever written; only running it catches that.
#
# Manual gate: CI's pytest testpaths do not reach scripts/, so run this by hand
# after changing wt-board.sh:
#     bash scripts/tests/wt-board-selftest.sh
#
# It works on a throwaway board (WT_BOARD_DIR) so a test run can never disturb
# the claims real worktrees are holding on the shared board.
set -uo pipefail

board="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/wt-board.sh"
export WT_BOARD_DIR
WT_BOARD_DIR="$(mktemp -d)"
trap 'rm -rf "$WT_BOARD_DIR"' EXIT

failures=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; failures=$((failures + 1)); }
check() { # check <description> <condition-exit-code>
  if [ "$2" -eq 0 ]; then pass "$1"; else fail "$1"; fi
}

reset_board() { rm -rf "$WT_BOARD_DIR"; mkdir -p "$WT_BOARD_DIR"; }

echo "wt-board self-test  (board: $WT_BOARD_DIR)"

echo "[1] help states the DELIVERY_LEDGER boundary"
out="$("$board" help)"
check "help exits 0" $?
case "$out" in *DELIVERY_LEDGER.md*) check "help names the ledger it must not duplicate" 0 ;;
  *) check "help names the ledger it must not duplicate" 1 ;; esac

echo "[2] claim / duplicate claim"
reset_board
"$board" claim cdp-9222 --ttl 600 --note "first holder" >/dev/null
check "first claim succeeds" $?
out="$("$board" claim cdp-9222 --note "second holder" 2>&1)"
rc=$?
check "duplicate claim exits non-zero" "$([ "$rc" -ne 0 ]; echo $?)"
case "$out" in *"first holder"*) check "refusal names the current holder's note" 0 ;;
  *) check "refusal names the current holder's note" 1 ;; esac

echo "[3] status"
out="$("$board" status)"
check "status exits 0" $?
case "$out" in *cdp-9222*left*) check "status shows the claim with time left" 0 ;;
  *) check "status shows the claim with time left" 1 ;; esac
case "$out" in *"-- worktrees --"*) check "status lists worktrees" 0 ;;
  *) check "status lists worktrees" 1 ;; esac

echo "[4] renew extends the expiry"
before="$(grep '^expires_at_epoch=' "$WT_BOARD_DIR/locks/cdp-9222/owner" | cut -d= -f2)"
"$board" renew cdp-9222 --ttl 7200 >/dev/null
check "renew exits 0" $?
after="$(grep '^expires_at_epoch=' "$WT_BOARD_DIR/locks/cdp-9222/owner" | cut -d= -f2)"
check "expiry moved forward" "$([ "$after" -gt "$before" ]; echo $?)"
case "$(cat "$WT_BOARD_DIR/locks/cdp-9222/owner")" in *"first holder"*)
  check "renew keeps the original note" 0 ;; *) check "renew keeps the original note" 1 ;; esac

echo "[5] release is idempotent, then the resource is free again"
"$board" release cdp-9222 >/dev/null
check "release exits 0" $?
"$board" release cdp-9222 >/dev/null
check "releasing an unclaimed resource still exits 0" $?
"$board" claim cdp-9222 --ttl 600 >/dev/null
check "re-claim after release succeeds" $?

echo "[6] an expired claim is reclaimed, and the takeover is reported"
reset_board
"$board" claim port-8788 --ttl 1 --note "crashed holder" >/dev/null
sleep 2
out="$("$board" status)"
case "$out" in *EXPIRED*) check "status marks the stale claim EXPIRED" 0 ;;
  *) check "status marks the stale claim EXPIRED" 1 ;; esac
out="$("$board" claim port-8788 --ttl 300 --note "took over" 2>&1)"
check "claim over an expired holder succeeds" $?
case "$out" in *reclaimed*"crashed holder"*|*reclaimed*) check "takeover says it reclaimed an expired claim" 0 ;;
  *) check "takeover says it reclaimed an expired claim" 1 ;; esac

echo "[7] concurrent claims: exactly one winner"
reset_board
racers=8
results="$WT_BOARD_DIR/race"
mkdir -p "$results"
for i in $(seq 1 "$racers"); do
  (
    # Spin on the barrier so all racers reach mkdir within the same few
    # milliseconds; a staggered start would prove nothing about atomicity.
    while [ ! -f "$WT_BOARD_DIR/go" ]; do :; done
    if out="$("$board" claim main-app --ttl 60 --note "racer $i" 2>&1)"; then
      echo "$i" >"$results/win.$i"
    else
      printf '%s' "$out" >"$results/lose.$i"
    fi
  ) &
done
touch "$WT_BOARD_DIR/go"
wait
wins="$(find "$results" -name 'win.*' | wc -l | tr -d ' ')"
losses="$(find "$results" -name 'lose.*' | wc -l | tr -d ' ')"
printf '  (%s racers: %s won, %s lost)\n' "$racers" "$wins" "$losses"
check "exactly one racer won" "$([ "$wins" -eq 1 ]; echo $?)"
check "every other racer lost" "$([ "$losses" -eq $((racers - 1)) ]; echo $?)"
# Every loser must have read the winner's metadata WHOLE. A partially written
# owner file used to be readable, and the losers printed a holder with a blank
# expiry and a blank note — a plausible-looking, wrong board.
winner="$(basename "$(find "$results" -name 'win.*' | head -1)" | cut -d. -f2)"
partial=0
for f in "$results"/lose.*; do
  case "$(cat "$f")" in *"racer $winner"*) ;; *) partial=$((partial + 1)) ;; esac
done
check "every loser read the winner's metadata whole (note included)" "$([ "$partial" -eq 0 ]; echo $?)"

echo "[7b] a claim caught mid-write is reported as held, not as a corpse"
# Regression: the two-shell race really does land inside the window between
# mkdir and the metadata write. The loser used to be told the holder had died
# and pointed at `release --force`, which would have destroyed a live claim.
reset_board
lock="$WT_BOARD_DIR/locks/main-app"
mkdir -p "$lock"                                  # the lock exists, metadata does not yet
(
  sleep 0.3                                       # the holder is still writing its owner file
  {
    echo "branch=slow/writer"
    echo "worktree=/somewhere/else"
    echo "claimed_at_human=now"
    echo "expires_at_epoch=$(($(date +%s) + 600))"
    echo "expires_at_human=later"
    echo "note=slow writer"
  } >"$lock/owner"
) &
out="$("$board" claim main-app --ttl 60 --note "racer" 2>&1)"
rc=$?
wait
check "claiming against a mid-write lock is refused" "$([ "$rc" -ne 0 ]; echo $?)"
case "$out" in *"slow writer"*) check "the refusal names the holder once it finishes writing" 0 ;;
  *) check "the refusal names the holder once it finishes writing" 1 ;; esac
case "$out" in *"never described itself"*) check "the refusal does NOT call the live holder dead" 1 ;;
  *) check "the refusal does NOT call the live holder dead" 0 ;; esac

echo "[8] bad input is rejected at the boundary"
"$board" claim "../escape" >/dev/null 2>&1
check "a resource name with path characters is refused" "$([ $? -ne 0 ]; echo $?)"
"$board" claim port-1 --ttl abc >/dev/null 2>&1
check "a non-numeric --ttl is refused" "$([ $? -ne 0 ]; echo $?)"
"$board" claim port-1 --ttl >/dev/null 2>&1
check "a --ttl with no value is refused" "$([ $? -ne 0 ]; echo $?)"
"$board" frobnicate >/dev/null 2>&1
check "an unknown command is refused" "$([ $? -ne 0 ]; echo $?)"

echo "[9] another worktree's live claim needs --force to release"
reset_board
"$board" claim cdp-9222 --ttl 600 --note "neighbour" >/dev/null
owner="$WT_BOARD_DIR/locks/cdp-9222/owner"
sed -i 's|^worktree=.*|worktree=/somewhere/else|' "$owner"
"$board" release cdp-9222 >/dev/null 2>&1
check "release refuses a live claim owned elsewhere" "$([ $? -ne 0 ]; echo $?)"
"$board" release cdp-9222 --force >/dev/null 2>&1
check "release --force clears it" $?

echo "[10] note appends to the log and status shows it"
reset_board
"$board" note "restarting the app on 9222" >/dev/null
"$board" note "vendor rebuild running, sidecar will bounce" >/dev/null
lines="$(wc -l <"$WT_BOARD_DIR/log" | tr -d ' ')"
check "both notes were appended" "$([ "$lines" -eq 2 ]; echo $?)"
case "$("$board" status)" in *"vendor rebuild running"*) check "status shows recent notes" 0 ;;
  *) check "status shows recent notes" 1 ;; esac

echo
if [ "$failures" -eq 0 ]; then
  echo "wt-board self-test: all checks passed"
else
  echo "wt-board self-test: $failures check(s) FAILED"
fi
exit "$((failures > 0))"
