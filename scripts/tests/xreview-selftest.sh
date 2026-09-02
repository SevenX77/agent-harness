#!/usr/bin/env bash
# Self-test for scripts/xreview.sh — runs the real script against a fake `gh`,
# never asserts on its source text. A shell condition that is silently
# always-false survives every text assertion ever written; only running it
# catches that (same reason as scripts/tests/wt-board-selftest.sh).
#
# Manual gate: CI's pytest testpaths do not reach scripts/, so run this by hand
# after changing xreview.sh:
#     bash scripts/tests/xreview-selftest.sh
#
# WHAT THE FAKE gh DOES. It answers the two calls xreview.sh makes, with the
# payloads GitHub really returns:
#   * `gh api ...` — prints RAW comment JSON, one array per page, back to back,
#     exactly as `gh api --paginate` does. It prints page 2 only when
#     --paginate is present, which is how GitHub behaves, so fixture [1] is a
#     real test of that flag. Because the fake hands over raw JSON, the
#     script's own parsing runs for real — which is what gives the
#     `created_at` ordering contract (fixture [5b]) any protection at all.
#   * `gh pr comment <n> --body-file <f>` — saves the body, appends it to the
#     fixture as a new comment, and prints its URL, so the post round-trip
#     (post -> read back -> compare) really happens.
#   * With XREVIEW_FAKE_API_RC set, `gh api` fails with that exit code, which is
#     how fixture [10] proves an unreachable API is never reported as 尚未审.
#
# WHY SOME BODIES COME FROM FILES. A body is fixture data, so it must reach the
# fake gh unchanged — and the two bodies that matter most cannot survive a shell
# variable: one carries a NUL (bash drops it) and one is 90 KB (which is where
# `head` in a pipeline started killing its producer with SIGPIPE). Those are
# written by Python straight to disk and base64'd from there.
#
# MUTATION-CHECKED. Each of these was applied to xreview.sh and the suite was
# run: every one turns it red, so every one of these contracts is really held
# here rather than merely written down.
#   * `created_at` -> `updated_at`            -> [5b]
#   * drop `--paginate`                       -> [1]
#   * drop the author filter                  -> [4]
#   * compare the author case-sensitively     -> [4b]
#   * LOGIN_RE anchored with `$` not `\Z`     -> [9] (a trailing blank line)
#   * "exactly one 裁决 line" -> "at least one"-> [3b] AND [8], from ONE edit,
#     which is what "the reader and the writer share an implementation" looks
#     like when you try to break it.
set -uo pipefail

script="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/xreview.sh"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

# A real interpreter for the fixtures — and, exported as XREVIEW_PYTHON, for the
# script under test, so the suite does not re-probe `uv run python` on every one
# of its ~40 invocations. Fixture [11] is the one that unsets it and exercises
# the script's own resolution order.
selftest_python() {
  local cand path
  for cand in python3 python; do
    path="$(command -v "$cand" 2>/dev/null)" || continue
    case "$(printf '%s' "$path" | tr '[:upper:]' '[:lower:]')" in *windowsapps*) continue ;; esac
    if "$cand" -c 'import sys' >/dev/null 2>&1; then printf '%s\n' "$path"; return 0; fi
  done
  printf '%s\n' ""
}
REAL_PY="$(selftest_python)"
if [ -n "$REAL_PY" ]; then
  PY="$REAL_PY"
else
  PY="uv run python"
fi
export XREVIEW_PYTHON="$PY"

export XREVIEW_COORDINATOR="coordinator-login"
export XREVIEW_FAKE_PAGES="$workdir/pages"
export XREVIEW_FAKE_POSTED="$workdir/posted-body.txt"
export XREVIEW_FAKE_POST_URL="https://github.com/o/r/pull/9#issuecomment-999999"
export PATH="$workdir/bin:$PATH"
mkdir -p "$workdir/bin" "$XREVIEW_FAKE_PAGES"

cat >"$workdir/fixture.py" <<'FIXTURE'
import json, os, sys

