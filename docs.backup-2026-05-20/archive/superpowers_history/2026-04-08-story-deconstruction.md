# Story Deconstruction Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the complete Node 0 + Node 1 story analysis pipeline into graph_agent standard skills, serving as a production-grade E2E stress test for the graph_agent framework.

**Architecture:** 4 subgraph skills + 1 orchestrator skill with LLM-driven batch loop. Each skill has 3-layer validation (structural → semantic → annotation). Tools make internal LLM calls for analysis paths. Entity registration is merged with character analysis (star topology). Batch accumulator pattern threads state across batches.

**Tech Stack:** Python 3.11+, graph_agent framework, LangChain StructuredTool, Pydantic v2

---

## File Structure

```
skills/story-deconstruction/
├── SKILL.md                              # Orchestrator (type: graph)
├── script/
│   ├── orchestrator.py                   # Batch loop + data prep tools
│   └── validators.py                     # Orchestrator-level validation
├── references/
│   └── calibration/
│       └── rules.yaml                    # Orchestrator rules
├── nodes/
│   ├── 01_segmentation.md                # Node config for text-segmentation subgraph
│   ├── 02_event_extraction.md            # Node config for event-extraction subgraph
│   ├── 03_batch_loop.md                  # Node config for LLM-driven batch loop
│   └── 04_global_synthesis.md            # Node config for global-synthesis subgraph
│
├── subskills/
│   ├── text-segmentation/
│   │   ├── SKILL.md                      # ABC segmentation (type: graph, 3 nodes)
│   │   ├── script/
│   │   │   ├── segmenter.py              # Line numbering, parsing, text extraction
│   │   │   └── validators.py             # 3-layer validator
│   │   ├── nodes/
│   │   │   ├── 01_setup.md               # Code-only: prepare chapter text
│   │   │   ├── 02_segment.md             # LLM: initial ABC segmentation
│   │   │   └── 03_review.md              # LLM: Two-Pass validation/correction
│   │   └── references/
│   │       └── calibration/
│   │           ├── golden_examples.json   # Human-verified correct segmentations
│   │           ├── corrections.json       # Triple-store correction records
│   │           └── rules.yaml             # Inferred rules from annotations
│   │
│   ├── event-extraction/
│   │   ├── SKILL.md                      # Event timeline (type: graph, 4 nodes)
│   │   ├── script/
│   │   │   ├── extractor.py              # Event parsing, segment formatting, merging
│   │   │   └── validators.py             # 3-layer validator
│   │   ├── nodes/
│   │   │   ├── 01_setup.md               # Code-only: format segments
│   │   │   ├── 02_aggregate.md           # LLM: event aggregation + timeline reorder
│   │   │   ├── 03_review.md              # LLM: semantic coherence review
│   │   │   └── 04_settings.md            # LLM: setting extraction + merge
│   │   └── references/
│   │       └── calibration/
│   │           ├── golden_examples.json
│   │           ├── corrections.json
│   │           └── rules.yaml
│   │
│   ├── batch-analysis/
│   │   ├── SKILL.md                      # Single-batch analysis (type: graph, 5 nodes)
│   │   ├── script/
│   │   │   ├── paths.py                  # 7 analysis path tools (each calls LLM internally)
│   │   │   ├── entity.py                 # Entity registration + disambiguation
│   │   │   ├── continuity.py             # Narrative continuity check
│   │   │   ├── accumulator.py            # BatchAccumulator state management
│   │   │   └── validators.py             # 3-layer validator
│   │   ├── nodes/
│   │   │   ├── 01_prepare.md             # Code-only: prepare batch data + load state
│   │   │   ├── 02_entity_and_characters.md  # LLM: entity registration + character analysis (star center)
│   │   │   ├── 03_parallel_analysis.md   # LLM: 6 remaining paths (tension/system/props/arcs/foreshadow/spatiotemporal)
│   │   │   ├── 04_continuity.md          # LLM: narrative continuity check
│   │   │   └── 05_assemble.md            # Code-only: merge results + update accumulator
│   │   └── references/
│   │       └── calibration/
│   │           ├── golden_examples.json
│   │           ├── corrections.json
│   │           └── rules.yaml
│   │
│   └── global-synthesis/
│       ├── SKILL.md                      # Global analysis (type: graph, 4 nodes)
│       ├── script/
│       │   ├── synthesis.py              # Ranking, closure analysis tools
│       │   ├── retroactive.py            # Retroactive correction tools
│       │   ├── scene_builder.py          # Unified event stream assembly
│       │   └── validators.py             # 3-layer validator
│       ├── nodes/
│       │   ├── 01_global_analysis.md     # LLM: 3 global paths (climax/foreshadow/character ranking)
│       │   ├── 02_scene_assembly.md      # Code-only: unified event stream
│       │   ├── 03_retroactive.md         # LLM: retroactive correction
│       │   └── 04_export.md              # Code-only: final output assembly
│       └── references/
│           └── calibration/
│               ├── golden_examples.json
│               ├── corrections.json
│               └── rules.yaml
│
├── data/
│   └── test_input/                       # E2E test chapters (3-5 chapters min)
│       ├── chapter_001.txt
│       ├── chapter_002.txt
│       └── chapter_003.txt
│
└── tests/
    ├── test_text_segmentation.py
    ├── test_event_extraction.py
    ├── test_batch_analysis.py
    ├── test_global_synthesis.py
    └── test_e2e_pipeline.py
```

---

## Source Code Reference Map

Every tool function ports logic from these source files. Implementers MUST read the source before writing.

| Target Tool | Source File | Source Lines | Key Logic |
|---|---|---|---|
| `segmenter.py` | `AI-narrated-recap-analyst/src/pipeline/story_core/tools/abc_segmenter.py` | Full file | Line numbering, LLM output parsing, text extraction, scene break detection |
| `segmenter.py` prompts | `AI-narrated-recap-analyst/src/pipeline/story_core/prompts/abc_segmenter_pass1.yaml` | Full file | A/B/C classification rules, P0 principles |
| `segmenter.py` prompts | `AI-narrated-recap-analyst/src/pipeline/story_core/prompts/abc_segmenter_pass2.yaml` | Full file | 4-step validation process |
| `extractor.py` | `AI-narrated-recap-analyst/src/pipeline/story_core/tools/event_timeline_extractor.py` | Full file | 3-pass event extraction, N:1 constraint, setting merge |
| `extractor.py` prompts | `AI-narrated-recap-analyst/src/pipeline/story_core/prompts/event_timeline_pass1.yaml` | Full file | Event aggregation + timeline reorder |
| `extractor.py` prompts | `AI-narrated-recap-analyst/src/pipeline/story_core/prompts/event_timeline_review.yaml` | Full file | Semantic coherence review |
| `extractor.py` prompts | `AI-narrated-recap-analyst/src/pipeline/story_core/prompts/event_timeline_pass2.yaml` | Full file | Setting extraction + correlation |
| `paths.py` | `AI-narrated-recap-analyst/src/pipeline/story_core/node1_agent.py` | Lines 1-800 | 7 path prompts, batch processing |
| `accumulator.py` | `AI-narrated-recap-analyst/src/pipeline/story_core/node1_agent.py` | Lines 800-1200 | BatchAccumulator class |
| `entity.py` | `AI-narrated-recap-analyst/skills/pipeline/visualization/visual_extract_v2/tools/reconciler.py` | Full file | Entity registration, alias resolution |
| `continuity.py` | `AI-narrated-recap-analyst/skills/pipeline/visualization/narrative_continuity/analyzer.py` | Full file | Continuity checking logic |
| `synthesis.py` | `AI-narrated-recap-analyst/src/pipeline/story_core/node1_agent.py` | Lines 1200-1600 | Global 3-path analysis |
| `retroactive.py` | `AI-narrated-recap-analyst/src/pipeline/story_core/node1_agent.py` | Lines 1600-1800 | Anchor point scanning, correction patches |
| `scene_builder.py` | `AI-narrated-recap-analyst/src/pipeline/story_core/node1_agent.py` | Lines 1800-2100 | Scene aggregation (deterministic O(n)) |

