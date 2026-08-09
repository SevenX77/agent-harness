"""Studio's boundary onto the Engine's on-disk run layout.

The Engine writes run and predict directories, so the Engine names them. Studio
writes into the same directories (run metadata, sealed artifacts) and lists them
back, so the two must agree — and agreeing on one definition means importing it,
not restating it.

This module is where that import happens, so no Studio business service reaches
into the SDK for a path. What crosses here is two functions over `Path`; no SDK
type escapes.
"""

from __future__ import annotations

from graph_agent.io.run_layout import (
    PREDICTS_DIRNAME as PREDICTS_DIRNAME,
)
from graph_agent.io.run_layout import (
    RUNS_DIRNAME as RUNS_DIRNAME,
)
from graph_agent.io.run_layout import (
    predicts_root as predicts_root,
)
from graph_agent.io.run_layout import (
    runs_root as runs_root,
)

__all__ = ["PREDICTS_DIRNAME", "RUNS_DIRNAME", "predicts_root", "runs_root"]
