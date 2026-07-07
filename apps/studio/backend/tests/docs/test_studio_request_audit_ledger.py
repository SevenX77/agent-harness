from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
AUDIT_DOC = REPO_ROOT / "docs" / "development" / "STUDIO_REQUEST_AUDIT.md"
BACKEND_ROUTERS = REPO_ROOT / "apps" / "studio" / "backend" / "app" / "routers"
FRONTEND_SRC = REPO_ROOT / "apps" / "studio" / "frontend" / "src"

HTTP_METHODS = {"get", "post", "put", "delete", "patch"}
API_CALL_RE = re.compile(
    r"\bapi\.(get|post|put|delete|patch)(?:<[^>]+>)?\(\s*([`'\"])(.*?)\2",
    re.DOTALL,
)
WS_URL_RE = re.compile(r"\bwsUrl\(\s*([`'\"])(.*?)\1", re.DOTALL)
SWR_DIRECT_KEY_RE = re.compile(
    r"\buseSWR(?:<[^>]+>)?\(\s*([`'\"])(.*?)\1\s*,\s*fetcher\b",
    re.DOTALL,
)
SWR_TERNARY_KEY_RE = re.compile(
    r"\buseSWR(?:<[^>]+>)?\(\s*[^,]*?\?\s*([`'\"])(.*?)\1\s*:\s*null\s*,\s*fetcher\b",
    re.DOTALL,
)
LEDGER_RE = re.compile(r"```studio-request-audit-ledger\n(?P<body>.*?)\n```", re.DOTALL)
VERDICTS_RE = re.compile(r"```studio-request-audit-verdicts\n(?P<body>.*?)\n```", re.DOTALL)
TEMPLATE_EXPR_RE = re.compile(r"\$\{([^}]+)\}")
VERDICT_STATUSES = {"ok", "partial", "bad", "internal", "review"}
VerdictRow = tuple[str, str, str, str]


def _join_paths(prefix: str, path: str) -> str:
    combined = f"{prefix.rstrip('/')}/{path.lstrip('/')}" if path else prefix
    normalized = re.sub(r"/+", "/", combined)
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _string_constant(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _router_prefixes(tree: ast.Module) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Name) or call.func.id != "APIRouter":
            continue
        prefix = ""
        for keyword in call.keywords:
            if keyword.arg == "prefix":
                prefix = _string_constant(keyword.value) or ""
                break
        for target in node.targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix
    return prefixes


