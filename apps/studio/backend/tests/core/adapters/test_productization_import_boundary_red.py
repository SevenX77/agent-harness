from __future__ import annotations

import ast
import sys
import tomllib
from collections.abc import Iterable
from importlib.metadata import packages_distributions
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
    "app/core/adapters/media_gateway.py": {
        "owner": "studio-settings",
        "reason": "media_gateway is the Studio boundary for the Gateway media generation domain (catalog/schema/probe)",
        "risk": "Gateway media SDK concrete types can leak past the adapter into Studio business services",
        "expiry": "replace SDK concrete DTO reuse with Studio-owned media port DTOs when media-invocation-runtime lands",
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
    "app/core/adapters/run_layout.py": {
        "owner": "studio-platform",
        "reason": "run/predict directory names are Engine-owned; this re-exports them so no Studio service imports the SDK for a path",
        "risk": "an Engine layout change reaches Studio through this one file instead of being caught at a port",
        "expiry": "remove when run artifacts are addressed through an Engine-owned storage port instead of filesystem paths",
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


def test_the_backend_declares_every_sdk_it_imports() -> None:
    """A dependency you use but never name is one somebody else can take away.

    The backend imports both SDKs (through the adapters allowlisted above) and
    named only ``graph-agent`` — the gateway arrived as a transitive gift from
    the engine, which held only while the engine kept declaring a package its
    own tests forbid it to import.
    """
    imported = {
        prefix
        for path in _production_files()
        for module in _imported_modules(path)
        for prefix in SDK_PREFIXES
        if module == prefix or module.startswith(f"{prefix}.")
    }
    declared = _declared_distributions(BACKEND_ROOT / "pyproject.toml")

    undeclared = sorted(prefix for prefix in imported if prefix.replace("_", "-") not in declared)
    assert undeclared == []


def test_the_locked_closure_covers_every_gateway_lazy_import() -> None:
    """The desktop app must be able to import everything the gateway it bundles can.

    The gateway keeps provider clients behind lazy imports and ships them in
    optional extras. The backend declared `graph-agent-gateway` with NO extras, so
    the vendored dependency closure — `uv export --package studio-backend`, see
    `apps/studio/backend/scripts/build_vendor.py` — simply did not contain
    `langchain-google-genai`, and every gemini route in the packaged app died on
    ImportError while the dev tree (synced with `--all-extras`) looked fine.

    The assertion is therefore about the CLOSURE, not about a manifest field: for
    every module the gateway can lazily import, the distribution providing it must
    be reachable from `studio-backend` in `uv.lock` — the same graph
    `uv export --package studio-backend` walks, rather than a declaration that has
    not been resolved yet.

    Both ends are resolved rather than guessed: the module names come from the AST
    of the gateway's own `importlib.import_module("...")` calls, and module →
    distribution comes from installed metadata, because an import name is not a
    package name (`google-genai` provides `google`, `PyYAML` provides `yaml`). A
    module nothing installed provides is reported, not skipped.

    Scope is deliberately "everything the bundled gateway can lazily import",
    which is wider than "the protocols Studio exposes today": a provider path
    present in the shipped SDK that raises ImportError when a user picks it is a
    defect either way, and this version of the rule needs no hand-kept list of
    which routes count.

    What it does NOT catch, so nobody reads more into a green run than it earns:

    * a stale COMMITTED lock. CI runs `uv sync` before pytest and `build_vendor`'s
      export is not `--locked`, so both silently refresh an out-of-date lock in the
      workspace. This reads whatever lock is on disk by then.
    * a dependency edge whose environment marker excludes the target platform or
      Python version — markers are not evaluated here.
    * a top-level name shared by several distributions (namespace packages such as
      `google.*`): finding ANY of its providers in the closure is accepted, which
      does not prove the specific submodule ships. No lazy import in the gateway is
      a namespace package today.
    * a lock with two nodes of the same distribution name; the walk keys on name,
      so it would follow one of them.
    * a dynamic import whose argument is not a literal string.
    """
    gateway_root = BACKEND_ROOT.parents[2] / "packages" / "graph-agent-gateway"
    lazy_modules = _lazily_imported_modules(gateway_root / "src")
    assert lazy_modules, "no literal `importlib.import_module` call found in the gateway source"

    closure = _locked_closure(BACKEND_ROOT.parents[2] / "uv.lock", "studio-backend")
    module_owners = packages_distributions()

    unreachable: list[str] = []
    for module in sorted(lazy_modules):
        top_level = module.split(".", 1)[0]
        providers = module_owners.get(top_level)
        if not providers:
            # Not installed here at all. The dev tree syncs `--all-extras`, so this
            # is a typo or a dependency nobody declared — never a thing to skip.
            unreachable.append(f"{module}: nothing installed provides {top_level!r}")
            continue
        if not any(_normalize_distribution(name) in closure for name in providers):
            unreachable.append(
                f"{module}: provided by {sorted(providers)}, none of them in the closure"
            )

    assert unreachable == []


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


def _declared_distributions(manifest: Path) -> set[str]:
    project = tomllib.loads(manifest.read_text(encoding="utf-8"))["project"]
    requirements: list[str] = list(project.get("dependencies") or [])
    for extra in (project.get("optional-dependencies") or {}).values():
        requirements.extend(extra)
    return {_distribution_name(requirement) for requirement in requirements}


def _lazily_imported_modules(source_root: Path) -> set[str]:
    """Third-party module names passed as literals to `importlib.import_module`.

    A lazy import is how a package says "this path only works if something else
    is installed", so these are exactly the names whose absence turns a feature
    into an ImportError at run time.

    Only `importlib.import_module(...)` counts — matching a bare `import_module`
    attribute on anything at all would pick up an unrelated local helper that
    happens to share the name. Standard-library targets and relative imports are
    dropped because no distribution ships them, so demanding one would be a false
    alarm rather than a finding.
    """
    modules: set[str] = set()
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            if not isinstance(target, ast.Attribute) or target.attr != "import_module":
                continue
            if not isinstance(target.value, ast.Name) or target.value.id != "importlib":
                continue
            if not node.args:
                continue
            first = node.args[0]
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                continue
            module = first.value
            if module.startswith(".") or module.split(".", 1)[0] in sys.stdlib_module_names:
                continue
            modules.add(module)
    return modules


def _locked_closure(lock_path: Path, root: str) -> set[str]:
    """Distributions reachable from `root` in a uv lock, extras followed as requested.

    This is the set an export of `root` installs: a dependency edge may carry
    `extra = [...]`, which pulls that package's matching `optional-dependencies`
    group and nothing else from it. Dev groups are not walked, so the result is a
    subset of what the vendor build installs — enough to prove a distribution IS
    present, which is the direction this gate needs.
    """
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = {package["name"]: package for package in lock.get("package") or []}
    reached: set[str] = set()
    visited: set[tuple[str, frozenset[str]]] = set()
    pending: list[tuple[str, frozenset[str]]] = [(root, frozenset())]
    while pending:
        name, extras = pending.pop()
        if (name, extras) in visited:
            continue
        visited.add((name, extras))
        reached.add(_normalize_distribution(name))
        package = packages.get(name)
        if package is None:
            continue
        requirements = list(package.get("dependencies") or [])
        optional = package.get("optional-dependencies") or {}
        for extra in extras:
            requirements.extend(optional.get(extra) or [])
        for requirement in requirements:
            pending.append((requirement["name"], frozenset(requirement.get("extra") or ())))
    return reached


def _normalize_distribution(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _distribution_name(requirement: str) -> str:
    name = requirement.strip()
    for separator in ("[", "<", ">", "=", "!", "~", ";", " "):
        name = name.split(separator, 1)[0]
    return name.strip().lower().replace("_", "-")


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
