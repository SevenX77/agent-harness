# Migration Runbook — graph_agent → video_analysis (upgrade replace)

**Date**: 2026-04-30
**Owner**: agent-harness maintainers
**Type**: **upgrade replacement** (not a fresh integration)
**Status**: Engine wheel built, smoke-tested; **migration prompt rewritten
to require a compatibility evaluation step before any source replacement**
**Companion document**: `docs/migration/PROMPT_FOR_VIDEO_ANALYSIS_AGENT.md`

---

## 1. Context discovery — what video_analysis actually has

After reading `/Users/sevenx/Documents/coding/video_analysis`, the
situation turned out to be **fundamentally different from a greenfield
integration**:

- video_analysis already vendors a **graph_agent 1.0.0** copy at
  `src/core/graph_agent/` (5.5 MB, includes a 2.3 MB embedded `deerflow/`)
- Business code uses path-style imports: `from src.core.graph_agent.xxx
  import yyy` (not `from graph_agent ...`) — there are 7 such imports
  across `src/`, `test/`, and the `visual_gt_analysis` skill
- The business skill `src/skills/visual_gt_analysis/SKILL.md` uses the
  legacy `<node id="..."><phase_config>...</phase_config></node>` wrapper
  syntax that **does not exist anywhere in the new engine** — neither in
  the loader code path nor in any upstream skill example
- Two business tools (`shot_tools.py`, `scene_tools.py`) import
  `understand_video_tool` from `graph_agent.tools.understand_video`,
  but the new wheel **does not contain that file at all** (deleted in
  v1-reset)

In short: this is a **forked-then-diverged** situation. The new wheel is
NOT a drop-in replacement for the old vendored copy.

---

## 2. New vs old engine — the actual breaking changes

| Surface | Old (1.0.0) | New (wheel) | Impact |
|---------|-------------|-------------|--------|
| Public API symbols | 23 | 33 (strict superset) | ✅ safe |
| `tools/synthesize_speech.py` | exists | exists | ✅ safe |
| `tools/md_to_json.py` | exists | exists | ✅ safe |
| `tools/providers.py` | exists | exists, but no longer imports multimodal_config | ⚠️ semantic shift |
| `tools/understand_video.py` (300 lines) | exists | **DELETED** | ❌ breaks shot_tools, scene_tools |
| `tools/generate_image.py` (316 lines) | exists | **DELETED** | ⚠️ breaks if business uses it |
| `tools/generate_video.py` (259 lines) | exists | **DELETED** | ⚠️ breaks if business uses it |
| `config/multimodal_config.py` | exists | **DELETED** | ❌ breaks all 4 multimodal tools above |
| `tools/__init__.py` exports | `generate_image_tool`, `generate_video_tool`, `synthesize_speech_tool` | only `synthesize_speech_tool` | ❌ breaks any `from ...tools import generate_*_tool` |
| `config/__init__.py` exports | `get_multimodal_role_config`, `load_multimodal_config`, `reset_multimodal_role_config` | none of those | ❌ |
| `<node id="...">` SKILL.md syntax | accepted by old loader | **NOT recognized** by new loader | ❌ visual_gt_analysis SKILL.md will not compile |
| `core/loader.py` | 660 lines | 159 lines (−76%) | ⚠️ large refactor; further hidden semantic changes possible |
| `core/compiler.py` | 885 lines | 241 lines (−73%) | ⚠️ same as above |
| `deerflow/` subtree (2.3 MB) | embedded | **completely removed** | ✅ business has 0 `import deerflow`, so removal is safe |

**Conclusion**: a naive `rm -rf src/core/graph_agent && unzip wheel.whl`
would break video_analysis production. The migration prompt has to lead
with **evaluation, not replacement**.

---

## 3. Decision: rewrite the migration prompt with a 3-path framing

The prompt was rewritten end-to-end to:

1. **Refuse to default to "upgrade is good"** — explicitly tells the
   downstream agent that "stay on 1.0.0" is a legitimate engineering
   answer when the cost/benefit doesn't favor upgrading
2. **Require a compatibility evaluation phase before any file is
   touched** (§3 of the prompt) — the downstream agent must first run
   read-only checks (rg for imports, `compile_skill()` dry-run on the
   business SKILL.md in a throwaway venv) and produce a written
   recommendation before asking the user to choose
