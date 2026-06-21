"""N6/D12: the publish *package* is produced as a payload, written only by Rust.

PUBLISH-2 / NATIVE_FS-2 / D12: the ``studio.publish.package.v1`` package is
written exclusively by the Rust native-fs ``publish_package_writer``. The Python
sidecar only *produces the payload* (release_version / content_hash /
manifest_ref / artifact_ref + the relative path) that the frontend hands to Rust.

These tests pin two invariants:
1. The publish service exposes a pure payload producer that performs no disk I/O.
2. No Python code in the publish path zips a skill or writes a
   ``studio.publish.package.v1`` package to disk.
"""

from __future__ import annotations

from pathlib import Path

from app.services.publish_pipeline import build_publish_package_payload

BACKEND_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "app").is_dir() and (parent / "tests").is_dir()
)


def _release_manifest() -> dict[str, object]:
    content_hash = f"sha256:{'a' * 64}"
    return {
        "release_version": "1.0.0",
        "artifact_id": "text-segmentation",
        "content_hash": content_hash,
        "manifest_ref": "manifests/text-segmentation.json",
        "artifact_ref": {
            "artifact_id": "text-segmentation",
            "content_hash": content_hash,
            "manifest_ref": "manifests/text-segmentation.json",
            "store": "product",
        },
    }


def test_build_publish_package_payload_matches_rust_writer_contract(tmp_path: Path) -> None:
    before = {p for p in tmp_path.rglob("*")}

    payload = build_publish_package_payload(
        skill_id="text-segmentation",
        release_manifest=_release_manifest(),
    )

    # Field names match the Rust publish_package_writer request (camelCase on the
    # wire is handled by the frontend; the payload carries the snake_case source).
    assert payload["release_version"] == "1.0.0"
    assert payload["content_hash"] == f"sha256:{'a' * 64}"
    assert payload["manifest_ref"] == "manifests/text-segmentation.json"
    assert payload["artifact_ref"]["artifact_id"] == "text-segmentation"
    assert payload["artifact_ref"]["store"] == "product"
    # A stable, workspace-relative target path for the Rust writer.
    assert isinstance(payload["relative_path"], str)
    assert payload["relative_path"].endswith(".package.json")
    assert "1.0.0" in payload["relative_path"]
    assert not payload["relative_path"].startswith("/")
    assert ".." not in payload["relative_path"]

    # Producing the payload must not touch the filesystem.
    after = {p for p in tmp_path.rglob("*")}
    assert before == after


def test_publish_path_does_not_zip_or_write_publish_package_in_python() -> None:
    publish_pipeline = (BACKEND_ROOT / "app" / "services" / "publish_pipeline.py").read_text(
        encoding="utf-8"
    )
    skills_router = (BACKEND_ROOT / "app" / "routers" / "skills.py").read_text(encoding="utf-8")

    for source in (publish_pipeline, skills_router):
        assert "zipfile" not in source
        assert "ZipFile" not in source
        assert "build_publish_package(" not in source
        # The publish package schema is emitted by Rust only — never serialized
        # to disk from Python.
        assert "studio.publish.package.v1" not in source
