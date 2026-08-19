"""Out-of-process probe: engine state types survive a checkpoint round-trip.

Run as a script, once per msgpack mode, by
``test_checkpoint_state_type_registry.py``. It lives out of process because
``langgraph.checkpoint.serde._msgpack`` reads ``LANGGRAPH_STRICT_MSGPACK``
once, at import time — a test cannot turn strict mode on inside the pytest
process that already imported langgraph.

The leading underscore keeps this file out of pytest's ``test_*.py``
collection glob.

Output contract: one ``<backend> data=<type> flow=<type>`` line per backend on
stdout; every langgraph serde warning on stderr. The caller asserts on both.
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from graph_agent.core.checkpointer import checkpointer_context
from graph_agent.core.state import WorkflowState


def _round_trip(saver: Any, thread_id: str) -> dict[str, Any]:
    """Run one node through ``saver`` and read the checkpoint back through it.

    The read goes through the checkpointer object rather than
    ``graph.get_state`` on purpose: that is the out-of-band read the engine
    itself performs (``core/checkpoint_validity.checkpoint_id_before_phase``
    walks ``checkpointer.list(...)``), and it is the read that loses the state
    types when the checkpointer has not been told what they are.
    """
    builder: Any = StateGraph(WorkflowState)
    builder.add_node(
        "phase",
        lambda state: {
            "data": {"answer": "ok"},
            "flow": {"current_phase": "phase"},
        },
    )
    builder.add_edge(START, "phase")
    builder.add_edge("phase", END)
    graph = builder.compile(checkpointer=saver)

    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke({"data": {}, "flow": {}, "messages": []}, config=config)

    restored = saver.get_tuple(config)
    assert restored is not None, f"{thread_id}: checkpointer stored nothing"
    values: dict[str, Any] = restored.checkpoint["channel_values"]
    return values


def main() -> int:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    with tempfile.TemporaryDirectory() as tmp:
        for backend, db_path in (
            ("memory", None),
            ("sqlite", str(Path(tmp) / "checkpoints.db")),
        ):
            with checkpointer_context(db_path, backend=backend) as saver:
                values = _round_trip(saver, f"thread-{backend}")
            print(
                f"{backend} "
                f"data={type(values['data']).__name__} "
                f"flow={type(values['flow']).__name__}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
