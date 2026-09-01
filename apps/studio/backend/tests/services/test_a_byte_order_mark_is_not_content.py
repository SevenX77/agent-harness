"""What an outside editor prepends is encoding, and the backend must not read it as text.

Windows editors write a UTF-8 byte-order mark (bytes ``EF BB BF``) at the start
of a file by default — Notepad does, PowerShell redirection does. A skill
authored outside Studio therefore arrives with one, and every reader that
decodes it as ``utf-8`` gets a ``\\ufeff`` character sitting in front of the
author's first real character.

The backend used to answer this two ways at once: ``runtime_config`` reads a
workspace JSON file with ``utf-8-sig`` and, twelve lines away, an authored
markdown file with ``utf-8``. Ledger K7 is what the second answer costs.

The hash cases below are the sharpest of the lot. The Rust native-fs layer is
the sole writer of skill files and drops the mark when it reads one; if the
backend keeps it, the two sides compute different hashes for the same file, and
every optimistic-lock write on a signed file reports a conflict that never
happened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core.adapters.storage_local import LocalFilesystemBackend
from app.core.authored_text import read_authored_text
from app.services import run_manager
from app.services.golden_diff import workspace_text_hash
from app.services.local_settings import read_local_settings
from app.services.runtime_config import (
    _graph_phase_ids,
    _input_fields_from_markdown,
    ensure_import_layout,
    read_runtime_config,
)
from app.services.skills import _graph_content_hash, _read_current_graph_markdown
from app.services.validator import _parse_input_file

BOM = b"\xef\xbb\xbf"

PHASE_MARKDOWN = """---
name: alpha
io:
  inputs:
    properties:
      topic: {type: string}
      depth: {type: integer}
---

body
"""

GRAPH_MARKDOWN = """---
schema_version: "v0.3.0"
name: signed-skill
description: a skill an outside editor saved
phases:
  - setup
  - review
---
<phase depends_on="input" output>setup</phase>
"""


def _signed(path: Path, text: str) -> Path:
    """Write a file exactly as a Windows editor leaves it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(BOM + text.encode("utf-8"))
    return path


def test_the_exit_drops_the_signature(tmp_path: Path) -> None:
    assert read_authored_text(_signed(tmp_path / "GRAPH.md", "---\nname: x\n---\n")) == (
        "---\nname: x\n---\n"
    )


def test_the_exit_keeps_a_mark_that_is_not_the_signature(tmp_path: Path) -> None:
    """Only the leading one is encoding; further in it is a character the author typed."""
    inner = tmp_path / "note.md"
    inner.write_text("plain\ufeffword", encoding="utf-8")

    assert read_authored_text(inner) == "plain\ufeffword"


def test_a_signed_phase_still_declares_its_inputs(tmp_path: Path) -> None:
    """The frontmatter matcher is anchored, so the mark hides the whole block."""
    path = _signed(tmp_path / "LOGIC.md", PHASE_MARKDOWN)

    assert _input_fields_from_markdown(path) == {"topic", "depth"}


def test_a_signed_graph_still_declares_its_phases(tmp_path: Path) -> None:
    """K7's own shape, and the half of it that was still unfixed.

    ``_input_fields_from_markdown`` above went through the shared exit; the graph
    reader twelve lines away kept plain ``utf-8``, so a signed ``GRAPH.md``
    answered "zero phases" — the exact symptom the ledger recorded — and did so
    SILENTLY: ``_frontmatter_block`` tests ``startswith("---")``, and a leading
    ``\\ufeff`` makes that false, which is indistinguishable from a file that
    genuinely has no frontmatter.
    """
    skill_dir = tmp_path / "signed-skill"
    _signed(skill_dir / "GRAPH.md", GRAPH_MARKDOWN)

    assert _graph_phase_ids(skill_dir) == ["setup", "review"]


def test_a_signed_graph_still_gets_its_per_phase_import_directories(tmp_path: Path) -> None:
    """What the silence actually costs the user, asserted at the public surface.

    ``ensure_import_layout`` derives the per-phase import directories from the
    graph's phase list. Reading zero phases is not an error there — it is a valid
    instruction to create nothing and prune whatever exists, so a signed file
    leaves the user with no per-phase import slots and no diagnostic naming why.
    """
    skill_dir = tmp_path / "signed-skill"
    _signed(skill_dir / "GRAPH.md", GRAPH_MARKDOWN)

    assert ensure_import_layout(skill_dir) == ["review", "setup"]


def test_a_signed_graph_hashes_for_the_canvas_lock_like_the_writer_reads_it(tmp_path: Path) -> None:
    """The optimistic-lock case this module's docstring calls the sharpest of the lot.

    ``_read_current_graph_markdown`` feeds ``_graph_content_hash``, and that hash
    is compared against the one the frontend holds — which came from the Rust
    native-fs layer, the sole writer, which DOES drop the mark
    (``native_fs.rs``: ``if text.starts_with('\\u{feff}') { text.drain(..) }``).
    Keeping it on this side makes the two sides hash the same bytes differently,
    so every canvas save of a signed ``GRAPH.md`` reports a conflict that did not
    happen — and a conflict the user cannot clear, because nothing is actually
    out of date.
    """
    signed_dir = tmp_path / "signed"
    plain_dir = tmp_path / "plain"
    _signed(signed_dir / "GRAPH.md", GRAPH_MARKDOWN)
    plain = plain_dir / "GRAPH.md"
    plain.parent.mkdir(parents=True)
    plain.write_text(GRAPH_MARKDOWN, encoding="utf-8")

    assert _graph_content_hash(_read_current_graph_markdown(signed_dir)) == _graph_content_hash(
        _read_current_graph_markdown(plain_dir)
    )


