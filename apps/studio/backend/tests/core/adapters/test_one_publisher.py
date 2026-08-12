"""There is one way to publish a file, and it is not `os.replace`.

Five modules had each written the same publish-by-rename dance by hand, and all
five renamed with `os.replace` — the one Win32 call that refuses while any
handle is open on the destination. They were not wrong in the same way by
coincidence: `os.replace` is what the obvious reading of "atomic write"
suggests, so the sixth copy would have made the same choice.

`write_text_atomically` / `open_published` are the pair that works on all three
platforms, and this keeps them the only pair. A module that genuinely needs a
different rename can add itself to the exemption below with a reason — the
point is that it becomes a decision somebody made rather than a default nobody
noticed.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3] / "app"

# The publisher itself: it owns the platform-specific rename this rule exists
# to funnel everything through.
EXEMPT = {BACKEND_ROOT / "core" / "adapters" / "atomic_file.py"}


def _renames_by_hand(source: Path) -> list[int]:
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "replace"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    ]


def test_only_the_publisher_renames_a_file_into_place() -> None:
    offenders = {
        str(path.relative_to(BACKEND_ROOT)): lines
        for path in sorted(BACKEND_ROOT.rglob("*.py"))
        if path not in EXEMPT and (lines := _renames_by_hand(path))
    }

    assert offenders == {}, (
        "publish through app.core.adapters.atomic_file.write_text_atomically; "
        f"os.replace refuses on Windows while a reader holds the file: {offenders}"
    )
