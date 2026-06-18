from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "app").is_dir() and (parent / "tests").is_dir()
)


def _string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            part = _string_value(value)
            if part is None:
                return None
            parts.append(part)
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_value(node.left)
        right = _string_value(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
        if len(node.args) >= 2:
            return _string_value(node.args[1])
    return None


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"missing function: {name}")


def test_publish_endpoint_writes_product_artifact_release_instead_of_zipping_source() -> None:
    source = (BACKEND_ROOT / "app" / "routers" / "skills.py").read_text(encoding="utf-8")

    assert "ProductArtifactStore" in source
    assert "PublishArtifactRequest" in source
    assert "build_publish_package" not in source
    assert '"build_publish_" + "package"' not in source
    assert "sv_registry" not in source
    assert "package_bytes" not in source
    assert "package_kind" in source
    assert "product_artifact" in source


def test_publish_route_never_builds_or_uploads_package_bytes_even_via_dynamic_names() -> None:
    source = (BACKEND_ROOT / "app" / "routers" / "skills.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    publish_skill = _function(tree, "publish_skill")

    forbidden_strings: list[str] = []
    forbidden_calls: list[str] = []
    for node in ast.walk(publish_skill):
        value = _string_value(node)
        if value in {"build_publish_package", "package_bytes"}:
            forbidden_strings.append(value)
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in {"build_publish_package", "upload_artifact", "ZipFile", "write_bytes"}:
                forbidden_calls.append(name)
        if isinstance(node, ast.Attribute) and node.attr == "package_bytes":
            forbidden_strings.append("package_bytes")

    assert forbidden_strings == []
    assert forbidden_calls == []


def test_skills_service_never_exposes_publish_package_bytes_or_dynamic_package_builder() -> None:
    source = (BACKEND_ROOT / "app" / "services" / "skills.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden: list[str] = []
    for node in ast.walk(tree):
        value = _string_value(node)
        if value in {"build_publish_package", "package_bytes"}:
            forbidden.append(value)
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in {"build_publish_package", "upload_artifact", "ZipFile"}:
                forbidden.append(name)

    assert forbidden == []


def test_artifact_registry_does_not_build_local_publish_packages() -> None:
    source = (BACKEND_ROOT / "app" / "services" / "artifact_registry.py").read_text(
        encoding="utf-8"
    )

    assert "build_publish_package" not in source
    assert '"build_publish_" + "package"' not in source
    assert "zipfile" not in source
    assert "ZipFile" not in source
    assert "package_bytes" not in source


def test_artifact_registry_release_sync_does_not_upload_product_blob_bytes() -> None:
    source = (BACKEND_ROOT / "app" / "services" / "artifact_registry.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    sync_release = _function(tree, "sync_product_artifact_release")

    forbidden_calls: list[str] = []
    for node in ast.walk(sync_release):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in {"upload_artifact", "build_publish_package", "ZipFile"}:
                forbidden_calls.append(name)

    assert forbidden_calls == []
