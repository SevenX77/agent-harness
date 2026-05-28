from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages/graph-agent"
FIXTURES = PACKAGE_ROOT / "tests/fixtures/round28"

SCHEMA_PATH = PACKAGE_ROOT / "spec/round28-manifest-schema.yaml"
FEATURES_PATH = PACKAGE_ROOT / "spec/features.yaml"
SOURCE_MAP_PATH = PACKAGE_ROOT / "spec/source_file_map.yaml"
CONTRACT_MAP_PATH = PACKAGE_ROOT / "spec/contract_map.yaml"
VALIDATOR_PATH = PACKAGE_ROOT / "scripts/validate_round28_manifest.py"
CODEOWNERS_PATH = REPO_ROOT / ".github/CODEOWNERS"
CHECKLIST_PATH = REPO_ROOT / "docs/engine/feature-compliance-checklist.md"
PUBLIC_API_CONTRACT_PATH = REPO_ROOT / "docs/engine/public-api-contract.md"
PUBLIC_API_TEST_PATH = PACKAGE_ROOT / "tests/test_public_api_contract.py"
EXEMPTIONS_PATH = PACKAGE_ROOT / "tests/contract-exemptions.yaml"
OLD_HASH_LOCK_PATH = PACKAGE_ROOT / "tests/test_skill_spec_hash_lock.py"
CONTRACT_HASH_LOCK_PATH = PACKAGE_ROOT / "tests/test_contract_hash_lock.py"

VENDOR_ONLY_SYMBOLS = {
    "AgentSkillDef",
    "GraphSkillDef",
    "IoInput",
    "PersonaSkillDef",
    "CompileIssue",
    "parse_skill_file",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(_read(path))


def _frontmatter(path: Path) -> dict[str, Any]:
    text = _read(path)
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    return yaml.safe_load(text[4:end]) or {}


def _round28_schema() -> dict[str, Any]:
    assert SCHEMA_PATH.exists(), "round28 manifest schema is missing"
    schema = _load_yaml(SCHEMA_PATH)
    assert isinstance(schema, dict), "round28 manifest schema must be a YAML mapping"
    Draft202012Validator.check_schema(schema)
    return schema


def _validate_manifest(instance: Any, schema_key: str) -> None:
    schema = _round28_schema()
    definitions = schema.get("$defs") or schema.get("definitions") or {}
    assert schema_key in definitions, f"schema missing {schema_key} definition"
    Draft202012Validator(definitions[schema_key]).validate(instance)


def _run_validator(*fixture_paths: Path) -> subprocess.CompletedProcess[str]:
    cmd = ["python", str(VALIDATOR_PATH), *map(str, fixture_paths)]
    return subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=False)


def _public_api_symbols() -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"^## ([A-Za-z_][A-Za-z0-9_]*)$", _read(PUBLIC_API_CONTRACT_PATH), re.MULTILINE)
        if match.group(1) != "Coverage"
    }


def _src_python_files() -> set[str]:
    return {str(path.relative_to(REPO_ROOT)) for path in (PACKAGE_ROOT / "src/graph_agent").rglob("*.py")}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a0_feature_boundary_schema_rejects_invalid_fixtures() -> None:
    for fixture_name in [
        "invalid_feature_bad_boundary.yaml",
        "invalid_feature_empty_description.yaml",
        "invalid_feature_missing_sources.yaml",
    ]:
        with pytest.raises(ValidationError):
            _validate_manifest(_load_yaml(FIXTURES / fixture_name), "feature")


def test_a1_vendor_only_symbols_are_required_in_contract_map_fixture() -> None:
    invalid_contract_map = _load_yaml(FIXTURES / "invalid_contract_map_missing_vendor_only.yaml")
    with pytest.raises(ValidationError):
        _validate_manifest(invalid_contract_map, "contract_map")

    result = _run_validator(FIXTURES / "invalid_contract_map_missing_vendor_only.yaml")
    assert result.returncode != 0
    assert "R28_VENDOR_ONLY_UNMAPPED" in result.stderr


def test_a2_non_functional_contract_schema_requires_evidence_and_other() -> None:
    invalid_feature = _load_yaml(FIXTURES / "invalid_feature_nonfunctional_missing_evidence.yaml")
    with pytest.raises(ValidationError):
        _validate_manifest(invalid_feature, "feature")

    other_feature = _load_yaml(FIXTURES / "valid_feature_other_nonfunctional.yaml")
    _validate_manifest(other_feature, "feature")


