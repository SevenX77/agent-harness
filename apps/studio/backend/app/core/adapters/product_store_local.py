from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.adapters.http_transport import StudioAdapterError


@dataclass
class ArtifactRef:
    artifact_id: str
    content_hash: str
    store: str
    manifest_ref: str
    source_map_ref: str | None = None


class LocalProductArtifactStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def put(self, content: bytes, artifact_id: str, store: str = "product") -> ArtifactRef:
        sha256_val = hashlib.sha256(content).hexdigest()
        content_hash = f"sha256:{sha256_val}"

        blobs_dir = self.root / "blobs"
        blobs_dir.mkdir(parents=True, exist_ok=True)
        file_path = blobs_dir / sha256_val

        temp_path = file_path.with_suffix(".tmp")
        with open(temp_path, "wb") as f:
            f.write(content)
        temp_path.replace(file_path)

        manifest_ref = f"manifests/{artifact_id}.json"

        return ArtifactRef(
            artifact_id=artifact_id,
            content_hash=content_hash,
            store=store,
            manifest_ref=manifest_ref,
        )

    def get(self, content_hash: str) -> bytes:
        if not content_hash.startswith("sha256:"):
            raise ValueError("Invalid hash format")
        sha256_val = content_hash.split(":", 1)[1]

        file_path = self.root / "blobs" / sha256_val
        if not file_path.exists():
            raise StudioAdapterError("artifact.not_found", {"hash": content_hash})

        content = file_path.read_bytes()

        actual_sha = hashlib.sha256(content).hexdigest()
        if actual_sha != sha256_val:
            raise StudioAdapterError(
                "artifact.hash_mismatch",
                {
                    "expected": sha256_val,
                    "actual": actual_sha,
                },
            )

        return content

    def blob_path(self, content_hash: str) -> Path:
        if not content_hash.startswith("sha256:"):
            raise ValueError("Invalid hash format")
        sha256_val = content_hash.split(":", 1)[1]
        return self.root / "blobs" / sha256_val

    def has_release(self, skill_id: str, release_version: str) -> bool:
        release_file = self.root / "releases" / skill_id / f"{release_version}.json"
        return release_file.exists()

    def stage_release(self, skill_id: str, release_version: str, payload: dict[str, Any]) -> None:
        release_dir = self.root / "releases" / skill_id
        release_dir.mkdir(parents=True, exist_ok=True)
        stage_file = release_dir / f"{release_version}.stage"

        with open(stage_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def commit_release(self, skill_id: str, release_version: str) -> None:
        release_dir = self.root / "releases" / skill_id
        stage_file = release_dir / f"{release_version}.stage"
        release_file = release_dir / f"{release_version}.json"

        if not stage_file.exists():
            raise FileNotFoundError(f"Staged release {release_version} not found")

        stage_file.replace(release_file)

    def rollback_release(self, skill_id: str, release_version: str) -> None:
        release_dir = self.root / "releases" / skill_id
        stage_file = release_dir / f"{release_version}.stage"
        release_file = release_dir / f"{release_version}.json"

        if stage_file.exists():
            try:
                stage_file.unlink()
            except Exception:
                pass
        if release_file.exists():
            try:
                release_file.unlink()
            except Exception:
                pass
