"""Tests for read_file builtin tool."""
from __future__ import annotations

from pathlib import Path

from graph_agent.tools.builtin.read_file import make_read_file_tool


class TestReadFileBuiltin:
    def test_reads_file_from_references_dir(self, tmp_path: Path) -> None:
        ref_dir = tmp_path / "references"
        ref_dir.mkdir()
        (ref_dir / "01_role.md").write_text("# Role definition\n", encoding="utf-8")

        tool_fn = make_read_file_tool(["references/01_role.md"], tmp_path)
        result = tool_fn({}, "references/01_role.md")

        assert "# Role definition" in result

    def test_path_normalization(self, tmp_path: Path) -> None:
        ref_dir = tmp_path / "references"
        ref_dir.mkdir()
        (ref_dir / "foo.md").write_text("content", encoding="utf-8")

        tool_fn = make_read_file_tool(["references/foo.md"], tmp_path)

        assert "content" in tool_fn({}, "references/foo.md")
        assert "content" in tool_fn({}, "foo.md")

    def test_file_not_found_returns_error(self, tmp_path: Path) -> None:
        tool_fn = make_read_file_tool(["references/missing.md"], tmp_path)

        result = tool_fn({}, "references/missing.md")

        assert "[read_file Error] File not found" in result
        assert "Available references" in result

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        secret = tmp_path.parent / "secret.txt"
        secret.write_text("secret data", encoding="utf-8")
        try:
            ref_dir = tmp_path / "references"
            ref_dir.mkdir()
            tool_fn = make_read_file_tool([], tmp_path)

            result = tool_fn({}, "../secret.txt")

            assert "[read_file Error]" in result
            assert "secret data" not in result
        finally:
            secret.unlink(missing_ok=True)

    def test_file_too_large_blocked(self, tmp_path: Path) -> None:
        ref_dir = tmp_path / "references"
        ref_dir.mkdir()
        big = ref_dir / "big.md"
        big.write_text("x" * 300_000, encoding="utf-8")

        tool_fn = make_read_file_tool(["references/big.md"], tmp_path)
        result = tool_fn({}, "references/big.md")

        assert "File too large" in result

    def test_directory_path_returns_error(self, tmp_path: Path) -> None:
        ref_dir = tmp_path / "references"
        ref_dir.mkdir()
        (ref_dir / "subdir").mkdir()
        tool_fn = make_read_file_tool([], tmp_path)

        result = tool_fn({}, "references/subdir")

        assert "[read_file Error]" in result
        assert "File not found" in result

    def test_non_reference_skill_file_blocked(self, tmp_path: Path) -> None:
        (tmp_path / "SKILL.md").write_text("private prompt", encoding="utf-8")
        tool_fn = make_read_file_tool([], tmp_path)

        result = tool_fn({}, "SKILL.md")

        assert "[read_file Error]" in result
        assert "private prompt" not in result
