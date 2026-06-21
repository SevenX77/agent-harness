from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

BACKEND_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "app").is_dir() and (parent / "tests").is_dir()
)

SDK_PREFIXES = ("graph_agent", "graph_agent_gateway")
SDK_IMPORT_ALLOWLIST = {
    "app/core/adapters/engine.py": {
        "owner": "studio-platform",
        "reason": "EngineAdapter is the Studio boundary for Engine SDK calls",
        "risk": "Engine SDK concrete types can leak past the adapter port",
        "expiry": "replace SDK concrete DTO reuse with Studio-owned port DTOs before Wave 3 runtime expansion",
        "gate": "test_studio_business_layer_does_not_import_sdk_internals_directly",
    },
    "app/core/adapters/gateway.py": {
        "owner": "studio-platform",
        "reason": "GatewayAdapter is the Studio boundary for Gateway SDK calls",
        "risk": "Gateway SDK concrete types can leak past the adapter port",
        "expiry": "replace SDK concrete DTO reuse with Studio-owned port DTOs before Wave 3 runtime expansion",
        "gate": "test_studio_business_layer_does_not_import_sdk_internals_directly",
    },
    "app/core/adapters/gateway_config_store_local.py": {
        "owner": "studio-platform",
        "reason": "local config truth store implements the Gateway storage contract",
        "risk": "Gateway storage contract types can spread into Studio business services",
        "expiry": "replace direct contract imports with a Studio-owned config port when config persistence moves out of local storage",
        "gate": "test_studio_business_layer_does_not_import_sdk_internals_directly",
    },
    "app/core/adapters/run_artifact_store_local.py": {
        "owner": "studio-platform",
        "reason": "local run artifact store implements the Engine artifact storage contract",
        "risk": "Engine storage contract types can spread into Studio business services",
        "expiry": "remove per-file entries when DTO ports no longer need SDK concrete imports",
        "gate": "test_studio_business_layer_does_not_import_sdk_internals_directly",
    },
    "app/core/adapters/runtime_state_resume_bridge.py": {
        "owner": "studio-platform",
        "reason": "runtime resume bridge is the narrow adapter boundary for Engine resume_skill",
        "risk": "Engine runtime calls can leak into Studio resume business logic",
        "expiry": "replace with an Engine-owned resume artifact API before Wave 3 resume expansion",
        "gate": "test_studio_business_layer_does_not_import_sdk_internals_directly",
    },
    "app/core/adapters/runtime_state_store_local.py": {
        "owner": "studio-platform",
        "reason": "local runtime state store restores Engine checkpointer state",
        "risk": "Engine checkpointer contracts can leak into Studio runtime state services",
        "expiry": "replace with an Engine-owned runtime state port before Wave 3 resume expansion",
        "gate": "test_studio_business_layer_does_not_import_sdk_internals_directly",
    },
    "app/models/llm_config.py": {
        "owner": "studio-settings",
        "reason": "temporary DTO mirror of Gateway registry schema for Settings API compatibility",
        "risk": "Gateway schema concrete types can leak from DTOs into business logic",
        "expiry": "replace with Studio-owned DTOs before Wave 3 runtime settings expansion",
        "gate": "test_studio_business_layer_does_not_import_sdk_internals_directly",
    },
    "app/models/runs.py": {
        "owner": "studio-runs",
        "reason": "temporary response DTO reuse for Engine run trace records",
        "risk": "Engine trace concrete types can become business-layer dependencies",
        "expiry": "replace with Studio-owned run DTOs before Wave 3 trace UI expansion",
        "gate": "test_studio_business_layer_does_not_import_sdk_internals_directly",
    },
    "app/models/skills.py": {
        "owner": "studio-skills",
        "reason": "temporary response DTO reuse for Engine manifest metadata",
        "risk": "Engine manifest concrete types can become authoring-layer dependencies",
        "expiry": "replace with Studio-owned skill manifest DTOs before Wave 3 graph authoring expansion",
        "gate": "test_studio_business_layer_does_not_import_sdk_internals_directly",
    },
    "app/core/exceptions.py": {
        "owner": "studio-platform",
        "reason": "temporary compatibility mapping for Engine compile exception type",
        "risk": "business callers may catch Engine exceptions directly instead of Studio errors",
        "expiry": "replace with Studio-owned exception mapping before Wave 3 compile API expansion",
        "gate": "test_studio_business_layer_does_not_import_sdk_internals_directly",
    },
    "app/services/llm_credentials.py": {
        "owner": "studio-settings",
        "reason": "reuses the gateway's canonical stable-ID helpers (route_slug/stable_endpoint_id) so Studio-persisted endpoint/route IDs are byte-identical to the gateway's; reimplementing the ID algorithm in Studio would risk silent ID drift and broken route resolution",
        "risk": "a gateway ID-helper signature/algorithm change would silently shift Studio-persisted IDs",
        "expiry": "expose the stable-ID helpers through a Studio-owned config port before Wave 3 runtime settings expansion",
        "gate": "test_studio_business_layer_does_not_import_sdk_internals_directly",
    },
    "app/services/llm_stable_id_migration.py": {
        "owner": "studio-settings",
        "reason": "one-shot migration rewriting legacy credentials to the gateway's stable IDs; needs route_identity (canonical ID helpers) and ImportDraftStore to re-key evidence stored under the old IDs",
        "risk": "gateway stable-ID or import-draft-store contract changes would break the migration path",
        "expiry": "retire once all installs are migrated off legacy IDs and this module is removed",
        "gate": "test_studio_business_layer_does_not_import_sdk_internals_directly",
    },
}


