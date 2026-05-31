from __future__ import annotations

import pytest
from typing import Any
from pydantic import BaseModel

# Try to import input_hash. This will fail in Red Phase!
try:
    from graph_agent.core._predict_internal.hash import input_hash
except ImportError:
    input_hash = None  # type: ignore


class SimpleModel(BaseModel):
    name: str
    value: int


def test_input_hash_canonical_normalization() -> None:
    assert input_hash is not None, "input_hash function must be defined"
    
    inputs_1 = {"a": 1, "b": "hello", "c": [1, 2, 3]}
    inputs_2 = {"c": [1, 2, 3], "a": 1, "b": "hello"}  # Different key order
    
    hash_1 = input_hash(inputs_1)
    hash_2 = input_hash(inputs_2)
    
    assert hash_1 == hash_2, "input_hash must be independent of key order"
    assert isinstance(hash_1, str) and len(hash_1) == 64, "input_hash must return sha256 hex string"


def test_input_hash_pydantic_model_safety() -> None:
    assert input_hash is not None, "input_hash function must be defined"
    
    model = SimpleModel(name="test_name", value=42)
    inputs_with_model = {
        "item": model,
        "flag": True
    }
    
    # This must NOT throw TypeError due to Pydantic model not being JSON serializable.
    # It must serialize it using model_dump(mode="json") or default Pydantic serialization.
    try:
        h = input_hash(inputs_with_model)
        assert isinstance(h, str)
    except TypeError as exc:
        pytest.fail(f"input_hash crashed with TypeError on Pydantic model: {exc}")
