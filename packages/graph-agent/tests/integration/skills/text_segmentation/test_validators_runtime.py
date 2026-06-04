"""Runtime schema smoke tests for the V2.1 text-segmentation skill."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["segmentation_result"],
        "properties": {
            "segmentation_result": {
                "type": "object",
                "required": ["chapter_number", "total_paragraphs", "paragraphs"],
                "properties": {
                    "chapter_number": {"type": "integer"},
                    "total_paragraphs": {"type": "integer"},
                    "paragraphs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["index", "type", "start_line", "end_line", "content", "description"],
                            "properties": {
                                "index": {"type": "integer"},
                                "type": {"type": "string", "enum": ["A", "B", "C"]},
                                "start_line": {"type": "integer"},
                                "end_line": {"type": "integer"},
                                "content": {"type": "string"},
                                "description": {"type": "string"},
                            }
                        }
                    },
                    "metadata": {"type": "object"}
                }
            }
        }
    }


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


def _segment(
    *,
    index: int,
    type_: str = "B",
    start_line: int = 1,
    end_line: int = 5,
    content: str = "测试段落内容",
    description: str = "现实事件推进",
) -> dict[str, Any]:
    return {
        "index": index,
        "type": type_,
        "start_line": start_line,
        "end_line": end_line,
        "content": content,
        "description": description,
    }


def _good_result() -> dict[str, Any]:
    return {
        "segmentation_result": {
            "chapter_number": 1,
            "total_paragraphs": 2,
            "paragraphs": [
                _segment(index=1, type_="B", start_line=1, end_line=10),
                _segment(index=2, type_="A", start_line=11, end_line=20),
            ],
            "metadata": {"reviewed": True},
        }
    }


class TestTextSegmentationOutputSchema:
    def test_accepts_well_formed_segmentation_result(self) -> None:
        assert list(_validator().iter_errors(_good_result())) == []

    def test_rejects_missing_required_root(self) -> None:
        errors = list(_validator().iter_errors({}))

        assert any("segmentation_result" in error.message for error in errors)

    def test_rejects_invalid_segment_type(self) -> None:
        payload = _good_result()
        payload["segmentation_result"]["paragraphs"][0]["type"] = "Z"

        errors = list(_validator().iter_errors(payload))

        assert any("'Z' is not one of" in error.message for error in errors)

    def test_rejects_missing_line_field(self) -> None:
        payload = _good_result()
        del payload["segmentation_result"]["paragraphs"][0]["start_line"]

        errors = list(_validator().iter_errors(payload))

        assert any("start_line" in error.message for error in errors)
