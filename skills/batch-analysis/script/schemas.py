"""Pydantic result schemas for batch-analysis parallel analysis functions.

Each schema maps to one of the 7 analysis functions in paths.py.
All schemas are flat (event_id + scalar/list[str] fields) to be compatible
with the MD parser (md_to_json) and the assemble_batch_results() function.

Field naming must match what assemble_batch_results() accesses:
  character_results → .get('changes', [])
  prop_results      → .get('changes', [])
  arc_results       → .get('curve', [])
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class TensionEmotionVibeResult(BaseModel):
    """Output of analyze_tension_emotion_vibe — per-event tension and atmosphere."""

    event_id: str
    climax_intensity: int = 0  # 0-10; clamped by validator
    emotion_intensity: int = 0  # 0-10; clamped by validator
    climax_type: str = ""
    emotion_type: str = ""
    lighting_vibe: str = ""

    @field_validator("climax_intensity", "emotion_intensity", mode="before")
    @classmethod
    def _clamp_0_10(cls, v: object) -> int:
        try:
            return max(0, min(int(v), 10))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return 0


class SystemEvolutionResult(BaseModel):
    """Output of analyze_system_evolution — system/power changes in C-type events."""

    event_id: str
    system_action: str = ""
    updated_parameters: list[str] = []


class CharacterChangesResult(BaseModel):
    """Output of analyze_character_changes — per-event character state transitions.

    The ``changes`` field is accessed by assemble_batch_results via
    ``character.get(ev_id, {}).get('changes', [])``.
    """

    event_id: str
    changes: list[str] = []


class PropChangesResult(BaseModel):
    """Output of analyze_prop_changes — per-event prop state transitions.

    The ``changes`` field is accessed by assemble_batch_results via
    ``prop.get(ev_id, {}).get('changes', [])``.
    """

    event_id: str
    changes: list[str] = []


class EmotionalArcsResult(BaseModel):
    """Output of analyze_emotional_arcs — per-event emotional arc curve.

    The ``curve`` field is accessed by assemble_batch_results via
    ``arc.get(ev_id, {}).get('curve', [])``.
    """

    event_id: str
    curve: list[str] = []


class ForeshadowingResult(BaseModel):
    """Output of analyze_foreshadowing — foreshadowing planted and paid off."""

    event_id: str
    plant: list[str] = []
    payoff: list[str] = []


class SpatiotemporalResult(BaseModel):
    """Output of analyze_spatiotemporal — space-time standardization."""

    event_id: str
    normalized_location: str = ""
    scene_space_type: str = ""
    time_desc: str = ""
