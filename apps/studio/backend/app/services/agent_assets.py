"""Single-source loader for the packaged agent assets (``app/agents/``).

The four asset layers (roles / operating manual / surface contexts / knowledge)
plus the skill pool and the agent→skill map live in exactly one directory that
ships with the backend. Both loading paths (SDK panel assembly here, ah-side
materialization in the Tauri layer) read this same tree; nothing else may carry
a second copy of any of these truths.

Fail-loud contract: a missing file is reported together with every other
missing file in one diagnostic, so a broken package surfaces as a single
complete list instead of a peel-one-fix-one loop.
"""

from __future__ import annotations

import hashlib
import json
from functools import cache, lru_cache
from pathlib import Path

_AGENTS_DIR = Path(__file__).resolve().parents[1] / "agents"

_ROLE_NAMES = ("moirai", "clotho", "lachesis", "atropos")
_SURFACES = ("panel", "cli")

# Every file the loaders hand out; missing_assets() reports against this set.
_REQUIRED_RELPATHS = (
    *(f"roles/{name}.md" for name in _ROLE_NAMES),
    "operating-manual.md",
    *(f"contexts/{surface}.md" for surface in _SURFACES),
    "knowledge/KB-00-hub.md",
    "agent-skill-map.json",
)


class AgentAssetsError(RuntimeError):
    """Raised when the packaged asset tree is unusable; message carries the
    full missing-file list (fail loud, complete diagnostics)."""


def agents_dir() -> Path:
    return _AGENTS_DIR


def missing_assets(root: Path | None = None) -> list[str]:
    """All required asset files absent under ``root`` (POSIX relpaths)."""

    base = root if root is not None else _AGENTS_DIR
    return [rel for rel in _REQUIRED_RELPATHS if not (base / rel).is_file()]


def _ensure_complete() -> None:
    missing = missing_assets()
    if missing:
        raise AgentAssetsError(
            "agent assets incomplete under "
            f"{_AGENTS_DIR}: missing {len(missing)} file(s):\n"
            + "\n".join(f"  - {rel}" for rel in missing)
        )


@cache
def _load(relpath: str) -> str:
    _ensure_complete()
    return (_AGENTS_DIR / relpath).read_text(encoding="utf-8").strip()


def load_role(name: str) -> str:
    if name not in _ROLE_NAMES:
        raise AgentAssetsError(f"unknown agent role {name!r}; expected one of {_ROLE_NAMES}")
    return _load(f"roles/{name}.md")


def load_operating_manual() -> str:
    return _load("operating-manual.md")


def load_context(surface: str) -> str:
    if surface not in _SURFACES:
        raise AgentAssetsError(f"unknown surface {surface!r}; expected one of {_SURFACES}")
    return _load(f"contexts/{surface}.md")


def knowledge_dir() -> Path:
    return _AGENTS_DIR / "knowledge"


def skill_names() -> list[str]:
    """Shipped skill pool (``skills/<name>/SKILL.md``), sorted by name."""

    skills_root = _AGENTS_DIR / "skills"
    if not skills_root.is_dir():
        return []
    return sorted(p.name for p in skills_root.iterdir() if (p / "SKILL.md").is_file())


@lru_cache(maxsize=1)
def load_skill_map() -> dict[str, list[str]]:
    """agent-skill-map.json, validated: known agents only, mapped skills shipped."""

    _ensure_complete()
    raw = json.loads((_AGENTS_DIR / "agent-skill-map.json").read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AgentAssetsError("agent-skill-map.json must be a JSON object")
    shipped = set(skill_names())
    problems: list[str] = []
    for agent, skills in raw.items():
        if agent not in _ROLE_NAMES:
            problems.append(f"unknown agent {agent!r}")
            continue
        if not isinstance(skills, list) or not all(isinstance(s, str) for s in skills):
            problems.append(f"{agent}: skills must be a list of strings")
            continue
        unshipped = sorted(set(skills) - shipped)
        if unshipped:
            problems.append(f"{agent}: maps to unshipped skills {unshipped}")
    missing_agents = sorted(set(_ROLE_NAMES) - set(raw))
    if missing_agents:
        problems.append(f"agents missing from map: {missing_agents}")
    if problems:
        raise AgentAssetsError(
            "agent-skill-map.json invalid:\n" + "\n".join(f"  - {p}" for p in problems)
        )
    return {agent: list(skills) for agent, skills in raw.items()}


def fingerprint_of(root: Path) -> str:
    """sha256 (8 hex) over every file under ``root`` — relpath + content — so a
    change in ANY layer (roles/manual/contexts/knowledge/skills/map) shifts it."""

    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:8]


@lru_cache(maxsize=1)
def assets_fingerprint() -> str:
    """Fingerprint of the shipped asset tree, echoed as ``assets@<8hex>`` in
    ``context_resolved`` so users can verify which asset version a session ate."""

    _ensure_complete()
    return fingerprint_of(_AGENTS_DIR)


def assemble_inline(source_relpaths: list[str]) -> str:
    """In-memory assembly (SDK append / AgentDefinition prompt): ONE header line
    naming the sources, then the stripped source bodies — no per-section markers
    (R1.4; anti-hidden-magic is carried by the assets fingerprint instead)."""

    bodies = [_load(rel) for rel in source_relpaths]
    header = f"<!-- assembled-by=studio sources={','.join(source_relpaths)} -->"
    return "\n\n".join([header, *bodies])


def clear_caches() -> None:
    """Test hook: drop memoized file contents after fixtures mutate the tree."""

    _load.cache_clear()
    load_skill_map.cache_clear()
    assets_fingerprint.cache_clear()