def test_studio_business_layer_does_not_import_sdk_internals_directly() -> None:
    offenders: list[str] = []

    for path in _production_files():
        for module in _imported_modules(path):
            if module in SDK_PREFIXES or module.startswith(tuple(f"{prefix}." for prefix in SDK_PREFIXES)):
                rel = path.relative_to(BACKEND_ROOT)
                if not _is_allowed_sdk_import(rel):
                    offenders.append(f"{rel} imports {module}")

    assert offenders == []


def test_boundary_guard_auto_discovers_all_production_modules() -> None:
    scanned_paths = {path.relative_to(BACKEND_ROOT) for path in _production_files()}

    assert Path("app/services/run_manager.py") in scanned_paths
    assert Path("app/routers/runs.py") in scanned_paths
    assert Path("app/models/runs.py") in scanned_paths
    assert Path("app/core/adapters/engine.py") in scanned_paths
    assert all(path.parts[0] == "app" for path in scanned_paths)


def test_sdk_import_allowlist_entries_have_owner_reason_risk_expiry_and_gate() -> None:
    required = {"owner", "reason", "risk", "expiry", "gate"}
    missing: list[str] = []
    for entry, metadata in SDK_IMPORT_ALLOWLIST.items():
        absent = sorted(field for field in required if not str(metadata.get(field) or "").strip())
        if absent:
            missing.append(f"{entry}: {absent}")

    assert missing == []


def test_sdk_import_allowlist_does_not_grant_directory_wide_adapter_escape() -> None:
    assert not _is_allowed_sdk_import(Path("app/core/adapters/unreviewed_sdk_escape.py"))


def test_boundary_guard_recurses_within_configured_business_packages(tmp_path: Path) -> None:
    package_dir = tmp_path / "services"
    nested_file = package_dir / "nested" / "flow.py"
    nested_file.parent.mkdir(parents=True)
    nested_file.write_text("from __future__ import annotations\n", encoding="utf-8")

    scanned_paths = set(_production_files((package_dir,)))

    assert nested_file in scanned_paths


def test_gateway_owner_boundary_rules_are_not_implemented_in_studio_adapter() -> None:
    gateway_path = BACKEND_ROOT / "app" / "core" / "adapters" / "gateway.py"
    tree = ast.parse(gateway_path.read_text(encoding="utf-8"), filename=str(gateway_path))
    gateway_class = _class_def(tree, "GatewayAdapter")

    private_owner_helpers = {
        "_private_apply_intent",
        "_private_apply_output_token_intent",
        "_private_enable_reasoning",
        "_private_max_output_tokens",
    }
    defined_methods = {node.name for node in gateway_class.body if isinstance(node, ast.FunctionDef)}
    assert defined_methods.isdisjoint(private_owner_helpers)

    materialize_role = _method_def(gateway_class, "materialize_role")
    materialize_tokens = _node_tokens(materialize_role)
    assert materialize_tokens.isdisjoint(
        {
            "_private_apply_intent",
            "_private_apply_output_token_intent",
            "_private_enable_reasoning",
            "_private_max_output_tokens",
            "role_fit",
            "thinking_unsupported",
            "thinking_capability_unknown",
            "thinking_not_enabled",
            "token_cap_blocked",
            "token_downgraded",
        }
    )
    assert "gateway_materialize_role" in materialize_tokens

    decide_fallback = _method_def(gateway_class, "decide_fallback")
    fallback_tokens = _node_tokens(decide_fallback)
    assert "gateway_decide_fallback" in fallback_tokens
    assert "gateway.fallback_exhausted" not in fallback_tokens
    assert not _contains_retry_status_set(decide_fallback)


def _production_files(package_dirs: Iterable[Path] | None = None) -> list[Path]:
    roots = tuple(package_dirs or (BACKEND_ROOT / "app",))
    return sorted(
        path
        for root in roots
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _is_allowed_sdk_import(path: Path) -> bool:
    return path.as_posix() in SDK_IMPORT_ALLOWLIST


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _class_def(tree: ast.AST, class_name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(f"{class_name} class not found")


def _method_def(class_node: ast.ClassDef, method_name: str) -> ast.FunctionDef:
    for node in class_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node
    raise AssertionError(f"{class_node.name}.{method_name} method not found")


def _node_tokens(node: ast.AST) -> set[str]:
    tokens: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            tokens.add(child.id)
        elif isinstance(child, ast.Attribute):
            tokens.add(child.attr)
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            tokens.add(child.value)
    return tokens


def _contains_retry_status_set(node: ast.AST) -> bool:
    retry_statuses = {429, 500, 502, 503, 504, 529}
    for child in ast.walk(node):
        if isinstance(child, ast.Set):
            values = {
                element.value
                for element in child.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, int)
            }
            if retry_statuses.issubset(values):
                return True
    return False
