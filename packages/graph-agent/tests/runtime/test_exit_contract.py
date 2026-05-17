from __future__ import annotations

from graph_agent.runtime.exit_contract import inject_exit_contract
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


def test_inject_exit_contract_appends_user_message() -> None:
    result = inject_exit_contract([], "Call finish_task when done.")

    assert len(result) == 1
    assert isinstance(result[-1], HumanMessage)
    assert result[-1].content == "Call finish_task when done."


def test_inject_exit_contract_preserves_previous_messages() -> None:
    messages = [
        SystemMessage(content="You are careful."),
        HumanMessage(content="Start."),
        AIMessage(content="Working."),
    ]

    result = inject_exit_contract(messages, "Finish only after validation.")

    assert result[:3] == messages
    assert len(result) == 4
    assert isinstance(result[-1], HumanMessage)
    assert result[-1].content == "Finish only after validation."


def test_inject_exit_contract_empty_contract_is_noop() -> None:
    messages = [HumanMessage(content="existing")]

    result = inject_exit_contract(messages, "")

    assert result == messages
    assert result is not messages


def test_inject_exit_contract_does_not_mutate_input() -> None:
    messages = [HumanMessage(content="existing")]

    result = inject_exit_contract(messages, "Call finish_task.")

    assert len(messages) == 1
    assert messages[0].content == "existing"
    assert len(result) == 2


def test_inject_exit_contract_each_round_consistent() -> None:
    contract = "Call finish_task only after all required fields are present."
    base_messages = [SystemMessage(content="Rules.")]

    first_call = inject_exit_contract(base_messages, contract)
    second_call = inject_exit_contract(
        base_messages + [AIMessage(content="Need more work.")],
        contract,
    )

    assert isinstance(first_call[-1], HumanMessage)
    assert isinstance(second_call[-1], HumanMessage)
    assert first_call[-1].content == contract
    assert second_call[-1].content == contract
