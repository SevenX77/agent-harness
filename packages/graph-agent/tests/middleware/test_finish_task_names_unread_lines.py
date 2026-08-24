"""没读懂的行必须走到**模型手里**,而不只是被记在系统自己的账本上。

#850 让 `parse_md` 记下"我没读懂这几行"(`ParsedBlock.meta.unread`),
它的决议立的论点是**日志不是生产方能听见的通道**:生产方是 LLM,唯一的反馈
回路是 finish_task 判决拼进退回模型的那条 ToolMessage。
但 #850 的中间件测试断言的对象是 `FinishTaskVerdictEvent`——那是 trace 侧的
账本,不是回路本身。

外科式反证(2026-08-18 实测):把 `_validate_finish_args` 里
`if parse_gap is not None: return parse_gap` 改成永不返回,unread 照样被记录、
`_parse_gap_validation` 照样就地往 `story` 里追加叙述,于是判决的 `details`
一字不差,只有模型什么都收不到。改前的 4 条中间件测试里只有 1 条转红,
`test_the_verdict_details_narrate_the_parse_gap` 仍然 PASSED ——
**#850 要治的病在它自己的测试里复发了:记账做了,送达没做,而测试只看记账。**

所以本文件的断言对象是**退回模型的那条 ToolMessage**:它的 `content`、
`status`,以及把这一轮送回模型的 `Command.goto`。判决事件的 `details` 另有
一条测试管,但它不代表送达。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from graph_agent.core.io_manager import IODef, IOManager
from graph_agent.core.schema_engine import SchemaEngine
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware
from graph_agent.tools.md_to_json import parse_md

from .test_cognitive_flow import _handler, _request

# 真跑 09f67b86 里模型写出的形态:`list` 字段用嵌套 bullet,子项自己再带子键。
# 第 4-8 行(整份 markdown 从 1 数起)没有任何字段能承载,解析器只读进
# `parsed_segments: ['index: 1']`。
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

# (行号, 原文):模型要照着行号定位,所以两者必须出现在同一行里,单有行号或
# 单有原文都定位不到——同一份 markdown 里 `    type: B` 就出现了两次。
UNREAD_LINES: tuple[tuple[int, str], ...] = (
    (4, "    type: B"),
    (5, "    start_line: 1"),
    (6, "  - index: 2"),
    (7, "    type: B"),
    (8, "    start_line: 6"),
)

class Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def verdicts(self) -> list[Any]:
        return [e for e in self.events if getattr(e, "event_type", "") == "finish_task_verdict"]


def _schema() -> Any:
    # 故意用 `list[str]`:残缺后的 ['index: 1'] 完美满足这个类型,schema 这一关
    # 拦不住它(见 test_truncated_data_that_satisfies_the_schema_is_refused_anyway)。
    return SchemaEngine().parse_from_md("parsed_segments: list[str]\nsegments_summary: str")


def _middleware(recorder: Recorder) -> CognitiveFlowMiddleware:
    return CognitiveFlowMiddleware(
        IOManager([IODef(source_field="business_data_parsed", target_field="items")]),
        schema_engine=SchemaEngine(),
        current_phase_schema=_schema(),
        phase_name="segment",
        callbacks=(recorder,),
    )


def _submit(middleware: CognitiveFlowMiddleware, md: str) -> Command[Any]:
    """提交一次 finish_task,并把中间件交还给图的那个 Command 原样返回。

    #850 的版本把返回值丢了,于是"模型收到了什么"在测试里根本不可见。
    """
    return middleware.wrap_tool_call(
        _request(
            name="finish_task",
            args={"reasoning": "done", "diagnostics_md": "ok", "business_data_md": md},
        ),
        _handler,
    )


def _reply_to_model(command: Command[Any]) -> ToolMessage:
    """退回模型的那一条 ToolMessage —— 本文件全部断言的落点。"""
    (message,) = (command.update or {})["messages"]
    assert isinstance(message, ToolMessage)
    return message


def _quotes_line(content: str, line_number: int, text: str) -> bool:
    return any(text in line and str(line_number) in line for line in content.splitlines())


def test_the_parse_gap_comes_back_to_the_model_as_a_failed_tool_call() -> None:
    recorder = Recorder()

    command = _submit(_middleware(recorder), NESTED_BULLET_MD)

    reply = _reply_to_model(command)
    assert reply.name == "finish_task"
    assert reply.status == "error", "模型必须看见这是一次失败的调用,而不是一段闲聊"
    assert command.goto == "model", "这一轮必须交回模型重写,不能往下走"
    assert set(command.update or {}) == {"messages"}, (
        "残缺解析不许写进 data/flow —— 一旦写进去,'没读懂'就变成了下游的既成事实"
    )


def test_the_reply_to_the_model_quotes_every_unread_line_with_its_number() -> None:
    recorder = Recorder()

    command = _submit(_middleware(recorder), NESTED_BULLET_MD)

    content = str(_reply_to_model(command).content)
    for line_number, text in UNREAD_LINES:
        assert _quotes_line(content, line_number, text), (
            f"退回模型的话里必须有一行同时带上第 {line_number} 行的行号与原文 {text!r};"
            f"实际收到:\n{content}"
        )


def test_the_verdict_details_narrate_the_parse_gap_on_a_rejected_verdict() -> None:
    """判决事件是 trace 侧的账本。它记的是同一件事,但**不能**代表送达:

    切断投递的变异体里,`_parse_gap_validation` 仍然就地改了 `story`,所以
    details 一字不差——变的是它挂在了一个 `accepted` 判决上。所以这里连
    verdict 一起钉:叙述"我没读懂 5 行"却判"通过",本身就是缺陷。
    """
    recorder = Recorder()

    _submit(_middleware(recorder), NESTED_BULLET_MD)

    (verdict,) = recorder.verdicts()
    assert verdict.verdict == "rejected"
    assert any("5" in detail and "unread" in detail for detail in verdict.details), (
        f"叙述必须说清没读懂几行;实际 details:{verdict.details}"
    )


def test_no_later_stage_judges_the_data_that_was_not_read() -> None:
    """先证明 gap 确实被报了,再证明后面的关卡一道都没在残缺数据上开口。

    真跑 09f67b86 里模型收到的是阶段校验器在残缺数据上得出的判读
    (「No segments produced. Re-analyze the chapter text.」)——它把模型指向一个
    不存在的问题:章节分析没坏,坏的是输出格式没被读懂。所以 gap 必须**短路**,
    而不是"照常判完再把 gap 一起附上"。

    判据落在叙述上,因为叙述逐步记录了哪一关真的跑过:gap 之后不该再出现
    schema 那一步。#850 的原版只有一句"结论文本没出现",而功能完全没实现时
    那句照样成立(2026-08-18 实测回退到 49f7ad0d 它 PASSED)——一条在"什么都
    没做"时也成立的断言没有区分力。
    """
    recorder = Recorder()

    command = _submit(_middleware(recorder), NESTED_BULLET_MD)

    content = str(_reply_to_model(command).content)
    for line_number, text in UNREAD_LINES:
        assert _quotes_line(content, line_number, text), f"第 {line_number} 行没被点名"

    (verdict,) = recorder.verdicts()
    joined = " ".join(verdict.details).lower()
    assert "md2json" in joined, "gap 是在解析之后发现的,所以解析那一步必须在叙述里"
    assert "schema check" not in joined, (
        f"gap 之后不许再有关卡在残缺数据上下结论;实际叙述:{verdict.details}"
    )


def test_truncated_data_that_satisfies_the_schema_is_refused_anyway() -> None:
    """最坏的一档不是"死得莫名其妙",是"根本不死"。

    `list[str]` 这一档里,残缺后的 `['index: 1']` 完美满足类型,schema 这一关
    什么也拦不住——挡在"错误数据带着通过标签流进下游"前面的只有 parse-gap 这
    一道。所以先把"schema 拦不住"证出来,再断言提交仍然被退回。
    """
    engine = SchemaEngine()
    schema = engine.parse_from_md("parsed_segments: list[str]\nsegments_summary: str")

    (block,) = parse_md(NESTED_BULLET_MD, engine.get_pydantic_model(schema))
    assert block.data == {"parsed_segments": ["index: 1"], "segments_summary": "两段"}
    assert engine.validate(block.data, schema).ok, (
        "这条测试的前提就是残缺数据满足类型;它若不再成立,本测试要重写而不是删掉"
    )

    recorder = Recorder()
    command = _submit(_middleware(recorder), NESTED_BULLET_MD)

    reply = _reply_to_model(command)
    assert reply.status == "error"
    assert str(reply.content) != "PHASE_COMPLETE", "残缺数据不许拿到阶段完成的通行证"
    # 写 `data` 通道就是 hoist 已经发生:接受路径的 update 是 data/flow/messages 三键,
    # 驳回路径只有 messages。断言 `business_data_parsed` 不在 update 里是**没有区分力**的
    # ——那是 finish_result 内部的键,两条路径的 update 里都不会出现它。
    assert "data" not in (command.update or {}), "更不许把残缺数据 hoist 进下游的 data 通道"


def test_a_fully_read_submission_still_reaches_the_model_as_phase_complete() -> None:
    """对照组:读全了的提交必须照旧通过。

    它在上面两个变异体下都 PASSED,这正是它该有的结果——它钉的是"合法输入零
    回归",不是新行为;拿它去杀变异体等于把对照组当实验组。
    """
    recorder = Recorder()

    command = _submit(
        _middleware(recorder),
        "## item-1\n- parsed_segments: a, b\n- segments_summary: 两段\n",
    )

    reply = _reply_to_model(command)
    assert str(reply.content) == "PHASE_COMPLETE"
    assert reply.status == "success"
    (verdict,) = recorder.verdicts()
    assert verdict.verdict == "accepted", verdict.errors