---

## Phase 1: Infrastructure & Shared Utilities

### Task 1: Create directory scaffold and shared data models

**Files:**
- Create: `skills/story-deconstruction/` (full directory tree as shown above)
- Create: `skills/story-deconstruction/shared/__init__.py`
- Create: `skills/story-deconstruction/shared/schemas.py`
- Create: `skills/story-deconstruction/shared/llm_utils.py`

**Why shared/:** All 4 subskills need the same Pydantic models (`ParagraphSegment`, `EventEntry`, `EventTimeline`, etc.) and LLM call helpers. Centralizing avoids duplication.

- [ ] **Step 1: Create full directory scaffold**

```bash
cd /Users/sevenx/Documents/coding/agent-harness

# Skill directories
mkdir -p skills/story-deconstruction/{script,nodes,references/calibration}
mkdir -p skills/story-deconstruction/subskills/text-segmentation/{script,nodes,references/calibration}
mkdir -p skills/story-deconstruction/subskills/event-extraction/{script,nodes,references/calibration}
mkdir -p skills/story-deconstruction/subskills/batch-analysis/{script,nodes,references/calibration}
mkdir -p skills/story-deconstruction/subskills/global-synthesis/{script,nodes,references/calibration}
mkdir -p skills/story-deconstruction/shared
mkdir -p skills/story-deconstruction/data/test_input
mkdir -p skills/story-deconstruction/tests

# __init__.py files
touch skills/story-deconstruction/__init__.py
touch skills/story-deconstruction/shared/__init__.py
touch skills/story-deconstruction/script/__init__.py
touch skills/story-deconstruction/subskills/__init__.py
for sub in text-segmentation event-extraction batch-analysis global-synthesis; do
  touch skills/story-deconstruction/subskills/$sub/__init__.py
  touch skills/story-deconstruction/subskills/$sub/script/__init__.py
done
```

- [ ] **Step 2: Write shared schemas** (`shared/schemas.py`)

Port from `AI-narrated-recap-analyst/src/pipeline/story_core/schemas.py`. Must include:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pydantic import BaseModel, Field, field_validator


class ParagraphSegment(BaseModel):
    """Single ABC-classified paragraph."""
    index: int = Field(..., ge=1)
    type: str = Field(...)  # "A", "B", or "C"
    content: str = Field(..., min_length=1)
    start_line: int = Field(..., ge=0)
    end_line: int = Field(..., ge=0)
    description: str = ""

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("A", "B", "C"):
            return "B"  # Auto-correct invalid types
        return v


class SegmentationResult(BaseModel):
    """Chapter segmentation output."""
    chapter_number: int
    total_paragraphs: int
    paragraphs: list[ParagraphSegment]
    metadata: dict = Field(default_factory=dict)


class EventEntry(BaseModel):
    """Single event in timeline."""
    event_id: str                           # Format: CCCCNNNNNNT
    event_summary: str
    event_type: str                         # "B" or "C"
    paragraph_indices: list[int]
    location: str = "位置未明确"
    location_change: str | None = None
    time: str = "时间未明确"
    time_change: str | None = None
    setting: list[dict] = Field(default_factory=list)
    is_inferred: list[str] = Field(default_factory=list)

    # Batch analysis enrichments (added by batch-analysis skill)
    climax_intensity: float = 0.0
    climax_type: str = ""
    climax_desc: str = ""
    emotion_intensity: float = 0.0
    emotion_type: str = ""
    emotion_desc: str = ""
    lighting_vibe: str = ""
    characters_involved: list[str] = Field(default_factory=list)
    character_states: list[dict] = Field(default_factory=list)
    character_changes: list[dict] = Field(default_factory=list)
    props_involved: list[str] = Field(default_factory=list)
    prop_changes: list[dict] = Field(default_factory=list)
    arc_moments: list[dict] = Field(default_factory=list)
    foreshadowing_plant: list[str] = Field(default_factory=list)
    foreshadowing_payoff: list[str] = Field(default_factory=list)
    time_coordinate: dict = Field(default_factory=dict)
    normalized_location: str = ""
    scene_space_type: str = ""
    location_visual_change: str = ""
    system_change: dict | None = None
    entity_ids: dict = Field(default_factory=dict)
    scene_id: str = ""


class EventTimeline(BaseModel):
    """Chapter event timeline."""
    chapter_number: int
    total_events: int
    events: list[EventEntry]
    metadata: dict = Field(default_factory=dict)


