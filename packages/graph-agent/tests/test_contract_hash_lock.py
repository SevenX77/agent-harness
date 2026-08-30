from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
EXEMPTIONS_PATH = Path(__file__).with_name("contract-exemptions.yaml")

EXPECTED_CONTRACT_HASHES = {
    # 2026-08-29 (J-X.4, forked-copy convergence): the fourteen
    # docs/engine/mvp0/skill-spec/ entries left this table with the tree
    # itself — that superseded留底 copy is deleted, git history is its
    # archive. What the lock protects instead is the LIVING format SSOT the
    # engine actually consumes (loader.py and the contract tests cite it):
    # docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md, declared FROZEN by
    # its own README. The mvp0 fork drifted ~898 lines precisely because
    # only the dead copy was pinned while the live one had no enforcement.
    "docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md": "4967006e0d5d95a8328ee60b8da3107a64aae18bdbbfc2d10d0e6c65e269bf41",
    # Re-pinned 2026-08-15 (PR E, legacy execution family removal): the
    # CallbackEvent union dropped the ten zero-emitter event classes
    # (ValidationPass/ValidationFail/Retry/RetryExhausted/ModelResolved/
    # FinishTask/AmbiguityReport/Heartbeat/ThreadCleanedUp/InternalError)
    # and the stale LLMFallbackEvent entry that never existed in code
    # (decision doc §5; pre-release, no-backward-compat, all consumers
    # updated in the same PR).
    "docs/engine/mvp0/public-api-contract.md": "68075217ba4c57feff2a5dce9b4d4e506d2a52095a4b2e891f0558baa60cd243",
    "docs/engine/mvp0/feature-compliance-checklist.md": "77ea3efd4c6dfed5a09f496a82a1ba7ff3d2832ad1dc92ba9ac1f5cb759dc5c7",
    "packages/graph-agent/spec/round28-manifest-schema.yaml": "bcdf70ea0469fe02adff8e2c20e03f813195c1eaa0e4c325f8987cb6cfed5481",
}


def _sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_hash_exemptions() -> set[str]:
    data = yaml.safe_load(EXEMPTIONS_PATH.read_text(encoding="utf-8")) or {}
    exemptions = data.get("exemptions", [])
    assert isinstance(exemptions, list), "contract exemptions must be a list"

    approved_hashes: set[str] = set()
    for index, exemption in enumerate(exemptions):
        assert isinstance(exemption, dict), f"exemption #{index} must be a mapping"
        hashes = exemption.get("hashes", [])
        assert isinstance(hashes, list), f"exemption #{index} hashes must be a list"
        if hashes:
            assert exemption.get("pr"), f"hash exemption #{index} must include pr"
            assert exemption.get("pm_approval"), f"hash exemption #{index} must include pm_approval"
        approved_hashes.update(str(hash_key) for hash_key in hashes)
    return approved_hashes


def test_contract_hashes_match_frozen_baseline_or_pm_exemption() -> None:
    approved_hashes = _load_hash_exemptions()

    drifted: list[str] = []
    for relative_path, expected_hash in EXPECTED_CONTRACT_HASHES.items():
        actual_hash = _sha256(REPO_ROOT / relative_path)
        if actual_hash != expected_hash and relative_path not in approved_hashes:
            drifted.append(f"{relative_path}: expected {expected_hash}, got {actual_hash}")

    assert not drifted, "Unapproved contract hash drift:\n" + "\n".join(drifted)
