from __future__ import annotations

import copy
import logging
from pathlib import Path

from pydantic import BaseModel

from pydantic import ValidationError

from graph_agent.tools.md_to_json import parse_md

logger = logging.getLogger(__name__)


def _md_to_models(md_text, schema):
    """Happy-path markdown parsing without the Patch-Agent fallback.

    Validator context has no skill_resolver, so invalid blocks are dropped
    loudly (WARNING) instead of being LLM-patched.
    """
    items = []
    for blk in parse_md(md_text or "", schema):
        try:
            items.append(schema.model_validate(blk.data))
        except ValidationError as exc:
            logger.warning("analysis md block dropped (%s): %s", schema.__name__, exc)
    return items

_SKILL_ROOT = Path(__file__).resolve().parents[2]


# Import Pydantic schemas from sibling or declare here
class TensionEmotionVibeResult(BaseModel):
    event_id: str
    climax_intensity: int = 0
    emotion_intensity: int = 0
    climax_type: str = ""
    emotion_type: str = ""
    lighting_vibe: str = ""


class SystemEvolutionResult(BaseModel):
    event_id: str
    system_action: str = ""
    updated_parameters: list[str] = []


class CharacterChangesResult(BaseModel):
    event_id: str
    changes: list[str] = []


class PropChangesResult(BaseModel):
    event_id: str
    changes: list[str] = []


class EmotionalArcsResult(BaseModel):
    event_id: str
    curve: list[str] = []


class ForeshadowingResult(BaseModel):
    event_id: str
    plant: list[str] = []
    payoff: list[str] = []


class SpatiotemporalResult(BaseModel):
    event_id: str
    normalized_location: str = ""
    scene_space_type: str = ""
    time_desc: str = ""


def _load_prompt(filename: str) -> dict:
    import yaml

    prompt_dir = _SKILL_ROOT / "prompts"
    with open(prompt_dir / filename, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate(output: dict, state_slice: dict, **kwargs) -> dict:
    """Run narrative parallel multi-dimensional analysis on batch events."""
    context = copy.deepcopy(state_slice)
    llm_call = context.get("_llm_call")

    if not llm_call:
        raise ValueError("Parallel analysis requires _llm_call in blackboard")

    events_text = context.get("batch_events_text", "")
    acc_text = context.get("accumulated_context_text", "")
    user_msg = f"Events:\n{events_text}\n\nAccumulated:\n{acc_text}"

    # 1. Tension Emotion Vibe
    prompt1 = _load_prompt("tension_emotion_vibe.yaml")
    raw1 = llm_call(prompt1["system"], user_msg, max_tokens=8000)
    tension_results = [
        r.model_dump() for r in _md_to_models(raw1, TensionEmotionVibeResult)
    ]
    logger.info("analyze_tension_emotion_vibe: parsed %d items", len(tension_results))

    # 2. System Evolution (C-type events only)
    events = context.get("batch_events", [])
    c_events = [e for e in events if e.get("event_type") == "C"]
    system_results = []
    if c_events:
        prompt2 = _load_prompt("system_evolution.yaml")
        c_events_text = "\n".join(
            f"[{e.get('event_id', 'unknown')}] {e.get('content', '')}"
            for e in c_events
        )
        user_msg_c = f"Events:\n{c_events_text}\n\nAccumulated:\n{acc_text}"
        raw2 = llm_call(prompt2["system"], user_msg_c, max_tokens=8000)
        system_results = [
            r.model_dump() for r in _md_to_models(raw2, SystemEvolutionResult)
        ]
        logger.info("analyze_system_evolution: parsed %d items", len(system_results))

    # 3. Prop Changes
    prompt3 = _load_prompt("prop_changes.yaml")
    raw3 = llm_call(prompt3["system"], user_msg, max_tokens=8000)
    prop_results = [r.model_dump() for r in _md_to_models(raw3, PropChangesResult)]
    logger.info("analyze_prop_changes: parsed %d items", len(prop_results))

    # 4. Emotional Arcs
    prompt4 = _load_prompt("emotional_arcs.yaml")
    raw4 = llm_call(prompt4["system"], user_msg, max_tokens=8000)
    arc_results = [r.model_dump() for r in _md_to_models(raw4, EmotionalArcsResult)]
    logger.info("analyze_emotional_arcs: parsed %d items", len(arc_results))

    # 5. Foreshadowing
    prompt5 = _load_prompt("foreshadowing.yaml")
    raw5 = llm_call(prompt5["system"], user_msg, max_tokens=8000)
    foreshadowing_results = [
        r.model_dump() for r in _md_to_models(raw5, ForeshadowingResult)
    ]
    logger.info("analyze_foreshadowing: parsed %d items", len(foreshadowing_results))

    # 6. Spatiotemporal
    prompt6 = _load_prompt("spatiotemporal.yaml")
    raw6 = llm_call(prompt6["system"], user_msg, max_tokens=8000)
    spatiotemporal_results = [
        r.model_dump() for r in _md_to_models(raw6, SpatiotemporalResult)
    ]
    logger.info(
        "analyze_spatiotemporal: parsed %d items", len(spatiotemporal_results)
    )

    return {
        "tension_results": tension_results,
        "system_results": system_results,
        "prop_results": prop_results,
        "arc_results": arc_results,
        "foreshadowing_results": foreshadowing_results,
        "spatiotemporal_results": spatiotemporal_results,
    }
