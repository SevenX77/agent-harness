"""How Studio mints a run id, and what an id tells you back.

Studio is the only producer of these ids, so the shape is Studio's to define and
Studio's to read. That is what makes the prefix usable as a fact here and not in
the engine: the engine receives ids it did not mint, and a library that infers
storage layout from a string it does not own files somebody else's run in the
wrong place the day their convention differs.
"""

from __future__ import annotations

import uuid
from datetime import datetime

PREDICT_RUN_ID_PREFIX = "predict-"


def _local_now() -> datetime:
    """The wall clock on the machine producing the run.

    Run ids are read by a person looking at a folder listing, and a UTC stamp
    reads as the wrong time to that person. This is deliberately naive: the id
    is a label for humans, never a value anything computes with.
    """
    return datetime.now()


def _id_stamp() -> str:
    return _local_now().strftime("%Y-%m-%dT%H-%M-%S")


def new_run_id() -> str:
    return f"{_id_stamp()}_{uuid.uuid4().hex[:8]}"


def new_predict_run_id() -> str:
    """A predict id is a run id wearing a prefix.

    Same producer, so the two shapes cannot drift apart — which is exactly how
    predict ended up as a bare uuid that sorted by nothing.
    """
    return f"{PREDICT_RUN_ID_PREFIX}{new_run_id()}"


def is_predict_run_id(run_id: str) -> bool:
    """Whether this id names a rehearsal rather than a run.

    Predict artifacts live in their own root, and every path helper needs to
    pick that root from the only thing a caller reliably has: the id.
    """
    return run_id.startswith(PREDICT_RUN_ID_PREFIX)
