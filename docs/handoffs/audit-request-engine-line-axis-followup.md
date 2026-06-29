# Audit request — engine body-tag line-axis follow-up (implemented by the original AUDITOR, needs INDEPENDENT review)

> Status: **audit request for a fresh, independent engine agent.** Authored 2026-06-29.
> ⚠️ Role-integrity note: the changes below were implemented by the agent who was
> *auditing* the original P1/P2/P5 work — i.e. self-implemented and self-verified, so they
> have had **no independent audit**. That gap is the reason this request exists. Please
> review as if the author cannot be trusted to have verified their own work.

## How we got here (situation)

1. Another agent implemented P1/P2/P5 in `loader.py` (collect-all diagnostics + role/goal/
   action file-absolute line attribution + empty-action detection). That work was
   independently audited (verdict: PASS) — see `docs/handoffs/engine-lint-collect-all-diagnostics.md`.
2. The audit surfaced two follow-ups. The auditor was asked "how would you solve these?"
   and **mistakenly implemented them directly instead of handing them off** — overstepping
   the audit-only role. The user chose to KEEP the changes but requires an independent audit.

So: **everything in §"Changes to audit" below is what you must review.** The P1/P2/P5 work
is already audited; do not re-litigate it except where these changes touch it.

## Changes to audit (4 files, all uncommitted in the `main` working tree)

### A. `loader.py` — extend file-absolute line axis to the SIBLING body-tag diagnostics (the "②" follow-up)
P1 fixed role/goal/action to use `_body_file_line` (file-absolute). I migrated the remaining
body-tag diagnostics in the same family from body-relative `_xml_line` to `_body_file_line`:
- `1816` agent-body unknown top-level tag (`[F-v3-agent-body-tag-unknown]`)
- `1822` agent-body `<steps>` ; `1830` `<exit_contract>` (same code)
- `1873` `[F-v3-agent-step-invalid]` ; `1889` `[F-v3-agent-protocol-invalid]` ; `1907` `[F-v3-agent-example-invalid]`
- `1920` `[F-v3-mention-syntax-invalid]` ; `1936` `[F-v3-mention-target-not-found]`
- `1210` GRAPH.md `[F-v3-graph-phase-id-invalid]` → `_body_file_line(graph_path, graph_body, …)`
- **Deliberately NOT changed:** `PhaseTokenInfo.line_start/line_end` (`1225-1226`) — these are
  internal token-span metadata consumed by serialization/attr-spans, NOT a user-facing
  diagnostic line. (Confirm this classification is correct.)
