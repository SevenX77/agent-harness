from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
EXEMPTIONS_PATH = Path(__file__).with_name("contract-exemptions.yaml")

EXPECTED_CONTRACT_HASHES = {
    "docs/engine/skill-spec/00-FORMAT-GROUND-TRUTH.md": "083f158bdb4c6ae3bea7b5b66ce1d57e1897a668c81dac757a2ddb2bf067af0e",
    "docs/engine/skill-spec/01-physical-layout.md": "9478f81d9d8552227c82c440f6b047dc587652fcaa21200b0f38e3a93dcd8cc4",
    "docs/engine/skill-spec/02-graph-md-spec.md": "08c67068d5b88672739b98537c8b88eae634e9db3d9e18a202fae743cfe2d329",
    "docs/engine/skill-spec/03-logic-md-spec.md": "8ca96dd83fbbded37d22840b021eb7478d8821983ebc57e1c288fe09c4c4ddd3",
    "docs/engine/skill-spec/04-subgraph-md-spec.md": "f509813bb71a5acf69f4e8d7e98d59230fc5ca232b3b6b52ca216a6a60f04bdc",
    "docs/engine/skill-spec/05-agent-md-spec.md": "d2167f6dbcd4030b8c57ee2c372424469fd2281bdb35f3c5af1d783ed2f71277",
    "docs/engine/skill-spec/06-cognitive-template-spec.md": "c469949849a22420770459a12485ab2206e9d64f0bb9cd7d4a8cc471cc42d676",
    "docs/engine/skill-spec/07-mention-syntax-spec.md": "3447a2f7868731afd8ec8ff59efdd4c8eb0ec78559260867a00a29143aa90e3d",
    "docs/engine/skill-spec/08-resource-mechanisms-spec.md": "76317093d118bfa618496ae3d3b281bf07d290fb45e72d237db7d9132b59d4d7",
    "docs/engine/skill-spec/09-builtin-modules-spec.md": "dd38121c9906ae338026bc5805b9b76a7d832eb965917703f13171cf7e66586f",
    "docs/engine/skill-spec/10-skill-resolver-protocol-spec.md": "9cc8f9a3df095623b67c74a353838c63825fae678e77a94593a18716cded660c",
    "docs/engine/skill-spec/11-error-code-spec.md": "07c594bfca9182f096e0746e2be49871c72c73b4e0803492ec324b086e27a32b",
    "docs/engine/skill-spec/12-compile-runtime-flow-spec.md": "a3defd2e4f5e123e5821a0284a131784144b82f0b5699dfa6f7509d058f1a259",
    "docs/engine/skill-spec/README.md": "1716f2891e0a7ed6987489debb3c46948825430efeff61975caa7f420114c4b3",
    "docs/engine/public-api-contract.md": "59379703b51c267f772f35c751ecbd6e54b0bbd100c2b469be8f32dc6525d837",
    "docs/engine/feature-compliance-checklist.md": "4b7ee286fa372206af6ba1e2e97b36e5cdb3cf1e2653f81d43f0d1c06de076a0",
    "packages/graph-agent/spec/round28-manifest-schema.yaml": "bcdf70ea0469fe02adff8e2c20e03f813195c1eaa0e4c325f8987cb6cfed5481",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_hash_exemptions() -> set[str]:
    data = yaml.safe_load(EXEMPTIONS_PATH.read_text()) or {}
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
