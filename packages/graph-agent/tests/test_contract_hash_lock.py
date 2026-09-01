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
    # Re-pinned 2026-08-31 (J-X.10, user ruling "默认角色应该是空,必须要设置,
    # 不设置 compile 报错"): the effective-role chain lost its invented
    # graph_agent fallback — unset stays unset, and a governed compile
    # rejects it as [F-v3-agent-llm-role-missing]. Same PR as the engine
    # change (design and implementation land together).
    # Re-pinned 2026-09-01 (F-T2, cross-repo pointer currency): added a
    # scope-boundary section at the top. FROZEN now says what it covers —
    # the frozen in-repo engine (packages/graph-agent) only — because
    # docs/design/gskill-restructure-decision-2026-08-31.md §4.2 moved the
    # sole engine owner to graph-skill-runtime and froze this repo's copy to
    # a read-only mirror. The NEW format's authority is that repo's
    # docs/skill-spec/01-PORTABLE-GSKILL-V1.md (audited-ready); its own
    # 00-FORMAT-GROUND-TRUTH.md is superseded. Both repos carry a file by
    # this name, so an unqualified "00" was a two-referent ambiguity.
    # The pointer is deliberately STATELESS: it names which repo owns the new
    # format and stops there, because copying the other repo's status values
    # (audited-ready / superseded / phase progress) would fork a second,
    # staleable copy of facts that document owns — F-T3 is already queued to
    # flip that document's status, which would have falsified a copy on
    # arrival. Text-only change: no field, rule, or template was altered, so
    # no engine code or contract map moves with it.
    "docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md": "d442e4dcb0dcefdc855f88efc9a015e318d6753decdd573beffceeeb6ae98200",
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
