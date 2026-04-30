from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STUDIO_BACKEND = REPO_ROOT / "studio-backend"
SRC_CORE = REPO_ROOT / "src" / "core"

for path in (STUDIO_BACKEND, SRC_CORE):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
