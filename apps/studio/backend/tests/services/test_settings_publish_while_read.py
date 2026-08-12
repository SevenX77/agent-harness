"""Saving a settings file must not depend on nobody currently reading it.

Every file under the settings tree is published the same way — write a sibling
temporary file, rename it over the destination — and every one of them is read
without a lock by something else in the same process: `load_credentials` reads
it straight off disk, and the file watcher resolves the path on every event it
sees in that directory.

On POSIX a rename over an open file is free. On Windows `os.replace` is
`MoveFileExW`, which refuses with `ACCESS_DENIED` while ANY handle is open on
the destination, so the publish fails on a file that is entirely healthy. That
is not a hypothetical: it is what turned `cross-platform-smoke (windows-latest)`
red on PR #739, a docs-only change —

    PermissionError: [WinError 5] Access is denied:
    '...\\settings\\llm\\.llm_credentials.json.p4alblj5.tmp'
    -> '...\\settings\\llm\\llm_credentials.json'

`app/core/adapters/atomic_file.py` already solves exactly this, and says so in
its own module docstring; the settings files used neither half of it — five
writers hand-rolled the dance and four readers opened with a plain `open()`.

Both halves are load-bearing, and the failure names which one is missing: with
the old publisher this raises WinError 5 (`MoveFileExW` refuses while any handle
is open), and with a publisher fixed but a plain-`open()` reader it raises
WinError 32 (the handle does not share delete). Only both together let a
publish through.

These tests hold a reader open on purpose. They pass on POSIX either way — the
platform makes them true for free — and they are the reproduction on Windows.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core import config
from app.core.adapters.atomic_file import open_published
from app.models.llm_config import LLMCredentialsFile, ProviderEndpoint, RolesData
from app.services.llm_credentials import credentials_path, load_credentials, save_credentials
from app.services.llm_paths import roles_path
from app.services.llm_roles import save_roles_file


def _credentials(display_name: str) -> LLMCredentialsFile:
    return LLMCredentialsFile(
        provider_endpoints={
            "vendor": ProviderEndpoint(
                endpoint_id="vendor",
                display_name=display_name,
                protocol="openai_compatible",
                base_url="https://vendor.example/v1",
                api_key="secret",
            )
        }
    )


def test_credentials_publish_while_something_holds_the_file_open(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    path = credentials_path()
    save_credentials(_credentials("First"), path)

    # Held the way this file is actually read. Both halves have to ask: the
    # reader shares delete, and the publisher renames with POSIX semantics.
    # With either half missing this raises — WinError 5 when the publisher used
    # `os.replace`, WinError 32 when the reader used a plain `open()`.
    with open_published(path) as reader:
        save_credentials(_credentials("Second"), path)
        assert json.loads(reader.read())["provider_endpoints"]["vendor"]["display_name"] == "First"

    assert load_credentials(path).provider_endpoints["vendor"].display_name == "Second"


def test_roles_publish_while_something_holds_the_file_open(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """`llm_roles.yaml` sits in the same watched directory and is resolved by the
    same watcher branch, so it races on exactly the same handle."""
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    path = roles_path()
    save_roles_file(path, RolesData())

    with open_published(path) as reader:
        save_roles_file(path, RolesData(schema_version=3))
        first = reader.read()

    assert "schema_version: 2" in first
    assert "schema_version: 3" in path.read_text(encoding="utf-8")


def test_a_published_settings_file_uses_line_feeds_on_every_platform(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Text is UTF-8 + LF everywhere (docs/development/CROSS_PLATFORM.md).

    Left to its default a text-mode write translates newlines, so the same
    credentials document differs byte for byte depending on which machine saved
    it — and a file whose bytes depend on the host cannot be compared, hashed or
    diffed across the three platforms this project supports.
    """
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    path = credentials_path()

    save_credentials(_credentials("First"), path)

    assert b"\r\n" not in path.read_bytes()
