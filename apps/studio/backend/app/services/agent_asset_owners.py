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

TWO SIDES, TWO EPISTEMIC STATUSES — the distinction this module is built on
--------------------------------------------------------------------------
*   The **local tree** is here, so this repository can hash it. `LOCAL_TREE`'s
    digest is *verified*: every gate run re-derives it from the very directory
    the loader serves, and a mismatch is red. This is a real check.
*   The **upstream bundle** is not here. There is no copy to hash, and
    `graph-skill-runtime` is deliberately not a dependency of this repository.
    Nothing local can verify it. `UPSTREAM_RECORD` is therefore a
    **transcription**: the values the owning repository's own gate pinned, at a
    named `asset_version`, copied in by hand.

An earlier revision of this module blurred those two. It called the
transcription an "authoritative owner", ran the relation comparison against it,
and its own docstring claimed that "a change on either side turns the gate red".
That claim was false for the upstream side and could not be made true here:
change the bundle upstream and every check in this file stays green, because no
check in this file has ever read a byte of it. The claim is withdrawn, and the
naming with it — nothing here is called authoritative any more, because nothing
here adjudicates anything about upstream.

WHERE THAT SENTENCE IS ACTUALLY ENCODED
---------------------------------------
In the owning repository, which is the only place that holds the bytes:
`graph-skill-runtime` `tests/integrations/test_moirai_asset_lock.py` +
`tests/integrations/moirai-asset-lock.json`, re-pinned there by
`scripts/repin_moirai_asset_lock.py`. Truth is guarded where truth lives.

THE HUMAN RECONCILIATION POINT
------------------------------
The two repositories are tied together by a pair a person can compare in one
glance: **`asset_version` + the first bytes of the tree digest**. This file
records `graph-skill-runtime@1.1.0#94c9c1fc`; the owning repository's lock
records the same anchor and the same digest for the same content. If the two
ever name one `asset_version` with two digests, one of them has moved without
the other being re-transcribed — and that is a review finding, not a test
failure, because only a human reading both repositories can see it. Making it a
test failure would require this repository to hold the bundle, which is exactly
what the cutover has not happened yet.

WHAT THIS MODULE STILL CHECKS, MECHANICALLY
-------------------------------------------
1.  The served tree equals `LOCAL_TREE`'s pin (digest and file count).
2.  The served tree's agent→skill relation equals the relation transcribed in
    `UPSTREAM_RECORD`. Skill ids differ between the two sides, so the relation
    is compared through a recorded translation table. This proves "the local
    relation still matches what was last transcribed", NOT "the local relation
    matches upstream right now" — the second is upstream's own gate to make.
3.  This repository holds no second MoirAI asset tree.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not read the remote owner's files, and does not pretend to.

The translation table is **not a runtime compatibility layer**. Nothing in the
serving path consults it; only this gate does. It is deleted with the retiring
copy at cutover, not kept as an alias.

PRIOR ART, AND WHAT WAS TAKEN FROM EACH
---------------------------------------
*   **`package-lock.json`'s `integrity` field / Go's `go.sum`.** Both record a
    hash for content that lives elsewhere. Taken: the shape of the record — it
    does not prove the remote is *currently* that content; it makes the version
    a change was reconciled against visible and citable. Rejected: their
    automatic refresh (`go mod tidy`, `npm install`). An auto-updating record
    would silently absorb the other side's drift. Also rejected, and this is
    where the earlier revision went wrong: `go.sum` gets its force from the
    toolchain re-hashing the downloaded module on every build. This repository
    downloads nothing, so the same file shape here buys provenance only — and
    must be described as provenance only.
*   **This repository's own audited-doc hash lock**
    (`apps/studio/backend/tests/test_doc_hash_lock.py`). Taken: LF-normalized
    SHA-256 so a checkout's line-ending setting cannot change a content
    identity, and a failure message that names its own remediation. Rejected:
    per-file granularity and the owner-approval exemption file.
*   Not borrowed: live remote verification (a network fetch in a unit gate).
    A gate that needs the network is a gate that goes red for reasons unrelated
    to the change under review.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.services import agent_assets

_BACKEND_APP = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_APP.parents[3]

_ROLE_FILENAMES = ("moirai.md", "clotho.md", "lachesis.md", "atropos.md")


@dataclass(frozen=True)
class UpstreamAssetRecord:
    """What the owning repository's own gate said its bundle was, transcribed here.

    Every field is a copy of a value produced somewhere else. Nothing in this
    repository can confirm any of them, so this type carries no verification
    method — only the coordinates a reviewer needs to go and compare:
    which owner, which ``asset_version``, which digest, and which upstream
    artifact the numbers were read out of.

    ``role_skills`` lives here rather than beside the table below because it
    came out of the same upstream snapshot as the digest. Keeping the three
    facts in one record makes a half-finished re-transcription — new digest,
    stale relation — visible at the point of edit.
    """

    owner_id: str
    asset_version: str
    tree_digest: str
    file_count: int
    role_skills: Mapping[str, tuple[str, ...]]
    source_reference: str


