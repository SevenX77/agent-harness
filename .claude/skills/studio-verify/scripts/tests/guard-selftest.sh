#!/usr/bin/env bash
# Self-test for the launcher board guard (assert-claim.ps1 + the two launchers)
# — it RUNS the real launchers instead of asserting on their source text. That
# distinction is the whole reason this file exists: on 2026-08-31 the guard was
# dot-sourced, its `exit 4` did not abort the caller, and every text-level
# reading of the code still said "the launcher refuses". Only executing it
# showed the launcher restarting the shared app right after printing a refusal.
#
# Manual gate, like scripts/tests/wt-board-selftest.sh: CI's pytest testpaths do
# not reach .claude/, so run this by hand after changing the guard or either
# launcher —
#     bash .claude/skills/studio-verify/scripts/tests/guard-selftest.sh
#
# SAFETY — this never touches the working tree, the real board, or the real app.
# It builds a throwaway replica repo in a temp dir (the real .ps1 files copied
# in, the real wt-board.sh, a git init so the board can name a worktree, and a
# STUB studio-dev.ps1 that only prints a marker), points WT_BOARD_DIR and TEMP
# at that temp dir, and runs the launchers there. Even a total fail-open starts
# nothing: the only thing behind the guard is the stub.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src_scripts="$(cd "$here/.." && pwd)"
src_repo="$(cd "$src_scripts/../../../.." && pwd)"

if ! command -v powershell >/dev/null 2>&1; then
  echo "SKIPPED: no powershell on this machine — these launchers are Windows-only."
  exit 0
fi

sandbox="$(mktemp -d)"
trap 'rm -rf "$sandbox"' EXIT
replica="$sandbox/repo"
replica_scripts="$replica/.claude/skills/studio-verify/scripts"
mkdir -p "$replica_scripts" "$replica/scripts" "$sandbox/temp" "$sandbox/board"

cp "$src_scripts/assert-claim.ps1" "$src_scripts/launch-studio-cdp.ps1" \
   "$src_scripts/launch-studio-clean.ps1" "$replica_scripts/"
cp "$src_repo/scripts/wt-board.sh" "$replica/scripts/"
printf 'Write-Host "STUB-STUDIO-DEV: PROCEEDED TO LAUNCH"\r\n' > "$replica/scripts/studio-dev.ps1"
# wt-board.sh asks git who the holder is, and `rev-parse --abbrev-ref HEAD`
# fails on an unborn branch, so the replica needs one commit to be a repo the
# board can describe.
git -C "$replica" init -q
git -C "$replica" -c user.email=selftest@local -c user.name=selftest \
    commit -q --allow-empty -m "replica"

export WT_BOARD_DIR="$sandbox/board"
export TEMP TMP
TEMP="$(cygpath -w "$sandbox/temp")"
TMP="$TEMP"

win() { cygpath -w "$1"; }
board() { ( cd "$replica" && bash scripts/wt-board.sh "$@" ); }

failures=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; failures=$((failures + 1)); }

# launch <cdp|clean> <expected exit> <launched|refused> <description> [env...]
launch() {
  local which="$1" want_rc="$2" want_state="$3" desc="$4"; shift 4
  local log="$sandbox/temp/studio-dev-$which.log"
  rm -f "$sandbox/temp/studio-dev-cdp.log" "$sandbox/temp/studio-dev-clean.log"
  local out rc state
  out="$(env "$@" powershell -NoProfile -ExecutionPolicy Bypass \
         -File "$(win "$replica_scripts/launch-studio-$which.ps1")" 2>&1)"
  rc=$?
  state="refused"; [ -f "$log" ] && state="launched"
  if [ "$rc" = "$want_rc" ] && [ "$state" = "$want_state" ]; then
    pass "$desc  (exit $rc, app $state)"
  else
    fail "$desc  (wanted exit $want_rc + app $want_state, got exit $rc + app $state)"
    printf '%s\n' "$out" | sed 's/^/       | /'
  fi
}

echo "studio-verify guard self-test  (replica: $replica)"

