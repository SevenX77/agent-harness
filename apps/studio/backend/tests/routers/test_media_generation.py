"""Media generation settings API: registry view, credential, probe, model settings."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.adapters.atomic_file import open_published
from app.core.adapters.media_gateway import MediaModelSettings
from app.services import media_generation
from fastapi.testclient import TestClient
from graph_agent_gateway.media import MediaProbeResult, MediaProviderCredential


@pytest.fixture()
def media_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "media_generation.json"
    monkeypatch.setenv("STUDIO_MEDIA_GENERATION_PATH", str(path))
    return path


def test_registry_lists_catalog_and_empty_provider(client: TestClient, media_path: Path) -> None:
    response = client.get("/api/media/registry")
    assert response.status_code == 200
    payload = response.json()

    models = payload["models"]
    assert len(models) == 10
    assert {m["modality"] for m in models} == {"image", "video"}
    assert all("params" in m and "settings" in m for m in models)

    providers = payload["providers"]
    assert len(providers) == 1
    runninghub = providers[0]
    assert runninghub["id"] == "runninghub"
    assert runninghub["api_key_set"] is False
    assert runninghub["last_probe"] is None


def test_put_credential_persists_and_masks_key(client: TestClient, media_path: Path) -> None:
    response = client.put(
        "/api/media/providers/runninghub/credential",
        json={"api_key": "0123456789abcdef0123456789abcdef"},
    )
    assert response.status_code == 200
    provider = response.json()["providers"][0]
    assert provider["api_key_set"] is True
    assert "0123456789abcdef" not in response.text

    again = client.get("/api/media/registry")
    assert again.json()["providers"][0]["api_key_set"] is True
    assert media_path.exists()


def test_secret_reveal_returns_plaintext(client: TestClient, media_path: Path) -> None:
    client.put(
        "/api/media/providers/runninghub/credential",
        json={"api_key": "0123456789abcdef0123456789abcdef"},
    )
    response = client.get("/api/media/providers/runninghub/credential/secret")
    assert response.status_code == 200
    assert response.json()["api_key"] == "0123456789abcdef0123456789abcdef"


def test_probe_stores_result_in_snapshot(
    client: TestClient, media_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_probe(credential: MediaProviderCredential, **_kwargs: object) -> MediaProbeResult:
        assert credential.api_key.get_secret_value() == "k" * 32
        return MediaProbeResult(
            status="ok",
            checked_at="2026-08-13T00:00:00+00:00",
            latency_ms=123,
            remain_coins="500",
            remain_money="10",
        )

    monkeypatch.setattr(
        "app.services.media_generation.probe_runninghub_account", fake_probe
    )

    client.put(
        "/api/media/providers/runninghub/credential", json={"api_key": "k" * 32}
    )
    response = client.post("/api/media/providers/runninghub/probe")
    assert response.status_code == 200
    probe = response.json()["providers"][0]["last_probe"]
    assert probe["status"] == "ok"
    assert probe["remain_coins"] == "500"

    again = client.get("/api/media/registry")
    assert again.json()["providers"][0]["last_probe"]["latency_ms"] == 123


def test_probe_without_key_is_rejected(client: TestClient, media_path: Path) -> None:
    response = client.post("/api/media/providers/runninghub/probe")
    assert response.status_code == 400


def test_patch_model_settings_persists_legal_defaults(
    client: TestClient, media_path: Path
) -> None:
    response = client.patch(
        "/api/media/models/rh-image-v2-t2i/settings",
        json={"enabled": False, "defaults": {"resolution": "2k", "aspectRatio": "16:9"}},
    )
    assert response.status_code == 200
    model = next(
        m for m in response.json()["models"] if m["id"] == "rh-image-v2-t2i"
    )
    assert model["settings"]["enabled"] is False
    assert model["settings"]["defaults"]["resolution"] == "2k"

    again = client.get("/api/media/registry")
    model_again = next(
        m for m in again.json()["models"] if m["id"] == "rh-image-v2-t2i"
    )
    assert model_again["settings"]["defaults"]["aspectRatio"] == "16:9"


def test_patch_model_settings_rejects_illegal_enum(
    client: TestClient, media_path: Path
) -> None:
    response = client.patch(
        "/api/media/models/rh-image-v2-t2i/settings",
        json={"defaults": {"resolution": "8k"}},
    )
    assert response.status_code == 400
    assert "resolution" in response.json()["message"]

    again = client.get("/api/media/registry")
    model = next(m for m in again.json()["models"] if m["id"] == "rh-image-v2-t2i")
    assert model["settings"]["defaults"] == {}


def test_patch_unknown_model_is_404(client: TestClient, media_path: Path) -> None:
    response = client.patch(
        "/api/media/models/no-such-model/settings", json={"enabled": False}
    )
    assert response.status_code == 404


def test_unknown_provider_is_404(client: TestClient, media_path: Path) -> None:
    response = client.put(
        "/api/media/providers/other/credential", json={"api_key": "x"}
    )
    assert response.status_code == 404


def test_a_probe_in_flight_does_not_clobber_a_write_that_lands_during_it(
    client: TestClient, media_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The probe is the one handler that awaits between reading and writing.

    Reading the state, awaiting a network round trip, then writing back the
    snapshot read BEFORE the await means everything committed during the await is
    overwritten by a stale copy. The probe result is one field; the write it
    silently reverts can be the user's API key.

    The fix is not a lock around the await — holding one across `await` on the
    event loop deadlocks the loop. It is to treat the probe like any other slow
    outside call: do it unlocked, then re-read and merge only its own result.
    """
    client.put(
        "/api/media/providers/runninghub/credential",
        json={"api_key": "k" * 32},
    )

    async def fake_probe(
        credential: MediaProviderCredential, **_kwargs: object
    ) -> MediaProbeResult:
        # Stands in for anything that commits while the probe is on the wire. It
        # writes through the service rather than the TestClient because a nested
        # client call cannot run on the event loop thread; what matters is only
        # that the file gains a change after the probe handler read it.
        with media_generation.locked_state() as landed:
            landed.providers[media_generation.MEDIA_PROVIDER_ID].model_settings[
                "rh-image-v2-t2i"
            ] = MediaModelSettings(enabled=False)
        return MediaProbeResult(
            status="ok",
            checked_at="2026-08-31T00:00:00+00:00",
            latency_ms=7,
        )

    monkeypatch.setattr(
        "app.services.media_generation.probe_runninghub_account", fake_probe
    )

    response = client.post("/api/media/providers/runninghub/probe")

    assert response.status_code == 200
    persisted = client.get("/api/media/registry").json()
    assert persisted["providers"][0]["last_probe"] is not None
    model = next(m for m in persisted["models"] if m["id"] == "rh-image-v2-t2i")
    assert model["settings"]["enabled"] is False


