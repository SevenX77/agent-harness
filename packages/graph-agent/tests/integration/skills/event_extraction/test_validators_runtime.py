"""Runtime schema smoke tests for the V2.1 event-extraction skill."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["event_timeline"],
        "properties": {
            "event_timeline": {
                "type": "object",
                "required": ["chapter_number", "events", "settings"],
                "properties": {
                    "chapter_number": {"type": "integer"},
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["event_id", "title", "type", "paragraph_indices", "summary", "location", "time"],
                            "properties": {
                                "event_id": {"type": "string"},
                                "title": {"type": "string"},
                                "type": {"type": "string", "enum": ["B", "C", "M"]},
                                "paragraph_indices": {
                                    "type": "array",
                                    "items": {"type": "integer"}
                                },
                                "summary": {"type": "string"},
                                "location": {"type": "string"},
                                "time": {"type": "string"}
                            }
                        }
                    },
                    "settings": {
                        "type": "array",
                        "items": {"type": "object"}
                    },
                    "metadata": {"type": "object"}
                }
            }
        }
    }


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


def _good_timeline(event_id: str = "EVT-001") -> dict[str, Any]:
    return {
        "event_timeline": {
            "chapter_number": 1,
            "events": [
                {
                    "event_id": event_id,
                    "title": "遭遇弱点",
                    "type": "B",
                    "paragraph_indices": [3, 4, 5],
                    "summary": "主角确认诡异弱点与火焰、高频电流有关。",
                    "location": "废弃商场",
                    "time": "夜间",
                }
            ],
            "settings": [{"setting_id": "SET-001"}],
            "metadata": {"reviewed": True},
        }
    }


class TestEventExtractionOutputSchema:
    def test_accepts_well_formed_timeline(self) -> None:
        assert list(_validator().iter_errors(_good_timeline())) == []

    def test_rejects_missing_event_timeline(self) -> None:
        errors = list(_validator().iter_errors({}))

        assert any("event_timeline" in error.message for error in errors)

    def test_rejects_missing_event_id(self) -> None:
        payload = _good_timeline()
        del payload["event_timeline"]["events"][0]["event_id"]

        errors = list(_validator().iter_errors(payload))

        assert any("event_id" in error.message for error in errors)

    def test_rejects_non_integer_paragraph_index(self) -> None:
        payload = _good_timeline()
        payload["event_timeline"]["events"][0]["paragraph_indices"] = ["3"]

        errors = list(_validator().iter_errors(payload))

        assert any("is not of type 'integer'" in error.message for error in errors)
