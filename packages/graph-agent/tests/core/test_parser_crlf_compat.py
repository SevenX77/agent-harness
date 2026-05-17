from __future__ import annotations

from graph_agent.core.parser import parse_markdown_parts


def test_parse_markdown_parts_accepts_crlf_on_disk(tmp_path):
    path = tmp_path / "GRAPH.md"
    path.write_bytes(
        b'---\r\nschema_version: "2.1"\r\nname: crlf-skill\r\n---\r\n<body />\r\n'
    )

    frontmatter, body, meta = parse_markdown_parts(path)

    assert frontmatter["schema_version"] == "2.1"
    assert frontmatter["name"] == "crlf-skill"
    assert "<body />" in body
    assert meta["body_start"] == 5
