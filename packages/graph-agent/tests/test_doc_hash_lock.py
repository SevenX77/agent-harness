from __future__ import annotations

import hashlib
import json
import string
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_ROOT = REPO_ROOT / "docs" / "engine" / "mvp1"
HASH_LOCK_PATH = DOCS_ROOT / "_audited-ready-hashes.json"
EXEMPTIONS_PATH = DOCS_ROOT / "_doc-exemptions.yaml"
HASH_LOCK_REMEDIATION = (
    "revert unapproved doc edits; or with owner approval update "
    "docs/engine/mvp1/_audited-ready-hashes.json; or add a temporary exemption "
    "to docs/engine/mvp1/_doc-exemptions.yaml with file, sha256, reason, and owner_approval"
)


def _sha256(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(character in string.hexdigits for character in value)


def _assert_safe_relative_path(value: object, *, context: str) -> str:
    assert isinstance(value, str) and value, f"{context} must include a non-empty file path"
    relative_path = Path(value)
    assert not relative_path.is_absolute() and ".." not in relative_path.parts, (
        f"{context} path must stay relative to docs/engine/mvp1: {value}"
    )
    return value


def _load_expected_hashes(hash_lock_path: Path = HASH_LOCK_PATH) -> dict[str, str]:
    assert hash_lock_path.exists(), f"engine doc hash lock baseline missing: {hash_lock_path}"
    data = json.loads(hash_lock_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "engine doc hash lock must be a JSON object"

    hashes = data.get("hashes")
    assert isinstance(hashes, dict), "engine doc hash lock must contain a hashes object"

    meta = data.get("_meta")
    if isinstance(meta, dict) and "count" in meta:
        assert meta["count"] == len(hashes), "engine doc hash lock _meta.count must match hashes count"

    expected_hashes: dict[str, str] = {}
    for relative_path, expected_hash in hashes.items():
        safe_relative_path = _assert_safe_relative_path(relative_path, context="engine doc hash")
        assert isinstance(expected_hash, str) and _is_sha256_hex(expected_hash), (
            f"engine doc hash for {safe_relative_path} must be a SHA-256 hex digest"
        )
        expected_hashes[safe_relative_path] = expected_hash

    return expected_hashes


def _load_hash_exemptions(exemption_path: Path = EXEMPTIONS_PATH) -> set[tuple[str, str]]:
    assert exemption_path.exists(), f"engine doc exemptions file missing: {exemption_path}"
    data = yaml.safe_load(exemption_path.read_text(encoding="utf-8")) or {}
    assert isinstance(data, dict), "engine doc exemptions must be a mapping"

    exemptions = data.get("exemptions", [])
    assert isinstance(exemptions, list), "engine doc exemptions must be a list"

    approved_hashes: set[tuple[str, str]] = set()
    for index, exemption in enumerate(exemptions):
        assert isinstance(exemption, dict), f"engine doc exemption #{index} must be a mapping"

        relative_path = _assert_safe_relative_path(
            exemption.get("file"),
            context=f"engine doc exemption #{index}",
        )
        approved_hash = exemption.get("sha256")
        reason = exemption.get("reason")
        owner_approval = exemption.get("owner_approval")

        assert isinstance(approved_hash, str) and _is_sha256_hex(approved_hash), (
            f"engine doc exemption #{index} must include sha256"
        )
        assert isinstance(reason, str) and reason, f"engine doc exemption #{index} must include reason"
        assert isinstance(owner_approval, str) and owner_approval, (
            f"engine doc exemption #{index} must include owner_approval"
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
    locked_dirs = {Path(relative_path).parent for relative_path in expected_paths}

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

    for doc_path in sorted(docs_root.rglob("*.md")):
        relative_path = doc_path.relative_to(docs_root).as_posix()
        if relative_path in expected_paths or doc_path.relative_to(docs_root).parent not in locked_dirs:
            continue
        actual_hash = _sha256(doc_path)
        if (relative_path, actual_hash) not in approved_hashes:
            violations.append(
                f"{relative_path}: not listed in hash table, got {actual_hash}; remediation: {HASH_LOCK_REMEDIATION}"
            )

    return violations


def test_hash_lock_reports_drift_missing_and_untracked_docs(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "engine" / "mvp1"
    docs_root.mkdir(parents=True)

    tracked = docs_root / "existing-unit" / "baseline.md"
    tracked.parent.mkdir()
    tracked.write_text("audited baseline\n")
    expected_tracked_hash = _sha256(tracked)
    tracked.write_text("silent drift\n")

    new_doc = docs_root / "existing-unit" / "extra.md"
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
    assert any("existing-unit/extra.md" in violation and "not listed" in violation for violation in violations)


def test_hash_lock_exemption_allows_only_exact_file_and_hash(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "engine" / "mvp1"
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


def test_hash_exemptions_require_file_hash_reason_and_owner_approval(tmp_path: Path) -> None:
    exemption_path = tmp_path / "_doc-exemptions.yaml"
    exemption_path.write_text(
        """
version: "1"
exemptions:
  - file: "unit/baseline.md"
    sha256: "1111111111111111111111111111111111111111111111111111111111111111"
    reason: "Temporary approved drift."
""",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="owner_approval"):
        _load_hash_exemptions(exemption_path)


def test_engine_audited_ready_doc_hashes_match_baseline_or_exemption() -> None:
    expected_hashes = _load_expected_hashes()
    approved_hashes = _load_hash_exemptions()

    violations = _collect_hash_lock_violations(
        docs_root=DOCS_ROOT,
        expected_hashes=expected_hashes,
        approved_hashes=approved_hashes,
    )

    assert not violations, "Unapproved Engine audited-ready doc hash drift:\n" + "\n".join(violations)
