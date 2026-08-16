"""没读懂的行必须走到模型面前,不能只进日志。

`parse_md` 记下"我没读懂这几行"之后,这份记录还要跨过中间件才算送达:
finish_task 的判决事件是模型与 trace 共用的那条回路
(`_reject_finish` 把 `errors` 逐行拼进退回给模型的 ToolMessage,
`_say_verdict` 把 `errors`/`details` 发成 FinishTaskVerdictEvent)。
本文件钉的就是这一段:没读懂 → 驳回 → 驳回理由里点出行号与原文。

顺序也在钉:解析没吃完整份输入时,先报"这几行没读进来",不报由残缺数据
推出的 schema/业务错误 —— 真跑里模型收到的正是后者
("No segments produced. Re-analyze the chapter text."),它指向一个不存在
的问题,模型照做只会重复同一个格式。
"""

from __future__ import annotations

from typing import Any

from graph_agent.core.io_manager import IODef, IOManager
from graph_agent.core.schema_engine import SchemaEngine
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware

from .test_cognitive_flow import _handler, _request

NESTED_BULLET_MD = """## item-1
- parsed_segments:
  - index: 1
    type: B
    start_line: 1
  - index: 2
    type: B
    start_line: 6
- segments_summary: 两段
"""


class Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def verdicts(self) -> list[Any]:
        return [e for e in self.events if getattr(e, "event_type", "") == "finish_task_verdict"]


def _middleware(recorder: Recorder) -> CognitiveFlowMiddleware:
    engine = SchemaEngine()
    return CognitiveFlowMiddleware(
        IOManager([IODef(source_field="business_data_parsed", target_field="items")]),
        schema_engine=engine,
        current_phase_schema=engine.parse_from_md(
            "parsed_segments: list[str]\nsegments_summary: str"
        ),
        phase_name="segment",
        callbacks=(recorder,),
    )


def _submit(middleware: CognitiveFlowMiddleware, md: str) -> None:
    middleware.wrap_tool_call(
        _request(
            name="finish_task",
            args={"reasoning": "done", "diagnostics_md": "ok", "business_data_md": md},
        ),
        _handler,
    )


def test_unread_lines_reject_the_submission_and_name_themselves_to_the_model() -> None:
    recorder = Recorder()

    _submit(_middleware(recorder), NESTED_BULLET_MD)

    (verdict,) = recorder.verdicts()
    assert verdict.verdict == "rejected"
    joined = "\n".join(verdict.errors)
    for quoted in ("    type: B", "    start_line: 1", "  - index: 2", "    start_line: 6"):
        assert quoted in joined, f"驳回理由必须原样点出没读懂的行:{quoted!r}"
    for line_number in ("4", "5", "6", "7", "8"):
        assert line_number in joined, "驳回理由必须带行号,模型才定位得到"


def test_the_verdict_details_narrate_the_parse_gap() -> None:
    recorder = Recorder()

    _submit(_middleware(recorder), NESTED_BULLET_MD)

    (verdict,) = recorder.verdicts()
    joined = " ".join(verdict.details)
    assert "5" in joined, "叙述必须带上没读懂的行数"


def test_a_parse_gap_is_reported_instead_of_the_errors_derived_from_the_truncated_data() -> None:
    recorder = Recorder()

    _submit(_middleware(recorder), NESTED_BULLET_MD)

    (verdict,) = recorder.verdicts()
    joined = "\n".join(verdict.errors)
    assert "segments_summary" not in joined, (
        "残缺解析结果推出来的 schema 判读会把模型指向不存在的问题,不许一起报"
    )


def test_a_fully_read_submission_still_passes() -> None:
    recorder = Recorder()

    _submit(
        _middleware(recorder),
        "## item-1\n- parsed_segments: a, b\n- segments_summary: 两段\n",
    )

    (verdict,) = recorder.verdicts()
    assert verdict.verdict == "accepted", verdict.errors
