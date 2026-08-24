"""finish_task 的判决是一个事件，不是一条日志。

CognitiveFlowMiddleware 收下或驳回一次 finish_task 提交时，此前只写
logger.info —— 用户在 trace 里看到的是九个一模一样的 tool_call 行，
既不知道哪次被驳、为什么被驳，也不知道最后哪次被收（实测 2026-08-13,
决议 B3/D4）。判决影响执行(驳回=退给模型重试,收下=写入状态),按
「发决定不发路过」它必须自己发声。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from graph_agent.core.io_manager import IODef, IOManager
from graph_agent.core.schema_engine import SchemaEngine
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware

from .test_cognitive_flow import (
    INVALID_BUSINESS_MD,
    VALID_BUSINESS_MD,
    _handler,
    _request,
    _state,
)


class Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def verdicts(self) -> list[Any]:
        return [e for e in self.events if getattr(e, "event_type", "") == "finish_task_verdict"]


def _middleware(recorder: Recorder | None, io: IOManager | None = None) -> CognitiveFlowMiddleware:
    engine = SchemaEngine()
    return CognitiveFlowMiddleware(
        io or IOManager([IODef(source_field="business_data_parsed", target_field="items")]),
        schema_engine=engine,
        current_phase_schema=engine.parse_from_md("title: str\nscore: int"),
        phase_name="segment",
        callbacks=(recorder,) if recorder else None,
    )


def _finish(md: str) -> dict[str, Any]:
    return {"reasoning": "done", "diagnostics_md": "ok", "business_data_md": md}


def test_an_accepted_finish_says_so_and_says_what_it_accepted() -> None:
    recorder = Recorder()
    middleware = _middleware(recorder)

    middleware.wrap_tool_call(_request(name="finish_task", args=_finish(VALID_BUSINESS_MD)), _handler)

    (verdict,) = recorder.verdicts()
    assert verdict.verdict == "accepted"
    assert verdict.phase_name == "segment"
    assert verdict.item_count == 1
    # 像 print 一样说人话:一句完整的话,而不是让读者拼字段。
    assert "accepted" in verdict.message.lower() and "1" in verdict.message


def test_the_verdict_narrates_its_pipeline_like_print() -> None:
    """用户三问「有没有调中间件?有没有调 md2json?validator 检查了什么?」的答案
    必须写在判决事件里,像 print 一样逐步叙述,而不是让读者去猜。

    叙述里的每一步都必须是**这道闸真的跑过**的一步。原来还有第三步「业务校验器
    的结论」,而这道闸从来就没有业务校验器可调(台账 E16),于是那一步说的是一件
    没发生的事;阶段真正的业务规则在它自己的 `validator.py` 里,由 `PhaseWrapper`
    在阶段跑完之后执行、失败即致命,与这道闸无关。
    """
    recorder = Recorder()
    middleware = _middleware(recorder)

    middleware.wrap_tool_call(_request(name="finish_task", args=_finish(VALID_BUSINESS_MD)), _handler)

    (verdict,) = recorder.verdicts()
    joined = " ".join(verdict.details)
    assert "md2json" in joined, "第一步:md2json 解析了 markdown"
    assert "1" in joined, "叙述必须带上解析出的块数"
    assert "schema" in joined.lower(), "第二步:按 schema 逐块校验"
    assert "business validator" not in joined.lower(), "这道闸不跑业务校验,就不许说它跑了"


def test_a_rejected_finish_says_why() -> None:
    recorder = Recorder()
    middleware = _middleware(recorder)

    middleware.wrap_tool_call(
        _request(name="finish_task", args={"business_data_md": INVALID_BUSINESS_MD}), _handler
    )

    (verdict,) = recorder.verdicts()
    assert verdict.verdict == "rejected"
    assert verdict.errors, "驳回必须带原因——没有原因的驳回和沉默一样是黑箱"
    assert any("score" in error for error in verdict.errors)


def test_a_duplicate_finish_in_the_same_turn_is_reported_not_silently_swallowed() -> None:
    recorder = Recorder()
    middleware = _middleware(recorder)
    # 重复判定按「本轮」算——轮次身份取自最后一条 AI 消息的 id,所以状态里
    # 必须真的有那条消息,空消息列表根本进不了重复分支。
    state = _state()
    state["messages"] = [AIMessage(content="", id="turn-1")]

    middleware.wrap_tool_call(_request(name="finish_task", args=_finish(VALID_BUSINESS_MD), state=state), _handler)
    middleware.wrap_tool_call(_request(name="finish_task", args=_finish(VALID_BUSINESS_MD), state=state), _handler)

    verdicts = recorder.verdicts()
    assert [v.verdict for v in verdicts] == ["accepted", "duplicate"]


def test_racing_duplicate_submissions_yield_one_accept_and_one_duplicate() -> None:
    """轮内 gate 是 check-then-act:两个并行 finish_task 同时进门时,后到者
    必须看到先到者已收下。2026-08-14 实测(fixture: DeepSeek 并行重复):门不
    原子时两笔都走接受分支,同一超步对无 reducer 的 data/flow 通道写两次,
    整个 run 以 InvalidUpdateError 收场。慢业务校验器把竞态窗口拉宽到必现。"""
    import threading
    import time

    class SlowSchemaEngine(SchemaEngine):
        """校验慢一点,把「检查完到收下」之间的窗口拉宽到必现。

        窗口本身不是这里造出来的:两个线程本来就都能走到接受分支。慢一点只是
        让它每次都发生,而不是偶尔。
        """

        def validate(self, *args: Any, **kwargs: Any) -> Any:
            time.sleep(0.05)
            return super().validate(*args, **kwargs)

    recorder = Recorder()
    engine = SlowSchemaEngine()

    middleware = CognitiveFlowMiddleware(
        IOManager([IODef(source_field="business_data_parsed", target_field="items")]),
        schema_engine=engine,
        current_phase_schema=engine.parse_from_md("title: str\nscore: int"),
        phase_name="segment",
        callbacks=(recorder,),
    )
    state = _state()
    state["messages"] = [AIMessage(content="", id="turn-1")]

    barrier = threading.Barrier(2)

    def submit() -> None:
        barrier.wait()
        middleware.wrap_tool_call(
            _request(name="finish_task", args=_finish(VALID_BUSINESS_MD), state=state), _handler
        )

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert sorted(v.verdict for v in recorder.verdicts()) == ["accepted", "duplicate"]


def test_a_middleware_without_listeners_still_works() -> None:
    middleware = _middleware(None)

    result = middleware.wrap_tool_call(
        _request(name="finish_task", args=_finish(VALID_BUSINESS_MD)), _handler
    )

    assert result is not None