@dataclass(frozen=True)
class LocalAssetTree:
    """The retiring copy in this repository, and the digest it is pinned to.

    This one is verifiable, and is verified: ``verify()`` re-derives the digest
    from the directory the loader actually serves and compares it here.

    ``relative_path`` is the tree's identity *inside this git repository* and is
    used only by the source scan in ``tracked_moirai_role_trees()``. It is
    deliberately not how the tree gets located for hashing: in the packaged
    sidecar the backend lives under ``apps/studio/tauri/vendor/backend/`` and a
    repo-root-relative path does not resolve. The runtime address is
    ``agent_assets.agents_dir()``, and the two are asserted to coincide in a
    checkout by this module's tests.
    """

    relative_path: str
    tree_digest: str
    file_count: int


#: Transcribed by hand from the owning repository's lock file. Re-transcribe the
#: whole record together, from the same upstream commit, or the anchor stops
#: describing the digest next to it.
UPSTREAM_RECORD = UpstreamAssetRecord(
    owner_id="graph-skill-runtime",
    asset_version="1.1.0",
    tree_digest="94c9c1fcb5d76fc2457b40ab6b27c8017e3d5545d33d1bb23eb0ced64d81c061",
    file_count=29,
    # Order is part of the relation: position one is the role's entry skill.
    role_skills={
        "moirai": ("moirai", "moirai-brainstorming"),
        "clotho": (
            "moirai-domain-analysis",
            "moirai-graph-design",
            "moirai-agent-prompt-design",
        ),
        "lachesis": ("moirai-compile-repair", "moirai-graph-design"),
        "atropos": ("moirai-eval-judgement", "moirai-agent-prompt-design"),
    },
    source_reference=(
        "SevenX77/graph-skill-runtime · bundle "
        "src/graph_skill_runtime/integrations/assets/moirai · transcribed from "
        "tests/integrations/moirai-asset-lock.json at commit 8aed65e4 "
        "(re-pinned there by scripts/repin_moirai_asset_lock.py)"
    ),
)

LOCAL_TREE = LocalAssetTree(
    relative_path="apps/studio/backend/app/agents",
    tree_digest="8cc7ad0eafff49647a825ad2b73a604e42a201398b10a3cb20ee7e5fb41d264e",
    file_count=35,
)

#: Migration-window comparison table, gate-only (see the module docstring).
#: `moirai-intro` maps to the upstream `moirai` front-door skill because the
#: self-introduction protocol was merged into it rather than becoming a ninth
#: skill; that ruling is recorded in the owning repository's decision document.
LOCAL_TO_UPSTREAM_SKILL_ID: dict[str, str] = {
    "moirai-intro": "moirai",
    "brainstorming": "moirai-brainstorming",
    "domain-analysis": "moirai-domain-analysis",
    "graph-design": "moirai-graph-design",
    "agent-prompt-design": "moirai-agent-prompt-design",
    "compile-error-repair": "moirai-compile-repair",
    "eval-judgement": "moirai-eval-judgement",
    "web-research": "moirai-web-research",
}

_LOCAL_REPIN = (
    "re-pin LOCAL_TREE in app/services/agent_asset_owners.py in the same change, "
    "and say in the change description what moved under app/agents/ and why"
)

_RETRANSCRIBE_UPSTREAM = (
    "if the upstream bundle is what moved, re-transcribe UPSTREAM_RECORD in "
    "app/services/agent_asset_owners.py from graph-skill-runtime's own lock "
    "(tests/integrations/moirai-asset-lock.json) — digest, file count and relation "
    "together — and name the asset_version you transcribed"
)