@dataclass
class BatchAccumulator:
    """Cross-batch state accumulator."""
    # Cumulative lists
    character_changes: list = field(default_factory=list)
    prop_changes: list = field(default_factory=list)
    foreshadowing: list = field(default_factory=list)
    emotional_arcs: list = field(default_factory=list)
    system_evolution: list = field(default_factory=list)
    climax_candidates: list = field(default_factory=list)

    # Context summaries
    known_characters: list = field(default_factory=list)
    known_props: list = field(default_factory=list)
    open_foreshadowing: list = field(default_factory=list)
    active_arcs: list = field(default_factory=list)

    # Spatiotemporal state
    time_tracker: dict = field(default_factory=lambda: {
        "current_day": 1, "current_period": "day", "last_time_desc": ""
    })
    location_registry: list = field(default_factory=list)
    current_lighting_vibe: str = ""

    # Dynamic state
    system_parameters: dict = field(default_factory=dict)
    character_latest_states: dict = field(default_factory=dict)

    # Entity registry
    entity_registry: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize for context passing."""
        import dataclasses
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> BatchAccumulator:
        """Deserialize from context."""
        return cls(**{
            k: d.get(k, f.default_factory() if f.default_factory is not dataclasses.MISSING else f.default)
            for k, f in cls.__dataclass_fields__.items()
        })

    def build_context_text(self) -> str:
        """Format accumulated state for LLM prompt injection."""
        parts = [
            "=== 前批次累积上下文 ===",
            f"【已知角色】{', '.join(self.known_characters[:30]) or '无'}",
            f"【已知道具】{', '.join(self.known_props[:20]) or '无'}",
            f"【待回收伏笔】{len(self.open_foreshadowing)}条",
            f"【进行中弧线】{len(self.active_arcs)}条",
            f"【时空坐标】第{self.time_tracker.get('current_day', 1)}天 "
            f"{self.time_tracker.get('current_period', 'day')}",
            f"【已知地点】{len(self.location_registry)}处",
        ]
        if self.system_parameters:
            parts.append(f"【系统参数】{self.system_parameters}")
        if self.character_latest_states:
            char_summary = "; ".join(
                f"{name}: {state.get('appearance', '?')}"
                for name, state in list(self.character_latest_states.items())[:10]
            )
            parts.append(f"【角色最新状态】{char_summary}")
        return "\n".join(parts)
```

- [ ] **Step 3: Write shared LLM utils** (`shared/llm_utils.py`)

```python
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


def safe_parse_json_list(raw: str, label: str) -> list:
    """Parse LLM output as JSON list with truncation retry hint."""
    raw = raw.strip()
    # Extract JSON from markdown code blocks
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", raw, re.DOTALL)
    if match:
        raw = match.group(1).strip()

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        return []
    except json.JSONDecodeError as exc:
        if _is_truncated_json(raw):
            logger.warning("[%s] JSON appears truncated: %s", label, exc)
            return []  # Caller should retry with larger max_tokens
        logger.warning("[%s] JSON parse failed: %s", label, exc)
        return []


def _is_truncated_json(raw: str) -> bool:
    """Detect likely truncated JSON output."""
    raw = raw.rstrip()
    if not raw:
        return False
    open_brackets = raw.count("[") + raw.count("{")
    close_brackets = raw.count("]") + raw.count("}")
    return open_brackets > close_brackets


def clamp(value: float, low: float, high: float) -> float:
    """Double-sided clamp."""
    return max(low, min(value, high))


def safe_get_str(d: dict, key: str, default: str = "") -> str:
    """Safe dict access with type coercion to str."""
    val = d.get(key, default)
    if val is None:
        return default
    return str(val)


def safe_get_list(d: dict, key: str) -> list:
    """Safe dict access with type coercion to list."""
    val = d.get(key, [])
    if isinstance(val, str):
        return [val]
    if isinstance(val, list):
        return val
    return []
```

- [ ] **Step 4: Run structure verification**

```bash
find skills/story-deconstruction -type f | head -30
```

Expected: All directories and __init__.py files present.

- [ ] **Step 5: Commit**

```bash
git add skills/story-deconstruction/
git commit -m "feat(story-deconstruction): scaffold directory structure and shared schemas"
```

---

### Task 2: Prepare E2E test data

**Files:**
- Create: `skills/story-deconstruction/data/test_input/chapter_001.txt`
- Create: `skills/story-deconstruction/data/test_input/chapter_002.txt`
- Create: `skills/story-deconstruction/data/test_input/chapter_003.txt`

**Requirement:** 3 chapters from a public-domain or user-provided novel. Must contain:
- A-type (setting/world rules) paragraphs
- B-type (narrative events) paragraphs
- C-type (system/alternate dimension) paragraphs if applicable
- Multiple scene transitions (location/time changes)
- At least 2 named characters recurring across chapters
- At least 1 foreshadowing setup

- [ ] **Step 1: Source test chapters**

Use existing project test data from `AI-narrated-recap-analyst/data/projects/` or ask user to provide 3 chapters. Copy to `skills/story-deconstruction/data/test_input/`.

- [ ] **Step 2: Verify content covers all paragraph types**

```bash
wc -l skills/story-deconstruction/data/test_input/*.txt
# Each chapter should be 100-500 lines
```

- [ ] **Step 3: Commit**

```bash
git add skills/story-deconstruction/data/
git commit -m "feat(story-deconstruction): add E2E test chapters"
```

---

## Phase 2: text-segmentation Skill

### Task 3: Write text-segmentation SKILL.md

**Files:**
- Create: `skills/story-deconstruction/subskills/text-segmentation/SKILL.md`
- Create: `skills/story-deconstruction/subskills/text-segmentation/nodes/01_setup.md`
- Create: `skills/story-deconstruction/subskills/text-segmentation/nodes/02_segment.md`
- Create: `skills/story-deconstruction/subskills/text-segmentation/nodes/03_review.md`

**Source:** Read `abc_segmenter_pass1.yaml` and `abc_segmenter_pass2.yaml` completely. Port prompt text verbatim into `<system_prompt>` tags.

- [ ] **Step 1: Write SKILL.md frontmatter and graph structure**

```markdown
---
name: text-segmentation
description: >
  ABC paragraph segmentation with Two-Pass validation.
  Classifies chapter paragraphs as A(setting)/B(event)/C(system).
  Use when analyzing raw chapter text for story deconstruction.
type: graph
context_mapping:
  chapter_content: "{input.chapter_content}"
  chapter_number: "{input.chapter_number}"
io:
  inputs:
    - name: chapter_content
      type: str
      source: runtime
    - name: chapter_number
      type: int
      source: runtime
  outputs:
    - name: segmentation_result
      type: dict
      target: artifact
---

<node id="setup" depends_on="">
<ref path="nodes/01_setup.md" />
</node>

<node id="segment" depends_on="setup">
<ref path="nodes/02_segment.md" />
</node>

<node id="review" depends_on="segment">
<ref path="nodes/03_review.md" />
</node>
```

- [ ] **Step 2: Write nodes/01_setup.md** (code-only phase)

```markdown
<phase_config>
name: setup
requires_llm: false
tools:
  - script.segmenter.prepare_chapter
</phase_config>

<system_prompt>
Setup phase: prepare chapter text with line numbers for segmentation.
</system_prompt>
```

- [ ] **Step 3: Write nodes/02_segment.md** (LLM phase — Pass 1)

Port system_prompt from `abc_segmenter_pass1.yaml` verbatim. This is the core ABC classification prompt with:
- A/B/C type definitions and decision rules
- P0 principle (A/C must be independently segmented)
- Scene break detection criteria
- Output format specification (段落N（X类-描述）+ 行号)

```markdown
<phase_config>
name: segment
tier: balanced
tools:
  - script.segmenter.parse_segmentation_output
  - script.segmenter.store_segments
max_iterations: 10
max_nudges: 2
</phase_config>

<system_prompt>
[PORT VERBATIM FROM abc_segmenter_pass1.yaml system prompt]
[Include full A/B/C classification rules, P0 principles, output format]
</system_prompt>

<user_prompt>
请对以下章节进行ABC分段：

第{chapter_number}章

{chapter_with_line_numbers}
</user_prompt>

<data_architecture>
## Input
- `chapter_with_line_numbers`: str — Chapter text with "    N| line" format
- `chapter_number`: int

## Output (stored in context by store_segments tool)
- `segments`: list[dict] — Each: {index, type, content, start_line, end_line, description}
- `raw_segmentation`: str — LLM raw output for Pass 2 review
</data_architecture>
```

- [ ] **Step 4: Write nodes/03_review.md** (LLM phase — Pass 2)

Port system_prompt from `abc_segmenter_pass2.yaml` verbatim. This is the 4-step validation:
1. C类边界检查
2. A/B混合检查
3. B类时空连续性检查
4. 分类基础准确性检查

```markdown
<phase_config>
name: review
tier: balanced
tools:
  - script.segmenter.parse_segmentation_output
  - script.segmenter.store_segments
  - script.segmenter.log_ambiguous_segments
validator: script.validators.validate_segmentation
max_retries: 2
retry_target: segment
max_iterations: 10
max_nudges: 2
</phase_config>

<system_prompt>
[PORT VERBATIM FROM abc_segmenter_pass2.yaml system prompt]
[Include 4-step validation process, correction output format]
</system_prompt>

<user_prompt>
请检查以下分段结果：

【原文】
{chapter_content}

【Pass 1 分段结果】
{raw_segmentation}

第{chapter_number}章
</user_prompt>
```

- [ ] **Step 5: Verify SKILL.md compiles**

```bash
cd /Users/sevenx/Documents/coding/agent-harness
python -c "
from graph_agent.core.compiler import compile_skill
from pathlib import Path
result = compile_skill(Path('skills/story-deconstruction/subskills/text-segmentation'))
print(f'Issues: {len(result.issues)}')
for issue in result.issues:
    print(f'  [{issue.severity}] {issue.rule_id}: {issue.message}')
"
```

Expected: 0 FATAL issues. WARNING issues acceptable for missing tool implementations.

- [ ] **Step 6: Commit**

```bash
git add skills/story-deconstruction/subskills/text-segmentation/
git commit -m "feat(text-segmentation): SKILL.md with Two-Pass ABC segmentation"
```

---

### Task 4: Write text-segmentation tool functions

**Files:**
- Create: `skills/story-deconstruction/subskills/text-segmentation/script/segmenter.py`

**Source:** Port from `abc_segmenter.py`. Key functions to implement:

- [ ] **Step 1: Write segmenter.py**

Port these functions from `abc_segmenter.py`:
- `prepare_chapter(chapter_content, chapter_number, ctx)` — Add line numbers, store in context
- `parse_segmentation_output(raw_output, ctx)` — Regex parse LLM markdown output into segment dicts
- `store_segments(segments_json, ctx)` — Validate and store parsed segments in context
- `log_ambiguous_segments(segment_index, reason, ctx)` — Layer 3 annotation for uncertain segments

Key porting rules:
- All functions take `ctx: dict` parameter (graph_agent convention)
- Return `str` (graph_agent tool requirement)
- Store results in `ctx["segments"]`, `ctx["raw_segmentation"]`
- Port `_parse_llm_output()` regex patterns exactly
- Port `_extract_paragraph_contents()` bounds checking
- Port `_detect_scene_breaks()` heuristic keywords
- Port `_contains_a_class_content()` detection

```python
# Function signatures (exact implementations ported from abc_segmenter.py):

def prepare_chapter(chapter_content: str, chapter_number: int, context: dict) -> str:
    """Prepare chapter text with line numbers for ABC segmentation.
    
    Adds line numbers in '    N| line' format and stores in context.
    Call this first before segmentation.
    """

def parse_segmentation_output(raw_output: str, context: dict) -> str:
    """Parse LLM segmentation markdown into structured segments.
    
    Extracts paragraph headers (段落N（X类）) and line ranges.
    Stores parsed segments in context['parsed_segments'].
    Returns summary of parsed segments count and any warnings.
    """

def store_segments(context: dict) -> str:
    """Validate and finalize parsed segments.
    
    Extracts paragraph content from original text using line ranges.
    Validates text restoration (segments reconstruct original).
    Stores final result in context['segments'] and context['segmentation_result'].
    Returns completion summary.
    """

def log_ambiguous_segments(segment_index: int, reason: str, confidence: float, context: dict) -> str:
    """Log an uncertain segmentation decision for human review.
    
    When confidence < 0.7, call this to flag the segment for annotation.
    Stores in context['_ambiguity_reports'] for calibration pipeline.
    """
```

- [ ] **Step 2: Verify tool function signatures**

```bash
python -c "
import inspect
import importlib.util
spec = importlib.util.spec_from_file_location(
    'segmenter',
    'skills/story-deconstruction/subskills/text-segmentation/script/segmenter.py'
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
for name in ['prepare_chapter', 'parse_segmentation_output', 'store_segments', 'log_ambiguous_segments']:
    fn = getattr(mod, name)
    sig = inspect.signature(fn)
    print(f'{name}{sig} -> {fn.__annotations__.get(\"return\", \"?\")}')
"
```

Expected: All functions have `context: dict` param, return `str`.

- [ ] **Step 3: Commit**

```bash
git add skills/story-deconstruction/subskills/text-segmentation/script/segmenter.py
git commit -m "feat(text-segmentation): port segmenter tools from abc_segmenter.py"
```

---

### Task 5: Write text-segmentation 3-layer validator

**Files:**
- Create: `skills/story-deconstruction/subskills/text-segmentation/script/validators.py`

- [ ] **Step 1: Write validators.py**

```python
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def validate_segmentation(ctx: dict) -> tuple[bool, list[str]]:
    """3-layer validation for ABC segmentation.

    Layer 1: Structural completeness (fields exist, types correct, coverage).
    Layer 2: Semantic self-consistency (summary coherence, type accuracy).
    Layer 3: Annotation flagging (mark uncertain cases for calibration).

    Returns:
        (passed, errors) — passed=False triggers retry with errors as feedback.
    """
    errors: list[str] = []
    segments = ctx.get("segments", [])
    chapter_lines = ctx.get("chapter_lines", [])

    # === Layer 1: Structural Completeness ===
    if not segments:
        errors.append("No segments produced. Re-analyze the chapter text.")
        return (False, errors)

    # Check required fields
    for seg in segments:
        if not seg.get("type") or seg["type"] not in ("A", "B", "C"):
            errors.append(f"Segment {seg.get('index')}: invalid type '{seg.get('type')}'")
        if not seg.get("content"):
            errors.append(f"Segment {seg.get('index')}: empty content")

    # Check line coverage
    if chapter_lines:
        total_lines = len(chapter_lines)
        covered = set()
        for seg in segments:
            for ln in range(seg.get("start_line", 0), seg.get("end_line", 0) + 1):
                covered.add(ln)
        coverage = len(covered) / total_lines if total_lines > 0 else 0
        if coverage < 0.9:
            errors.append(
                f"Line coverage {coverage:.0%} < 90%. "
                f"Missing lines: check segment boundaries."
            )

    # Check continuity (no gaps between segments)
    sorted_segs = sorted(segments, key=lambda s: s.get("start_line", 0))
    for i in range(1, len(sorted_segs)):
        prev_end = sorted_segs[i - 1].get("end_line", 0)
        curr_start = sorted_segs[i].get("start_line", 0)
        if curr_start > prev_end + 1:
            errors.append(
                f"Gap between segment {sorted_segs[i-1].get('index')} "
                f"(end={prev_end}) and {sorted_segs[i].get('index')} "
                f"(start={curr_start})"
            )

    # === Layer 2: Semantic Self-Consistency ===

    # Check: A-type segments should not contain narrative action verbs
    action_verbs = re.compile(r"(跑|打|杀|追|逃|抓|砍|刺|射|冲|跳)")
    setting_keywords = re.compile(r"(规则|体系|原则|铁律|系统|等级|能力|序列)")
    for seg in segments:
        if seg.get("type") == "A":
            action_count = len(action_verbs.findall(seg.get("content", "")))
            setting_count = len(setting_keywords.findall(seg.get("content", "")))
            if action_count > 3 and setting_count < 2:
                errors.append(
                    f"Segment {seg.get('index')} classified as A(setting) "
                    f"but contains {action_count} action verbs — likely B(event)."
                )

    # Check: segments with multiple distinct actions may need splitting
    for seg in segments:
        content = seg.get("content", "")
        # Count sentences with different subjects (rough heuristic)
        sentences = [s.strip() for s in re.split(r"[。！？]", content) if s.strip()]
        if len(sentences) > 15:
            ctx.setdefault("_ambiguity_reports", []).append({
                "segment_index": seg.get("index"),
                "reason": f"Segment has {len(sentences)} sentences — may need splitting",
                "confidence": 0.5,
                "layer": "L2_semantic",
            })

    # Check: adjacent same-type segments with similar content may need merging
    for i in range(1, len(sorted_segs)):
        prev = sorted_segs[i - 1]
        curr = sorted_segs[i]
        if prev.get("type") == curr.get("type") == "B":
            prev_desc = prev.get("description", "")
            curr_desc = curr.get("description", "")
            if prev_desc and curr_desc and prev_desc == curr_desc:
                errors.append(
                    f"Segments {prev.get('index')} and {curr.get('index')} "
                    f"have identical descriptions — consider merging."
                )

    if errors:
        return (False, errors)
    return (True, [])
```

- [ ] **Step 2: Write unit test for validator**

```python
# tests/test_text_segmentation.py
import pytest
from skills.story_deconstruction.subskills.text_segmentation.script.validators import (
    validate_segmentation,
)

class TestSegmentationValidator:
    def test_empty_segments_fails(self):
        ctx = {"segments": [], "chapter_lines": ["line1"]}
        passed, errors = validate_segmentation(ctx)
        assert not passed
        assert "No segments" in errors[0]

    def test_valid_segments_passes(self):
        ctx = {
            "segments": [
                {"index": 1, "type": "B", "content": "他冲了出去。", "start_line": 1, "end_line": 3, "description": "主角行动"},
                {"index": 2, "type": "A", "content": "这个世界有规则体系。", "start_line": 4, "end_line": 5, "description": "世界设定"},
            ],
            "chapter_lines": ["l1", "l2", "l3", "l4", "l5"],
        }
        passed, errors = validate_segmentation(ctx)
        assert passed

    def test_invalid_type_detected(self):
        ctx = {
            "segments": [{"index": 1, "type": "X", "content": "text", "start_line": 1, "end_line": 1}],
            "chapter_lines": ["text"],
        }
        passed, errors = validate_segmentation(ctx)
        assert not passed
        assert "invalid type" in errors[0]
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/sevenx/Documents/coding/agent-harness
python -m pytest skills/story-deconstruction/tests/test_text_segmentation.py -xvs
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add skills/story-deconstruction/subskills/text-segmentation/script/validators.py
git add skills/story-deconstruction/tests/test_text_segmentation.py
git commit -m "feat(text-segmentation): 3-layer validator with unit tests"
```

---

### Task 6: Write text-segmentation calibration references

**Files:**
- Create: `skills/story-deconstruction/subskills/text-segmentation/references/calibration/golden_examples.json`
- Create: `skills/story-deconstruction/subskills/text-segmentation/references/calibration/corrections.json`
- Create: `skills/story-deconstruction/subskills/text-segmentation/references/calibration/rules.yaml`

- [ ] **Step 1: Create initial calibration files**

`golden_examples.json` — starts empty, populated by human review:
```json
[]
```

`corrections.json` — Triple-Store format, starts empty:
```json
[]
```

`rules.yaml` — Initial rules derived from abc_segmenter_pass1.yaml:
```yaml
# Segmentation rules inferred from calibration
# Updated automatically as human annotations accumulate

type_rules:
  A_setting:
    - "Contains world-building explanation (3-question test: function + importance + universality)"
    - "Must be independently segmented, never merged with B"
  B_event:
    - "Character actions, scene descriptions, plot progression"
    - "Split on: time change, location change, event change"
    - "Do NOT split on: minor detail variation within same scene"
  C_system:
    - "Content outside physical reality (system space, consciousness)"
    - "Must be independently segmented, never merged with B"
    - "Entire [enter → exit] block is one C segment"

splitting_rules:
  too_long: "If summary cannot cover all content in one sentence, split"
  too_short: "If summary overlaps with adjacent segment, merge"
  scene_break: "Time/location markers mid-paragraph indicate split point"
```

- [ ] **Step 2: Commit**

```bash
git add skills/story-deconstruction/subskills/text-segmentation/references/
git commit -m "feat(text-segmentation): initial calibration reference files"
```

---

## Phase 3: event-extraction Skill

### Task 7: Write event-extraction SKILL.md and nodes

**Files:**
- Create: `skills/story-deconstruction/subskills/event-extraction/SKILL.md`
- Create: `skills/story-deconstruction/subskills/event-extraction/nodes/01_setup.md`
- Create: `skills/story-deconstruction/subskills/event-extraction/nodes/02_aggregate.md`
- Create: `skills/story-deconstruction/subskills/event-extraction/nodes/03_review.md`
- Create: `skills/story-deconstruction/subskills/event-extraction/nodes/04_settings.md`

**Source:** Port prompts from `event_timeline_pass1.yaml`, `event_timeline_review.yaml`, `event_timeline_pass2.yaml` verbatim.

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: event-extraction
description: >
  Extract event timeline from ABC-segmented paragraphs using 3-pass system.
  Pass 1: event aggregation + timeline reordering.
  Pass 1R: semantic coherence review.
  Pass 2: setting extraction + correlation.
  Use after text-segmentation completes.
type: graph
context_mapping:
  segmentation_result: "{input.segmentation_result}"
  chapter_number: "{input.chapter_number}"
  prev_chapter_last_event: "{input.prev_chapter_last_event}"
io:
  inputs:
    - name: segmentation_result
      type: dict
      source: runtime
    - name: chapter_number
      type: int
      source: runtime
    - name: prev_chapter_last_event
      type: dict
      source: runtime
  outputs:
    - name: event_timeline
      type: dict
      target: artifact
---

<node id="setup" depends_on="">
<ref path="nodes/01_setup.md" />
</node>

<node id="aggregate" depends_on="setup">
<ref path="nodes/02_aggregate.md" />
</node>

<node id="review" depends_on="aggregate">
<ref path="nodes/03_review.md" />
</node>

<node id="settings" depends_on="review">
<ref path="nodes/04_settings.md" />
</node>
```

- [ ] **Step 2: Write nodes/01_setup.md** — Code-only: format segments as markdown

- [ ] **Step 3: Write nodes/02_aggregate.md** — LLM: Port from event_timeline_pass1.yaml

Key prompt elements to preserve:
- Dual tasks: timeline reordering + event aggregation
- Strict N:1 segment-to-event mapping
- Time field rules (parentheses = original text only)
- Cross-chapter context injection
- Output format with Event N headers

- [ ] **Step 4: Write nodes/03_review.md** — LLM: Port from event_timeline_review.yaml

Key elements:
- Semantic coherence test
- Temporal layer detection (flashback splits)
- Brief background mentions → don't split
- Renumbering on splits

- [ ] **Step 5: Write nodes/04_settings.md** — LLM: Port from event_timeline_pass2.yaml

Key elements:
- Setting identification (world mechanics, not character reactions)
- BF/BT/AF time positioning
- Core knowledge extraction (50-100 chars)
- Validator that checks N:1 constraint and coverage

- [ ] **Step 6: Verify compilation**

```bash
python -c "
from graph_agent.core.compiler import compile_skill
from pathlib import Path
result = compile_skill(Path('skills/story-deconstruction/subskills/event-extraction'))
print(f'FATAL: {sum(1 for i in result.issues if i.severity == \"FATAL\")}')
"
```

- [ ] **Step 7: Commit**

```bash
git add skills/story-deconstruction/subskills/event-extraction/
git commit -m "feat(event-extraction): SKILL.md with 3-pass event timeline extraction"
```

---

### Task 8: Write event-extraction tools and validator

**Files:**
- Create: `skills/story-deconstruction/subskills/event-extraction/script/extractor.py`
- Create: `skills/story-deconstruction/subskills/event-extraction/script/validators.py`

- [ ] **Step 1: Write extractor.py**

Port from `event_timeline_extractor.py`. Functions:
- `format_segments_for_prompt(context)` — Format segments as markdown for LLM
- `parse_events(raw_output, context)` — Parse event markdown, enforce N:1 constraint
- `parse_paragraph_indices(text)` — Robust regex parser ([1,2,3], 1-3, 段落1、段落2)
- `store_events(context)` — Validate and store EventTimeline
- `parse_settings(raw_output, context)` — Parse setting markdown
- `merge_settings_into_events(context)` — Merge with N:1 enforcement
- `log_ambiguous_events(event_id, reason, confidence, context)` — Layer 3 annotation

- [ ] **Step 2: Write validators.py**

```python
def validate_event_extraction(ctx: dict) -> tuple[bool, list[str]]:
    """3-layer validation for event extraction.
    
    L1: Structural — events exist, required fields present, N:1 constraint
    L2: Semantic — coverage (>= 50% B/C segments assigned), no pure-numeric times,
        event_summary covers key entities from source paragraphs
    L3: Annotation — flag events with empty paragraph_indices or unclear time
    """
```

Key checks ported from `_evaluate_timeline_quality()`:
- `empty_ratio <= 0.2` (max 20% events with empty indices)
- `coverage_ratio >= 0.5` (min 50% B/C segment coverage)
- `invalid_time_ratio == 0` (no pure-numeric time values)
- N:1 constraint: no paragraph_index appears in multiple events

- [ ] **Step 3: Write unit tests and run**

- [ ] **Step 4: Commit**

```bash
git add skills/story-deconstruction/subskills/event-extraction/script/
git commit -m "feat(event-extraction): port extractor tools and 3-layer validator"
```

---

## Phase 4: batch-analysis Skill

### Task 9: Write batch-analysis SKILL.md and nodes

**Files:**
- Create: `skills/story-deconstruction/subskills/batch-analysis/SKILL.md`
- Create: `skills/story-deconstruction/subskills/batch-analysis/nodes/01_prepare.md`
- Create: `skills/story-deconstruction/subskills/batch-analysis/nodes/02_entity_and_characters.md`
- Create: `skills/story-deconstruction/subskills/batch-analysis/nodes/03_parallel_analysis.md`
- Create: `skills/story-deconstruction/subskills/batch-analysis/nodes/04_continuity.md`
- Create: `skills/story-deconstruction/subskills/batch-analysis/nodes/05_assemble.md`

**Architecture:** Star topology — Node 2 (entity+characters) runs first as center node, Node 3 (6 remaining paths) consumes entity list.

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: batch-analysis
description: >
  Analyze a single batch (10 chapters) across 7 dimensions with entity registration
  and narrative continuity checking. Star topology: entity registration runs first,
  other paths consume entity list.
  Use for each batch in the story deconstruction pipeline.
type: graph
context_mapping:
  batch_events: "{input.batch_events}"
  accumulated_context: "{input.accumulated_context}"
  para_text_lookup: "{input.para_text_lookup}"
  dynamic_dimensions: "{input.dynamic_dimensions}"
  chapter_range: "{input.chapter_range}"
io:
  inputs:
    - name: batch_events
      type: list
      source: runtime
    - name: accumulated_context
      type: dict
      source: runtime
    - name: para_text_lookup
      type: dict
      source: runtime
    - name: dynamic_dimensions
      type: list
      source: runtime
    - name: chapter_range
      type: list
      source: runtime
  outputs:
    - name: batch_result
      type: dict
      target: artifact
    - name: updated_accumulated
      type: dict
      target: artifact
---

<node id="prepare" depends_on="">
<ref path="nodes/01_prepare.md" />
</node>

<node id="entity_and_characters" depends_on="prepare">
<ref path="nodes/02_entity_and_characters.md" />
</node>

<node id="parallel_analysis" depends_on="entity_and_characters">
<ref path="nodes/03_parallel_analysis.md" />
</node>

<node id="continuity" depends_on="parallel_analysis">
<ref path="nodes/04_continuity.md" />
</node>

<node id="assemble" depends_on="continuity">
<ref path="nodes/05_assemble.md" />
</node>
```

- [ ] **Step 2: Write node files**

**01_prepare.md** — Code-only: format batch data, load accumulated state, build context text

**02_entity_and_characters.md** — LLM phase (star center):
- System prompt ports _PROMPT_CHARACTER_CHANGES with entity registration merged
- Tools: `register_entity`, `resolve_alias`, `analyze_character_state`, `store_entity_results`
- This phase produces: entity_registry updates + character_states + character_changes
- Other paths reference entity IDs from this phase's output

**03_parallel_analysis.md** — LLM phase (6 remaining paths):
- Tools that internally call LLM for each dimension:
  - `analyze_tension_emotion_vibe(batch_events_text, context)` — Port _PROMPT_TENSION_EMOTION_VIBE
  - `analyze_system_evolution(c_type_events_text, context)` — Port _PROMPT_SYSTEM_EVOLUTION
  - `analyze_prop_changes(events_text, context)` — Port _PROMPT_PROP_CHANGES
  - `analyze_emotional_arcs(events_text, context)` — Port _PROMPT_EMOTIONAL_ARCS
  - `analyze_foreshadowing(events_text, context)` — Port _PROMPT_FORESHADOWING
  - `analyze_spatiotemporal(events_text, context)` — Port _PROMPT_SPATIOTEMPORAL
- Agent calls all 6 tools, storing results in context

**04_continuity.md** — LLM phase:
- Checks entity states vs previous batch for contradictions
- Tools: `check_continuity`, `log_continuity_warning`

**05_assemble.md** — Code-only:
- Merges all 7 paths into enriched events
- Updates BatchAccumulator
- Derives elements views (character_evolution, prop_evolution, emotion_curve, location_timeline)

- [ ] **Step 3: Verify compilation and commit**

---

### Task 10: Write batch-analysis path tools

**Files:**
- Create: `skills/story-deconstruction/subskills/batch-analysis/script/paths.py`

**Source:** Port all 7 prompt texts from `node1_agent.py` (lines 1-800).

- [ ] **Step 1: Write paths.py**

Each function:
1. Formats input events into prompt text
2. Calls LLM via graph_agent's model resolver (or a shared LLM utility)
3. Parses JSON response with truncation retry
4. Stores results in context
5. Returns summary string

```python
def analyze_tension_emotion_vibe(context: dict) -> str:
    """Analyze tension, emotion, and lighting for all batch events.
    
    Runs LLM analysis for climax_intensity, climax_type, emotion_intensity,
    emotion_type, and lighting_vibe. Call after entity registration completes.
    Results stored in context['tension_results'].
    """

def analyze_system_evolution(context: dict) -> str:
    """Analyze system/world-rule changes from C-type events only.
    
    Tracks dynamic system parameters across batches.
    Results stored in context['system_results'].
    """

# ... (4 more functions with same pattern)
```

- [ ] **Step 2: Commit**

---

### Task 11: Write batch-analysis entity and accumulator tools

**Files:**
- Create: `skills/story-deconstruction/subskills/batch-analysis/script/entity.py`
- Create: `skills/story-deconstruction/subskills/batch-analysis/script/accumulator.py`
- Create: `skills/story-deconstruction/subskills/batch-analysis/script/continuity.py`

- [ ] **Step 1: Write entity.py**

Port from `visual_extract_v2/tools/reconciler.py`:
- `register_entity(name, entity_type, description, initial_state, context)` — Assign ID (CHR_NNN/LOC_NNN/PRP_NNN)
- `resolve_alias(alias, canonical_name, context)` — Link alias to existing entity
- `get_entity_registry(context)` — Return current registry as formatted string
- `store_entity_results(context)` — Finalize entity updates for this batch

- [ ] **Step 2: Write accumulator.py**

Port `BatchAccumulator` operations:
- `load_accumulated_state(context)` — Deserialize accumulated_context into working state
- `update_accumulator(context)` — Merge current batch results into accumulator
- `save_accumulated_state(context)` — Serialize back to context for next batch
- `build_batch_context_text(context)` — Format accumulated state for prompt injection

- [ ] **Step 3: Write continuity.py**

Port from `narrative_continuity/analyzer.py`:
- `check_continuity(context)` — Compare entity states vs previous batch
- `log_continuity_warning(entity_id, field, expected, actual, context)` — Record contradiction

- [ ] **Step 4: Commit**

---

### Task 12: Write batch-analysis validator

**Files:**
- Create: `skills/story-deconstruction/subskills/batch-analysis/script/validators.py`

- [ ] **Step 1: Write validators.py**

Port dimension coverage thresholds from `node1_agent.py` judge():

```python
DIMENSION_THRESHOLDS = {
    "characters_involved": 0.40,
    "character_changes": 0.15,
    "props_involved": 0.08,
    "prop_changes": 0.04,
    "climax_intensity": 0.04,
    "emotion_intensity": 0.90,
    "emotion_type": 0.90,
    "lighting_vibe": 0.80,
    "scene_space_type": 0.90,
    "system_change": 0.01,
    "foreshadowing": 0.02,
    "arc_moments": 0.03,
}

def validate_batch_analysis(ctx: dict) -> tuple[bool, list[str]]:
    """3-layer validation for batch analysis.
    
    L1: All 7 path results exist, events fully covered
    L2: Cross-path consistency (climax ↔ emotion, character death ↔ absence)
    L3: Flag low-confidence entity matches and continuity warnings
    """
```

- [ ] **Step 2: Commit**

---

## Phase 5: global-synthesis Skill

### Task 13: Write global-synthesis SKILL.md and nodes

**Files:**
- Create: `skills/story-deconstruction/subskills/global-synthesis/SKILL.md`
- Create: `skills/story-deconstruction/subskills/global-synthesis/nodes/01_global_analysis.md`
- Create: `skills/story-deconstruction/subskills/global-synthesis/nodes/02_scene_assembly.md`
- Create: `skills/story-deconstruction/subskills/global-synthesis/nodes/03_retroactive.md`
- Create: `skills/story-deconstruction/subskills/global-synthesis/nodes/04_export.md`

- [ ] **Step 1: Write SKILL.md and 4 nodes**

**Node 1 (LLM):** 3 global analysis tools — climax ranking, foreshadowing closure, character ranking
**Node 2 (code-only):** Scene aggregation — deterministic O(n) algorithm from `_aggregate_scenes()`
**Node 3 (LLM):** Retroactive correction — anchor point scanning
**Node 4 (code-only):** Final export assembly — unified event stream JSON + Markdown

- [ ] **Step 2: Commit**

---

### Task 14: Write global-synthesis tools and validator

**Files:**
- Create: `skills/story-deconstruction/subskills/global-synthesis/script/synthesis.py`
- Create: `skills/story-deconstruction/subskills/global-synthesis/script/retroactive.py`
- Create: `skills/story-deconstruction/subskills/global-synthesis/script/scene_builder.py`
- Create: `skills/story-deconstruction/subskills/global-synthesis/script/validators.py`

- [ ] **Step 1: Write synthesis.py**

Port 3 global analysis prompts from `node1_agent.py`:
- `rank_climaxes(context)` — Normalize intensity, global ranking
- `close_foreshadowing(context)` — Verify open/resolved/abandoned status
- `rank_characters(context)` — Appearances + changes + aliases merge

- [ ] **Step 2: Write retroactive.py**

Port from `_run_retroactive_correction()`:
- `scan_anchor_points(context)` — Find explicit text anchors
- `apply_corrections(context)` — Patch batch_outputs in-place
- Modifiable fields: clothing, makeup, hygiene, injuries, key_relationships, social_position, normalized_location, lighting_vibe, time_coordinate.absolute_date
- Unmodifiable: scene_space_type, climax_intensity, emotion_type

- [ ] **Step 3: Write scene_builder.py**

Port from `_aggregate_scenes()`:
- `build_unified_event_stream(context)` — Deterministic scene boundary detection
- Scene boundary triggers: location change, day crossing, space_type toggle
- Output: JSON + Markdown

- [ ] **Step 4: Write validators.py**

```python
def validate_global_synthesis(ctx: dict) -> tuple[bool, list[str]]:
    """3-layer validation for global synthesis.
    
    L1: climax_ranking, character_ranking, foreshadowing_closure all present
    L2: Logic backtracking — top climax has traceable foreshadowing
    L3: Flag corrections that introduce new contradictions
    """
```

- [ ] **Step 5: Commit**

---

## Phase 6: Orchestrator Skill

### Task 15: Write orchestrator SKILL.md

**Files:**
- Create: `skills/story-deconstruction/SKILL.md`
- Create: `skills/story-deconstruction/nodes/01_segmentation.md`
- Create: `skills/story-deconstruction/nodes/02_event_extraction.md`
- Create: `skills/story-deconstruction/nodes/03_batch_loop.md`
- Create: `skills/story-deconstruction/nodes/04_global_synthesis.md`

**Architecture:** 4 nodes — 2 subgraphs + 1 LLM-driven batch loop + 1 subgraph

- [ ] **Step 1: Write SKILL.md**

```markdown
---
name: story-deconstruction
description: >
  Complete story deconstruction pipeline. Orchestrates text segmentation,
  event extraction, batch analysis (LLM-driven loop), and global synthesis.
  Use for full novel/screenplay analysis.
type: graph
context_mapping:
  chapters: "{input.chapters}"
  project_id: "{input.project_id}"
io:
  inputs:
    - name: chapters
      type: list
      source: runtime
    - name: project_id
      type: str
      source: runtime
  outputs:
    - name: story_framework
      type: dict
      target: artifact
---

<node id="segmentation" depends_on="">
<ref path="nodes/01_segmentation.md" />
</node>

<node id="event_extraction" depends_on="segmentation">
<ref path="nodes/02_event_extraction.md" />
</node>

<node id="batch_loop" depends_on="event_extraction">
<ref path="nodes/03_batch_loop.md" />
</node>

<node id="global_synthesis" depends_on="batch_loop">
<ref path="nodes/04_global_synthesis.md" />
</node>
```

- [ ] **Step 2: Write nodes/01_segmentation.md**

Code-only phase that loops through chapters, calling text-segmentation subgraph for each:

```markdown
<phase_config>
name: segmentation
requires_llm: false
tools:
  - script.orchestrator.segment_all_chapters
</phase_config>
```

`segment_all_chapters` iterates chapters, invokes text-segmentation subskill per chapter, collects results.

- [ ] **Step 3: Write nodes/02_event_extraction.md**

Code-only phase that loops through segmented chapters, calling event-extraction subgraph:

```markdown
<phase_config>
name: event_extraction
requires_llm: false
tools:
  - script.orchestrator.extract_all_events
</phase_config>
```

- [ ] **Step 4: Write nodes/03_batch_loop.md** (LLM-driven loop — 方案A)

```markdown
<phase_config>
name: batch_loop
tier: balanced
tools:
  - script.orchestrator.prepare_next_batch
  - script.orchestrator.run_batch_analysis
  - script.orchestrator.check_all_batches_done
  - script.orchestrator.discover_tracking_dimensions
max_iterations: 50
max_nudges: 5
</phase_config>

<system_prompt>
你是故事解构分析的编排器。你的任务是按批次（每10章一批）分析所有事件。

## 执行步骤

1. 首先调用 discover_tracking_dimensions 发现动态追踪维度
2. 调用 prepare_next_batch 获取下一批事件
3. 调用 run_batch_analysis 运行批次分析
4. 调用 check_all_batches_done 检查是否还有未处理的批次
5. 如果还有批次，回到步骤2
6. 所有批次处理完毕后，调用 finish_task 报告完成

## 重要
- 每个批次必须按顺序处理（第1批 → 第2批 → ...）
- 每个批次的结果会累积到下一个批次的上下文中
- 如果某个批次失败，记录警告并继续下一批
</system_prompt>

<user_prompt>
项目：{project_id}
总章节数：{total_chapters}
总事件数：{total_events}

请开始批次分析。
</user_prompt>
```

- [ ] **Step 5: Write nodes/04_global_synthesis.md**

Subgraph invocation of global-synthesis skill:

```markdown
<phase_config>
name: global_synthesis
subgraph: subskills/global-synthesis/SKILL.md
context_bridge:
  inputs:
    batch_outputs: all_batch_results
    accumulated_context: final_accumulated
    entity_registry: entity_registry
  outputs:
    story_framework: story_framework
</phase_config>
```

- [ ] **Step 6: Commit**

---

### Task 16: Write orchestrator tools

**Files:**
- Create: `skills/story-deconstruction/script/orchestrator.py`

- [ ] **Step 1: Write orchestrator.py**

```python
def segment_all_chapters(context: dict) -> str:
    """Run text-segmentation subskill for each chapter.
    
    Iterates context['chapters'], invokes text-segmentation SKILL for each.
    Stores results in context['all_segmentations'].
    """

def extract_all_events(context: dict) -> str:
    """Run event-extraction subskill for each segmented chapter.
    
    Uses context['all_segmentations'], invokes event-extraction SKILL for each.
    Stores results in context['all_events'] and context['para_text_lookup'].
    """

def discover_tracking_dimensions(context: dict) -> str:
    """Discover story-specific tracking dimensions from first 30 events.
    
    Calls LLM to identify dynamic dimensions (e.g., cultivation_level, vehicle).
    Stores in context['dynamic_dimensions'].
    """

def prepare_next_batch(context: dict) -> str:
    """Prepare the next 10-chapter batch of events.
    
    Increments batch index, slices events by chapter range.
    Returns batch summary for agent awareness.
    """

def run_batch_analysis(context: dict) -> str:
    """Run batch-analysis subskill for current batch.
    
    Invokes batch-analysis SKILL with current batch events + accumulated state.
    Stores batch result and updates accumulated context.
    """

def check_all_batches_done(context: dict) -> str:
    """Check if all batches have been processed.
    
    Returns 'ALL_BATCHES_COMPLETE' or 'BATCHES_REMAINING: N'.
    """
```

- [ ] **Step 2: Commit**

---

## Phase 7: E2E Integration & Testing

### Task 17: Write E2E integration test

**Files:**
- Create: `skills/story-deconstruction/tests/test_e2e_pipeline.py`

- [ ] **Step 1: Write smoke test**

```python
"""E2E smoke test for story-deconstruction pipeline.

