from __future__ import annotations

from pathlib import Path
from typing import Any


def resume_restored_runtime_state(
    artifact_root: Path,
    *,
    workspace_dir: Path,
    run_id: str,
    checkpoint_id: str | None,
    checkpoint_ns: str | None,
    checkpointer: Any,
    context_overrides: dict[str, Any] | None,
    human_response: dict[str, Any] | None,
    skill_resolver: Any,
    llm_provider: Any,
) -> Any:
    import graph_agent

    return graph_agent.resume_skill(
        artifact_root,
        workspace_dir=workspace_dir,
        run_id=run_id,
        checkpoint_id=checkpoint_id,
        checkpoint_ns=checkpoint_ns,
        checkpointer=checkpointer,
        context_overrides=context_overrides,
        human_response=human_response,
        skill_resolver=skill_resolver,
        llm_provider=llm_provider,
    )