3. **Offer three paths with full trade-offs**:
   - **Path A: skip the upgrade** — zero risk, lose the API surplus
   - **Path B: salvage merge** — keep the legacy multimodal stack
     (understand_video, generate_image/video, multimodal_config),
     replace only the engine core, delete deerflow, keep `from
     src.core.graph_agent.xxx` import style. Recommended by default.
   - **Path C: full pip install + import refactor** — cleanest long-term
     but biggest blast radius, only worth it for teams committed to
     tracking upstream
4. **Spell out the salvage merge** (Path B) in concrete `cp` / `rsync`
   commands with a 60-second rollback procedure (`mv graph_agent_bak_v1
   graph_agent`), so the downstream agent does not have to invent the
   merge plan
5. **Include a SKILL.md rewrite mapping** (§4.3 of the prompt): old
   `<node id="X"><phase_config>...</phase_config></node>` → new
   `phases:` list under YAML frontmatter, with the `tier` →
   `mode/llm_role` translation table

---

## 4. What was NOT changed about the wheel

The `graph_agent_engine-0.1.0` wheel itself stands as built earlier today.
No new build was needed — the wheel is correct as a representation of the
new engine. Specifically:

- SHA256 still `9175a55cbc2e92293557e371ba5fd08c319e2ebd85915842eb8749df3a8f7b40`
- Size 248,197 bytes
- Located at `dist/graph_agent_engine-0.1.0-py3-none-any.whl`
- Source subproject at `packages/graph-agent-engine/`

What changed is only the **prompt that travels with the wheel** — the
prompt now treats the wheel as "an upgrade candidate that the downstream
must evaluate" rather than "an installation target the downstream must
adopt".

---

## 5. Recommendation to upstream maintainers

This migration surfaced two real upstream debts that should be tracked
(but **NOT fixed as part of this migration** — out of scope):

1. **`RELEASE_NOTES` does not document the multimodal-tool deletion** in
   v1-reset. From a downstream perspective, removing `understand_video`,
   `generate_image`, `generate_video`, and `multimodal_config.py` is a
   silent breaking change for any project that vendored 1.0.0. Either:
   (a) restore them as `[multimodal]` extras in the wheel; or (b) add a
   migration shim that emits a clear deprecation error pointing at where
   the functionality moved (or that it was removed by design).

2. **`src/core/graph_agent/README.md` is stale**. It still describes
   tools (understand_video, generate_video, generate_image) and config
   files (multimodal_config.py, multimodal_roles.yaml) that no longer
   exist. The migration prompt corrects this out-of-band, but a README
   refresh would prevent future downstream agents from going down the
   same dead end.

Filed as soft TODOs. The migration of video_analysis can proceed without
them.

---

## 6. Handoff steps (for the human operator)

1. Send the wheel (`dist/graph_agent_engine-0.1.0-py3-none-any.whl`) to
   the video_analysis machine — though if both repos live on the same
   filesystem the file path itself works
2. Send `docs/migration/PROMPT_FOR_VIDEO_ANALYSIS_AGENT.md` to the
   video_analysis project's coding agent (paste the full content, it is
   self-contained)
3. **Wait for the downstream agent's evaluation report** before
   approving any file replacement — this is the prompt's §3 and is
   intentionally a hard gate
4. Pick path A / B / C based on the evaluation
5. Hold the agent to the §4.5 verification (pytest + import smoke +
   compile_skill) before merging the upgrade branch

---

## 7. Files produced in this session

- `packages/graph-agent-engine/{pyproject.toml, README.md}` — engine
  subproject build config
- `packages/graph-agent-engine/graph_agent` — symlink to
  `../../src/core/graph_agent/`
- `dist/graph_agent_engine-0.1.0-py3-none-any.whl` — the wheel
- `docs/migration/PROMPT_FOR_VIDEO_ANALYSIS_AGENT.md` — self-contained
  prompt for the downstream agent (rewritten in this session to switch
  from "fresh integration" to "evaluate-then-upgrade-replace")
- `docs/migration/2026-04-30-graph-agent-to-video-analysis.md` — this file
- `.gitignore` — added `.build-venv/` and `.verify-venv/` (transient
  build/test environments)

Nothing in `src/core/graph_agent/` was modified. The root `pyproject.toml`
was not modified. Existing Studio backend / agent-harness tests are
unaffected.
