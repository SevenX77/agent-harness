"""Tests for RunContext dataclass."""
from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError
from pathlib import Path

from graph_agent.core.run_context import RunContext


class TestRunContext:
    """Test RunContext frozen dataclass behavior."""

    def test_default_field_values(self):
        """Test that optional fields have correct defaults."""
        ctx = RunContext(thread_id="test-123")
        
        assert ctx.thread_id == "test-123"
        assert ctx.trace_dir is None
        assert ctx.runtime_inputs == {}
        assert ctx.storage_manager is None
        assert ctx.artifact_saver is None
        assert ctx.callbacks == []

    def test_frozen_cannot_reassign_attributes(self):
        """frozen=True protects attribute *reassignment*; mutating the
        mutable dict / list *contents* of runtime_inputs / callbacks is
        still allowed by Python's dataclass frozen semantics.

        We document both behaviors: reassigning the attribute raises,
        mutating the container does not — call sites must respect the
        "RunContext is read-only per run" contract by convention.
        """
        ctx = RunContext(thread_id="test-456")

        with pytest.raises(FrozenInstanceError):
            ctx.thread_id = "modified"

        with pytest.raises(FrozenInstanceError):
            ctx.trace_dir = Path("/tmp")

        with pytest.raises(FrozenInstanceError):
            ctx.runtime_inputs = {"new": "dict"}

        # Mutating the container contents is *not* blocked by
        # frozen=True. Enforcing deep immutability would require wrapping
        # the dict in MappingProxyType which adds noise to every caller
        # that just reads from it.
        ctx.runtime_inputs["ok_this_works"] = "value"
        assert ctx.runtime_inputs["ok_this_works"] == "value"

    def test_runtime_inputs_is_independent(self):
        """Test that runtime_inputs is not shared between instances."""
        ctx1 = RunContext(thread_id="test-1")
        ctx2 = RunContext(thread_id="test-2")
        
        # Verify they don't share the same dict
        assert ctx1.runtime_inputs is not ctx2.runtime_inputs
        
        # Modify one, verify other is unaffected
        ctx1_dict = ctx1.runtime_inputs
        ctx1_dict["key"] = "value"
        
        ctx3 = RunContext(thread_id="test-3")
        assert ctx3.runtime_inputs == {}
        assert "key" not in ctx3.runtime_inputs

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
