from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, overload

from graph_agent.core.storage_contracts import ObjectRef, RunArtifactIndex

from app.core.adapters.http_transport import StudioAdapterError


class LocalRunArtifactStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def begin_run(self, run_id: str, metadata: dict[str, Any] | None = None) -> None:
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        sealed_file = run_dir / "sealed"
        if sealed_file.exists():
            raise StudioAdapterError("artifact.sealed_write", {"detail": "Run is sealed"})
        manifest_file = run_dir / "manifest.json"
        if not manifest_file.exists():
            self._write_manifest(
                manifest_file,
                {
                    "files": {},
                    "object_refs": {},
                    "metadata": metadata or {},
                },
            )
        elif metadata is not None:
            manifest = self._read_manifest(manifest_file)
            manifest["metadata"] = metadata
            self._write_manifest(manifest_file, manifest)
        return None

    @overload
    def put_batch(self, run_id: str, objects: dict[str, bytes]) -> dict[str, ObjectRef]:
        ...

    @overload
    def put_batch(self, run_id: str, objects: list[dict[str, Any]]) -> None:
        ...

    def put_batch(
        self,
        run_id: str,
        objects: dict[str, bytes] | list[dict[str, Any]],
    ) -> dict[str, ObjectRef] | None:
        run_dir = self._run_dir(run_id)
        sealed_file = run_dir / "sealed"
        if sealed_file.exists():
            raise StudioAdapterError("artifact.sealed_write", {"detail": "Run is sealed"})

        manifest_file = run_dir / "manifest.json"
        if not manifest_file.exists():
            self.begin_run(run_id)

        manifest = self._read_manifest(manifest_file)

        blobs_dir = self.root / "blobs"
        blobs_dir.mkdir(parents=True, exist_ok=True)

        refs: dict[str, ObjectRef] = {}
        if isinstance(objects, list):
            legacy_objects = True
            object_items = [(str(obj["path"]), obj["content"]) for obj in objects]
        else:
            legacy_objects = False
            object_items = [(str(path), content) for path, content in objects.items()]

        for path, content in object_items:
            if isinstance(content, str):
                content = content.encode("utf-8")

            sha256_val = hashlib.sha256(content).hexdigest()
            content_hash = f"sha256:{sha256_val}"
            ref = ObjectRef(
                bytes_ref=f"bytes://{content_hash}",
                content_hash=content_hash,
                size_bytes=len(content),
                path=path,
            )

            blob_file = blobs_dir / sha256_val
            temp_file = blob_file.with_suffix(".tmp")
            with open(temp_file, "wb") as f:
                f.write(content)
            temp_file.replace(blob_file)

            manifest["files"][path] = content_hash
            manifest.setdefault("object_refs", {})[path] = ref.model_dump(mode="json")
            refs[path] = ref

        self._write_manifest(manifest_file, manifest)
        return None if legacy_objects else refs

    def seal_run(self, run_id: str) -> RunArtifactIndex:
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        sealed_file = run_dir / "sealed"
        manifest_file = run_dir / "manifest.json"
        manifest = self._read_manifest(manifest_file) if manifest_file.exists() else {"object_refs": {}}
        objects = self._manifest_object_refs(manifest, manifest_file)
        if manifest_file.exists():
            manifest["object_refs"] = {ref.path: ref.model_dump(mode="json") for ref in objects}
            self._write_manifest(manifest_file, manifest)
        with open(sealed_file, "w", encoding="utf-8") as f:
            f.write("sealed")
        return RunArtifactIndex(run_id=run_id, objects=objects, sealed=True)

    def get_object(self, content_hash: str | None = None, *, hash: str | None = None) -> bytes:
        hash_value = hash if hash is not None else content_hash
        if hash_value is None:
            raise ValueError("Missing hash")
        sha256_val = hash_value.split(":", 1)[1] if hash_value.startswith("sha256:") else hash_value
        if len(sha256_val) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in sha256_val):
            raise StudioAdapterError("artifact.invalid_hash", {"hash": hash_value})

        blob_file = self.root / "blobs" / sha256_val
        if not blob_file.exists():
            raise StudioAdapterError("artifact.not_found", {"hash": hash_value})

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

    def get_run_object(self, run_id: str, path: str) -> bytes:
        run_dir = self._run_dir(run_id)
        manifest_file = run_dir / "manifest.json"
        if not manifest_file.exists():
            raise StudioAdapterError("artifact.not_found", {"run_id": run_id, "path": path})
        if not (run_dir / "sealed").exists():
            raise StudioAdapterError("artifact.run_not_sealed", {"run_id": run_id, "path": path})

        manifest = self._read_manifest(manifest_file)
        object_refs = manifest["object_refs"]
        if path not in object_refs:
            raise StudioAdapterError("artifact.not_found", {"run_id": run_id, "path": path})
        ref = self._validate_object_ref(manifest_file, object_refs[path])
        return self.get_object(hash=ref.content_hash)

    def list_run_objects(self, run_id: str) -> list[ObjectRef]:
        run_dir = self._run_dir(run_id)
        manifest_file = run_dir / "manifest.json"
        if not manifest_file.exists():
            raise StudioAdapterError("artifact.not_found", {"run_id": run_id})
        if not (run_dir / "sealed").exists():
            raise StudioAdapterError("artifact.run_not_sealed", {"run_id": run_id})
        manifest = self._read_manifest(manifest_file)
        return [
            self._validate_object_ref(manifest_file, ref)
            for ref in manifest["object_refs"].values()
        ]

    def _read_manifest(self, manifest_file: Path) -> dict[str, Any]:
        try:
            with open(manifest_file, encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError as exc:
            raise StudioAdapterError(
                "artifact.corrupt_manifest",
                {"path": str(manifest_file), "detail": str(exc)},
            ) from exc
        if not isinstance(manifest, dict):
            raise self._corrupt_manifest(manifest_file, "manifest must be a JSON object")
        files = manifest.setdefault("files", {})
        object_refs = manifest.setdefault("object_refs", {})
        metadata = manifest.setdefault("metadata", {})
        if not isinstance(files, dict):
            raise self._corrupt_manifest(manifest_file, "files must be an object")
        if not isinstance(object_refs, dict):
            raise self._corrupt_manifest(manifest_file, "object_refs must be an object")
        if not isinstance(metadata, dict):
            raise self._corrupt_manifest(manifest_file, "metadata must be an object")
        return manifest

    def _write_manifest(self, manifest_file: Path, manifest: dict[str, Any]) -> None:
        temp_manifest = manifest_file.with_suffix(".tmp")
        with open(temp_manifest, "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        temp_manifest.replace(manifest_file)

    def _run_dir(self, run_id: str) -> Path:
        if not _is_safe_run_id(run_id):
            raise StudioAdapterError("artifact.invalid_run_id", {"run_id": run_id})
        return self.root / "runs" / run_id

    def _manifest_object_refs(self, manifest: dict[str, Any], manifest_file: Path) -> list[ObjectRef]:
        refs = [
            self._validate_object_ref(manifest_file, ref)
            for ref in manifest.get("object_refs", {}).values()
        ]
        if refs:
            return refs

        backfilled: list[ObjectRef] = []
        files = manifest.get("files", {})
        if not isinstance(files, dict):
            return backfilled
        for path, content_hash in files.items():
            if not isinstance(path, str) or not isinstance(content_hash, str):
                continue
            sha256_val = content_hash.split(":", 1)[1] if content_hash.startswith("sha256:") else content_hash
            blob_file = self.root / "blobs" / sha256_val
            size_bytes = blob_file.stat().st_size if blob_file.exists() else 0
            backfilled.append(
                ObjectRef(
                    bytes_ref=f"bytes://{content_hash}",
                    content_hash=content_hash,
                    size_bytes=size_bytes,
                    path=path,
                )
            )
        return backfilled

    def _validate_object_ref(self, manifest_file: Path, ref_payload: Any) -> ObjectRef:
        if not isinstance(ref_payload, dict):
            raise self._corrupt_manifest(manifest_file, "object ref must be an object")
        try:
            return ObjectRef.model_validate(ref_payload)
        except Exception as exc:
            raise self._corrupt_manifest(manifest_file, str(exc)) from exc

    def _corrupt_manifest(self, manifest_file: Path, detail: str) -> StudioAdapterError:
        return StudioAdapterError(
            "artifact.corrupt_manifest",
            {"path": str(manifest_file), "detail": detail},
        )


def _is_safe_run_id(run_id: str) -> bool:
    if not run_id:
        return False
    path = Path(run_id)
    if path.is_absolute():
        return False
    parts = tuple(path.parts)
    return len(parts) == 1 and parts[0] not in {"", ".", ".."}
