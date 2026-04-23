"""graph_agent builtin tools.

Tools under this package are loadable from any SKILL.md by writing
``tools: [builtin.<tool_name>]`` — the loader special-cases references
beginning with ``builtin.`` to look here instead of inside the calling
skill's directory.
"""
from __future__ import annotations

from .parallel_map import parallel_map

__all__ = ["parallel_map"]