Runs the full orchestrator with 3 test chapters.
Verifies all subskills produce expected output structure.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# This test requires LLM API access — skip in CI without keys
pytestmark = pytest.mark.skipif(
    not Path(".env").exists(),
    reason="Requires .env with API keys"
)


def test_full_pipeline_produces_story_framework():
    """Run full pipeline on 3 test chapters, verify output structure."""
    from graph_agent.core.runner import run_skill

    skill_path = Path("skills/story-deconstruction")
    test_data = Path("skills/story-deconstruction/data/test_input")

    chapters = []
    for ch_file in sorted(test_data.glob("chapter_*.txt")):
        chapters.append({
            "chapter_number": int(ch_file.stem.split("_")[1]),
            "content": ch_file.read_text(encoding="utf-8"),
        })

    assert len(chapters) >= 3, "Need at least 3 test chapters"

    result = run_skill(
        skill_path,
        inputs={"chapters": chapters, "project_id": "test_e2e"},
    )

    ctx = result["context"]

    # Verify segmentation
    assert "all_segmentations" in ctx
    for seg in ctx["all_segmentations"]:
        assert seg["total_paragraphs"] > 0
        for p in seg["paragraphs"]:
            assert p["type"] in ("A", "B", "C")

    # Verify events
    assert "all_events" in ctx

    # Verify batch results
    assert "all_batch_results" in ctx
    assert len(ctx["all_batch_results"]) >= 1

    # Verify global synthesis
    assert "story_framework" in ctx
    fw = ctx["story_framework"]
    assert "climax_ranking" in fw
    assert "character_ranking" in fw
    assert "foreshadowing_closure" in fw
