"""Allow ``python -m graph_agent`` to run the CLI."""
from __future__ import annotations

from .core.runner import main

if __name__ == "__main__":
    main()
