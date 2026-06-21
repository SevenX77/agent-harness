from __future__ import annotations

import hashlib
import json
import os
import time
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
        sha256_val = self._parse_content_hash(content_hash)

        file_path = self.blob_path(content_hash)
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
        sha256_val = self._parse_content_hash(content_hash)
        blobs_dir = self.root / "blobs"
        file_path = blobs_dir / sha256_val
        try:
            file_path.resolve().relative_to(blobs_dir.resolve())
        except ValueError as exc:
            raise StudioAdapterError("artifact.invalid_hash", {"content_hash": content_hash}) from exc
        return file_path

    def has_release(self, skill_id: str, release_version: str) -> bool:
        return self._release_file(skill_id, release_version, ".json").exists()

    def get_release(self, skill_id: str, release_version: str) -> dict[str, Any] | None:
        release_file = self._release_file(skill_id, release_version, ".json")
        if not release_file.exists():
            return None
        return self._read_release_manifest(release_file, skill_id, release_version)

    def list_releases(self, skill_id: str) -> list[dict[str, Any]]:
        release_dir = self._release_dir(skill_id)
        if not release_dir.exists():
            return []
        return [
            self._read_release_manifest(release_file, skill_id, release_file.stem)
            for release_file in sorted(release_dir.glob("*.json"))
        ]

    def _read_release_manifest(self, release_file: Path, skill_id: str, release_version: str) -> dict[str, Any]:
        try:
            with open(release_file, encoding="utf-8") as f:
                payload = json.load(f)
        except (json.JSONDecodeError, ValueError) as exc:
            raise StudioAdapterError(
                "release.invalid_manifest",
                {"skill_id": skill_id, "release_version": release_version},
            ) from exc
        if not isinstance(payload, dict):
            raise StudioAdapterError(
                "release.invalid_manifest",
                {"skill_id": skill_id, "release_version": release_version},
            )
        manifest = self._normalize_release_manifest(skill_id, release_version, payload)
        remote_sync = self.get_remote_sync_state(skill_id, release_version)
        if remote_sync is not None:
            manifest["remote_sync"] = remote_sync
        return manifest

    def stage_release(self, skill_id: str, release_version: str, payload: dict[str, Any]) -> None:
        stage_file = self._release_file(skill_id, release_version, ".stage")
        release_file = self._release_file(skill_id, release_version, ".json")
        manifest = self._normalize_release_manifest(skill_id, release_version, payload)
        stage_file.parent.mkdir(parents=True, exist_ok=True)

        if release_file.exists():
            raise self._release_conflict_error(
                skill_id,
                release_version,
                manifest,
                existing=self._read_release_manifest(release_file, skill_id, release_version),
            )

        try:
            fd = os.open(stage_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        except FileExistsError as exc:
            staged_manifest = self._read_conflicting_release_manifest(
                stage_file,
                release_file,
                skill_id,
                release_version,
            )
            raise self._release_conflict_error(
                skill_id,
                release_version,
                manifest,
                existing=staged_manifest,
            ) from exc
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def _read_conflicting_release_manifest(
        self,
        stage_file: Path,
        release_file: Path,
        skill_id: str,
        release_version: str,
    ) -> dict[str, Any] | None:
        deadline = time.monotonic() + 0.2
        while True:
            if release_file.exists():
                return self._read_release_manifest(release_file, skill_id, release_version)
            if stage_file.exists():
                try:
                    return self._read_release_manifest(stage_file, skill_id, release_version)
                except FileNotFoundError:
                    pass
                except StudioAdapterError as exc:
                    if exc.error_code != "release.invalid_manifest":
                        raise
            if time.monotonic() >= deadline:
                return self.get_release(skill_id, release_version)
            time.sleep(0.01)

    def commit_release(self, skill_id: str, release_version: str) -> None:
        stage_file = self._release_file(skill_id, release_version, ".stage")
        release_file = self._release_file(skill_id, release_version, ".json")

        if not stage_file.exists():
            raise FileNotFoundError(f"Staged release {release_version} not found")

        try:
            os.link(stage_file, release_file)
        except FileExistsError as exc:
            try:
                with open(stage_file, encoding="utf-8") as f:
                    request = json.load(f)
            except Exception:
                request = {}
            try:
                stage_file.unlink()
            except FileNotFoundError:
                pass
            raise self._release_conflict_error(
                skill_id,
                release_version,
                request if isinstance(request, dict) else {},
                existing=self._read_release_manifest(release_file, skill_id, release_version),
            ) from exc
        except OSError:
            raise
        else:
            stage_file.unlink()

    def rollback_release(self, skill_id: str, release_version: str) -> None:
        stage_file = self._release_file(skill_id, release_version, ".stage")
        release_file = self._release_file(skill_id, release_version, ".json")
        remote_sync_file = self._remote_sync_file(skill_id, release_version)
        failures: list[dict[str, str]] = []

        for cleanup_file in (stage_file, release_file, remote_sync_file):
            if not cleanup_file.exists():
                continue
            try:
                cleanup_file.unlink()
            except FileNotFoundError:
                continue
            except Exception as exc:
                failures.append(
                    {
                        "path": str(cleanup_file),
                        "error": str(exc),
                        "error_type": exc.__class__.__name__,
                    }
                )

        if failures:
            raise StudioAdapterError(
                "release.compensation_gc_failed",
                {
                    "phase": "compensation_gc",
                    "skill_id": skill_id,
                    "release_version": release_version,
                    "failed_paths": [failure["path"] for failure in failures],
                    "failures": failures,
                    "error": failures[0]["error"],
                },
            )

    def cleanup_staged_releases(
        self,
        skill_id: str | None = None,
        *,
        max_age_seconds: float,
        now: float | None = None,
        limit: int | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        cutoff_now = time.time() if now is None else now
        cleaned: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        scanned = 0

        for release_dir in self._stage_scan_dirs(skill_id):
            scan_skill_id = release_dir.name
            for stage_file in sorted(release_dir.glob("*.stage")):
                if limit is not None and scanned >= limit:
                    return {"cleaned": cleaned, "failed": failed}
                scanned += 1
                release_version = stage_file.stem
                try:
                    age_seconds = cutoff_now - stage_file.stat().st_mtime
                except FileNotFoundError:
                    continue
                except Exception as exc:
                    failed.append(self._compensation_gc_failure(scan_skill_id, release_version, exc))
                    continue
                if age_seconds < max_age_seconds:
                    continue
                try:
                    stage_file.unlink()
                except FileNotFoundError:
                    continue
                except Exception as exc:
                    failed.append(self._compensation_gc_failure(scan_skill_id, release_version, exc))
                    continue
                cleaned.append(
                    {
                        "phase": "compensation_gc",
                        "skill_id": scan_skill_id,
                        "release_version": release_version,
                        "age_seconds": age_seconds,
                    }
                )
        return {"cleaned": cleaned, "failed": failed}

    def record_remote_sync_state(
        self,
        skill_id: str,
        release_version: str,
        state: dict[str, Any],
    ) -> None:
        if not self.has_release(skill_id, release_version):
            raise StudioAdapterError(
                "release.not_found",
                {"skill_id": skill_id, "release_version": release_version},
            )
        remote_sync_file = self._remote_sync_file(skill_id, release_version)
        remote_sync_file.parent.mkdir(parents=True, exist_ok=True)
        payload = self._normalize_remote_sync_state(skill_id, release_version, state)
        temp_path = remote_sync_file.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        temp_path.replace(remote_sync_file)

    def get_remote_sync_state(
        self,
        skill_id: str,
        release_version: str,
    ) -> dict[str, Any] | None:
        remote_sync_file = self._remote_sync_file(skill_id, release_version)
        if not remote_sync_file.exists():
            return None
        try:
            with open(remote_sync_file, encoding="utf-8") as f:
                payload = json.load(f)
        except (json.JSONDecodeError, ValueError) as exc:
            raise StudioAdapterError(
                "remote_sync.invalid_state",
                {"skill_id": skill_id, "release_version": release_version},
            ) from exc
        if not isinstance(payload, dict):
            raise StudioAdapterError(
                "remote_sync.invalid_state",
                {"skill_id": skill_id, "release_version": release_version},
            )
        return self._normalize_remote_sync_state(skill_id, release_version, payload)

    def _release_dir(self, skill_id: str) -> Path:
        safe_skill_id = self._release_path_part(skill_id, "skill_id", skill_id, None)
        return self.root / "releases" / safe_skill_id

    def _stage_scan_dirs(self, skill_id: str | None) -> list[Path]:
        if skill_id is not None:
            release_dir = self._release_dir(skill_id)
            return [release_dir] if release_dir.exists() else []
        releases_root = self.root / "releases"
        if not releases_root.exists():
            return []
        return sorted(path for path in releases_root.iterdir() if path.is_dir())

    def _compensation_gc_failure(
        self,
        skill_id: str,
        release_version: str,
        exc: Exception,
    ) -> dict[str, Any]:
        return {
            "error_code": "release.compensation_gc_failed",
            "phase": "compensation_gc",
            "skill_id": skill_id,
            "release_version": release_version,
            "error": str(exc),
        }

    def _release_conflict_error(
        self,
        skill_id: str,
        release_version: str,
        request_manifest: dict[str, Any],
        *,
        existing: dict[str, Any] | None = None,
    ) -> StudioAdapterError:
        return StudioAdapterError(
            "release.conflict",
            {
                "skill_id": skill_id,
                "release_version": release_version,
                "existing": self._release_identity(existing),
                "request": self._release_identity(request_manifest),
            },
        )

    def _release_identity(self, manifest: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(manifest, dict):
            return {}
        artifact_ref = manifest.get("artifact_ref")
        if not isinstance(artifact_ref, dict):
            artifact_ref = manifest
        identity: dict[str, Any] = {}
        for key in ("artifact_id", "content_hash", "manifest_ref"):
            value = artifact_ref.get(key) if isinstance(artifact_ref, dict) else None
            if isinstance(value, str) and value:
                identity[key] = value
        for key in ("release_version", "idempotency_key"):
            value = manifest.get(key)
            if isinstance(value, str) and value:
                identity[key] = value
        return identity

    def _release_file(self, skill_id: str, release_version: str, suffix: str) -> Path:
        safe_skill_id = self._release_path_part(skill_id, "skill_id", skill_id, release_version)
        safe_release_version = self._release_path_part(
            release_version,
            "release_version",
            skill_id,
            release_version,
        )
        return self.root / "releases" / safe_skill_id / f"{safe_release_version}{suffix}"

    def _remote_sync_file(self, skill_id: str, release_version: str) -> Path:
        safe_skill_id = self._release_path_part(skill_id, "skill_id", skill_id, release_version)
        safe_release_version = self._release_path_part(
            release_version,
            "release_version",
            skill_id,
            release_version,
        )
        return self.root / "remote_sync" / safe_skill_id / f"{safe_release_version}.json"

    def _release_path_part(
        self,
        value: str,
        field: str,
        skill_id: str | None,
        release_version: str | None,
    ) -> str:
        if (
            not isinstance(value, str)
            or not value
            or Path(value).is_absolute()
            or len(Path(value).parts) != 1
            or value in {".", ".."}
            or "/" in value
            or "\\" in value
        ):
            payload: dict[str, Any] = {"field": field}
            if isinstance(skill_id, str):
                payload["skill_id"] = skill_id
            if isinstance(release_version, str):
                payload["release_version"] = release_version
            raise StudioAdapterError("release.invalid_path", payload)
        return value

    def _normalize_release_manifest(
        self, skill_id: str, release_version: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        artifact_ref = payload.get("artifact_ref")
        if not isinstance(artifact_ref, dict):
            raise StudioAdapterError(
                "release.invalid_manifest",
                {
                    "skill_id": skill_id,
                    "release_version": release_version,
                    "field": "artifact_ref",
                },
            )

        manifest_release_version = self._required_release_str(
            payload.get("release_version", release_version),
            skill_id,
            release_version,
            "release_version",
        )
        if manifest_release_version != release_version:
            raise StudioAdapterError(
                "release.invalid_manifest",
                {
                    "skill_id": skill_id,
                    "release_version": release_version,
                    "field": "release_version",
                    "actual": manifest_release_version,
                },
            )
        artifact_id = self._required_release_str(
            artifact_ref.get("artifact_id") or payload.get("artifact_id"),
            skill_id,
            release_version,
            "artifact_id",
        )
        content_hash = self._required_release_str(
            artifact_ref.get("content_hash") or payload.get("content_hash"),
            skill_id,
            release_version,
            "content_hash",
        )
        sha256_val = self._parse_content_hash(
            content_hash,
            error_code="release.invalid_manifest",
            error_payload={
                "skill_id": skill_id,
                "release_version": release_version,
                "field": "content_hash",
            },
        )
        content_hash = f"sha256:{sha256_val}"
        manifest_ref = self._required_release_str(
            artifact_ref.get("manifest_ref") or payload.get("manifest_ref"),
            skill_id,
            release_version,
            "manifest_ref",
        )

        normalized_artifact_ref: dict[str, Any] = {
            "artifact_id": artifact_id,
            "content_hash": content_hash,
            "manifest_ref": manifest_ref,
            "store": "product",
        }
        source_map_ref = artifact_ref.get("source_map_ref")
        if isinstance(source_map_ref, str) and source_map_ref:
            normalized_artifact_ref["source_map_ref"] = source_map_ref

        manifest: dict[str, Any] = {
            "release_version": manifest_release_version,
            "artifact_id": artifact_id,
            "content_hash": content_hash,
            "manifest_ref": manifest_ref,
            "artifact_ref": normalized_artifact_ref,
        }
        idempotency_key = payload.get("idempotency_key")
        if isinstance(idempotency_key, str) and idempotency_key:
            manifest["idempotency_key"] = idempotency_key
        created_at = payload.get("created_at")
        if isinstance(created_at, str) and created_at:
            manifest["created_at"] = created_at
        if "idempotency_key" not in manifest and "created_at" not in manifest:
            raise StudioAdapterError(
                "release.invalid_manifest",
                {
                    "skill_id": skill_id,
                    "release_version": release_version,
                    "field": "idempotency_key",
                },
            )
        return manifest

    def _required_release_str(self, value: Any, skill_id: str, release_version: str, field: str) -> str:
        if isinstance(value, str) and value:
            return value
        raise StudioAdapterError(
            "release.invalid_manifest",
            {
                "skill_id": skill_id,
                "release_version": release_version,
                "field": field,
            },
        )

    def _normalize_remote_sync_state(
        self,
        skill_id: str,
        release_version: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        status = payload.get("status")
        if status not in {"pending", "failed", "succeeded", "skipped"}:
            raise StudioAdapterError(
                "remote_sync.invalid_state",
                {
                    "skill_id": skill_id,
                    "release_version": release_version,
                    "field": "status",
                },
            )
        normalized: dict[str, Any] = {"status": status}
        for key in ("reason", "error_type", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                normalized[key] = value
        details = payload.get("details")
        if isinstance(details, dict) and details:
            normalized["details"] = details
        return normalized

    def _parse_content_hash(
        self,
        content_hash: str,
        *,
        error_code: str = "artifact.invalid_hash",
        error_payload: dict[str, Any] | None = None,
    ) -> str:
        if isinstance(content_hash, str) and content_hash.startswith("sha256:"):
            sha256_val = content_hash.split(":", 1)[1]
            if len(sha256_val) == 64 and all(c in "0123456789abcdefABCDEF" for c in sha256_val):
                return sha256_val.lower()
        raise StudioAdapterError(
            error_code,
            error_payload or {"content_hash": content_hash},
        )
