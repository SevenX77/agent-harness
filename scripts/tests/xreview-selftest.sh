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
# WHAT THE FAKE gh DOES. It answers the two calls xreview.sh makes:
#   * `gh api ... --jq <projection>` — prints the TSV rows a real gh would print
#     after applying that projection. It prints only the FIRST 30 rows unless
#     --paginate is present, which is how GitHub actually behaves; that is what
#     makes fixture [1] a real test of the flag rather than a decoration.
#   * `gh pr comment <n> --body-file <f>` — saves the body for inspection,
#     appends it to the comment fixture as a new row, and prints its URL, so the
#     post round-trip (post → read back → compare) really happens.
#
# WHAT IT CANNOT COVER. The projection string itself is interpreted by gh's
# built-in jq, which the fake replaces — verify that against a real PR after
# changing it. Everything below the API is covered here.
set -uo pipefail

script="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/xreview.sh"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

export XREVIEW_COORDINATOR="coordinator-login"
export XREVIEW_FAKE_COMMENTS="$workdir/comments.tsv"
export XREVIEW_FAKE_POSTED="$workdir/posted-body.txt"
export XREVIEW_FAKE_POST_URL="https://github.com/o/r/pull/9#issuecomment-999999"
export PATH="$workdir/bin:$PATH"

mkdir -p "$workdir/bin"
cat >"$workdir/bin/gh" <<'FAKE'
#!/usr/bin/env bash
set -uo pipefail
paginate=0
for a in "$@"; do [ "$a" = "--paginate" ] && paginate=1; done
case "${1:-}" in
  api)
    if [ "$paginate" -eq 1 ]; then
      cat "$XREVIEW_FAKE_COMMENTS"
    else
      head -n 30 "$XREVIEW_FAKE_COMMENTS"
    fi
    ;;
  pr)
    body=''
    while [ $# -gt 0 ]; do
      if [ "$1" = "--body-file" ]; then body="$2"; fi
      shift
    done
    cp "$body" "$XREVIEW_FAKE_POSTED"
    printf '%s\t%s\t%s\t%s\t%s\n' \
      "999999" "2030-01-01T00:00:00Z" "$XREVIEW_COORDINATOR" "$XREVIEW_FAKE_POST_URL" \
      "$(base64 <"$body" | tr -d '\n')" >>"$XREVIEW_FAKE_COMMENTS"
    printf '%s\n' "$XREVIEW_FAKE_POST_URL"
    ;;
  *) echo "fake gh: unexpected call: $*" >&2; exit 64 ;;
esac
FAKE
chmod +x "$workdir/bin/gh"

failures=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; failures=$((failures + 1)); }
check() { if [ "$2" -eq 0 ]; then pass "$1"; else fail "$1"; fi; }

# row <id> <created_at> <login> <url> <body>
row() {
  printf '%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$(printf '%s' "$5" | base64 | tr -d '\n')"
}
record() { # record <round> <verdict> [body-verdict]
  printf '交叉审 r%s:%s\n\n发现若干。\n\n裁决:%s\n' "$1" "$2" "${3:-$2}"
}
reset() { : >"$XREVIEW_FAKE_COMMENTS"; }

echo "xreview self-test  (workdir: $workdir)"

echo "[0] help and an unknown command"
"$script" help >/dev/null 2>&1
check "help exits 0" $?
"$script" bogus >/dev/null 2>&1
check "unknown command exits non-zero" "$([ $? -ne 0 ]; echo $?)"

echo "[1] 31 comments — the newest record is on page 2"
reset
i=1
while [ "$i" -le 30 ]; do
  row "$i" "2026-09-01T00:00:$(printf '%02d' $((i % 60)))Z" "$XREVIEW_COORDINATOR" \
      "https://x/$i" "$(record 1 rework)" >>"$XREVIEW_FAKE_COMMENTS"
  i=$((i + 1))
done
row 31 "2026-09-02T00:00:00Z" "$XREVIEW_COORDINATOR" "https://x/31" "$(record 2 approve)" \
  >>"$XREVIEW_FAKE_COMMENTS"
out="$("$script" latest 9 2>&1)"; rc=$?
check "latest exits 0 over 31 comments" "$rc"
[ "$out" = "approve" ]
check "reads the 31st comment (needs --paginate), got '$out'" $?

echo "[2] a comment that looks like a record but has an illegal first line"
reset
row 1 "2026-09-01T00:00:00Z" "$XREVIEW_COORDINATOR" "https://x/1" "$(record 1 approve)" \
  >>"$XREVIEW_FAKE_COMMENTS"
row 2 "2026-09-02T00:00:00Z" "$XREVIEW_COORDINATOR" "https://x/BAD" \
  "$(printf '交叉审 r6:aprove\n\n裁决:approve\n')" >>"$XREVIEW_FAKE_COMMENTS"
err="$("$script" latest 9 2>&1 >/dev/null)"; rc=$?
outonly="$("$script" latest 9 2>/dev/null)"
check "illegal first line exits non-zero" "$([ "$rc" -ne 0 ]; echo $?)"
case "$err" in *https://x/BAD*) check "the error names the offending comment URL" 0 ;;
  *) check "the error names the offending comment URL (got: $err)" 1 ;; esac
# The verdict is the ONLY thing latest may put on stdout, so an empty stdout is
# what "did not fall back to the older legal record" actually looks like.
# (Asserting on combined output would match the word `approve` inside the regex
# quoted by the error message — a green that means nothing.)
[ -z "$outonly" ]
check "prints no verdict at all — no fallback to the older record" $?