def _backend_route_keys() -> set[str]:
    keys: set[str] = set()
    for path in sorted(BACKEND_ROUTERS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        prefixes = _router_prefixes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                method = decorator.func.attr
                if method not in HTTP_METHODS and method != "websocket":
                    continue
                router_ref = decorator.func.value
                if not isinstance(router_ref, ast.Name) or router_ref.id not in prefixes:
                    continue
                route_path = _string_constant(decorator.args[0]) if decorator.args else ""
                if route_path is None:
                    continue
                verb = "WS" if method == "websocket" else method.upper()
                keys.add(f"BACKEND {verb} {_join_paths(prefixes[router_ref.id], route_path)}")
    return keys


def _template_placeholder(expr: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", expr.lower())
    if "filepath" in normalized or "encodedpath" in normalized:
        return "{file_path:path}"
    if "sourceid" in normalized:
        return "{source_id}"
    if "releaseversion" in normalized:
        return "{release_version}"
    if "comparegroupid" in normalized:
        return "{compare_group_id}"
    if "baserunid" in normalized:
        return "{base_run_id}"
    if "goldenid" in normalized:
        return "{golden_id}"
    if "inputid" in normalized or "selectedtestinputid" in normalized:
        return "{input_id}"
    if "nodeid" in normalized:
        return "{node_id}"
    if "endpointid" in normalized or "providerid" in normalized or "requestid" in normalized:
        return "{endpoint_id}"
    if "routeid" in normalized:
        return "{route_id}"
    if "rolename" in normalized:
        return "{role_name}"
    if "bundleid" in normalized:
        return "{bundle_id}"
    if "jobid" in normalized:
        return "{job_id}"
    if "runid" in normalized:
        return "{run_id}"
    if "skill" in normalized or "apiskillid" in normalized:
        return "{skill_id}"
    return "{param}"


def _normalize_frontend_path(raw: str) -> str:
    without_query = raw.replace("${query}", "").replace("${forceQuery}", "").split("?", 1)[0]
    replaced = TEMPLATE_EXPR_RE.sub(lambda match: _template_placeholder(match.group(1)), without_query)
    normalized = re.sub(r"/+", "/", replaced)
    if normalized.startswith("/api/") or normalized.startswith("/ws/") or normalized in {"/health"}:
        return normalized
    return f"/api{normalized}" if normalized.startswith("/") else f"/api/{normalized}"


def _frontend_route_keys() -> set[str]:
    keys: set[str] = set()
    for path in sorted(FRONTEND_SRC.rglob("*")):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        if ".test." in path.name or "testing" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in API_CALL_RE.finditer(text):
            keys.add(f"FRONTEND {match.group(1).upper()} {_normalize_frontend_path(match.group(3))}")
        for pattern in (SWR_DIRECT_KEY_RE, SWR_TERNARY_KEY_RE):
            for match in pattern.finditer(text):
                keys.add(f"FRONTEND GET {_normalize_frontend_path(match.group(2))}")
        for match in WS_URL_RE.finditer(text):
            keys.add(f"FRONTEND WS {_normalize_frontend_path(match.group(2))}")
    return keys


def _ledger_keys() -> set[str]:
    text = AUDIT_DOC.read_text(encoding="utf-8")
    match = LEDGER_RE.search(text)
    assert match is not None, "STUDIO_REQUEST_AUDIT.md must contain a studio-request-audit-ledger code fence."
    return {
        line.strip()
        for line in match.group("body").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def _verdict_rows() -> list[VerdictRow]:
    text = AUDIT_DOC.read_text(encoding="utf-8")
    match = VERDICTS_RE.search(text)
    assert match is not None, "STUDIO_REQUEST_AUDIT.md must contain a studio-request-audit-verdicts code fence."

    verdicts: list[VerdictRow] = []
    invalid: list[str] = []
    for line_number, raw_line in enumerate(match.group("body").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 4:
            invalid.append(f"line {line_number}: expected 4 pipe-delimited fields")
            continue
        key, status, guard, rationale = parts
        if status not in VERDICT_STATUSES:
            invalid.append(f"line {line_number}: invalid status {status!r}")
        if guard not in {"shared", "specific", "none"}:
            invalid.append(f"line {line_number}: invalid guard {guard!r}")
        if not rationale:
            invalid.append(f"line {line_number}: rationale is required")
        verdicts.append((key, status, guard, rationale))
    assert not invalid, "Invalid studio-request-audit-verdicts rows:\n" + "\n".join(invalid)
    return verdicts


def _verdict_keys() -> set[str]:
    return {key for key, _status, _guard, _rationale in _verdict_rows()}


def test_studio_request_audit_ledger_covers_current_backend_and_frontend_requests() -> None:
    inventory = _backend_route_keys() | _frontend_route_keys()
    ledger = _ledger_keys()

    missing = sorted(inventory - ledger)
    stale = sorted(ledger - inventory)
    assert not missing, (
        "Every Studio backend route and frontend request must be listed in "
        "docs/development/STUDIO_REQUEST_AUDIT.md's studio-request-audit-ledger block. Missing:\n"
        + "\n".join(missing)
    )
    assert not stale, (
        "docs/development/STUDIO_REQUEST_AUDIT.md's studio-request-audit-ledger block must not "
        "keep stale request keys. Stale:\n" + "\n".join(stale)
    )


def test_studio_request_audit_verdicts_cover_current_backend_and_frontend_requests() -> None:
    inventory = _backend_route_keys() | _frontend_route_keys()
    verdicts = _verdict_keys()

    missing = sorted(inventory - verdicts)
    stale = sorted(verdicts - inventory)
    assert not missing, (
        "Every Studio backend route and frontend request must have a request-policy verdict in "
        "docs/development/STUDIO_REQUEST_AUDIT.md's studio-request-audit-verdicts block. Missing:\n"
        + "\n".join(missing)
    )
    assert not stale, (
        "docs/development/STUDIO_REQUEST_AUDIT.md's studio-request-audit-verdicts block must not "
        "keep stale request keys. Stale:\n" + "\n".join(stale)
    )


def test_frontend_request_policy_verdicts_are_resolved() -> None:
    unresolved = [
        f"{key} | {status} | {rationale}"
        for key, status, _guard, rationale in _verdict_rows()
        if key.startswith("FRONTEND ") and status == "review"
    ]

    assert not unresolved, (
        "Frontend requests are user-visible performance surfaces and must not remain "
        "at the placeholder 'review' verdict. Classify each as ok/partial/bad/internal "
        "with its trigger and guard-test rationale:\n" + "\n".join(unresolved)
    )


def test_backend_request_policy_verdicts_are_resolved() -> None:
    unresolved = [
        f"{key} | {status} | {rationale}"
        for key, status, _guard, rationale in _verdict_rows()
        if key.startswith("BACKEND ") and status == "review"
    ]

    assert not unresolved, (
        "Backend routes define the server-owned request surface and must not remain "
        "at the placeholder 'review' verdict. Classify each as ok/partial/bad/internal "
        "with its trigger, canonical response, and event rationale:\n" + "\n".join(unresolved)
    )
