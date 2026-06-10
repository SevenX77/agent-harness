from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

from graph_agent.core.exceptions import ErrorPayload, GraphAgentError
from graph_agent.core.result import RunResult

REPO_ROOT = Path(__file__).resolve().parents[4]
ERROR_SPEC = (
    REPO_ROOT
    / "docs"
    / "engine"
    / "mvp1"
    / "01-contract"
    / "03-compile-rules"
    / "mvp1-alignment.md"
)

P0_2_METADATA_FIELDS = {
    "remediation",
    "doc_ref",
    "doc_url",
    "details_schema",
    "schema_version",
    "status",
}

CATALOG_ITEM_FIELDS = {
    "code",
    "level",
    "stage",
    "domain",
    "remediation",
    "doc_ref",
    "doc_url",
    "status",
    "details_schema",
    "schema_version",
}


def _registry_module() -> Any:
    return importlib.import_module("graph_agent.core.error_registry")


def _spec_codes() -> set[str]:
    text = ERROR_SPEC.read_text(encoding="utf-8")
    section_start = "## 4. 错误码全表(96)"
    section_end = "\n## 5."
    assert section_start in text, "mvp1 compile-rules must keep a bounded 96-code table section"
    section = text.split(section_start, 1)[1].split(section_end, 1)[0]
    return set(re.findall(r"\[F-v3-[a-z0-9-]+\]", section))


def _assert_https_url(value: str) -> None:
    parsed = urlparse(value)
    assert parsed.scheme == "https"
    assert parsed.netloc


def test_error_registry_metadata_exposes_p0_2_fields_for_every_existing_code() -> None:
    registry_module = _registry_module()
    registry = registry_module.ERROR_REGISTRY

    assert set(registry) == _spec_codes()
    assert len(registry) == 96

    for code, metadata in registry.items():
        missing_fields = sorted(field for field in P0_2_METADATA_FIELDS if not hasattr(metadata, field))
        assert missing_fields == [], f"{code} missing P0-2 metadata fields: {missing_fields}"

        assert metadata.code == code
        assert metadata.level in {"FATAL", "WARN"}
        assert metadata.stage
        assert metadata.doc_link
        assert isinstance(metadata.remediation, str) and metadata.remediation.strip()
        assert metadata.doc_ref.startswith("graph-agent://errors/")
        assert code.strip("[]") in metadata.doc_ref or code in metadata.doc_ref
        _assert_https_url(metadata.doc_url)
        assert isinstance(metadata.details_schema, dict)
        assert metadata.details_schema.get("type") == "object"
        assert isinstance(metadata.schema_version, str) and metadata.schema_version
        assert metadata.status == "active"
        json.dumps(
            {
                "code": metadata.code,
                "level": metadata.level,
                "stage": metadata.stage,
                "doc_link": metadata.doc_link,
                "remediation": metadata.remediation,
                "doc_ref": metadata.doc_ref,
                "doc_url": metadata.doc_url,
                "details_schema": metadata.details_schema,
                "schema_version": metadata.schema_version,
                "status": metadata.status,
            },
            sort_keys=True,
        )


def test_error_catalog_export_envelope_is_json_safe_versioned_and_stably_sorted() -> None:
    registry_module = _registry_module()

    assert hasattr(registry_module, "export_error_catalog")
    catalog = registry_module.export_error_catalog()

    dumped = json.loads(json.dumps(catalog, sort_keys=True))
    assert isinstance(dumped["registry_version"], str) and dumped["registry_version"]
    assert isinstance(dumped["schema_version"], str) and dumped["schema_version"]
    assert isinstance(dumped["items"], list)

    items = dumped["items"]
    assert [item["code"] for item in items] == sorted(_spec_codes())
    assert len(items) == 96

    for item in items:
        assert CATALOG_ITEM_FIELDS <= set(item)
        assert item["code"] in _spec_codes()
        assert item["level"] in {"FATAL", "WARN"}
        assert isinstance(item["stage"], list) and item["stage"]
        assert isinstance(item["domain"], str) and item["domain"]
        assert isinstance(item["remediation"], str) and item["remediation"].strip()
        assert item["doc_ref"].startswith("graph-agent://errors/")
        _assert_https_url(item["doc_url"])
        assert item["status"] == "active"
        assert isinstance(item["details_schema"], dict)
        assert item["details_schema"].get("type") == "object"
        assert isinstance(item["schema_version"], str) and item["schema_version"]


def test_error_catalog_single_code_export_rejects_unknown_without_claiming_gateway_codes() -> None:
    registry_module = _registry_module()

    assert hasattr(registry_module, "export_error_metadata")
    export_error_metadata = registry_module.export_error_metadata

    item = export_error_metadata("[F-v3-graph-phase-cycle]")
    assert CATALOG_ITEM_FIELDS <= set(item)
    assert item["code"] == "[F-v3-graph-phase-cycle]"

    with pytest.raises(ValueError, match="unknown graph_agent error code"):
        export_error_metadata("[F-v3-not-in-spec]")

    exc = GraphAgentError(
        "[F-v3-gateway-provider-timeout] upstream failed",
        context={"provider": "test"},
    )
    assert exc.payload is None
    assert exc.context == {"provider": "test"}


def test_registry_p0_2_does_not_change_p0_1_payload_details_or_run_diagnostics(tmp_path: Path) -> None:
    payload = ErrorPayload(
        code="[F-v3-runtime-state-mapping-failed]",
        message="bad state",
        details={"path": tmp_path / "state.json"},
    )

    result = RunResult(
        success=False,
        run_id="run-1",
        skill_id="skill-1",
        error=payload,
    )

    dumped = json.loads(result.model_dump_json())
    assert dumped["error"]["details"] == {"path": str(tmp_path / "state.json")}
    assert dumped["diagnostics"][0]["code"] == "[F-v3-runtime-state-mapping-failed]"
    assert dumped["diagnostics"][0]["details"] == {"path": str(tmp_path / "state.json")}
    assert dumped["diagnostic_counts"] == {
        "total": 1,
        "by_level": {"FATAL": 1},
        "by_code": {"[F-v3-runtime-state-mapping-failed]": 1},
    }