```

- [ ] **Step 2: Run smoke test**

```bash
cd /Users/sevenx/Documents/coding/agent-harness
python -m pytest skills/story-deconstruction/tests/test_e2e_pipeline.py -xvs --timeout=600
```

Expected: Full pipeline completes with all assertions passing.

- [ ] **Step 3: Commit**

```bash
git add skills/story-deconstruction/tests/
git commit -m "test(story-deconstruction): E2E smoke test for full pipeline"
```

---

### Task 18: Graph_agent feature coverage verification

**Purpose:** Verify the pipeline exercises all graph_agent features listed in the design.

- [ ] **Step 1: Create coverage checklist**

| graph_agent Feature | Exercised By | Verified |
|---|---|---|
| Multi-phase orchestration | Orchestrator 4 nodes | [ ] |
| Subgraph nesting | text-seg, event-ext, global-syn subgraphs | [ ] |
| context_bridge | All subgraph invocations | [ ] |
| LLM phase | segment, review, aggregate, etc. | [ ] |
| Code-only phase | setup, assemble, scene_assembly | [ ] |
| Tool calling | All analysis tools | [ ] |
| Cognitive loop | batch_loop LLM-driven iteration | [ ] |
| Validator + retry | All subskill validators | [ ] |
| Checkpoint compaction | Long batch_loop conversations | [ ] |
| Working memory | Batch accumulator state | [ ] |
| Planning enforcement | Complex analysis phases | [ ] |
| Dead-end detection | Tool failures in analysis | [ ] |
| Error recovery | JSON truncation in path tools | [ ] |
| Cross-phase state | accumulated_context threading | [ ] |

- [ ] **Step 2: Run with tracing enabled and verify**

```bash
GRAPH_AGENT_TRACE_DIR=./trace python -m pytest \
  skills/story-deconstruction/tests/test_e2e_pipeline.py -xvs --timeout=600
```

Inspect trace JSON for all features being invoked.

- [ ] **Step 3: Final commit**

```bash
git add -A skills/story-deconstruction/
git commit -m "feat(story-deconstruction): complete pipeline with E2E tests and feature coverage"
```

---

## Execution Notes

### Delegation Strategy
All code writing tasks (Tasks 1-18) should be delegated to **Codex** via `/ask codex`. Each task is self-contained with:
- Exact file paths
- Source code references with line numbers
- Expected function signatures
- Test commands and expected output

### Quality Gates
- Each task ends with a commit — checkpoint for review
- Validators must pass before proceeding to dependent tasks
- E2E test (Task 17) is the final acceptance gate

### Risk Areas
1. **Prompt porting accuracy** — Prompts must be copied verbatim from YAML files, not paraphrased
2. **Tool function signatures** — Must follow graph_agent conventions (context: dict, return str)
3. **Subgraph context_bridge** — Input/output key mapping must be exact
4. **Batch accumulator serialization** — Must survive JSON round-trip between subgraph calls
5. **LLM calls within tools** — Need to use graph_agent's model resolver, not direct API calls
