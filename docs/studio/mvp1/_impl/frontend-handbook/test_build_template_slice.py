"""Guards that the generated handbook references screenshots instead of inlining them.

`index.html` is a derived artifact regenerated whenever a slice changes, and it
is committed so the page can be served from the main repo root. Inlining the
147 PNGs as base64 made each regeneration rewrite ~18 MB of high-entropy text
that git cannot delta-compress — 132 such versions cost 1.9 GB of history for
14 MB of screenshots that are already committed alongside.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

HANDBOOK = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location("build_template_slice", HANDBOOK / "build_template_slice.py")
assert _spec is not None and _spec.loader is not None
build_template_slice = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_template_slice)

DATA_URI = re.compile(r"data:image/[a-z]+;base64,")
SHOT_SRC = re.compile(r'src="(screenshots/[^"]+)"')


def test_embed_shot_emits_a_relative_path() -> None:
    """A screenshot becomes an <img src="screenshots/...">, never a data URI."""
    first_shot = sorted(build_template_slice.SHOTS.glob("*.png"))[0]

    markup = build_template_slice.embed_shot(first_shot.name, caption="probe")

    assert f'src="screenshots/{first_shot.name}"' in markup, markup
    assert not DATA_URI.search(markup), "screenshot was inlined as a data URI"


def test_committed_handbook_inlines_no_images() -> None:
    """The committed index.html must stay free of inlined image payloads."""
    html = build_template_slice.OUT.read_text(encoding="utf-8")

    assert not DATA_URI.search(html), (
        f"{build_template_slice.OUT.name} still inlines images as base64 — regenerate it with build_template_slice.py"
    )


def test_every_referenced_screenshot_exists() -> None:
    """Relative srcs only work if the PNG is committed next to the page."""
    html = build_template_slice.OUT.read_text(encoding="utf-8")

    referenced = {Path(m) for m in SHOT_SRC.findall(html)}
    assert referenced, "no screenshot references found — did the page lose its shots?"

    missing = sorted(str(p) for p in referenced if not (HANDBOOK / p).exists())
    assert not missing, f"referenced screenshots are not on disk: {missing}"