echo "[3] header verdict contradicts the body's 裁决 line"
reset
row 1 "2026-09-01T00:00:00Z" "$XREVIEW_COORDINATOR" "https://x/SPLIT" \
  "$(record 3 approve rework)" >>"$XREVIEW_FAKE_COMMENTS"
out="$("$script" latest 9 2>&1)"; rc=$?
check "contradictory record exits non-zero" "$([ "$rc" -ne 0 ]; echo $?)"
case "$out" in *https://x/SPLIT*) check "the error names the contradictory comment" 0 ;;
  *) check "the error names the contradictory comment (got: $out)" 1 ;; esac

echo "[4] a non-coordinator posting a newer, well-formed record"
reset
row 1 "2026-09-01T00:00:00Z" "$XREVIEW_COORDINATOR" "https://x/1" "$(record 1 rework)" \
  >>"$XREVIEW_FAKE_COMMENTS"
row 2 "2026-09-09T00:00:00Z" "someone-else" "https://x/IMPOSTER" "$(record 2 approve)" \
  >>"$XREVIEW_FAKE_COMMENTS"
out="$("$script" latest 9 2>&1)"; rc=$?
check "outsider record does not trip fail-fast" "$rc"
[ "$out" = "rework" ]
check "outsider cannot overwrite the record, got '$out'" $?

echo "[5] two records in the same second — larger comment id wins"
reset
row 41 "2026-09-05T12:00:00Z" "$XREVIEW_COORDINATOR" "https://x/41" "$(record 4 rework)" \
  >>"$XREVIEW_FAKE_COMMENTS"
row 42 "2026-09-05T12:00:00Z" "$XREVIEW_COORDINATOR" "https://x/42" "$(record 5 approve)" \
  >>"$XREVIEW_FAKE_COMMENTS"
out="$("$script" latest 9)"
[ "$out" = "approve" ]
check "same-second tie broken by id, got '$out'" $?
out="$("$script" latest 9 --with-url)"
case "$out" in *https://x/42*) check "--with-url points at the winning comment" 0 ;;
  *) check "--with-url points at the winning comment (got: $out)" 1 ;; esac

echo "[6] a PR with no record at all"
reset
row 1 "2026-09-01T00:00:00Z" "$XREVIEW_COORDINATOR" "https://x/1" "just a normal comment" \
  >>"$XREVIEW_FAKE_COMMENTS"
out="$("$script" latest 9)"; rc=$?
check "no record exits 0" "$rc"
[ "$out" = "尚未审" ]
check "no record reads 尚未审, got '$out'" $?

echo "[7] post builds the header from the file's own verdict"
reset
printf 'P1 — 某处 — 某问题\n\n裁决:rework\n' >"$workdir/verdict.txt"
out="$("$script" post 9 7 "$workdir/verdict.txt" 2>&1)"; rc=$?
check "post exits 0" "$rc"
head -n 1 "$XREVIEW_FAKE_POSTED" | grep -qx '交叉审 r7:rework'
check "first line is constructed as 交叉审 r7:rework" $?
[ -z "$(sed -n '2p' "$XREVIEW_FAKE_POSTED")" ]
check "a blank line separates header from the verbatim body" $?
grep -qx '裁决:rework' "$XREVIEW_FAKE_POSTED"
check "the original text is kept verbatim" $?
[ "$("$script" latest 9)" = "rework" ]
check "post's read-back sees its own record" $?

echo "[8] post refuses a file whose last line is not a verdict"
reset
printf 'P1 — 某处 — 某问题\n\n最后一行不是裁决行\n' >"$workdir/bad.txt"
out="$("$script" post 9 8 "$workdir/bad.txt" 2>&1)"; rc=$?
check "post exits non-zero" "$([ "$rc" -ne 0 ]; echo $?)"
[ ! -s "$XREVIEW_FAKE_COMMENTS" ]
check "nothing was posted" $?
printf 'x\n\n裁决:approve\n' >"$workdir/ok.txt"
"$script" post 9 not-a-number "$workdir/ok.txt" >/dev/null 2>&1
check "a non-numeric round is refused" "$([ $? -ne 0 ]; echo $?)"

echo "[9] the coordinator account comes from .xreview-coordinator when unset"
reset
row 1 "2026-09-01T00:00:00Z" "file-login" "https://x/1" "$(record 1 approve)" \
  >>"$XREVIEW_FAKE_COMMENTS"
fakerepo="$workdir/repo"
mkdir -p "$fakerepo"
( cd "$fakerepo" && git init -q . && git config user.email t@e && git config user.name t )
printf 'file-login\n' >"$fakerepo/.xreview-coordinator"
out="$(cd "$fakerepo" && env -u XREVIEW_COORDINATOR "$script" latest 9 2>&1)"
[ "$out" = "approve" ]
check "login read from the checked-in file, got '$out'" $?
rm -f "$fakerepo/.xreview-coordinator"
out="$(cd "$fakerepo" && env -u XREVIEW_COORDINATOR "$script" latest 9 2>&1)"; rc=$?
check "missing login file exits non-zero" "$([ "$rc" -ne 0 ]; echo $?)"

echo
if [ "$failures" -eq 0 ]; then
  echo "xreview self-test: all checks passed"
else
  echo "xreview self-test: $failures check(s) FAILED"
fi
exit "$((failures > 0))"