echo "[0] the .ps1 files stay pure ASCII"
# Windows PowerShell 5.1 decodes a BOM-less .ps1 with the system ANSI codepage
# (cp936 here), and .gitattributes stores .ps1 without a BOM. Measured
# 2026-08-31: one U+2014 em dash in a string literal makes the file fail to
# PARSE, because its 0x94 byte is read as a GBK lead byte that swallows the
# closing quote. A guard that cannot parse is a guard that is not there.
for f in assert-claim.ps1 launch-studio-cdp.ps1 launch-studio-clean.ps1; do
  if LC_ALL=C grep -qP '[\x80-\xff]' "$src_scripts/$f"; then
    fail "$f is pure ASCII"
  else
    pass "$f is pure ASCII"
  fi
done

echo "[1] no claim on the board -> refuse"
launch cdp 4 refused "cdp launcher refuses with no claim" WT_BOARD_AGENT=agent-alpha
launch clean 4 refused "clean launcher refuses with no claim" WT_BOARD_AGENT=agent-alpha

echo "[2] claim held by this session -> allow"
WT_BOARD_AGENT=agent-alpha board claim cdp-9222 --ttl 600 --note "guard self-test" >/dev/null
launch cdp 0 launched "cdp launcher proceeds while holding the claim" WT_BOARD_AGENT=agent-alpha
launch clean 0 launched "clean launcher proceeds while holding the claim" WT_BOARD_AGENT=agent-alpha

echo "[3] a different WT_BOARD_AGENT -> refuse again"
launch cdp 4 refused "cdp launcher refuses agent-beta" WT_BOARD_AGENT=agent-beta
launch clean 4 refused "clean launcher refuses agent-beta" WT_BOARD_AGENT=agent-beta
launch cdp 4 refused "cdp launcher refuses an anonymous caller" WT_BOARD_AGENT=

echo "[4] the guard cannot ASK the board -> refuse with the OTHER code (5)"
# The claim is still held here, so anything that refuses can only be refusing
# because it could not ask — which must not be reported as "you did not claim".
cat > "$sandbox/no-bash.ps1" <<EOF
\$env:PATH = ''
\$env:ProgramFiles = ''
\${env:ProgramFiles(x86)} = ''
\$env:LOCALAPPDATA = ''
& '$(win "$replica_scripts/launch-studio-cdp.ps1")'
exit \$LASTEXITCODE
EOF
out="$(WT_BOARD_AGENT=agent-alpha powershell -NoProfile -ExecutionPolicy Bypass \
       -File "$(win "$sandbox/no-bash.ps1")" 2>&1)"; rc=$?
if [ "$rc" = 5 ] && [ ! -f "$sandbox/temp/studio-dev-cdp.log" ]; then
  pass "no Git Bash reachable -> exit 5, app not started"
else
  fail "no Git Bash reachable -> exit 5, app not started (got exit $rc)"
  printf '%s\n' "$out" | sed 's/^/       | /'
fi

mv "$replica/scripts/wt-board.sh" "$replica/scripts/wt-board.sh.away"
launch cdp 5 refused "board script missing -> exit 5" WT_BOARD_AGENT=agent-alpha
mv "$replica/scripts/wt-board.sh.away" "$replica/scripts/wt-board.sh"

echo "[5] the guard file itself is unreachable -> still no launch"
mv "$replica_scripts/assert-claim.ps1" "$replica_scripts/assert-claim.ps1.away"
launch cdp 1 refused "missing guard aborts the launcher" WT_BOARD_AGENT=agent-alpha
mv "$replica_scripts/assert-claim.ps1.away" "$replica_scripts/assert-claim.ps1"

echo "[6] a refusal leaves a diagnosable trace on disk"
# The launchers run detached and hidden, so the console is nobody's screen.
if [ -s "$sandbox/temp/studio-verify-guard.log" ]; then
  pass "studio-verify-guard.log records the refusals"
else
  fail "studio-verify-guard.log records the refusals"
fi

echo
if [ "$failures" -eq 0 ]; then
  echo "ALL PASS"
else
  echo "$failures FAILURE(S)"
fi
exit "$failures"
