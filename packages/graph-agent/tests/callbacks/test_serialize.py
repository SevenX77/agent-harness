"""Tests for to_jsonable_dict (T-A3)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from graph_agent.callbacks.serialize import to_jsonable_dict  # noqa: E402


class _ExamplePydantic(BaseModel):
    name: str
    count: int


class TestPrimitives:
    @pytest.mark.parametrize("value", [None, True, False, 0, 3.14, "hi"])
    def test_passthrough(self, value):
        assert to_jsonable_dict(value) == value


class TestStdlibStructural:
    def test_path(self):
        assert to_jsonable_dict(Path("/tmp/x")) == "/tmp/x"

    def test_datetime(self):
        dt = datetime(2026, 4, 23, 12, 0, 0, tzinfo=UTC)
        assert to_jsonable_dict(dt) == dt.isoformat()

    def test_uuid(self):
        u = uuid4()
        assert to_jsonable_dict(u) == str(u)

    def test_decimal_preserves_precision(self):
        assert to_jsonable_dict(Decimal("1.2345")) == "1.2345"

    def test_set_sorted(self):
        assert to_jsonable_dict({"b", "a", "c"}) == ["a", "b", "c"]

    def test_frozenset(self):
        assert to_jsonable_dict(frozenset({3, 1, 2})) == [1, 2, 3]


class TestPydantic:
    def test_dump_mode_json(self):
        m = _ExamplePydantic(name="hi", count=3)
        assert to_jsonable_dict(m) == {"name": "hi", "count": 3}


class TestRecursion:
    def test_nested_dict_and_list(self):
        data = {
            "pairs": [(1, "a"), (2, "b")],
            "when": datetime(2026, 4, 23, tzinfo=UTC),
            "tags": {"beta", "alpha"},
        }
        out = to_jsonable_dict(data)
        # list-of-tuple → list-of-list
        assert out["pairs"] == [[1, "a"], [2, "b"]]
        assert out["when"].startswith("2026-04-23")
        assert out["tags"] == ["alpha", "beta"]

    def test_full_json_round_trip(self):
        data = {
            "path": Path("/a/b"),
            "uid": UUID("12345678-1234-5678-1234-567812345678"),
            "amount": Decimal("9.99"),
        }
        out = to_jsonable_dict(data)
        # the whole thing must now be json.dumps-safe
        assert json.dumps(out)  # does not raise


class TestUnsupported:
    def test_unsupported_object_returns_repr_and_warning(self):
        class Opaque:
            def __repr__(self) -> str:
                return "<Opaque instance>"

        out = to_jsonable_dict(Opaque())
        assert isinstance(out, dict)
        assert out["_warning"] == "unsupported_type"
        assert "Opaque" in out["_repr"]

    def test_callable_becomes_documented_stub(self):
        def some_tool():
            pass

        out = to_jsonable_dict(some_tool)
        assert out == {"_type": "callable", "name": "some_tool"}


class TestDepthLimit:
    def test_deep_recursion_is_capped(self):
        # Build a nested dict 25 levels deep (> _MAX_DEPTH=20)
        data: dict = {"v": 1}
        cursor = data
        for _ in range(25):
            cursor["next"] = {}
            cursor = cursor["next"]

        out = to_jsonable_dict(data)
        # Walk down — at some point we must see the "max_depth_exceeded" sentinel
        cur = out
        depth = 0
        while isinstance(cur, dict) and "next" in cur:
            cur = cur["next"]
            depth += 1
            if isinstance(cur, dict) and cur.get("_warning") == "max_depth_exceeded":
                break
        else:
            pytest.fail("Depth limit was not enforced")
