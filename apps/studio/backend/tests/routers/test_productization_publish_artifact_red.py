from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

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


def test_engine_compile_does_not_zip_live_skill_dir_for_product_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.adapters.engine as engine_module
    import graph_agent.core.artifacts as artifacts_module
    from app.core.adapters.engine import EngineAdapter

    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "GRAPH.md").write_text("phases: []\n", encoding="utf-8")

    def compile_without_source_archive(**_kwargs: object) -> object:
        return SimpleNamespace(
            artifact_ref=SimpleNamespace(
                manifest_ref=(tmp_path / "product-store" / "manifests" / "demo.skill.json").as_uri(),
            ),
            source_map_ref=(tmp_path / "product-store" / "source-maps" / "demo.skill.json").as_uri(),
            execution_fingerprint=f"sha256:{'e' * 64}",
            diagnostics=[],
            artifact_bytes=b"compiled artifact payload",
        )

    def build_manifest_stub(**kwargs: object) -> object:
        return SimpleNamespace(
            execution_fingerprint=kwargs["execution_fingerprint"],
            model_dump=lambda **_dump_kwargs: {
                "artifact_ref": kwargs["artifact_ref"].model_dump(mode="json"),
                "execution_fingerprint": kwargs["execution_fingerprint"],
                "diagnostics": kwargs["diagnostics"],
            },
        )

    def fail_if_zip_source_dir(_source_dir: Path) -> bytes:
        pytest.fail("D9.4 compile/publish must not zip live skill_dir as product source truth")

    monkeypatch.setattr(artifacts_module, "compile_artifact", compile_without_source_archive)
    monkeypatch.setattr(artifacts_module, "build_compiled_artifact_manifest", build_manifest_stub)
    monkeypatch.setattr(engine_module, "_zip_directory", fail_if_zip_source_dir, raising=False)

    result = EngineAdapter(transport="in_process").compile(
        {
            "skill_dir": str(skill_dir),
            "skill_id": "demo.skill",
            "artifact_scope": "product",
            "version": "1.0.0",
        }
    )

    assert result["store"] == "product"
    assert result["manifest_ref"].endswith("/product-store/manifests/demo.skill.json")
