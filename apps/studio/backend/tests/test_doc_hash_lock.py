from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
DOCS_ROOT = REPO_ROOT / "docs" / "studio" / "mvp1"
HASH_LOCK_PATH = DOCS_ROOT / "_audited-ready-hashes.json"
EXEMPTIONS_PATH = Path(__file__).with_name("studio-doc-exemptions.yaml")
HASH_LOCK_REMEDIATION = (
    "revert unapproved doc edits; or with owner approval update "
    "docs/studio/mvp1/_audited-ready-hashes.json; or add a temporary exemption "
    "to apps/studio/backend/tests/studio-doc-exemptions.yaml with file, sha256, reason, and owner_approval"
)


def _sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _load_expected_hashes() -> dict[str, str]:
    data = json.loads(HASH_LOCK_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "studio doc hash lock must be a JSON object"

    hashes = data.get("hashes")
    assert isinstance(hashes, dict), "studio doc hash lock must contain a hashes object"

    meta = data.get("_meta")
    if isinstance(meta, dict) and "count" in meta:
        assert meta["count"] == len(hashes), "studio doc hash lock _meta.count must match hashes count"

    expected_hashes: dict[str, str] = {}
    for relative_path, expected_hash in hashes.items():
        assert isinstance(relative_path, str) and relative_path, "studio doc hash paths must be non-empty strings"
        assert not relative_path.startswith("/") and ".." not in Path(relative_path).parts, (
            f"studio doc hash path must stay relative to docs/studio/mvp1: {relative_path}"
        )
        assert isinstance(expected_hash, str) and len(expected_hash) == 64, (
            f"studio doc hash for {relative_path} must be a SHA-256 hex digest"
        )
        expected_hashes[relative_path] = expected_hash

    return expected_hashes


def _load_hash_exemptions() -> set[tuple[str, str]]:
    data = yaml.safe_load(EXEMPTIONS_PATH.read_text(encoding="utf-8")) or {}
    assert isinstance(data, dict), "studio doc exemptions must be a mapping"

    exemptions = data.get("exemptions", [])
    assert isinstance(exemptions, list), "studio doc exemptions must be a list"

    approved_hashes: set[tuple[str, str]] = set()
    for index, exemption in enumerate(exemptions):
        assert isinstance(exemption, dict), f"studio doc exemption #{index} must be a mapping"

        relative_path = exemption.get("file")
        approved_hash = exemption.get("sha256")
        reason = exemption.get("reason")
        owner_approval = exemption.get("owner_approval")

        assert isinstance(relative_path, str) and relative_path, f"studio doc exemption #{index} must include file"
        assert isinstance(approved_hash, str) and len(approved_hash) == 64, (
            f"studio doc exemption #{index} must include sha256"
        )
        assert isinstance(reason, str) and reason, f"studio doc exemption #{index} must include reason"
        assert isinstance(owner_approval, str) and owner_approval, (
            f"studio doc exemption #{index} must include owner_approval"
        )

        approved_hashes.add((relative_path, approved_hash))

    return approved_hashes


def _collect_hash_lock_violations(
    *,
    docs_root: Path,
    expected_hashes: Mapping[str, str],
    approved_hashes: set[tuple[str, str]],
) -> list[str]:
    violations: list[str] = []
    expected_paths = set(expected_hashes)

    for relative_path, expected_hash in sorted(expected_hashes.items()):
        doc_path = docs_root / relative_path
        if not doc_path.exists():
            violations.append(
                f"{relative_path}: missing; expected SHA-256 {expected_hash}; remediation: {HASH_LOCK_REMEDIATION}"
            )
            continue

        actual_hash = _sha256(doc_path)
        if actual_hash != expected_hash and (relative_path, actual_hash) not in approved_hashes:
            violations.append(
                f"{relative_path}: expected {expected_hash}, got {actual_hash}; remediation: {HASH_LOCK_REMEDIATION}"
            )

    locked_file_names = {Path(relative_path).name for relative_path in expected_paths}
    for doc_path in sorted(docs_root.rglob("*.md")):
        relative_path = doc_path.relative_to(docs_root).as_posix()
        if relative_path in expected_paths or doc_path.name not in locked_file_names:
            continue
        actual_hash = _sha256(doc_path)
        if (relative_path, actual_hash) not in approved_hashes:
            violations.append(
                f"{relative_path}: not listed in hash table, got {actual_hash}; remediation: {HASH_LOCK_REMEDIATION}"
            )

    return violations


def test_hash_lock_reports_drift_missing_and_untracked_docs(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "studio" / "mvp1"
    docs_root.mkdir(parents=True)

    tracked = docs_root / "existing-unit" / "baseline.md"
    tracked.parent.mkdir()
    tracked.write_text("audited baseline\n")
    expected_tracked_hash = _sha256(tracked)
    tracked.write_text("silent drift\n")

    new_doc = docs_root / "new-unit" / "baseline.md"
    new_doc.parent.mkdir()
    new_doc.write_text("new audited-style doc\n")

    violations = _collect_hash_lock_violations(
        docs_root=docs_root,
        expected_hashes={
            "existing-unit/baseline.md": expected_tracked_hash,
            "missing.md": "0" * 64,
        },
        approved_hashes=set(),
    )

    assert any(
        "existing-unit/baseline.md" in violation and "expected" in violation and "got" in violation
        for violation in violations
    )
    assert any("missing.md" in violation and "missing" in violation for violation in violations)
    assert any("new-unit/baseline.md" in violation and "not listed" in violation for violation in violations)


def test_hash_lock_exemption_allows_only_exact_file_and_hash(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "studio" / "mvp1"
    docs_root.mkdir(parents=True)

    doc_path = docs_root / "unit" / "baseline.md"
    doc_path.parent.mkdir()
    doc_path.write_text("audited baseline\n")
    expected_hash = _sha256(doc_path)

    doc_path.write_text("owner approved drift\n")
    approved_hash = _sha256(doc_path)

    assert (
        _collect_hash_lock_violations(
            docs_root=docs_root,
            expected_hashes={"unit/baseline.md": expected_hash},
            approved_hashes={("unit/baseline.md", approved_hash)},
        )
        == []
    )

    doc_path.write_text("second silent drift\n")
    violations = _collect_hash_lock_violations(
        docs_root=docs_root,
        expected_hashes={"unit/baseline.md": expected_hash},
        approved_hashes={("unit/baseline.md", approved_hash)},
    )

    assert any("unit/baseline.md" in violation and "expected" in violation and "got" in violation for violation in violations)


def test_studio_audited_ready_doc_hashes_match_baseline_or_exemption() -> None:
    expected_hashes = _load_expected_hashes()
    approved_hashes = _load_hash_exemptions()

    violations = _collect_hash_lock_violations(
        docs_root=DOCS_ROOT,
        expected_hashes=expected_hashes,
        approved_hashes=approved_hashes,
    )

    assert not violations, "Unapproved Studio audited-ready doc hash drift:\n" + "\n".join(violations)