- Unchanged (already P1, agent's): `1781`/`1788` logic-action lines, `1945` `_body_file_line` def,
  `1979` `_missing_block_line`.

### B. `parser.py` — file-absolute line for the parser-side body diagnostic
- `280` NEW `_body_offset_to_file_line(path, body, offset)` — a **mirror of loader's
  `_body_file_line`** (parser can't import loader = circular dependency, so I duplicated the
  ~10-line pure mapping). `308` `scan_forbidden_topology_tags` now uses it instead of the
  inline body-relative count.

### C. `tests/e2e/test_round14_compiler_e2e.py` — Windows fixture fix (the "①" follow-up)
- `80` `_rewrite_copied_subgraph_paths`: the repl was a plain f-string holding a Windows tmp
  path (`C:\Users\…`), so `re.sub` parsed `\U` as an escape and raised. Changed the repl to a
  function: `lambda _match: f"path: {expander}"`. This unblocked all 21 round14 tests on Windows.

### D. `tests/core/test_compiler_line_locations.py` — regression tests for B/A
- `346` `test_unknown_body_tag_points_to_tag_file_line` (agent-body sibling → file line 14)
- `363` `test_forbidden_topology_tag_in_body_points_to_file_line` (parser scan_forbidden → file line 14)

## Rationale (the claim you're auditing)

Frontmatter errors emit FILE-absolute lines (`_frontmatter_key_line` uses
`splitlines()` over the whole file); Studio forwards `error.line` verbatim onto a Monaco
**full-file** view (`field-compile-errors.ts` → `lint-monaco-markers.ts`). So a body-relative
`_xml_line` value lands too high by the frontmatter length. `_body_file_line` reads the file
and anchors via `content.rfind(body)` (body is a frontmatter-stripped SUFFIX of the file).
The claim: ALL body-tag diagnostics must use the file-absolute axis for the editor marker to
hit the right line.

## Verification I ran (reproduce + challenge these — do not take them on faith)

- `uv run pytest packages/graph-agent/tests/core/test_compiler_line_locations.py` → **16 passed**.
- `uv run pytest packages/graph-agent/tests/e2e/test_round14_compiler_e2e.py` → **21 passed** (was 21 errors before fix C).
- `uv run pytest packages/graph-agent/tests` → **14 failed, 1367 passed, 0 errors** (baseline before my changes: 14 failed, 1344 passed, 21 errors). The 14 failures are pre-existing Windows/env noise (`.sh` exec-bit, doc/contract-hash CRLF, public-api exemptions, round18/storage/productization_red) — identical list before/after.
- `uv run mypy --strict packages/graph-agent/src` → clean. `uv run ruff check packages/graph-agent` → clean.

## Specifically scrutinize (where I'm least certain / most likely wrong)

1. **`rfind(body)` anchoring correctness.** Is `body` ALWAYS a suffix of file content? (`_strip_frontmatter` does `lstrip()` → body has leading whitespace removed; does rfind still anchor at the true body start in every case — CRLF files, body text that also appears inside the frontmatter, empty body?) Verify the offset→line count stays correct under `\r\n`.
2. **Duplication in `parser.py`.** `_body_offset_to_file_line` duplicates `_body_file_line`. Is the duplication acceptable, or should the canonical helper live in `parser.py` (the body/frontmatter owner) with `loader.py` importing it? Confirm the two copies are behaviorally identical.
3. **GRAPH.md (`1210`).** Confirm `graph_body` is a suffix of GRAPH.md content (same `_strip_frontmatter` path) so `_body_file_line(graph_path, …)` anchors correctly, AND that GRAPH.md diagnostics are consumed file-absolute by Studio just like SKILL.md.
4. **Completeness.** Did I miss any body-tag diagnostic still on `_xml_line` that SHOULD be file-absolute? Is leaving `PhaseTokenInfo.line_start/end` (1225-1226) correct (truly not a diagnostic)?
5. **Fixture fix (C).** Does the lambda repl change test semantics at all, or is round14 now passing for the right reasons (not masking a real failure)? Spot-check one located-code case.
6. **Zero-regression claim.** Re-run the full suite (or stash my 4 files and diff the failure set) to confirm I introduced no new failures.

## Audit checklist
- [ ] §1-6 scrutiny points resolved with evidence.
- [ ] All body-tag diagnostics share the file-absolute axis; spans correctly excluded.
- [ ] No error CODES changed; round14 located-code matrix green; line tests assert correct file lines.
- [ ] No regression (failure set unchanged); mypy --strict + ruff clean.
- [ ] Verdict + any required fixes, returned to the user (not to me).

---

## ROUND 2 — defect fix for the first audit's CHANGES-REQUESTED finding (NEEDS RE-AUDIT)

The first independent audit (verdict: CHANGES REQUESTED) found one real defect: I had
mis-classified `PhaseTokenInfo.line_start` as "not a diagnostic". It IS consumed as the
diagnostic line for two GRAPH.md `<phase>` errors — `[F-v3-graph-phase-cycle]` (loader.py
self-dep check) and `[F-v3-graph-depends-unknown]` — both of which emitted line 1 (the
frontmatter `---`), the exact symptom this effort exists to remove. Good catch; my
self-classification was the unverified assumption I'd flagged.

**Fix (chose the lowest-risk option, NOT the auditor's "flip line_start"):**
- `line_start`/`line_end` are LEFT UNTOUCHED — they stay body-relative for the
  serializer/cache round-trip. This **deliberately avoids the hash-lock risk** the auditor
  flagged (flipping the serialized value could shift round28 / source-map hash fixtures,
  which can't be cleanly re-baselined on Windows).
- Added a NEW field `BodyPhaseRef.diag_line: int` (file-absolute), computed at construction
  in `_extract_body_phase_refs` via `_body_file_line(graph_path, graph_body, match.start())`
  — the same offset/axis as the already-migrated `[F-v3-graph-phase-id-invalid]` (1210).
  `BodyPhaseRef` is **NOT serialized** (verified: `cache.py` references `PhaseTokenInfo`,
  never `BodyPhaseRef`), so this touches no cached/hashed value.
- The two diagnostics now read `ref.diag_line` instead of `ref.token.line_start`.
- **Deliberately still NOT changed:** `PhaseTokenInfo.line_start/line_end` (token metadata)
  and `PhaseAttributeSpan` lines (serialization only).

**New regression tests** (the auditor noted these lines were unguarded):
- `test_graph_phase_cycle_points_to_phase_tag_file_line` → phase-cycle line == 14 (the `<phase>` file line).
- `test_graph_depends_unknown_points_to_phase_tag_file_line` → depends-unknown line == 14.

**Verification (re-run + challenge):**
- `test_compiler_line_locations.py` → **18 passed** (the 2 new ones empirically show the
  diagnostic now reads `GRAPH.md:14`, was `:1`).
- round14 e2e → **21 passed** (unchanged). Full suite → **14 failed, 1369 passed, 0 errors**
  (the 14 are the same pre-existing Windows/env noise; +2 = the new tests; zero new failures).
- mypy --strict + ruff → clean.

**Re-audit scrutiny points:**
1. Confirm `BodyPhaseRef` is genuinely not serialized/hashed anywhere → the fix can't shift round28/source-map hashes (the reason I avoided flipping `line_start`). Verify on Linux CI that round28 + source-map hash locks are unchanged.
2. Confirm `diag_line` (offset = `<phase>` tag start) is the right line for BOTH phase-cycle and depends-unknown (vs, say, the `depends_on` attribute span).
3. Any OTHER consumer of `token.line_start` as a diagnostic that I still missed? (grep showed only these two; confirm.)
4. Reproduce the 18/21/14-1369-0 + mypy/ruff numbers.

> Role note: this fix was implemented by the same author whose work is under audit, so it
> again needs INDEPENDENT review — do not take the verification on faith.
