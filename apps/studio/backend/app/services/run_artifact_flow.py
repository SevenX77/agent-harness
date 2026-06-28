from __future__ import annotations

from typing import NoReturn

from app.core.adapters.http_transport import StudioAdapterError
from app.core.adapters.product_store_local import ArtifactRef, LocalProductArtifactStore


def resolve_artifact_for_run(
    store: LocalProductArtifactStore,
    artifact_id: str,
    content_hash: str | None = None,
    store_type: str = "product",
    dev_mode: bool = True,
) -> ArtifactRef:
    if content_hash:
        try:
            # Verify and retrieve content
            store.get(content_hash)
            return ArtifactRef(
                artifact_id=artifact_id,
                content_hash=content_hash,
                store=store_type,
                manifest_ref=f"manifests/{artifact_id}.json",
            )
        except StudioAdapterError as exc:
            if exc.error_code == "artifact.hash_mismatch":
                raise exc
            if not dev_mode:
                reject_prod_missing_hash(artifact_id, content_hash)
            else:
                return compile_ephemeral_for_dev_missing_hash(artifact_id)
    else:
        if not dev_mode:
            reject_prod_missing_hash(artifact_id, None)
        else:
            return compile_ephemeral_for_dev_missing_hash(artifact_id)


def load_verified_artifact_bytes(store: LocalProductArtifactStore, content_hash: str) -> bytes:
    return store.get(content_hash)


def compile_ephemeral_for_dev_missing_hash(artifact_id: str) -> ArtifactRef:
    from app.services.skills import resolve_skill_dir

    skill_dir = resolve_skill_dir(artifact_id)

    from app.core.adapters.transport_factory import build_engine_adapter

    adapter = build_engine_adapter()
    artifact_ref_dict = adapter.compile(
        {"skill_dir": str(skill_dir), "skill_id": artifact_id, "artifact_scope": "ephemeral"}
    )

    return ArtifactRef(
        artifact_id=artifact_ref_dict["artifact_id"],
        content_hash=artifact_ref_dict["content_hash"],
        store=artifact_ref_dict["store"],
        manifest_ref=artifact_ref_dict["manifest_ref"],
        source_map_ref=artifact_ref_dict.get("source_map_ref"),
    )


def reject_prod_missing_hash(artifact_id: str, content_hash: str | None) -> NoReturn:
    raise StudioAdapterError(
        "artifact.not_found",
        {"detail": f"Artifact {artifact_id} with hash {content_hash} is missing in production store"},
    )