def test_two_concurrent_writers_do_not_lose_each_other_s_change(
    media_path: Path,
) -> None:
    """Read-modify-write must be one critical section, not three steps anyone can
    interleave.

    Every write rewrites the WHOLE document, so two writers that each read before
    the other wrote will each save a document in which the other's change never
    happened. `locked_state` is what makes the three steps inseparable, and this
    is the test that says so: remove the lock from it and the second writer's
    model disappears.

    Deliberately NOT driven through the HTTP API. The handlers are `async def`
    with no await between reading and writing, so the event loop already
    serializes them — an HTTP-level version of this test passes with no lock at
    all and would prove nothing. The lock is here for writers that are not the
    event loop (a sync endpoint on the threadpool, a background task), and threads
    are how that is actually exercised.
    """
    import threading

    first_inside = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    second_finished = threading.Event()

    def write_first() -> None:
        with media_generation.locked_state() as state:
            state.providers[media_generation.MEDIA_PROVIDER_ID].model_settings[
                "rh-image-v2-t2i"
            ] = MediaModelSettings(enabled=False)
            first_inside.set()
            release_first.wait(timeout=5.0)

    def write_second() -> None:
        second_started.set()
        with media_generation.locked_state() as state:
            state.providers[media_generation.MEDIA_PROVIDER_ID].model_settings[
                "rh-video-x-i2v"
            ] = MediaModelSettings(enabled=False)
        second_finished.set()

    first = threading.Thread(target=write_first)
    first.start()
    assert first_inside.wait(timeout=5.0), "the first writer never entered its section"

    second = threading.Thread(target=write_second)
    second.start()
    # The second thread announces itself BEFORE reaching for the section, so the
    # window below starts only once it is provably running — otherwise a slow
    # thread start would let an unlocked implementation pass by never having tried.
    assert second_started.wait(timeout=5.0), "the second writer never started"
    # Expected to time out: while the first writer holds the section the second
    # must not have completed. Short so the test stays quick when the lock works.
    assert not second_finished.wait(timeout=0.5), (
        "the second writer committed while the first still held the critical section"
    )
    release_first.set()
    first.join(timeout=10.0)
    second.join(timeout=10.0)
    assert not first.is_alive() and not second.is_alive()

    settings = media_generation.load_state().providers[
        media_generation.MEDIA_PROVIDER_ID
    ].model_settings
    assert settings["rh-image-v2-t2i"].enabled is False
    assert settings["rh-video-x-i2v"].enabled is False


