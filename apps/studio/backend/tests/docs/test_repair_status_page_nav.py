from pathlib import Path

STATUS_PAGE = (
    Path(__file__).resolve().parents[5]
    / "docs/studio/mvp1/_impl/wave2/studio-mvp1-12d-repair-framework-2026-06-15.html"
)


def test_followups_do_not_render_sidebar_nodes_without_pages() -> None:
    html = STATUS_PAGE.read_text(encoding="utf-8")

    assert "id=\"nav-' + d.id + '-fu" not in html
    assert "follow-up · ' + short" not in html


def test_repair_nav_row_carries_followup_summary() -> None:
    html = STATUS_PAGE.read_text(encoding="utf-8")

    assert "followupRepairSummary(d)" in html
    assert "follow-up " in html
