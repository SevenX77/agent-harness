"""Cross-owner provenance for the MoirAI assets (批B′ 第 4 阶段).

WHY THIS MODULE EXISTS
----------------------
The MoirAI assets — four roles, eight skills, the knowledge base — used to live
in two repositories at once, each editing its own copy. The decision that ends
that (`docs/design/gskill-restructure-decision-2026-08-31.md` §4.6-2) makes the
`graph-skill-runtime` package their **single owner**; this repository's
`app/agents/` tree is a **retiring reader copy** that Studio still executes
against until the engine cutover.

`agent_assets.assets_fingerprint()` alone cannot police that arrangement. It
digests one tree — the retiring one — so it detects drift *inside* the copy
being retired and detects nothing about divergence *between* the owners. The
domain report names the consequence exactly: it "检测得到单 owner 内漂移,
检测不到跨 owner 分叉 —— 恰好给了错误的安心感"
(`docs/design/gskill-restructure-inventory-2026-08-31/domain-reports/
a66fac8a014fefd6b_v1.md:80`).

WHAT THIS MODULE DOES
---------------------
It records, for each owner, an identity: where it lives, its version anchor, a
content digest over its whole asset tree, and how many files that digest
covered. The local tree is re-derived and compared on every test run. The
remote owner's values are a **pin**: a checked-in value that a change on either
side invalidates, so no one can move one owner without a visible commit that
also states the other owner's current identity.

It also checks the first mechanically comparable slice of cross-owner meaning:
the agent→skill relation. The two owners use different skill ids, so the
relation is compared through a recorded translation table.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not read the remote owner's files. `graph-skill-runtime` is not a
dependency of this repository, and adding one to satisfy a gate would drag the
engine cutover forward into a verification change.

The translation table is **not a runtime compatibility layer**. Nothing in the
serving path consults it; only this gate does. It is deleted with the retiring
copy at cutover, not kept as an alias.

PRIOR ART, AND WHAT WAS TAKEN FROM EACH
---------------------------------------
*   **`package-lock.json`'s `integrity` field / Go's `go.sum`.** Both record a
    hash for content that lives in another repository and that the local build
    cannot re-derive from its own sources. Taken: the shape of the guarantee —
    a pin does not prove the remote is *currently* that content; it proves
    nobody changed it without a visible commit. That is precisely the property
    a migration window needs. Rejected: their automatic refresh (`go mod tidy`,
    `npm install`). An auto-updating pin would silently absorb the other
    owner's drift, which is the failure being removed. Re-pinning here is a
    human edit in a reviewed change.
*   **This repository's own audited-doc hash lock**
    (`apps/studio/backend/tests/test_doc_hash_lock.py`). Taken: LF-normalized
    SHA-256 so a checkout's line-ending setting cannot change a content
    identity, and a failure message that names its own remediation. Rejected:
    per-file granularity and the owner-approval exemption file. Sixty-odd files
    across two owners as individual rows is noise when the question is "did this
    tree move"; and an exemption during a migration is exactly the false
    assurance being removed.
*   Not borrowed: live remote verification (a network fetch in a unit gate).
    A gate that needs the network is a gate that goes red for reasons unrelated
    to the change under review.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

_BACKEND_APP = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_APP.parents[3]

_ROLE_FILENAMES = ("moirai.md", "clotho.md", "lachesis.md", "atropos.md")


@dataclass(frozen=True)
class MoiraiAssetOwner:
    """One place that holds a MoirAI asset tree, and the identity it is pinned to."""

    owner_id: str
    stance: str
    relative_path: str
    version_anchor: str | None
    tree_digest: str
    file_count: int
    source_reference: str

    def resolved_path(self) -> Path:
        return _REPO_ROOT / self.relative_path


#: The authoritative owner's own declaration, transcribed from
#: `graph-skill-runtime`'s `integration.json` `roles[].skills`. Order is part of
#: the relation: position one is the role's entry skill.
AUTHORITATIVE_ROLE_SKILLS: dict[str, tuple[str, ...]] = {
    "moirai": ("moirai", "moirai-brainstorming"),
    "clotho": (
        "moirai-domain-analysis",
        "moirai-graph-design",
        "moirai-agent-prompt-design",
    ),
    "lachesis": ("moirai-compile-repair", "moirai-graph-design"),
    "atropos": ("moirai-eval-judgement", "moirai-agent-prompt-design"),
}

#: Migration-window comparison table, gate-only (see the module docstring).
#: `moirai-intro` maps to the authoritative `moirai` front-door skill because
#: the self-introduction protocol was merged into it rather than becoming a
#: ninth skill; that ruling is recorded in the owner's own decision document.
LEGACY_TO_AUTHORITATIVE_SKILL_ID: dict[str, str] = {
    "moirai-intro": "moirai",
    "brainstorming": "moirai-brainstorming",
    "domain-analysis": "moirai-domain-analysis",
    "graph-design": "moirai-graph-design",
    "agent-prompt-design": "moirai-agent-prompt-design",
    "compile-error-repair": "moirai-compile-repair",
    "eval-judgement": "moirai-eval-judgement",
    "web-research": "moirai-web-research",
}

OWNERS: tuple[MoiraiAssetOwner, ...] = (
    MoiraiAssetOwner(
        owner_id="graph-skill-runtime",
        stance="authoritative",
        relative_path="",
        version_anchor="1.1.0",
        tree_digest="3a24bb9d637dd9b752a6d4080c0feb4e50a9ec13f962aacce15025fb37643578",
        file_count=29,
        source_reference=(
            "SevenX77/graph-skill-runtime "
            "src/graph_skill_runtime/integrations/assets/moirai (PR #16)"
        ),
    ),
    MoiraiAssetOwner(
        owner_id="studio-legacy-copy",
        stance="retiring-reader",
        relative_path="apps/studio/backend/app/agents",
        version_anchor=None,
        tree_digest="8cc7ad0eafff49647a825ad2b73a604e42a201398b10a3cb20ee7e5fb41d264e",
        file_count=35,
        source_reference="this checkout",
    ),
)

_REPIN_REMEDIATION = (
    "re-pin both owners in app/services/agent_asset_owners.py in the same change, "
    "and say in the change description which owner moved and why"
)


def tree_digest(root: Path) -> tuple[str, int]:
    """SHA-256 over every file under ``root`` — relpath plus LF-normalized bytes.

    Two normalizations, each removing a way for one piece of content to have two
    identities on two machines:

    *   **Line endings** belong to a checkout, not to content.
    *   **Order** is taken from the POSIX relative path *string*, never from
        sorting ``Path`` objects. ``PurePath`` comparison is case-insensitive on
        Windows and case-sensitive on POSIX, so sorting paths puts ``README.md``
        after ``operating-manual.md`` on Windows and before ``agent-skill-map``
        on Linux — the same tree, two digests. Field evidence: the first pinned
        value was computed on Windows and failed `pytest studio backend` on both
        the Ubuntu and macOS runners.
    """

    entries = sorted(
        (path.relative_to(root).as_posix(), path)
        for path in root.rglob("*")
        if path.is_file()
    )
    digest = hashlib.sha256()
    for relative_posix, path in entries:
        digest.update(relative_posix.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest(), len(entries)


def authoritative_owner() -> MoiraiAssetOwner:
    return _single_owner("authoritative")


def retiring_owner() -> MoiraiAssetOwner:
    return _single_owner("retiring-reader")


def _single_owner(stance: str) -> MoiraiAssetOwner:
    matches = [owner for owner in OWNERS if owner.stance == stance]
    if len(matches) != 1:
        raise AssertionError(f"exactly one {stance} owner must be recorded, found {len(matches)}")
    return matches[0]


def problems_for_digest(
    owner: MoiraiAssetOwner, *, digest: str, file_count: int
) -> list[str]:
    """Every mismatch between an observed tree and its pinned identity, at once."""

    problems: list[str] = []
    if file_count != owner.file_count:
        problems.append(
            f"{owner.owner_id}: file count {file_count} does not match the pinned "
            f"{owner.file_count}; {_REPIN_REMEDIATION}"
        )
    if digest != owner.tree_digest:
        problems.append(
            f"{owner.owner_id}: tree digest {digest[:12]}… does not match the pinned "
            f"{owner.tree_digest[:12]}…; {_REPIN_REMEDIATION}"
        )
    return problems


def problems_for_relation(legacy_role_skills: dict[str, list[str]]) -> list[str]:
    """Compare the retiring copy's agent→skill relation with the owner's own.

    Skill ids differ between the owners; the relation must not. A one-sided
    membership change or reorder is a cross-owner divergence — the class of
    defect the single-tree fingerprint could never see.
    """

    problems: list[str] = []
    unknown_roles = sorted(set(legacy_role_skills) - set(AUTHORITATIVE_ROLE_SKILLS))
    missing_roles = sorted(set(AUTHORITATIVE_ROLE_SKILLS) - set(legacy_role_skills))
    if unknown_roles:
        problems.append(f"roles absent from the authoritative owner: {unknown_roles}")
    if missing_roles:
        problems.append(f"roles absent from the retiring copy: {missing_roles}")

    for role, authoritative_skills in AUTHORITATIVE_ROLE_SKILLS.items():
        legacy_skills = legacy_role_skills.get(role)
        if legacy_skills is None:
            continue
        untranslatable = [
            skill for skill in legacy_skills if skill not in LEGACY_TO_AUTHORITATIVE_SKILL_ID
        ]
        if untranslatable:
            problems.append(
                f"{role}: legacy skills absent from the comparison table: {untranslatable}; "
                f"{_REPIN_REMEDIATION}"
            )
            continue
        translated = tuple(
            LEGACY_TO_AUTHORITATIVE_SKILL_ID[skill] for skill in legacy_skills
        )
        if translated != authoritative_skills:
            problems.append(
                f"{role}: relation diverged — retiring copy maps to {list(translated)}, "
                f"authoritative owner declares {list(authoritative_skills)}; "
                f"{_REPIN_REMEDIATION}"
            )
    return problems


def verify_role_skill_relation() -> list[str]:
    from app.services import agent_assets

    return problems_for_relation(agent_assets.load_skill_map())


def verify() -> list[str]:
    """Every cross-owner problem in one list (same fail-loud contract as
    ``agent_assets.missing_assets``: one complete diagnostic, not a peel-one loop)."""

    problems: list[str] = []
    local = retiring_owner()
    digest, file_count = tree_digest(local.resolved_path())
    problems.extend(problems_for_digest(local, digest=digest, file_count=file_count))
    problems.extend(verify_role_skill_relation())
    return problems


def tracked_moirai_role_trees() -> list[str]:
    """Git-tracked directories holding a full MoirAI role set, as POSIX relpaths.

    Scope is tracked source on purpose: the packaged sidecar snapshot under
    `apps/studio/tauri/vendor/backend/` is a build product, ignored by
    `apps/studio/tauri/.gitignore`, and a product is not a second fact source.

    Gate-only. It needs a git checkout, which a packaged sidecar does not have,
    so it must never be called from a serving path.
    """

    completed = subprocess.run(
        ["git", "ls-files", "-z", "--", "*/roles/moirai.md", "roles/moirai.md"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=True,
        encoding="utf-8",
    )
    trees: list[str] = []
    for entry in completed.stdout.split("\0"):
        if not entry:
            continue
        roles_dir = _REPO_ROOT / Path(entry).parent
        if all((roles_dir / filename).is_file() for filename in _ROLE_FILENAMES):
            trees.append(Path(entry).parent.parent.as_posix())
    return sorted(set(trees))


def provenance_label() -> str:
    """The string echoed in ``context_resolved``.

    It names both facts a reader needs and that the old single-tree echo could
    not distinguish: which tree this session actually read, and which owner is
    authoritative at which version. While the retiring copy is the one being
    executed, saying only ``assets@<hex>`` invites reading it as the owner's
    identity.
    """

    local = retiring_owner()
    owner = authoritative_owner()
    return (
        f"assets@{local.tree_digest[:8]} ({local.stance}) · "
        f"owner {owner.owner_id}@{owner.version_anchor}#{owner.tree_digest[:8]}"
    )


def record_as_json() -> dict[str, object]:
    """The whole record as plain data, so a review can see both pins at once."""

    return {
        "authoritative_owner": authoritative_owner().owner_id,
        "owners": [
            {
                "owner_id": owner.owner_id,
                "stance": owner.stance,
                "relative_path": owner.relative_path,
                "version_anchor": owner.version_anchor,
                "tree_digest": owner.tree_digest,
                "file_count": owner.file_count,
                "source_reference": owner.source_reference,
            }
            for owner in OWNERS
        ],
        "authoritative_role_skills": {
            role: list(skills) for role, skills in AUTHORITATIVE_ROLE_SKILLS.items()
        },
        "legacy_to_authoritative_skill_id": dict(LEGACY_TO_AUTHORITATIVE_SKILL_ID),
    }
