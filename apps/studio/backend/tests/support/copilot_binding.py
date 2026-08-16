"""One place for the skill binding that `build_options` demands of a chat session.

Tests that only care about SDK option assembly still have to hand it a binding,
because a chat session without one is rejected at the boundary (see
``app.services.copilot.build_options``). Naming that throwaway binding once keeps
the intent readable: these tests are not exercising skill identity.
"""

from __future__ import annotations

from pathlib import Path

from app.services.copilot_skill_binding import CopilotSkillBinding


def binding_for(workspace_root: str | Path, skill_id: str = "skill-under-test") -> CopilotSkillBinding:
    return CopilotSkillBinding(skill_id=skill_id, workspace_root=Path(workspace_root))
