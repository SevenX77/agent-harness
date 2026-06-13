"""MVP1 productization RED tests for resolver/config storage closure."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

GATEWAY_ROOT = Path(__file__).resolve().parents[1]


def test_model_resolver_no_longer_exposes_file_or_snapshot_bypass() -> None:
    from graph_agent_gateway.resolver import ModelResolver

    params = inspect.signature(ModelResolver.__init__).parameters
    bypass_params = {"credentials_path", "roles_path", "registry_snapshot"}

    assert bypass_params.isdisjoint(params)
    assert {"config_store", "config_truth_store"}.intersection(params)


def test_legacy_registry_snapshot_loader_is_removed_from_gateway_owner_path() -> None:
    resolver_source = (GATEWAY_ROOT / "src" / "graph_agent_gateway" / "resolver.py").read_text(encoding="utf-8")

    assert "def load_registry_snapshot" not in resolver_source


def test_config_truth_store_rejects_second_writer_with_stale_if_match() -> None:
    from graph_agent_gateway.storage_contracts import (
        ConfigConflictError,
        InMemoryConfigTruthStore,
    )

    store = InMemoryConfigTruthStore()
    initial_etag = store.put_config(
        user_id="user-a",
        key="roles",
        value={"version": 1},
        if_none_match="*",
    )

    first_writer_etag = store.put_config(
        user_id="user-a",
        key="roles",
        value={"version": 2, "writer": "first"},
        if_match=initial_etag,
    )

    with pytest.raises(ConfigConflictError) as conflict:
        store.put_config(
            user_id="user-a",
            key="roles",
            value={"version": 3, "writer": "second"},
            if_match=initial_etag,
        )

    assert conflict.value.error_code == "config.etag_conflict"
    assert conflict.value.error_payload["user_id"] == "user-a"
    assert conflict.value.error_payload["key"] == "roles"
    assert conflict.value.error_payload["expected_etag"] == first_writer_etag
    assert conflict.value.error_payload["actual_if_match"] == initial_etag
    assert store.get_config(user_id="user-a", key="roles").value == {
        "version": 2,
        "writer": "first",
    }
