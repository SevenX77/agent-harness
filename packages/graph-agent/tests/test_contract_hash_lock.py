from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
EXEMPTIONS_PATH = Path(__file__).with_name("contract-exemptions.yaml")

EXPECTED_CONTRACT_HASHES = {
    "docs/engine/mvp0/skill-spec/00-FORMAT-GROUND-TRUTH.md": "083f158bdb4c6ae3bea7b5b66ce1d57e1897a668c81dac757a2ddb2bf067af0e",
    "docs/engine/mvp0/skill-spec/01-physical-layout.md": "9478f81d9d8552227c82c440f6b047dc587652fcaa21200b0f38e3a93dcd8cc4",
    "docs/engine/mvp0/skill-spec/02-graph-md-spec.md": "d9202117a473cf055a58bcff29e454e7551a1438d1cecdd90ccac50e28646b6c",
    "docs/engine/mvp0/skill-spec/03-logic-md-spec.md": "f979921e9076b14a499d5dff257c7728afbe741b4e1d2ab642bed3fb0a369298",
    "docs/engine/mvp0/skill-spec/04-subgraph-md-spec.md": "2440be9949793cb5717ed1cb29712896c174fa71e8c1bfc48b41099a4ac33f3e",
    "docs/engine/mvp0/skill-spec/05-agent-md-spec.md": "51541ec8a805313c840c518130fe4ccf3615507614c0acf256f68102602f5b05",
    "docs/engine/mvp0/skill-spec/06-cognitive-template-spec.md": "8e7a942df4bef5f7c95812ec4a0886ee140a55c33ce49ff1b2328158d9203090",
    "docs/engine/mvp0/skill-spec/07-mention-syntax-spec.md": "ed8802373a1169fc0e4482f458e164d4153687b8a9123ca41da4d0284eadcc8d",
    "docs/engine/mvp0/skill-spec/08-resource-mechanisms-spec.md": "b52777065d6eb5a90a4e7be99d492b4e45f36317de80428dbb48499d59c6ad3b",
    "docs/engine/mvp0/skill-spec/09-builtin-modules-spec.md": "dac431f0a28d11448ea72193814ad4cb1c4cdb36cc1e09cc6fb9dfb7c11413d1",
    "docs/engine/mvp0/skill-spec/10-skill-resolver-protocol-spec.md": "9cc8f9a3df095623b67c74a353838c63825fae678e77a94593a18716cded660c",
    "docs/engine/mvp0/skill-spec/11-error-code-spec.md": "e51c09b196950c20d83ab658a8a02a17256aa24cc2922c376f7554d90055981c",
    "docs/engine/mvp0/skill-spec/12-compile-runtime-flow-spec.md": "0c632cbc7edbad3e741bf4a3676d08e68852ea2311f10624503d20f84d598223",
    "docs/engine/mvp0/skill-spec/README.md": "dc16c4c4caade48e027700f91ce666779b07f9a053ed3b8bda9f957fa6053b30",
    "docs/engine/mvp0/public-api-contract.md": "8a3ae8d4f7f5e723b356fd97881e38a17b69d1c493a7f80a3cfea782c5b848c5",
    "docs/engine/mvp0/feature-compliance-checklist.md": "77ea3efd4c6dfed5a09f496a82a1ba7ff3d2832ad1dc92ba9ac1f5cb759dc5c7",
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
