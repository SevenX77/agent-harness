"""Tests for RunContext dataclass."""

from __future__ import annotations

import types
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from graph_agent.core.run_context import RunContext


class TestRunContext:
    """Test RunContext frozen dataclass behavior."""

    def test_default_field_values(self):
        """Test that optional fields have correct defaults."""
        ctx = RunContext(thread_id="test-123")

        assert ctx.thread_id == "test-123"
        assert ctx.trace_dir is None
        # runtime_inputs is wrapped in MappingProxyType; equality still
        # delegates to the underlying dict so the == check works.
        assert ctx.runtime_inputs == {}
        assert isinstance(ctx.runtime_inputs, types.MappingProxyType)
        assert ctx.storage_manager is None
        assert ctx.artifact_saver is None
        # callbacks is normalised to tuple (immutable) at __post_init__.
        assert ctx.callbacks == ()
        assert isinstance(ctx.callbacks, tuple)

    def test_frozen_cannot_reassign_attributes(self):
        """``frozen=True`` blocks attribute reassignment for all fields."""
        ctx = RunContext(thread_id="test-456")

        with pytest.raises(FrozenInstanceError):
            ctx.thread_id = "modified"

        with pytest.raises(FrozenInstanceError):
            ctx.trace_dir = Path("/tmp")

        with pytest.raises(FrozenInstanceError):
            ctx.runtime_inputs = {"new": "dict"}

        with pytest.raises(FrozenInstanceError):
            ctx.callbacks = [object()]

    def test_runtime_inputs_and_callbacks_are_shallowly_immutable(self):
        """Post-D session blind-spot-1 fix: ``runtime_inputs`` is wrapped in
        ``MappingProxyType`` and ``callbacks`` in ``tuple`` so a runtime
        collaborator (PhaseExecutor, NudgeInjector, subgraph node) that only
        holds a reference cannot mutate them and clobber a sibling run.

        This is a *shallow* freeze — nested mutable values inside
        ``runtime_inputs`` (e.g. a dict value) are still mutable. Enforcing
        deep immutability is out of scope; the 99% case we're protecting
        against is ``ctx.runtime_inputs["key"] = "x"``.
        """
        ctx = RunContext(
            thread_id="t",
            runtime_inputs={"nested": {"mutable": True}},
            callbacks=[],
        )

        with pytest.raises(TypeError):
            ctx.runtime_inputs["new_key"] = "value"  # type: ignore[index]

        with pytest.raises(AttributeError):
            # tuples have no .append
            ctx.callbacks.append(object())  # type: ignore[attr-defined]

        # Nested mutation is not blocked (documented limitation).
        ctx.runtime_inputs["nested"]["added"] = True
        assert ctx.runtime_inputs["nested"]["added"] is True

    def test_runtime_inputs_is_independent(self):
        """Test that runtime_inputs is not shared between instances.

        After the MappingProxyType switch we can no longer mutate
        ``ctx.runtime_inputs`` directly to prove independence — instead,
        assert each instance wraps its own underlying dict and equality
        with a fresh empty dict still holds.
        """
        ctx1 = RunContext(thread_id="test-1", runtime_inputs={"a": 1})
        ctx2 = RunContext(thread_id="test-2")

        assert ctx1.runtime_inputs == {"a": 1}
        assert ctx2.runtime_inputs == {}
        # Each proxy wraps a distinct underlying dict — mutating the source
        # of ctx1 does not leak into ctx2.
        assert ctx1.runtime_inputs is not ctx2.runtime_inputs

    def test_custom_values(self):
        """Test that custom values are properly assigned."""

        def dummy_saver():
            pass

        ctx = RunContext(
            thread_id="custom-id",
            trace_dir=Path("/custom/path"),
            runtime_inputs={"input": "value"},
            storage_manager={"manager": True},
            artifact_saver=dummy_saver,
            callbacks=[],
        )

        assert ctx.thread_id == "custom-id"
        assert ctx.trace_dir == Path("/custom/path")
        assert ctx.runtime_inputs == {"input": "value"}
        assert ctx.storage_manager == {"manager": True}
        assert ctx.artifact_saver is dummy_saver
        assert ctx.callbacks == ()
