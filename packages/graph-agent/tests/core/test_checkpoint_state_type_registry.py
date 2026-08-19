"""The engine names the state types it puts in a checkpoint.

langgraph's msgpack serializer rebuilds a checkpointed object only when the
serializer was told the object's type is expected. Left at its default it
allows every type through and logs one warning per type per process
(``Deserializing unregistered type ...``); with ``LANGGRAPH_STRICT_MSGPACK``
it rebuilds nothing but a built-in safe list and hands back the raw payload
dict instead. Either way, a type the engine never declared is a type the
engine cannot rely on getting back.

Two gates live here:

* :func:`test_checkpoint_state_type_registry_names_every_engine_state_model`
  is the declaration gate — it fails when a state model is added to the
  ``WorkflowState`` schema and not added to ``CHECKPOINT_STATE_TYPES``.
* the probe tests are the behaviour gate — they run a real checkpoint round
  trip in a child process, in both msgpack modes, and fail when a type is
  blocked, warned about, or handed back untyped.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any, get_args, get_origin, get_type_hints

import pytest
from pydantic import BaseModel
from typing_extensions import is_typeddict

from graph_agent.core.checkpointer import CHECKPOINT_STATE_TYPES
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState

_PROBE = Path(__file__).with_name("_engine_checkpoint_roundtrip_probe.py")

_ENGINE_PACKAGE = "graph_agent."

_UNREGISTERED_WARNING = "Deserializing unregistered type"
_BLOCKED_WARNING = "Blocked deserialization of"


def _already_walked(annotation: Any, seen: dict[int, Any]) -> bool:
    """Track visited annotations by identity.

    Identity rather than equality because an ``Annotated[...]`` alias hashes
    its metadata, and ``WorkflowState``'s messages channel carries a
    ``DeltaChannel`` instance there, which is unhashable.

    ``seen`` maps id to the annotation itself rather than being a set of ids:
    the reference keeps each visited annotation alive for the whole walk, so
    CPython cannot hand a freed object's id to a later one and make this
    report an unvisited subtree as already walked. A stale id here would skip
    a subtree and let an unregistered model through — the gate failing open is
    the one outcome it must not have.
    """
    key = id(annotation)
    if key in seen:
        return True
    seen[key] = annotation
    return False


def _models_under_typeddict(annotation: Any, seen: dict[int, Any]) -> set[type[BaseModel]]:
    found: set[type[BaseModel]] = set()
    for field in get_type_hints(annotation, include_extras=True).values():
        found |= _reachable_models(field, seen)
    return found


def _models_under_model(annotation: type[BaseModel], seen: dict[int, Any]) -> set[type[BaseModel]]:
    """Return the model itself plus, if the engine owns it, its field models.

    Recursion stops at models the engine does not own: langgraph's built-in
    safe list already covers the langchain message models, and a foreign
    model's internals are not the engine's to declare. The
    ``foreign``-vs-``owned`` split is asserted separately below, so a foreign
    model from a NEW source still surfaces instead of being absorbed here.
    """
    found: set[type[BaseModel]] = {annotation}
    if not annotation.__module__.startswith(_ENGINE_PACKAGE):
        return found
    for field_info in annotation.model_fields.values():
        if field_info.annotation is not None:
            found |= _reachable_models(field_info.annotation, seen)
    return found


def _models_under_generic(annotation: Any, seen: dict[int, Any]) -> set[type[BaseModel]]:
    """Descend into a parameterized annotation such as ``list[X]`` or ``X | None``.

    ``Annotated[X, ...]`` descends only into ``X``: its metadata holds channel
    reducers, not state types.
    """
    if get_origin(annotation) is None:
        return set()
    args = get_args(annotation)
    if get_origin(annotation) is Annotated:
        return _reachable_models(args[0], seen)
    found: set[type[BaseModel]] = set()
    for arg in args:
        found |= _reachable_models(arg, seen)
    return found


def _reachable_models(annotation: Any, seen: dict[int, Any]) -> set[type[BaseModel]]:
    """Collect the pydantic models reachable from a state annotation."""
    if _already_walked(annotation, seen):
        return set()
    if is_typeddict(annotation):
        return _models_under_typeddict(annotation, seen)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _models_under_model(annotation, seen)
    return _models_under_generic(annotation, seen)


def test_checkpoint_state_type_registry_names_every_engine_state_model() -> None:
    reachable = _reachable_models(WorkflowState, {})

    owned = {m for m in reachable if m.__module__.startswith(_ENGINE_PACKAGE)}
    assert owned == set(CHECKPOINT_STATE_TYPES), (
        "every engine-owned state model reachable from WorkflowState must be "
        "declared in CHECKPOINT_STATE_TYPES, or a checkpoint hands it back as "
        "a plain dict"
    )
    assert {BusinessData, FrameworkState} <= owned

    foreign = {m for m in reachable if not m.__module__.startswith(_ENGINE_PACKAGE)}
    assert {m.__module__.split(".")[0] for m in foreign} == {"langchain_core"}, (
        "state models from a new third-party package appeared; rule on whether "
        "langgraph's built-in safe list covers them before letting them into "
        "the state schema"
    )


def _run_probe(*, strict: bool) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if strict:
        env["LANGGRAPH_STRICT_MSGPACK"] = "true"
    else:
        env.pop("LANGGRAPH_STRICT_MSGPACK", None)
    # The child's stdout/stderr are pipes, so CPython would otherwise encode
    # them with the machine's locale codepage (cp936 on this repo's Windows
    # dev box) while the parent below decodes UTF-8. Pinning both ends is the
    # repo's cross-platform rule, not a Windows workaround.
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(_PROBE)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )


@pytest.mark.parametrize("strict", [False, True], ids=["permissive", "strict"])
def test_engine_state_types_survive_a_checkpoint_round_trip(strict: bool) -> None:
    result = _run_probe(strict=strict)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "memory data=BusinessData flow=FrameworkState",
        "sqlite data=BusinessData flow=FrameworkState",
    ], result.stdout


@pytest.mark.parametrize("strict", [False, True], ids=["permissive", "strict"])
def test_checkpoint_round_trip_logs_no_serde_complaint(strict: bool) -> None:
    result = _run_probe(strict=strict)

    assert _UNREGISTERED_WARNING not in result.stderr, result.stderr
    assert _BLOCKED_WARNING not in result.stderr, result.stderr