def tree_digest(root: Path) -> tuple[str, int]:
    """SHA-256 over every file under ``root`` — relpath plus LF-normalized bytes.

    Byte-identical in algorithm to the owning repository's own lock
    (``tests/integrations/test_moirai_asset_lock.py``), on purpose: the two
    digests are meant to be compared by a human across repositories, and two
    algorithms would make equal content look different.

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


def problems_for_pinned_digest(
    tree: LocalAssetTree, *, digest: str, file_count: int
) -> list[str]:
    """Every mismatch between an observed tree and its pinned identity, at once."""

    problems: list[str] = []
    if file_count != tree.file_count:
        problems.append(
            f"{tree.relative_path}: file count {file_count} does not match the pinned "
            f"{tree.file_count}; {_LOCAL_REPIN}"
        )
    if digest != tree.tree_digest:
        problems.append(
            f"{tree.relative_path}: tree digest {digest[:12]}… does not match the pinned "
            f"{tree.tree_digest[:12]}…; {_LOCAL_REPIN}"
        )
    return problems


def problems_for_relation(local_role_skills: dict[str, list[str]]) -> list[str]:
    """Compare the retiring copy's agent→skill relation with the transcribed one.

    Skill ids differ between the two sides; the relation must not. A one-sided
    membership change or reorder is a cross-owner divergence — the class of
    defect the single-tree fingerprint could never see.

    What a green result means, precisely: the local relation still matches the
    relation transcribed into ``UPSTREAM_RECORD``. It does not mean the upstream
    relation is still that, which this repository cannot observe.
    """

    recorded = UPSTREAM_RECORD.role_skills
    problems: list[str] = []
    unknown_roles = sorted(set(local_role_skills) - set(recorded))
    missing_roles = sorted(set(recorded) - set(local_role_skills))
    if unknown_roles:
        problems.append(f"roles absent from the recorded upstream relation: {unknown_roles}")
    if missing_roles:
        problems.append(f"roles absent from the local copy: {missing_roles}")

    for role, recorded_skills in recorded.items():
        local_skills = local_role_skills.get(role)
        if local_skills is None:
            continue
        untranslatable = [
            skill for skill in local_skills if skill not in LOCAL_TO_UPSTREAM_SKILL_ID
        ]
        if untranslatable:
            problems.append(
                f"{role}: local skills absent from the comparison table: {untranslatable}; "
                f"{_RETRANSCRIBE_UPSTREAM}"
            )
            continue
        translated = tuple(LOCAL_TO_UPSTREAM_SKILL_ID[skill] for skill in local_skills)
        if translated != recorded_skills:
            problems.append(
                f"{role}: relation diverged — the local copy maps to {list(translated)}, "
                f"the recorded upstream relation is {list(recorded_skills)}; "
                f"{_RETRANSCRIBE_UPSTREAM}"
            )
    return problems


def verify_role_skill_relation() -> list[str]:
    return problems_for_relation(agent_assets.load_skill_map())


def verify() -> list[str]:
    """Every problem this repository can actually observe, in one list.

    Same fail-loud contract as ``agent_assets.missing_assets``: one complete
    diagnostic, not a peel-one loop.

    The tree is located through ``agent_assets.agents_dir()`` — the loader's own
    address — so the gate and the ``context_resolved`` echo can never end up
    describing two different directories.
    """

    problems: list[str] = []
    digest, file_count = tree_digest(agent_assets.agents_dir())
    problems.extend(problems_for_pinned_digest(LOCAL_TREE, digest=digest, file_count=file_count))
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

    The local digest is computed from the bytes this process actually loaded —
    never from ``LOCAL_TREE``'s pin. The pin is a review artifact; the echo is a
    report of what was read. Reporting the pin here would make a deployed tree
    that has drifted from source echo its *pre-drift* identity, so the one
    surface built to show what went in would be the surface hiding it. The cost
    is one tree hash per process: ``agent_assets.assets_fingerprint()`` memoizes
    it, so only the first turn pays.

    The upstream half is explicitly labelled a record, because that is all it
    is — see the module docstring. A reader comparing this line against the
    owning repository has both halves they need: the version anchor and the
    digest prefix.
    """

    return (
        f"assets@{agent_assets.assets_fingerprint()} (live digest of the retiring copy) · "
        f"recorded upstream {UPSTREAM_RECORD.owner_id}@{UPSTREAM_RECORD.asset_version}"
        f"#{UPSTREAM_RECORD.tree_digest[:8]}"
    )


def record_as_json() -> dict[str, object]:
    """The whole record as plain data, so a review can see both sides at once."""

    return {
        "upstream_record": {
            "owner_id": UPSTREAM_RECORD.owner_id,
            "asset_version": UPSTREAM_RECORD.asset_version,
            "tree_digest": UPSTREAM_RECORD.tree_digest,
            "file_count": UPSTREAM_RECORD.file_count,
            "role_skills": {
                role: list(skills) for role, skills in UPSTREAM_RECORD.role_skills.items()
            },
            "source_reference": UPSTREAM_RECORD.source_reference,
            "verified_here": False,
        },
        "local_tree": {
            "relative_path": LOCAL_TREE.relative_path,
            "tree_digest": LOCAL_TREE.tree_digest,
            "file_count": LOCAL_TREE.file_count,
            "verified_here": True,
        },
        "local_to_upstream_skill_id": dict(LOCAL_TO_UPSTREAM_SKILL_ID),
    }
