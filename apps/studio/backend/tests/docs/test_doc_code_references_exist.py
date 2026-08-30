"""Gate: code-path references in authority/baseline design docs must resolve.

J-X.4 (journey doc census 2026-08-23, fixed 2026-08-29): `native-fs/baseline.md`
kept citing `open_in_cursor` long after #196 deleted it, and two forked spec
trees survived because nothing checked that what a design doc points at still
exists. Docs whose role is to describe the CURRENT system — the `baseline.md`
(current/migration state) and `mvp1-alignment.md` (target design = truth)
carriers — lose that role the moment their code references go stale.

Scope and rule:
- Every `baseline.md` and `mvp1-alignment.md` under `docs/`.
- A code reference is a backtick-quoted repo-relative path starting with
  `apps/`, `packages/`, or `scripts/` and naming a file with an extension.
  An optional `:suffix` (line number or symbol name) is ignored — this gate
  asserts FILE existence only, per the J-X.4 acceptance; symbol-level drift
  stays a review concern.
- References containing wildcard/placeholder characters (`*<>{}…`) are
  skipped: they are patterns, not paths.

Dated records (audit reports, `.kiro` specs, decision docs) are deliberately
OUT of scope — they describe what was true when written; rewriting their
citations would falsify history (git history is the archive, 2026-08-12
ruling).

Pre-existing drift backlog: when this gate was introduced, 24 docs already
carried stale references accumulated over months. Repairing each needs real
archaeology (where did `core/harness.py` move?), so — following the repo's
own triage doctrine (AGENTS.md on SonarCloud: a gate that is always red is a
gate nobody reads) and the explicit-exemption shape of
`packages/graph-agent/tests/contract-exemptions.yaml` — those docs are listed
in ``STALE_REFERENCE_BACKLOG_2026_08_29`` below. The list is a RATCHET: a doc
not on it must be clean, and a listed doc that becomes clean must be removed
(the test fails otherwise), so the backlog can only shrink.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
DOCS_ROOT = REPO_ROOT / "docs"

_CODE_REFERENCE_PATTERN = re.compile(
    r"^(?:apps|packages|scripts)/[A-Za-z0-9_\-./]+\.[A-Za-z0-9]{1,6}(?::[^`]*)?$"
)
_PLACEHOLDER_CHARS = set("*<>{}…$")


def _missing_code_references(text: str, root: Path) -> list[str]:
    """Return the backtick-quoted code references in ``text`` whose file part
    does not exist under ``root``, keeping the original reference text."""
    missing: list[str] = []
    for match in re.finditer(r"`([^`\n]+)`", text):
        reference = match.group(1).strip()
        if _PLACEHOLDER_CHARS.intersection(reference):
            continue
        if not _CODE_REFERENCE_PATTERN.match(reference):
            continue
        file_part = reference.split(":", 1)[0]
        if not (root / file_part).is_file():
            missing.append(reference)
    return missing


# Docs that already had stale references when the gate landed (J-X.4,
# 2026-08-29). Burn-down only: never add to this list — fix the doc instead.
STALE_REFERENCE_BACKLOG_2026_08_29 = frozenset(
    {
        "docs/architecture/agent-cognitive-architecture/baseline.md",
        "docs/architecture/prod-dev-separation/baseline.md",
        "docs/engine/graph-agent-gateway/baseline.md",
        "docs/graph-agent-gateway/mvp0/baseline.md",
        "docs/graph-agent-gateway/mvp1/01-handoff-interface/baseline.md",
        "docs/graph-agent-gateway/mvp1/01-handoff-interface/mvp1-alignment.md",
        "docs/graph-agent-gateway/mvp1/03-orch-credentials-endpoints/baseline.md",
        "docs/graph-agent-gateway/mvp1/04-orch-registry-schema/baseline.md",
        "docs/graph-agent-gateway/mvp1/05-orch-capabilities-and-models/mvp1-alignment.md",
        "docs/graph-agent-gateway/mvp1/07-orch-fallback-circuit-probe/baseline.md",
        "docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/baseline.md",
        "docs/graph-agent-gateway/mvp1/09-inv-invocation-runtime/baseline.md",
        "docs/graph-agent-gateway/mvp1/10-inv-route-chat-model-factory/baseline.md",
        "docs/graph-agent-gateway/mvp1/11-inv-provider-profiles/baseline.md",
        "docs/graph-agent-gateway/mvp1/13-x-tracing-events-exceptions/baseline.md",
        "docs/studio/mvp0/02_features/copilot-chat/baseline.md",
        "docs/studio/mvp0/03_platform/llm-gateway/baseline.md",
        "docs/studio/mvp1/02_capabilities/debug-resume/baseline.md",
        "docs/studio/mvp1/02_capabilities/graph-authoring/baseline.md",
        "docs/studio/mvp1/02_capabilities/trace-observability/baseline.md",
        "docs/studio/mvp1/03_regions/canvas/baseline.md",
        "docs/studio/mvp1/03_regions/input/baseline.md",
        "docs/studio/mvp1/03_regions/local-history/baseline.md",
        "docs/studio/mvp1/03_regions/timeline/baseline.md",
    }
)


def _governed_docs() -> list[Path]:
    docs = [
        path
        for name in ("baseline.md", "mvp1-alignment.md")
        for path in DOCS_ROOT.rglob(name)
    ]
    assert docs, "expected baseline.md / mvp1-alignment.md carriers under docs/"
    return sorted(docs)


class TestMissingCodeReferenceExtraction:
    def test_existing_file_is_not_reported(self, tmp_path: Path) -> None:
        (tmp_path / "apps").mkdir()
        (tmp_path / "apps" / "real.py").write_text("", encoding="utf-8")
        assert _missing_code_references("see `apps/real.py`", tmp_path) == []

    def test_missing_file_is_reported(self, tmp_path: Path) -> None:
        assert _missing_code_references("see `apps/gone.py`", tmp_path) == [
            "apps/gone.py"
        ]

    def test_line_and_symbol_suffixes_are_stripped(self, tmp_path: Path) -> None:
        (tmp_path / "packages").mkdir()
        (tmp_path / "packages" / "mod.rs").write_text("", encoding="utf-8")
        text = "`packages/mod.rs:42` and `packages/mod.rs:some_symbol`"
        assert _missing_code_references(text, tmp_path) == []

    def test_missing_file_with_symbol_suffix_reports_full_reference(
        self, tmp_path: Path
    ) -> None:
        text = "`apps/studio/tauri/src/lib.rs:open_in_cursor`"
        assert _missing_code_references(text, tmp_path) == [
            "apps/studio/tauri/src/lib.rs:open_in_cursor"
        ]

    def test_placeholder_and_glob_references_are_skipped(self, tmp_path: Path) -> None:
        text = "`apps/studio/<module>/x.py` `packages/*/tests/y.py` `apps/{a,b}/z.py`"
        assert _missing_code_references(text, tmp_path) == []

    def test_non_code_backticks_are_ignored(self, tmp_path: Path) -> None:
        text = "`open_in_cursor` `docs/engine/skill-spec/README.md` `npm test`"
        assert _missing_code_references(text, tmp_path) == []


@pytest.mark.parametrize(
    "doc_path",
    _governed_docs(),
    ids=lambda path: str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
)
def test_code_references_in_authority_and_baseline_docs_exist(doc_path: Path) -> None:
    text = doc_path.read_text(encoding="utf-8")
    missing = _missing_code_references(text, REPO_ROOT)
    relative = str(doc_path.relative_to(REPO_ROOT)).replace("\\", "/")
    if relative in STALE_REFERENCE_BACKLOG_2026_08_29:
        # Ratchet: the moment a backlog doc is repaired, its entry must go,
        # so the backlog can only shrink and never quietly shields new drift.
        assert missing, (
            f"{relative} is clean now — remove it from "
            f"STALE_REFERENCE_BACKLOG_2026_08_29 so the gate enforces it."
        )
        return
    assert not missing, (
        f"{relative} references code files that do not "
        f"exist (fix the doc or record the deletion explicitly):\n"
        + "\n".join(f"  `{reference}`" for reference in missing)
    )


def test_stale_reference_backlog_entries_are_governed_docs() -> None:
    """A backlog entry that no longer names a governed doc is dead weight —
    the doc was deleted or renamed, so the entry must be dropped."""
    governed = {
        str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        for path in _governed_docs()
    }
    orphaned = sorted(STALE_REFERENCE_BACKLOG_2026_08_29 - governed)
    assert not orphaned, "backlog entries without a governed doc: " + ", ".join(
        orphaned
    )
