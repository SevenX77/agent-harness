from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_ROOT = REPO_ROOT / "docs" / "graph-agent-gateway" / "mvp1"
HASH_LOCK_PATH = DOCS_ROOT / "_audited-ready-hashes.json"
SNAPSHOT_PATH = DOCS_ROOT / "_design-unit-lock-snapshot.json"
EXEMPTIONS_PATH = Path(__file__).with_name("gateway-doc-exemptions.json")

HASH_LOCK_REMEDIATION = (
    "revert unapproved gateway doc edits; or with owner approval update "
    "docs/graph-agent-gateway/mvp1/_audited-ready-hashes.json; or add a temporary exemption "
    "to packages/graph-agent-gateway/tests/gateway-doc-exemptions.json with file, sha256, reason, and owner_approval"
)
SNAPSHOT_REMEDIATION = (
    "if this is an intentional gateway design-unit lock owner/state change, update "
    "docs/graph-agent-gateway/mvp1/_design-unit-lock-snapshot.json with owner approval; otherwise restore "
    "docs/graph-agent-gateway/mvp1/DESIGN_UNITS_INDEX.md"
)

VALID_OWNED_LOCKS = {"drafted", "locked"}
VALID_EXTERNAL_BINDINGS = {"none", "floating-draft", "pinned-draft", "frozen-pinned", "stale"}
VALID_INTEGRATION_LOCKS = {"unverified", "locked"}
VALID_ROLES = {"owner", "消费", "引", "落点"}
EXTERNAL_MODULE_PREFIXES = ("studio:", "engine:")
SPAN_ENTRY_RE = re.compile(r"^(?P<facet>.+?)→`(?P<module>[^`]+)`\((?P<role_note>.+)\)$")
ROLE_NOTE_RE = re.compile(r"^(?P<role>owner|消费|引|落点)(?:$|[;/,，;；]\s*.+$)")
STATUS_RE = re.compile(r"^status:\s*(?P<status>.+)$", re.MULTILINE)


@dataclass(frozen=True)
class SpanEntry:
    facet: str
    module: str
    role: str


