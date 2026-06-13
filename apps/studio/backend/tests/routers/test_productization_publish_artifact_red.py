from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "app").is_dir() and (parent / "tests").is_dir()
)


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
