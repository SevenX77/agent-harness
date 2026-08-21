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
from app.core.authored_text import read_authored_text
from app.services.golden_diff import workspace_text_hash
from app.services.runtime_config import _input_fields_from_markdown, read_runtime_config

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


def test_a_signed_runtime_config_reads_the_same_as_an_unsigned_one(tmp_path: Path) -> None:
    """``json.loads`` does not merely mis-read a signed file — it refuses it.

    Asserted as "the signature changes nothing" rather than against one field,
    because what the config merge does with any given key is that function's
    business; the signature must not be able to alter the answer either way.
    """
    payload = json.dumps({"import_inputs": {"version": 2, "files": []}})
    signed_dir = tmp_path / "signed"
    plain_dir = tmp_path / "plain"
    _signed(signed_dir / ".workspace" / "runtime_config.json", payload)
    plain = plain_dir / ".workspace" / "runtime_config.json"
    plain.parent.mkdir(parents=True)
    plain.write_text(payload, encoding="utf-8")

    assert read_runtime_config(signed_dir) == read_runtime_config(plain_dir)


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