def test_saving_works_while_a_reader_holds_the_file_open(
    client: TestClient, media_path: Path
) -> None:
    """Publishing must not require that nobody is reading.

    `os.replace` over a path with ANY open handle is refused on Windows
    (MoveFileExW returns ACCESS_DENIED), so a store that rolls its own
    temp-and-replace cannot publish while anyone reads. The shared
    `write_text_atomically` publishes through a POSIX-semantics rename, which is
    what makes the pair work — readers use `open_published` (sharing delete) and
    keep reading the version they opened while the publisher renames over it.
    This is the observable difference between going through that helper and not.
    """
    client.put(
        "/api/media/providers/runninghub/credential",
        json={"api_key": "k" * 32},
    )
    assert media_path.exists()

    with open_published(media_path) as reader:
        reader.read()
        response = client.patch(
            "/api/media/models/rh-image-v2-t2i/settings", json={"enabled": False}
        )
        assert response.status_code == 200

    model = next(
        m
        for m in client.get("/api/media/registry").json()["models"]
        if m["id"] == "rh-image-v2-t2i"
    )
    assert model["settings"]["enabled"] is False


def test_a_probe_is_discarded_when_the_credential_changed_under_it(
    client: TestClient, media_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A probe result describes the credential it was made with, and nothing else.

    Merging only `last_probe` into a freshly read state fixes the stale-snapshot
    overwrite, but on its own it would attribute the OLD key's verdict — success,
    failure, remaining balance — to whatever key is configured by the time the
    probe lands. Dropping the observation instead is the same rule the LLM
    registry applies on key rotation: an observation whose subject no longer
    exists is not evidence about its replacement.
    """
    client.put("/api/media/providers/runninghub/credential", json={"api_key": "k" * 32})

    async def fake_probe(
        credential: MediaProviderCredential, **_kwargs: object
    ) -> MediaProbeResult:
        assert credential.api_key.get_secret_value() == "k" * 32
        with media_generation.locked_state() as rotated:
            rotated.providers[media_generation.MEDIA_PROVIDER_ID].api_key = "j" * 32
        return MediaProbeResult(
            status="ok",
            checked_at="2026-08-31T00:00:00+00:00",
            latency_ms=7,
        )

    monkeypatch.setattr(
        "app.services.media_generation.probe_runninghub_account", fake_probe
    )

    response = client.post("/api/media/providers/runninghub/probe")

    assert response.status_code == 200
    provider = client.get("/api/media/registry").json()["providers"][0]
    # The rotation stands, and the old key's verdict is not shown as the new one's.
    assert provider["api_key_set"] is True
    assert provider["last_probe"] is None
    assert (
        client.get("/api/media/providers/runninghub/credential/secret").json()["api_key"]
        == "j" * 32
    )
