import pytest
from typing import Annotated
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.channels.delta import DeltaChannel
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from graph_agent.core.state import WorkflowState, BusinessData, FrameworkState, _messages_delta_reducer


def test_workflow_state_messages_use_deltachannel() -> None:
    # 1. Verify typing definition has DeltaChannel on messages
    from typing import get_type_hints
    hints = get_type_hints(WorkflowState, include_extras=True)
    messages_type = hints["messages"]

    # In annotated type hints, the __metadata__ holds DeltaChannel
    assert hasattr(messages_type, "__metadata__")
    metadata = messages_type.__metadata__
    assert any(isinstance(m, DeltaChannel) for m in metadata)


def test_sqlite_deltachannel_checkpoint_size(tmp_path) -> None:
    db_file = tmp_path / "checkpoints.sqlite"

    # 2. Build a StateGraph using our WorkflowState
    builder = StateGraph(WorkflowState)

    def first_node(state: WorkflowState) -> dict:
        return {"messages": [AIMessage(content="Hello world", id="msg-1")]}

    def second_node(state: WorkflowState) -> dict:
        return {"messages": [AIMessage(content="Hello again", id="msg-2")]}

    builder.add_node("first", first_node)
    builder.add_node("second", second_node)
    builder.add_edge(START, "first")
    builder.add_edge("first", "second")
    builder.add_edge("second", END)

    with SqliteSaver.from_conn_string(str(db_file)) as checkpointer:
        checkpointer.setup()
        graph = builder.compile(checkpointer=checkpointer)

        config = {"configurable": {"thread_id": "test-thread"}}
        initial_state = {
            "data": BusinessData(),
            "flow": FrameworkState(),
            "messages": [HumanMessage(content="Start", id="msg-0")]
        }

        # Run graph
        res = graph.invoke(initial_state, config=config)

        # Re-fetch state using get_state to ensure DeltaChannel replayed and rebuilt perfectly
        state_repr = graph.get_state(config)
        msg_contents = [m.content for m in state_repr.values["messages"]]
        assert "Start" in msg_contents
        assert "Hello world" in msg_contents
        assert "Hello again" in msg_contents

        # Inspect SQLite connection and writes table
        import sqlite3
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()

        # In DeltaChannel, writes are saved incrementally, so they should be inside the `writes` table
        cursor.execute("SELECT COUNT(*) FROM writes WHERE thread_id = 'test-thread'")
        writes_count = cursor.fetchone()[0]
        assert writes_count > 0, "Writes should be recorded in SQLite writes table for DeltaChannel"

        conn.close()