# The body arrives as a FILE, never as an argument: a 90 KB fixture does not fit
# in a Windows command line (~32 KB), and its size is the whole point of it.
path, cid, created, updated, login, url, body_path = sys.argv[1:8]
with open(body_path, "rb") as handle:
    body = handle.read().decode("utf-8")
record = {
    "id": int(cid),
    "created_at": created,
    "updated_at": updated,
    "user": {"login": login},
    "html_url": url,
    "body": body,
}
data = []
if os.path.exists(path) and os.path.getsize(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
data.append(record)
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False)
FIXTURE

# Bodies a shell variable would corrupt, written as bytes.
cat >"$workdir/make_body.py" <<'MAKEBODY'
import sys

kind, path = sys.argv[1], sys.argv[2]
if kind == "nul":
    # A NUL in front of an otherwise perfect record. The first line must NOT
    # match the anchored pattern; bash used to drop the NUL and make it match.
    body = "\x00交叉审 r8:approve\n\n发现若干。\n\n裁决:approve\n"
elif kind == "huge":
    # ~30k Chinese characters ≈ 90 KB — the size at which `head` in a pipeline
    # started reporting 141 (SIGPIPE), i.e. an ordinary long review report.
    body = "交叉审 r8:approve\n\n" + ("审查正文。" * 6000) + "\n\n裁决:approve\n"
elif kind == "two-verdicts":
    # A record whose header is fine but whose body votes twice. post refuses to
    # write this; latest must refuse to read it.
    body = "交叉审 r8:approve\n\n裁决:rework\n\n补充说明\n\n裁决:approve\n"
else:
    raise SystemExit("unknown body kind: %s" % kind)
with open(path, "wb") as handle:
    handle.write(body.encode("utf-8"))
MAKEBODY

cat >"$workdir/bin/gh" <<'FAKE'
#!/usr/bin/env bash
set -uo pipefail
case "${1:-}" in
  api)
    if [ -n "${XREVIEW_FAKE_API_RC:-}" ] && [ "${XREVIEW_FAKE_API_RC}" != "0" ]; then
      echo "fake gh: HTTP 503 (simulated)" >&2
      exit "$XREVIEW_FAKE_API_RC"
    fi
    paginate=0
    for a in "$@"; do [ "$a" = "--paginate" ] && paginate=1; done
    cat "$XREVIEW_FAKE_PAGES/page1.json"
    if [ "$paginate" -eq 1 ] && [ -f "$XREVIEW_FAKE_PAGES/page2.json" ]; then
      cat "$XREVIEW_FAKE_PAGES/page2.json"
    fi
    ;;
  pr)
    body=''
    while [ $# -gt 0 ]; do
      if [ "$1" = "--body-file" ]; then body="$2"; fi
      shift
    done
    cp "$body" "$XREVIEW_FAKE_POSTED"
    page="$XREVIEW_FAKE_PAGES/page1.json"
    [ -f "$XREVIEW_FAKE_PAGES/page2.json" ] && page="$XREVIEW_FAKE_PAGES/page2.json"
    $XREVIEW_FAKE_PY "$XREVIEW_FAKE_FIXTURE" "$page" 999999 \
      "2030-01-01T00:00:00Z" "2030-01-01T00:00:00Z" "$XREVIEW_COORDINATOR" \
      "$XREVIEW_FAKE_POST_URL" "$body"
    printf '%s\n' "$XREVIEW_FAKE_POST_URL"
    ;;
  *) echo "fake gh: unexpected call: $*" >&2; exit 64 ;;
esac
FAKE
chmod +x "$workdir/bin/gh"
export XREVIEW_FAKE_PY="$PY"
export XREVIEW_FAKE_FIXTURE="$workdir/fixture.py"

failures=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; failures=$((failures + 1)); }
check() { if [ "$2" -eq 0 ]; then pass "$1"; else fail "$1"; fi; }