@dataclass(frozen=True)
class DesignUnitLockRecord:
    unit: str
    owned_lock: str
    external_binding: str
    integration_lock: str
    owners: list[str]
    external_refs: list[str]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strip_inline_code(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


def _normalize_lock_value(value: str) -> str:
    return _strip_inline_code(value).strip()


def _load_json_object(path: Path, *, description: str) -> dict[str, Any]:
    assert path.exists(), f"Missing {description}: {path.relative_to(REPO_ROOT).as_posix()}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{description} must be a JSON object"
    return data


def _load_expected_hashes(path: Path = HASH_LOCK_PATH) -> dict[str, str]:
    data = _load_json_object(path, description="gateway doc hash lock")
    assert data.get("schema_version") == 1, "gateway doc hash lock schema_version must be 1"

    hashes = data.get("hashes")
    assert isinstance(hashes, dict), "gateway doc hash lock must contain a hashes object"

    meta = data.get("_meta")
    if isinstance(meta, dict) and "count" in meta:
        assert meta["count"] == len(hashes), "gateway doc hash lock _meta.count must match hashes count"

    expected_hashes: dict[str, str] = {}
    for relative_path, expected_hash in hashes.items():
        assert isinstance(relative_path, str) and relative_path, "gateway doc hash paths must be non-empty strings"
        assert not relative_path.startswith("/") and ".." not in Path(relative_path).parts, (
            f"gateway doc hash path must stay relative to docs/graph-agent-gateway/mvp1: {relative_path}"
        )
        assert isinstance(expected_hash, str) and len(expected_hash) == 64, (
            f"gateway doc hash for {relative_path} must be a SHA-256 hex digest"
        )
        expected_hashes[relative_path] = expected_hash
    return expected_hashes


def _load_exemptions(path: Path = EXEMPTIONS_PATH) -> tuple[set[tuple[str, str]], set[str]]:
    data = _load_json_object(path, description="gateway doc exemptions")
    assert data.get("version") == "1", "gateway doc exemptions version must be '1'"

    hash_exemptions = data.get("hash_exemptions", [])
    assert isinstance(hash_exemptions, list), "hash_exemptions must be a list"
    approved_hashes: set[tuple[str, str]] = set()
    for index, exemption in enumerate(hash_exemptions):
        assert isinstance(exemption, dict), f"gateway doc hash exemption #{index} must be a mapping"
        relative_path = exemption.get("file")
        approved_hash = exemption.get("sha256")
        reason = exemption.get("reason")
        owner_approval = exemption.get("owner_approval")
        assert isinstance(relative_path, str) and relative_path, f"gateway doc hash exemption #{index} must include file"
        assert isinstance(approved_hash, str) and len(approved_hash) == 64, (
            f"gateway doc hash exemption #{index} must include sha256"
        )
        assert isinstance(reason, str) and reason, f"gateway doc hash exemption #{index} must include reason"
        assert isinstance(owner_approval, str) and owner_approval, (
            f"gateway doc hash exemption #{index} must include owner_approval"
        )
        approved_hashes.add((relative_path, approved_hash))

    snapshot_exemptions = data.get("design_unit_lock_snapshot_exemptions", [])
    assert isinstance(snapshot_exemptions, list), "design_unit_lock_snapshot_exemptions must be a list"
    exempt_units: set[str] = set()
    for index, exemption in enumerate(snapshot_exemptions):
        assert isinstance(exemption, dict), f"gateway design-unit exemption #{index} must be a mapping"
        unit = exemption.get("unit")
        reason = exemption.get("reason")
        owner_approval = exemption.get("owner_approval")
        assert isinstance(unit, str) and unit, f"gateway design-unit exemption #{index} must include unit"
        assert isinstance(reason, str) and reason, f"gateway design-unit exemption #{index} must include reason"
        assert isinstance(owner_approval, str) and owner_approval, (
            f"gateway design-unit exemption #{index} must include owner_approval"
        )
        exempt_units.add(unit)

    return approved_hashes, exempt_units


def _frontmatter_status(markdown: str) -> str | None:
    if not markdown.startswith("---\n"):
        return None
    end = markdown.find("\n---\n", 4)
    if end == -1:
        return None
    match = STATUS_RE.search(markdown[4:end])
    return match.group("status").strip() if match else None


def _is_frozen_doc(path: Path) -> bool:
    status = _frontmatter_status(path.read_text(encoding="utf-8"))
    return bool(status and status.startswith("FROZEN"))


def _collect_hash_lock_violations(
    *,
    docs_root: Path,
    expected_hashes: dict[str, str],
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

    for doc_path in sorted(docs_root.rglob("*.md")):
        relative_path = doc_path.relative_to(docs_root).as_posix()
        if relative_path in expected_paths or not _is_frozen_doc(doc_path):
            continue
        actual_hash = _sha256(doc_path)
        if (relative_path, actual_hash) not in approved_hashes:
            violations.append(
                f"{relative_path}: FROZEN doc is not listed in hash table, got {actual_hash}; "
                f"remediation: {HASH_LOCK_REMEDIATION}"
            )

    return violations


def _parse_markdown_table_rows(markdown: str) -> list[dict[str, str]]:
    lines = markdown.splitlines()
    header_index = next(
        index for index, line in enumerate(lines) if line.startswith("| 单元 |") and "owned-lock" in line
    )
    headers = [cell.strip() for cell in lines[header_index].strip().strip("|").split("|")]
    rows: list[dict[str, str]] = []

    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != len(headers):
            raise AssertionError(
                f"Malformed gateway DESIGN_UNITS_INDEX.md row has {len(cells)} cells, expected {len(headers)}: {line}"
            )
        rows.append(dict(zip(headers, cells, strict=True)))

    return rows


def _parse_spans(*, unit: str, spans: str) -> list[SpanEntry]:
    entries: list[SpanEntry] = []
    for raw_entry in spans.split(" · "):
        entry = raw_entry.strip()
        if entry.count("→") != 1:
            raise AssertionError(
                f"{unit}: span entry must contain exactly one separator arrow: {entry}; remediation: "
                "write each span as 'facet→`module`(role)' and avoid arrows inside facet text"
            )
        match = SPAN_ENTRY_RE.fullmatch(entry)
        if not match:
            raise AssertionError(
                f"{unit}: span entry must match 'facet→`module`(role; optional note)': {entry}; remediation: "
                "split compound spans and add an explicit leading role owner/消费/引/落点"
            )
        role_note = match.group("role_note").strip()
        role_match = ROLE_NOTE_RE.fullmatch(role_note)
        if not role_match:
            raise AssertionError(
                f"{unit}: span entry role must be one of {sorted(VALID_ROLES)}, got {role_note!r} in {entry}; "
                "remediation: make the role the first token inside parentheses"
            )
        facet = match.group("facet").strip()
        module = match.group("module").strip()
        if not facet or not module:
            raise AssertionError(f"{unit}: span entry has empty facet/module: {entry}")
        entries.append(SpanEntry(facet=facet, module=module, role=role_match.group("role")))
    return entries


def _is_external_module(module: str) -> bool:
    return module.startswith(EXTERNAL_MODULE_PREFIXES)


def _canonicalize_design_units(index_path: Path) -> list[DesignUnitLockRecord]:
    records: list[DesignUnitLockRecord] = []
    rows = _parse_markdown_table_rows(index_path.read_text(encoding="utf-8"))
    seen_units: set[str] = set()

    for row in rows:
        unit = _strip_inline_code(row["单元"])
        if not unit:
            raise AssertionError("DESIGN_UNITS_INDEX.md contains a unit row with an empty unit id")
        if unit in seen_units:
            raise AssertionError(f"{unit}: duplicate unit row in DESIGN_UNITS_INDEX.md")
        seen_units.add(unit)

        owned_lock = _normalize_lock_value(row["owned-lock"])
        external_binding = _normalize_lock_value(row["external-binding"])
        integration_lock = _normalize_lock_value(row["integration-lock"])
        if owned_lock not in VALID_OWNED_LOCKS:
            raise AssertionError(f"{unit}: invalid owned-lock {owned_lock!r}; expected {sorted(VALID_OWNED_LOCKS)}")
        if external_binding not in VALID_EXTERNAL_BINDINGS:
            raise AssertionError(
                f"{unit}: invalid external-binding {external_binding!r}; expected {sorted(VALID_EXTERNAL_BINDINGS)}"
            )
        if integration_lock not in VALID_INTEGRATION_LOCKS:
            raise AssertionError(
                f"{unit}: invalid integration-lock {integration_lock!r}; expected {sorted(VALID_INTEGRATION_LOCKS)}"
            )
        expected_integration_lock = (
            "locked" if owned_lock == "locked" and external_binding in {"none", "frozen-pinned"} else "unverified"
        )
        if integration_lock != expected_integration_lock:
            raise AssertionError(
                f"{unit}: integration-lock must be {expected_integration_lock!r} for owned-lock={owned_lock!r} "
                f"and external-binding={external_binding!r}; got {integration_lock!r}"
            )

        span_entries = _parse_spans(unit=unit, spans=row["spans（切面 → 模块 · 角色;角色∈owner/消费/引/落点）"])
        owners = sorted({entry.module for entry in span_entries if entry.role == "owner"})
        external_refs = sorted(
            {f"{entry.facet}→{entry.module}" for entry in span_entries if entry.role == "引" and _is_external_module(entry.module)}
        )
        if external_binding == "none" and external_refs:
            raise AssertionError(
                f"{unit}: external-binding is none but external refs exist: {external_refs}; remediation: "
                "set external-binding to a non-none binding or remove the external '(引)' spans"
            )
        if external_binding != "none" and not external_refs:
            raise AssertionError(
                f"{unit}: external-binding is {external_binding!r} but no studio/engine '(引)' spans were found; "
                "remediation: add external refs or set external-binding to none"
            )

        records.append(
            DesignUnitLockRecord(
                unit=unit,
                owned_lock=owned_lock,
                external_binding=external_binding,
                integration_lock=integration_lock,
                owners=owners,
                external_refs=external_refs,
            )
        )

    return sorted(records, key=lambda record: record.unit)


def _load_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, Any]:
    data = _load_json_object(path, description="gateway design-unit lock snapshot")
    assert data.get("schema_version") == 1, "gateway design-unit lock snapshot schema_version must be 1"
    units = data.get("units")
    assert isinstance(units, list), "gateway design-unit lock snapshot must contain a units list"
    for index, unit in enumerate(units):
        assert isinstance(unit, dict), f"snapshot unit #{index} must be a JSON object"
    return data


def _snapshot_units(snapshot: dict[str, Any]) -> dict[str, DesignUnitLockRecord]:
    records: dict[str, DesignUnitLockRecord] = {}
    for index, unit in enumerate(snapshot["units"]):
        unit_id = unit.get("unit")
        assert isinstance(unit_id, str) and unit_id, f"snapshot unit #{index} must include unit"
        if unit_id in records:
            raise AssertionError(f"{unit_id}: duplicate unit in _design-unit-lock-snapshot.json")

        for key in ("owned_lock", "external_binding", "integration_lock"):
            assert isinstance(unit.get(key), str), f"{unit_id}: snapshot must include string field {key}"
        for key in ("owners", "external_refs"):
            value = unit.get(key)
            assert isinstance(value, list) and all(isinstance(item, str) for item in value), (
                f"{unit_id}: snapshot field {key} must be a list of strings"
            )
            assert value == sorted(set(value)), f"{unit_id}: snapshot field {key} must be sorted and unique"

        records[unit_id] = DesignUnitLockRecord(
            unit=unit_id,
            owned_lock=unit["owned_lock"],
            external_binding=unit["external_binding"],
            integration_lock=unit["integration_lock"],
            owners=unit["owners"],
            external_refs=unit["external_refs"],
        )

    return records


def _collect_snapshot_violations(
    *,
    current_records: list[DesignUnitLockRecord],
    snapshot_records: dict[str, DesignUnitLockRecord],
    exempt_units: set[str],
) -> list[str]:
    violations: list[str] = []
    current_by_unit = {record.unit: record for record in current_records}

    for unit, snapshot_record in sorted(snapshot_records.items()):
        if unit in exempt_units or snapshot_record.owned_lock != "locked":
            continue
        current_record = current_by_unit.get(unit)
        if current_record is None:
            violations.append(f"{unit}: locked unit is missing from DESIGN_UNITS_INDEX.md; remediation: {SNAPSHOT_REMEDIATION}")
            continue
        if current_record != snapshot_record:
            expected = asdict(snapshot_record)
            actual = asdict(current_record)
            changed_fields = [
                field
                for field in ("owned_lock", "external_binding", "integration_lock", "owners", "external_refs")
                if expected[field] != actual[field]
            ]
            details = "; ".join(f"{field}: expected {expected[field]!r}, got {actual[field]!r}" for field in changed_fields)
            violations.append(f"{unit}: locked unit drifted from snapshot ({details}); remediation: {SNAPSHOT_REMEDIATION}")

    for current_record in current_records:
        if current_record.unit in snapshot_records or current_record.unit in exempt_units:
            continue
        if current_record.owned_lock == "locked":
            violations.append(
                f"{current_record.unit}: INDEX marks owned-lock=locked but the unit is absent from "
                f"_design-unit-lock-snapshot.json; remediation: register the new lock in the snapshot or mark it drafted"
            )

    return violations


def test_gateway_hash_lock_reports_drift_missing_and_untracked_frozen_docs(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "graph-agent-gateway" / "mvp1"
    docs_root.mkdir(parents=True)

    tracked = docs_root / "existing-unit" / "baseline.md"
    tracked.parent.mkdir()
    tracked.write_text("---\nstatus: FROZEN\n---\naudited baseline\n", encoding="utf-8")
    expected_tracked_hash = _sha256(tracked)
    tracked.write_text("---\nstatus: FROZEN\n---\nsilent drift\n", encoding="utf-8")

    new_frozen = docs_root / "new-unit" / "baseline.md"
    new_frozen.parent.mkdir()
    new_frozen.write_text("---\nstatus: FROZEN\n---\nnew frozen doc\n", encoding="utf-8")

    new_draft = docs_root / "draft-unit" / "baseline.md"
    new_draft.parent.mkdir()
    new_draft.write_text("---\nstatus: drafted\n---\nnew draft doc\n", encoding="utf-8")

    violations = _collect_hash_lock_violations(
        docs_root=docs_root,
        expected_hashes={
            "existing-unit/baseline.md": expected_tracked_hash,
            "missing.md": "0" * 64,
        },
        approved_hashes=set(),
    )

    assert any("existing-unit/baseline.md" in violation and "expected" in violation for violation in violations)
    assert any("missing.md" in violation and "missing" in violation for violation in violations)
    assert any("new-unit/baseline.md" in violation and "not listed" in violation for violation in violations)
    assert not any("draft-unit/baseline.md" in violation for violation in violations)


def test_gateway_hash_lock_exemption_allows_only_exact_file_and_hash(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "graph-agent-gateway" / "mvp1"
    docs_root.mkdir(parents=True)
    doc_path = docs_root / "unit" / "baseline.md"
    doc_path.parent.mkdir()
    doc_path.write_text("---\nstatus: FROZEN\n---\naudited baseline\n", encoding="utf-8")
    expected_hash = _sha256(doc_path)

    doc_path.write_text("---\nstatus: FROZEN\n---\nowner approved drift\n", encoding="utf-8")
    approved_hash = _sha256(doc_path)
    assert (
        _collect_hash_lock_violations(
            docs_root=docs_root,
            expected_hashes={"unit/baseline.md": expected_hash},
            approved_hashes={("unit/baseline.md", approved_hash)},
        )
        == []
    )

    doc_path.write_text("---\nstatus: FROZEN\n---\nsecond silent drift\n", encoding="utf-8")
    violations = _collect_hash_lock_violations(
        docs_root=docs_root,
        expected_hashes={"unit/baseline.md": expected_hash},
        approved_hashes={("unit/baseline.md", approved_hash)},
    )
    assert any("unit/baseline.md" in violation and "expected" in violation for violation in violations)


def test_gateway_design_unit_snapshot_reports_locked_unit_drift_and_allows_new_drafts() -> None:
    snapshot_records = {
        "existing-locked": DesignUnitLockRecord(
            unit="existing-locked",
            owned_lock="locked",
            external_binding="none",
            integration_lock="locked",
            owners=["alpha"],
            external_refs=[],
        )
    }
    current_records = [
        DesignUnitLockRecord(
            unit="existing-locked",
            owned_lock="locked",
            external_binding="none",
            integration_lock="locked",
            owners=["beta"],
            external_refs=[],
        ),
        DesignUnitLockRecord(
            unit="new-draft",
            owned_lock="drafted",
            external_binding="none",
            integration_lock="unverified",
            owners=[],
            external_refs=[],
        ),
        DesignUnitLockRecord(
            unit="new-locked",
            owned_lock="locked",
            external_binding="none",
            integration_lock="locked",
            owners=["gamma"],
            external_refs=[],
        ),
    ]

    violations = _collect_snapshot_violations(
        current_records=current_records,
        snapshot_records=snapshot_records,
        exempt_units=set(),
    )

    assert any("existing-locked" in violation and "owners" in violation for violation in violations)
    assert not any("new-draft" in violation for violation in violations)
    assert any("new-locked" in violation and "absent" in violation for violation in violations)


def test_gateway_frozen_doc_hashes_match_snapshot_or_exemption() -> None:
    expected_hashes = _load_expected_hashes()
    approved_hashes, _ = _load_exemptions()

    violations = _collect_hash_lock_violations(
        docs_root=DOCS_ROOT,
        expected_hashes=expected_hashes,
        approved_hashes=approved_hashes,
    )

    assert not violations, "Unapproved gateway doc hash drift:\n" + "\n".join(violations)


def test_gateway_design_unit_lock_snapshot_matches_current_index() -> None:
    snapshot = _load_snapshot()
    current_records = _canonicalize_design_units(DOCS_ROOT / "DESIGN_UNITS_INDEX.md")
    snapshot_records = _snapshot_units(snapshot)
    _, exempt_units = _load_exemptions()

    violations = _collect_snapshot_violations(
        current_records=current_records,
        snapshot_records=snapshot_records,
        exempt_units=exempt_units,
    )

    assert not violations, "Unapproved gateway design unit lock drift:\n" + "\n".join(violations)