def test_a_signed_runtime_config_reads_the_same_as_an_unsigned_one(tmp_path: Path) -> None:
    """``json.loads`` does not merely mis-read a signed file — it refuses it.

    Asserted as "the signature changes nothing" rather than against one field,
    because what the config merge does with any given key is that function's
    business; the signature must not be able to alter the answer either way.

    ``updated_at`` is the exception, and it is not content: ``_with_fingerprint``
    stamps it with the clock on every read, which is why the module leaves it out
    of its own fingerprint. Two reads of the SAME file disagree there too. The
    ``fingerprint`` that stays in the comparison is the module's own answer to
    "is this the same config", so nothing is being waved through.
    """
    payload = json.dumps({"import_inputs": {"version": 2, "files": []}})
    signed_dir = tmp_path / "signed"
    plain_dir = tmp_path / "plain"
    _signed(signed_dir / ".workspace" / "runtime_config.json", payload)
    plain = plain_dir / ".workspace" / "runtime_config.json"
    plain.parent.mkdir(parents=True)
    plain.write_text(payload, encoding="utf-8")

    from_signed = read_runtime_config(signed_dir)
    from_plain = read_runtime_config(plain_dir)
    del from_signed["updated_at"], from_plain["updated_at"]

    assert from_signed == from_plain


def test_a_signed_test_input_still_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A declared test input is workspace content, so the same rule governs it.

    Sharper than the markdown cases rather than milder: ``json.loads`` does not
    silently mis-read a signed file, it refuses it outright with ``Expecting
    value: line 1 column 1``, which names neither the byte-order mark nor the
    file. The user sees a run refuse to start over an input they can open and
    read.
    """
    skill_dir = tmp_path / "signed-skill"
    _signed(
        skill_dir / ".workspace" / "import_files" / "smoke.json",
        json.dumps({"input_data": {"topic": "signed"}}),
    )
    monkeypatch.setattr(run_manager, "resolve_skill_dir", lambda _skill_id: skill_dir)

    assert run_manager._load_test_input("signed-skill", "smoke") == {"topic": "signed"}


def test_a_signed_validation_input_still_validates(tmp_path: Path) -> None:
    """``/validate_input`` reads a file the user picked out of their own workspace.

    Its failure is the one that misdirects hardest: the endpoint catches the
    decode error and answers 422 "invalid input file", which reads as a verdict
    on the CONTENT the user wrote rather than on how we opened it.
    """
    signed = _signed(tmp_path / "case.json", json.dumps({"topic": "signed"}))

    assert _parse_input_file(signed) == {"topic": "signed"}


def test_signed_local_settings_still_load(tmp_path: Path) -> None:
    """``.workspace/local_settings.json`` is named in the jurisdiction by path.

    Studio writes this file itself, so it carries no signature of ours — but the
    directory it lives in belongs to the user, who may copy, edit or regenerate
    it with any editor. What decides the reader is where the file lives, not who
    last wrote it.
    """
    skill_dir = tmp_path / "signed-skill"
    _signed(
        skill_dir / ".workspace" / "local_settings.json",
        json.dumps({"selected_phase": "setup"}),
    )

    assert read_local_settings(skill_dir) == {"selected_phase": "setup"}


@pytest.mark.anyio
async def test_the_storage_port_reads_authored_text_without_the_signature(tmp_path: Path) -> None:
    """The async transport has to answer the same as the sync one.

    ``StorageBackend`` is how services reach the disk, so a service that needs a
    signature-free read had only two options before this method existed: bypass
    the port, or keep the mark. Both are defects — the first drops the boundary
    and does blocking I/O on the event loop, the second is K7 again — so the port
    itself carries the rule.
    """
    _signed(tmp_path / "GRAPH.md", GRAPH_MARKDOWN)
    backend = LocalFilesystemBackend(tmp_path)

    assert await backend.read_authored_text("GRAPH.md") == GRAPH_MARKDOWN
    assert await backend.read_text("GRAPH.md") == "﻿" + GRAPH_MARKDOWN


def test_a_signed_file_hashes_like_the_writer_reads_it(tmp_path: Path) -> None:
    """Same content, same hash, signature or not — or the optimistic lock deadlocks."""
    content = '{"expected_output": {"summary": "hi"}}\n'
    signed = _signed(tmp_path / "signed.json", content)
    plain = tmp_path / "plain.json"
    plain.write_text(content, encoding="utf-8")

    assert workspace_text_hash(read_authored_text(signed)) == workspace_text_hash(
        read_authored_text(plain)
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_the_two_normalizations_compose(tmp_path: Path, newline: str) -> None:
    """A Windows editor writes both a signature and CRLF; neither may reach the hash."""
    body = newline.join(["---", "name: x", "---", ""])
    path = _signed(tmp_path / f"crlf{len(newline)}.md", body)

    assert workspace_text_hash(read_authored_text(path)) == workspace_text_hash(
        "---\nname: x\n---\n"
    )