def test_a3_schema_examples_reference_real_skill_spec_paths() -> None:
    invalid_feature = _load_yaml(FIXTURES / "invalid_feature_bad_skill_spec_path.yaml")
    result = _run_validator(FIXTURES / "invalid_feature_bad_skill_spec_path.yaml")
    assert result.returncode != 0
    assert "R28_SKILL_SPEC_ANCHOR_MISSING" in result.stderr
    with pytest.raises(ValidationError):
        _validate_manifest(invalid_feature, "feature")


def test_a4_hash_lock_is_single_renamed_contract_test() -> None:
    assert CONTRACT_HASH_LOCK_PATH.exists(), "contract hash lock test is missing"
    assert not OLD_HASH_LOCK_PATH.exists(), "old skill-spec-only hash lock must be removed"


def test_task1_schema_rejects_bad_feature_shape() -> None:
    invalid_feature = _load_yaml(FIXTURES / "invalid_feature_missing_core_paths_and_tests.yaml")
    with pytest.raises(ValidationError):
        _validate_manifest(invalid_feature, "feature")

    invalid_debt = _load_yaml(FIXTURES / "invalid_source_map_debt_missing_exemption.yaml")
    with pytest.raises(ValidationError):
        _validate_manifest(invalid_debt, "source_file_map")


def test_task2_features_single_entry_shape_is_enforced() -> None:
    feature = _load_yaml(FIXTURES / "valid_feature_minimal.yaml")
    _validate_manifest(feature, "feature")
    assert feature["id"].startswith("F-")
    assert feature["feature_boundary"]["kind"] in {
        "public-method",
        "lifecycle-behavior",
        "externally-observable-behavior",
    }
    assert feature["sources"]
    assert feature["core_paths"]
    for field in (
        "error_codes_primary",
        "error_codes_secondary",
        "events_primary",
        "events_secondary",
        "non_functional_contracts",
        "targeted_tests",
    ):
        assert field in feature


def test_task3_source_file_map_rejects_missing_src_file() -> None:
    result = _run_validator(FIXTURES / "invalid_source_map_missing_one_src.yaml")
    assert result.returncode != 0
    assert "R28_SOURCE_FILE_UNMAPPED" in result.stderr


def test_task4_contract_map_axes_require_feature_ids_and_consumer_kinds() -> None:
    invalid_contract_map = _load_yaml(FIXTURES / "invalid_contract_map_empty_feature_ids.yaml")
    with pytest.raises(ValidationError):
        _validate_manifest(invalid_contract_map, "contract_map")

    valid_contract_map = _load_yaml(FIXTURES / "valid_contract_map_minimal.yaml")
    _validate_manifest(valid_contract_map, "contract_map")
    assert {entry["kind"] for entry in valid_contract_map["consumer_files"]} == {
        "live-consumer",
        "stable-export",
        "vendor-only-debt",
    }


