from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.adapters.http_transport import StudioAdapterError


class LocalRunArtifactStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def begin_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self.root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = run_dir / "manifest.json"
        if not manifest_file.exists():
            with open(manifest_file, "w") as f:
                json.dump({"files": {}}, f)
        return {"run_id": run_id}

    def put_batch(self, run_id: str, objects: list[dict[str, Any]]) -> None:
        run_dir = self.root / "runs" / run_id
        sealed_file = run_dir / "sealed"
        if sealed_file.exists():
            raise StudioAdapterError("artifact.sealed_write", {"detail": "Run is sealed"})

        manifest_file = run_dir / "manifest.json"
        if not manifest_file.exists():
            self.begin_run(run_id)

        with open(manifest_file) as f:
            manifest = json.load(f)

        blobs_dir = self.root / "blobs"
        blobs_dir.mkdir(parents=True, exist_ok=True)

        for obj in objects:
            path = obj["path"]
            content = obj["content"]
            if isinstance(content, str):
                content = content.encode("utf-8")

            sha256_val = hashlib.sha256(content).hexdigest()
            content_hash = f"sha256:{sha256_val}"

            blob_file = blobs_dir / sha256_val
            temp_file = blob_file.with_suffix(".tmp")
            with open(temp_file, "wb") as f:
                f.write(content)
            temp_file.replace(blob_file)

            manifest["files"][path] = content_hash

        temp_manifest = manifest_file.with_suffix(".tmp")
        with open(temp_manifest, "w") as f:
            json.dump(manifest, f)
        temp_manifest.replace(manifest_file)

    def seal_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self.root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        sealed_file = run_dir / "sealed"
        with open(sealed_file, "w") as f:
            f.write("sealed")
        return {"run_id": run_id, "sealed": True}

    def get_object(self, content_hash: str) -> bytes:
        if not content_hash.startswith("sha256:"):
            raise ValueError("Invalid hash format")
        sha256_val = content_hash.split(":", 1)[1]

        blob_file = self.root / "blobs" / sha256_val
        if not blob_file.exists():
            raise StudioAdapterError("artifact.not_found", {"hash": content_hash})

        content = blob_file.read_bytes()
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