# add_file <page> <id> <created> <updated> <login> <url> <body-file>
add_file() {
  $PY "$workdir/fixture.py" "$XREVIEW_FAKE_PAGES/$1.json" "$2" "$3" "$4" "$5" "$6" "$7"
}
# add <page> <id> <created> <updated> <login> <url> <body-text>
add() {
  printf '%s' "$7" >"$workdir/body.tmp"
  add_file "$1" "$2" "$3" "$4" "$5" "$6" "$workdir/body.tmp"
}
record() { printf '交叉审 r%s:%s\n\n发现若干。\n\n裁决:%s\n' "$1" "$2" "${3:-$2}"; }
reset() { rm -f "$XREVIEW_FAKE_PAGES"/*.json; : >"$XREVIEW_FAKE_PAGES/page1.json"; unset XREVIEW_FAKE_API_RC; }

echo "xreview self-test  (workdir: $workdir, python: $PY)"

echo "[0] help and an unknown command"
"$script" help >/dev/null 2>&1
check "help exits 0" $?
"$script" bogus >/dev/null 2>&1
check "unknown command exits non-zero" "$([ $? -ne 0 ]; echo $?)"

echo "[1] 31 comments — the newest record is on page 2"
reset
i=1
while [ "$i" -le 30 ]; do
  add page1 "$i" "2026-09-01T00:00:$(printf '%02d' $((i % 60)))Z" "2026-09-01T00:00:00Z" \
      "$XREVIEW_COORDINATOR" "https://x/$i" "$(record 1 rework)"
  i=$((i + 1))
done
add page2 31 "2026-09-02T00:00:00Z" "2026-09-02T00:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/31" "$(record 2 approve)"
out="$("$script" latest 9 2>&1)"; rc=$?
check "latest exits 0 over 31 comments" "$rc"
[ "$out" = "approve" ]
check "reads page 2 (needs --paginate), got '$out'" $?

echo "[2] a comment that looks like a record but has an illegal first line"
reset
add page1 1 "2026-09-01T00:00:00Z" "2026-09-01T00:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/1" "$(record 1 approve)"
add page1 2 "2026-09-02T00:00:00Z" "2026-09-02T00:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/BAD" "$(printf '交叉审 r6:aprove\n\n裁决:approve\n')"
err="$("$script" latest 9 2>&1 >/dev/null)"; rc=$?
outonly="$("$script" latest 9 2>/dev/null)"
check "illegal first line exits non-zero" "$([ "$rc" -ne 0 ]; echo $?)"
case "$err" in *https://x/BAD*) check "the error names the offending comment URL" 0 ;;
  *) check "the error names the offending comment URL (got: $err)" 1 ;; esac
# The verdict is the ONLY thing latest may put on stdout, so an empty stdout is
# what "did not fall back to the older legal record" actually looks like.
# (Asserting on combined output would match the word approve inside the regex
# quoted by the error message — a green that means nothing.)
[ -z "$outonly" ]
check "prints no verdict at all — no fallback to the older record" $?

echo "[3] header verdict contradicts the body's 裁决 line"
reset
add page1 1 "2026-09-01T00:00:00Z" "2026-09-01T00:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/SPLIT" "$(record 3 approve rework)"
err="$("$script" latest 9 2>&1 >/dev/null)"; rc=$?
check "contradictory record exits non-zero" "$([ "$rc" -ne 0 ]; echo $?)"
case "$err" in *https://x/SPLIT*) check "the error names the contradictory comment" 0 ;;
  *) check "the error names the contradictory comment (got: $err)" 1 ;; esac

echo "[3b] a record whose body votes twice — the reader applies the writer's rule"
reset
$PY "$workdir/make_body.py" two-verdicts "$workdir/two-verdicts.txt"
add_file page1 1 "2026-09-01T00:00:00Z" "2026-09-01T00:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/TWICE" "$workdir/two-verdicts.txt"
err="$("$script" latest 9 2>&1 >/dev/null)"; rc=$?
outonly="$("$script" latest 9 2>/dev/null)"
check "two 裁决 lines in a comment exit non-zero" "$([ "$rc" -ne 0 ]; echo $?)"
[ -z "$outonly" ]
check "the trailing approve is not silently taken as the verdict" $?
case "$err" in *"exactly one"*) check "the error says exactly one verdict line" 0 ;;
  *) check "the error says exactly one verdict line (got: $err)" 1 ;; esac

echo "[3c] a body that begins with a NUL is not a record"
reset
$PY "$workdir/make_body.py" nul "$workdir/nul-body.txt"
add_file page1 1 "2026-09-01T00:00:00Z" "2026-09-01T00:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/NUL" "$workdir/nul-body.txt"
out="$("$script" latest 9 2>/dev/null)"; rc=$?
check "a NUL-prefixed body exits 0" "$rc"
[ "$out" = "尚未审" ]
check "NUL is not stripped into a matching first line, got '$out'" $?

echo "[3d] a 90 KB body — the length at which a piped head killed its producer"
reset
$PY "$workdir/make_body.py" huge "$workdir/huge-body.txt"
add_file page1 1 "2026-09-01T00:00:00Z" "2026-09-01T00:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/HUGE" "$workdir/huge-body.txt"
out="$("$script" latest 9 2>/dev/null)"; rc=$?
check "a 90 KB record exits 0 (no SIGPIPE 141)" "$rc"
[ "$out" = "approve" ]
check "a 90 KB record is read normally, got '$out'" $?

echo "[4] a non-coordinator posting a newer, well-formed record"
reset
add page1 1 "2026-09-01T00:00:00Z" "2026-09-01T00:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/1" "$(record 1 rework)"
add page1 2 "2026-09-09T00:00:00Z" "2026-09-09T00:00:00Z" "someone-else" \
    "https://x/IMPOSTER" "$(record 2 approve)"
out="$("$script" latest 9 2>&1)"; rc=$?
check "outsider record does not trip fail-fast" "$rc"
[ "$out" = "rework" ]
check "outsider cannot overwrite the record, got '$out'" $?

echo "[4b] the account is compared case-insensitively, as GitHub does"
reset
add page1 1 "2026-09-01T00:00:00Z" "2026-09-01T00:00:00Z" "SevenX77" \
    "https://x/CANON" "$(record 1 rework)"
out="$(XREVIEW_COORDINATOR=sevenx77 "$script" latest 9 2>&1)"
[ "$out" = "rework" ]
check "a lower-case account file matches the canonical author, got '$out'" $?
out="$(XREVIEW_COORDINATOR=SEVENX77 "$script" latest 9 2>&1)"
[ "$out" = "rework" ]
check "an upper-case account matches too, got '$out'" $?

echo "[5] two records in the same second — larger comment id wins"
reset
add page1 41 "2026-09-05T12:00:00Z" "2026-09-05T12:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/41" "$(record 4 rework)"
add page1 42 "2026-09-05T12:00:00Z" "2026-09-05T12:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/42" "$(record 5 approve)"
out="$("$script" latest 9)"
[ "$out" = "approve" ]
check "same-second tie broken by id, got '$out'" $?
out="$("$script" latest 9 --with-url)"
case "$out" in *https://x/42*) check "--with-url points at the winning comment" 0 ;;
  *) check "--with-url points at the winning comment (got: $out)" 1 ;; esac

echo "[5b] an edited OLD record whose updated_at is newer than the current one"
reset
# The old rework was edited long after the new approve was posted. Ordering by
# updated_at would resurrect it; ordering by created_at must not.
add page1 51 "2026-09-01T00:00:00Z" "2026-12-31T23:59:59Z" "$XREVIEW_COORDINATOR" \
    "https://x/EDITED-OLD" "$(record 6 rework)"
add page1 52 "2026-09-02T00:00:00Z" "2026-09-02T00:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/NEWEST" "$(record 7 approve)"
out="$("$script" latest 9 --with-url)"
case "$out" in approve*https://x/NEWEST*) check "ordered by created_at, not updated_at" 0 ;;
  *) check "ordered by created_at, not updated_at (got: $out)" 1 ;; esac

echo "[6] a PR with no record at all"
reset
add page1 1 "2026-09-01T00:00:00Z" "2026-09-01T00:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/1" "just a normal comment"
out="$("$script" latest 9)"; rc=$?
check "no record exits 0" "$rc"
[ "$out" = "尚未审" ]
check "no record reads 尚未审, got '$out'" $?

echo "[7] post builds the header from the file's own verdict"
reset
printf 'P1 — 某处 — 某问题\n\n裁决:rework\n' >"$workdir/verdict.txt"
"$script" post 9 7 "$workdir/verdict.txt" >/dev/null 2>&1
check "post exits 0" $?
head -n 1 "$XREVIEW_FAKE_POSTED" | grep -qx '交叉审 r7:rework'
check "first line is constructed as 交叉审 r7:rework" $?
[ -z "$(sed -n '2p' "$XREVIEW_FAKE_POSTED")" ]
check "a blank line separates header from the verbatim body" $?
grep -qx '裁决:rework' "$XREVIEW_FAKE_POSTED"
check "the original text is kept verbatim" $?
[ "$("$script" latest 9)" = "rework" ]
check "post's read-back sees its own record" $?

echo "[8] post refuses files it cannot reduce to one verdict"
reset
rm -f "$XREVIEW_FAKE_POSTED"
printf 'P1 — 某处 — 某问题\n\n最后一行不是裁决行\n' >"$workdir/bad.txt"
"$script" post 9 8 "$workdir/bad.txt" >/dev/null 2>&1
check "no verdict line at all is refused" "$([ $? -ne 0 ]; echo $?)"
printf 'x\n\n裁决:rework\n\n补充说明\n\n裁决:approve\n' >"$workdir/two.txt"
err="$("$script" post 9 8 "$workdir/two.txt" 2>&1 >/dev/null)"; rc=$?
check "two verdict lines are refused" "$([ "$rc" -ne 0 ]; echo $?)"
case "$err" in *"exactly one"*) check "the error says exactly one verdict line" 0 ;;
  *) check "the error says exactly one verdict line (got: $err)" 1 ;; esac
[ ! -e "$XREVIEW_FAKE_POSTED" ] && [ "$(cat "$XREVIEW_FAKE_PAGES/page1.json")" = "" ]
check "nothing was posted by either refusal" $?
printf 'x\n\n裁决:approve\n' >"$workdir/ok.txt"
"$script" post 9 not-a-number "$workdir/ok.txt" >/dev/null 2>&1
check "a non-numeric round is refused" "$([ $? -ne 0 ]; echo $?)"

echo "[9] the coordinator account file is validated, not merely read"
reset
add page1 1 "2026-09-01T00:00:00Z" "2026-09-01T00:00:00Z" "file-login" \
    "https://x/1" "$(record 1 approve)"
fakerepo="$workdir/repo"
mkdir -p "$fakerepo"
( cd "$fakerepo" && git init -q . && git config user.email t@e && git config user.name t )
run_in_repo() { ( cd "$fakerepo" && env -u XREVIEW_COORDINATOR "$script" "$@" ); }

printf 'file-login\n' >"$fakerepo/.xreview-coordinator"
out="$(run_in_repo latest 9 2>&1)"
[ "$out" = "approve" ]
check "one valid line is accepted, got '$out'" $?

printf 'file-login\nsecond-login\n' >"$fakerepo/.xreview-coordinator"
err="$(run_in_repo latest 9 2>&1 >/dev/null)"; rc=$?
check "a second line (appended during handover) is refused" "$([ "$rc" -ne 0 ]; echo $?)"

# "Exactly one line" means the content IS the login, not "one non-blank line
# among others": a stray blank line is a difference in the file, and a file this
# script cannot read unambiguously is not one it may guess at.
printf 'file-login\n\n' >"$fakerepo/.xreview-coordinator"
run_in_repo latest 9 >/dev/null 2>&1
check "a trailing blank line is refused, not ignored" "$([ $? -ne 0 ]; echo $?)"

printf 'fi le-login\n' >"$fakerepo/.xreview-coordinator"
run_in_repo latest 9 >/dev/null 2>&1
check "a login containing a space is refused, not silently rewritten" "$([ $? -ne 0 ]; echo $?)"

printf -- '-leading-hyphen\n' >"$fakerepo/.xreview-coordinator"
run_in_repo latest 9 >/dev/null 2>&1
check "a login starting with a hyphen is refused" "$([ $? -ne 0 ]; echo $?)"

printf 'file-login\r\n' >"$fakerepo/.xreview-coordinator"
err="$(run_in_repo latest 9 2>&1 >/dev/null)"; rc=$?
check "a CRLF account file is refused rather than mismatching forever" "$([ "$rc" -ne 0 ]; echo $?)"

rm -f "$fakerepo/.xreview-coordinator"
run_in_repo latest 9 >/dev/null 2>&1
check "a missing login file is refused" "$([ $? -ne 0 ]; echo $?)"

echo "[10] the GitHub API failing is never reported as 尚未审"
reset
add page1 1 "2026-09-01T00:00:00Z" "2026-09-01T00:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/1" "$(record 1 rework)"
export XREVIEW_FAKE_API_RC=77
outonly="$("$script" latest 9 2>/dev/null)"; rc=$?
err="$("$script" latest 9 2>&1 >/dev/null)"
unset XREVIEW_FAKE_API_RC
check "API failure exits non-zero" "$([ "$rc" -ne 0 ]; echo $?)"
[ -z "$outonly" ]
check "API failure prints nothing on stdout (no 尚未审, no stale verdict)" $?
case "$err" in *503*) check "the error relays gh's own stderr" 0 ;;
  *) check "the error relays gh's own stderr (got: $err)" 1 ;; esac

echo "[11] the interpreter is chosen, not merely found"
reset
add page1 1 "2026-09-01T00:00:00Z" "2026-09-01T00:00:00Z" "$XREVIEW_COORDINATOR" \
    "https://x/1" "$(record 1 approve)"
if [ -z "$REAL_PY" ]; then
  echo "  skip this machine has no directly runnable python to stand in for uv"
else
  mkdir -p "$workdir/store/WindowsApps" "$workdir/fakebin"
  export XREVIEW_STORE_HITS="$workdir/store-hits" XREVIEW_PLAIN_HITS="$workdir/plain-hits"
  export XREVIEW_REAL_PY="$REAL_PY"
  : >"$XREVIEW_STORE_HITS"; : >"$XREVIEW_PLAIN_HITS"
  # The Windows Store placeholder: on a real machine it opens the Store. Here it
  # just records that it was run and produces nothing, so using it would break
  # the run as well as trip the counter.
  cat >"$workdir/store/WindowsApps/python3" <<'STORESTUB'
#!/usr/bin/env bash
echo hit >>"$XREVIEW_STORE_HITS"
exit 0
STORESTUB
  # A perfectly good `python`, which must nevertheless not be reached: uv comes
  # first. It still works, so a wrong order shows up as this counter alone.
  cat >"$workdir/fakebin/python" <<'PLAINSTUB'
#!/usr/bin/env bash
echo hit >>"$XREVIEW_PLAIN_HITS"
exec "$XREVIEW_REAL_PY" "$@"
PLAINSTUB
  cat >"$workdir/fakebin/uv" <<'UVSTUB'
#!/usr/bin/env bash
if [ "${1:-}" = "run" ] && [ "${2:-}" = "python" ]; then shift 2; exec "$XREVIEW_REAL_PY" "$@"; fi
exit 64
UVSTUB
  chmod +x "$workdir/store/WindowsApps/python3" "$workdir/fakebin/python" "$workdir/fakebin/uv"
  out="$(env -u XREVIEW_PYTHON PATH="$workdir/store/WindowsApps:$workdir/fakebin:$PATH" \
         "$script" latest 9 2>&1)"
  [ "$out" = "approve" ]
  check "resolution finds a working interpreter, got '$out'" $?
  [ ! -s "$XREVIEW_STORE_HITS" ]
  check "the WindowsApps placeholder was never executed" $?
  [ ! -s "$XREVIEW_PLAIN_HITS" ]
  check "uv is tried before python3/python" $?
fi

echo
if [ "$failures" -eq 0 ]; then
  echo "xreview self-test: all checks passed"
else
  echo "xreview self-test: ${failures} check(s) FAILED"
fi
exit "$failures"