def test_task5_targeted_tests_are_collected_from_manifest_nodeids() -> None:
    features = _load_yaml(FIXTURES / "valid_features_collectable_tests.yaml")
    _validate_manifest(features["features"][0], "feature")
    nodeids = [nodeid for feature in features["features"] for nodeid in feature["targeted_tests"]]
    collect = subprocess.run(
        ["uv", "run", "pytest", "--collect-only", "-q", *nodeids],
        cwd=PACKAGE_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert collect.returncode == 0, collect.stdout + collect.stderr


def test_task6_codeowners_and_frozen_checklist_are_concrete() -> None:
    codeowners = _read(CODEOWNERS_PATH)
    assert "docs/engine/feature-compliance-checklist.md @SevenX77" in codeowners
    frontmatter = _frontmatter(CHECKLIST_PATH)
    assert frontmatter.get("status") == "FROZEN"
    assert "DO NOT EDIT: Golden principle contract baseline" in _read(CHECKLIST_PATH)


def test_task7_hash_lock_detects_mutated_schema_fixture() -> None:
    assert CONTRACT_HASH_LOCK_PATH.exists(), "contract hash lock test is missing"

    baseline_result = subprocess.run(
        ["uv", "run", "pytest", "tests/test_contract_hash_lock.py", "-q"],
        cwd=PACKAGE_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert baseline_result.returncode == 0, (
        "test_contract_hash_lock baseline must pass before mutation test\n"
        + baseline_result.stdout
        + baseline_result.stderr
    )

    original_content = _read(SCHEMA_PATH)
    original_hash = _sha256(SCHEMA_PATH)
    try:
        SCHEMA_PATH.write_text(original_content.replace("feature", "feature_weakened", 1), encoding="utf-8")
        assert _sha256(SCHEMA_PATH) != original_hash
        mutated_result = subprocess.run(
            ["uv", "run", "pytest", "tests/test_contract_hash_lock.py", "-q"],
            cwd=PACKAGE_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert mutated_result.returncode != 0, "hash lock must catch schema mutation"
        assert "round28-manifest-schema.yaml" in mutated_result.stdout + mutated_result.stderr
    finally:
        SCHEMA_PATH.write_text(original_content, encoding="utf-8")


def test_task8_exemption_schema_accepts_valid_and_rejects_invalid_fixtures() -> None:
    public_api_test = _read(PUBLIC_API_TEST_PATH)
    assert "test_exemptions_yaml_currently_empty_in_pr1" not in public_api_test

    valid_exemption = _load_yaml(FIXTURES / "valid_contract_exemption.yaml")
    _validate_manifest(valid_exemption, "contract_exemptions")

    for fixture_name in ["invalid_exemption_bad_id.yaml", "invalid_exemption_missing_required.yaml"]:
        with pytest.raises(ValidationError):
            _validate_manifest(_load_yaml(FIXTURES / fixture_name), "contract_exemptions")


def test_task9_validator_rejects_all_manifest_catch_classes() -> None:
    catch_cases = {
        "invalid_features_duplicate_error_primary.yaml": "R28_PRIMARY_OWNER_DUPLICATE",
        "invalid_source_map_debt_missing_exemption.yaml": "R28_DEBT_EXEMPTION_REQUIRED",
        "invalid_contract_map_missing_public_symbol.yaml": "R28_PUBLIC_API_UNMAPPED",
        "invalid_source_map_missing_one_src.yaml": "R28_SOURCE_FILE_UNMAPPED",
        "invalid_features_uncollectable_test.yaml": "R28_TARGETED_TEST_UNCOLLECTABLE",
    }
    for fixture_name, expected_error in catch_cases.items():
        result = _run_validator(FIXTURES / fixture_name)
        assert result.returncode != 0, f"{fixture_name} unexpectedly passed"
        assert expected_error in result.stderr


def test_primary_owner_unique_per_error_code_and_event() -> None:
    duplicate = _run_validator(FIXTURES / "invalid_features_duplicate_error_primary.yaml")
    assert duplicate.returncode != 0
    assert "R28_PRIMARY_OWNER_DUPLICATE" in duplicate.stderr

    missing_error_code = _run_validator(FIXTURES / "invalid_features_missing_error_code_owner.yaml")
    assert missing_error_code.returncode != 0
    assert "R28_PRIMARY_OWNER_MISSING" in missing_error_code.stderr

    missing_event = _run_validator(FIXTURES / "invalid_features_missing_event_owner.yaml")
    assert missing_event.returncode != 0
    assert "R28_PRIMARY_OWNER_MISSING" in missing_event.stderr

    valid = _run_validator(FIXTURES / "valid_features_primary_owners.yaml")
    assert valid.returncode == 0, valid.stderr


def test_feature_classification_reverse_mapping() -> None:
    invalid = _run_validator(FIXTURES / "invalid_feature_classification_unreferenced.yaml")
    assert invalid.returncode != 0
    assert "R28_FEATURE_FILE_NOT_IN_CORE_PATHS" in invalid.stderr

    valid = _run_validator(FIXTURES / "valid_feature_classification_referenced.yaml")
    assert valid.returncode == 0, valid.stderr


def test_cutover_discipline_quantifies_overlap() -> None:
    tasks = _read(REPO_ROOT / ".kiro/specs/engine-mvp0-rebuild-v030/round-28-feature-checklist-redesign/tasks.md")
    assert "24h" in tasks
    assert "1 个独立 PR" in tasks

    result = _run_validator(FIXTURES / "invalid_cutover_overlap_missing_attestation.yaml")
    assert result.returncode != 0
    assert "R28_CUTOVER_OVERLAP_ATTESTATION_MISSING" in result.stderr


def test_runtime_compat_features_cover_all_patches() -> None:
    patch_like_files = sorted(
        str(path.relative_to(REPO_ROOT))
        for path in (PACKAGE_ROOT / "src/graph_agent").rglob("*.py")
        if "patch" in path.parts or "patch" in path.name or "compat" in path.name
    )
    assert patch_like_files, "fixture expectation: repo has patch/compat modules"

    result = _run_validator(FIXTURES / "invalid_features_missing_runtime_compat.yaml")
    assert result.returncode != 0
    assert "R28_RUNTIME_COMPAT_FEATURE_MISSING" in result.stderr

    valid = _run_validator(FIXTURES / "valid_features_runtime_compat.yaml")
    assert valid.returncode == 0, valid.stderr
