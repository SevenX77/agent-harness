"""A skill write must keep every file it did not write.

`update_skill_files` persists the file map the caller submitted. That map can
only ever hold the paths `validate_skill_file_path` admits (`GRAPH.md`,
`io/*.json`, `tools/*.py`, `phases/<id>/<node>.md`,
`phases/<id>/{actions,tools}/*.py`), so `.git/`, `.workspace/` and `subgraph/`
are STRUCTURALLY unable to appear in it.

Replacing the whole skill directory with a directory built from that map
therefore has two consequences, and both are covered here:

1. the undeclared content is destroyed — exactly the content the caller had no
   way to submit;
2. the pre-write lint runs against a skill root that is missing that same
   content, so a skill whose graph reaches outside the declared set (a
   subgraph phase) can never pass and can never be saved at all.

The unit of replacement is the declared file, not the directory — the choice
`rsync` makes by leaving `--delete` off by default.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.core.adapters.storage_local import LocalFilesystemBackend
from app.services import skills as skill_service
from app.services.git_local import GitLocalService, initialize_skill_repository
from fastapi import HTTPException


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def metadata_store(tmp_path: Path) -> LocalJsonMetadataStore:
    return LocalJsonMetadataStore(global_config_dir=tmp_path / "global-config")


def _isolate_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    skills_root = tmp_path / "default-skills"
    skills_root.mkdir(exist_ok=True)
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", tmp_path / "global-config" / "app_settings.json")
    monkeypatch.setattr(config, "DEFAULT_SKILLS_ROOT", skills_root)
    return skills_root


_FLAT_GRAPH_MD = """---
schema_version: "v0.3.0"
name: keeper
description: {description}
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
phases:
  - setup
---
<phase depends_on="input" output>setup</phase>
"""

_SUBGRAPH_GRAPH_MD = """---
schema_version: "v0.3.0"
name: keeper
description: {description}
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
phases:
  - setup
  - review
---
<phase depends_on="input">setup</phase>
<phase depends_on="setup" output>review</phase>
"""

_LOGIC_MD = """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
<action>run</action>
"""

_ACTION_PY = "def run(inputs):\n    return {}\n"

_CHILD_GRAPH_MD = """---
schema_version: "v0.3.0"
name: child-graph
description: Child graph reached through subgraph/child
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - ingest
---
<phase depends_on="input" output>ingest</phase>
"""

_SUBGRAPH_MD = """---
name: review
path: subgraph/child
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
validator: false
---
"""

_HELPER_PY = "def helper():\n    return 1\n"


def _flat_files(description: str = "Original description") -> dict[str, str]:
    """Every path a caller may submit for the no-subgraph fixture."""
    return {
        "GRAPH.md": _FLAT_GRAPH_MD.format(description=description),
        "phases/setup/LOGIC.md": _LOGIC_MD,
        "phases/setup/actions/run.py": _ACTION_PY,
        "tools/helper.py": _HELPER_PY,
    }


def _subgraph_files(description: str = "Original description") -> dict[str, str]:
    """Every path a caller may submit for the subgraph fixture.

    `subgraph/child/**` is deliberately absent: `validate_skill_file_path`
    rejects it, so no caller can ever include it.
    """
    return {
        "GRAPH.md": _SUBGRAPH_GRAPH_MD.format(description=description),
        "phases/setup/LOGIC.md": _LOGIC_MD,
        "phases/setup/actions/run.py": _ACTION_PY,
        "phases/review/SUBGRAPH.md": _SUBGRAPH_MD,
        "tools/helper.py": _HELPER_PY,
    }


def _write_files(skill_dir: Path, files: dict[str, str]) -> None:
    for rel_path, content in files.items():
        target = skill_dir.joinpath(*rel_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _add_undeclared_content(skill_dir: Path) -> None:
    """Everything a real skill holds that a payload can never carry."""
    # .workspace/: Studio-owned runtime truth — golden cases, import files,
    # local settings. No payload key can reach it.
    workspace = skill_dir / ".workspace"
    (workspace / "golden").mkdir(parents=True, exist_ok=True)
    (workspace / "golden" / "case-1.json").write_text('{"case": 1}', encoding="utf-8")
    (workspace / "import_files").mkdir(parents=True, exist_ok=True)
    (workspace / "import_files" / "sample.txt").write_text("payload", encoding="utf-8")
    (workspace / "local_settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
    # .git/: the skill's own Local History repo (one skill = one git repo).
    initialize_skill_repository(skill_dir)


def _add_child_subgraph(skill_dir: Path) -> None:
    child_dir = skill_dir / "subgraph" / "child"
    (child_dir / "phases" / "ingest" / "actions").mkdir(parents=True, exist_ok=True)
    (child_dir / "GRAPH.md").write_text(_CHILD_GRAPH_MD, encoding="utf-8")
    (child_dir / "phases" / "ingest" / "LOGIC.md").write_text(_LOGIC_MD, encoding="utf-8")
    (child_dir / "phases" / "ingest" / "actions" / "run.py").write_text(_ACTION_PY, encoding="utf-8")


async def _register(metadata: LocalJsonMetadataStore, skill_id: str, skill_dir: Path) -> None:
    await metadata.save_skill_index_entry(skill_id, {"absolute_path": str(skill_dir), "l2_remote_url": ""})


def _assert_workspace_and_git_intact(skill_dir: Path) -> None:
    assert (skill_dir / ".git").is_dir(), ".git was destroyed by a write that never carried it"
    assert GitLocalService().log(skill_dir), "git history was destroyed"
    workspace = skill_dir / ".workspace"
    assert (workspace / "golden" / "case-1.json").read_text(encoding="utf-8") == '{"case": 1}'
    assert (workspace / "import_files" / "sample.txt").read_text(encoding="utf-8") == "payload"
    assert (workspace / "local_settings.json").read_text(encoding="utf-8") == '{"theme": "dark"}'


def _assert_child_subgraph_intact(skill_dir: Path) -> None:
    child_dir = skill_dir / "subgraph" / "child"
    assert (child_dir / "GRAPH.md").is_file(), "subgraph/ was destroyed"
    assert (child_dir / "phases" / "ingest" / "LOGIC.md").is_file(), "subgraph child phase was destroyed"
    assert (child_dir / "phases" / "ingest" / "actions" / "run.py").is_file()


def _assert_no_residue(skill_dir: Path) -> None:
    strays = sorted(p.name for p in skill_dir.parent.iterdir() if p.name != skill_dir.name)
    assert strays == [], f"temp/backup directories left behind: {strays}"


@pytest.mark.anyio
async def test_write_keeps_git_and_workspace_it_never_carried(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Submitting every declared file still must not delete the undeclared ones."""
    skills_root = _isolate_roots(tmp_path, monkeypatch)
    skill_dir = skills_root / "keeper"
    _write_files(skill_dir, _flat_files())
    _add_undeclared_content(skill_dir)
    await _register(metadata_store, "keeper", skill_dir)

    await skill_service.update_skill_files(
        "default",
        "keeper",
        _flat_files(description="Edited description"),
        LocalFilesystemBackend(tmp_path),
        metadata_store,
    )

    assert "Edited description" in (skill_dir / "GRAPH.md").read_text(encoding="utf-8")
    _assert_workspace_and_git_intact(skill_dir)
    _assert_no_residue(skill_dir)


@pytest.mark.anyio
async def test_partial_write_keeps_the_declared_files_it_did_not_carry(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Submitting only GRAPH.md updates GRAPH.md and touches nothing else.

    The payload says what to write; it is not an inventory of what may exist.
    """
    skills_root = _isolate_roots(tmp_path, monkeypatch)
    skill_dir = skills_root / "keeper"
    _write_files(skill_dir, _flat_files())
    _add_undeclared_content(skill_dir)
    await _register(metadata_store, "keeper", skill_dir)

    await skill_service.update_skill_files(
        "default",
        "keeper",
        {"GRAPH.md": _FLAT_GRAPH_MD.format(description="Only GRAPH changed")},
        LocalFilesystemBackend(tmp_path),
        metadata_store,
    )

    assert "Only GRAPH changed" in (skill_dir / "GRAPH.md").read_text(encoding="utf-8")
    assert (skill_dir / "phases" / "setup" / "LOGIC.md").read_text(encoding="utf-8") == _LOGIC_MD
    assert (skill_dir / "phases" / "setup" / "actions" / "run.py").read_text(encoding="utf-8") == _ACTION_PY
    assert (skill_dir / "tools" / "helper.py").read_text(encoding="utf-8") == _HELPER_PY
    _assert_workspace_and_git_intact(skill_dir)
    _assert_no_residue(skill_dir)


@pytest.mark.anyio
async def test_write_of_a_skill_with_a_subgraph_is_accepted(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pre-write lint must judge the skill as it will be, not just the payload.

    `subgraph/child/**` cannot be a payload key, so linting a directory built
    from the payload alone reports `subgraph path 'subgraph/child' is not a
    directory` and rejects every save of a perfectly valid skill.
    """
    skills_root = _isolate_roots(tmp_path, monkeypatch)
    skill_dir = skills_root / "keeper"
    _write_files(skill_dir, _subgraph_files())
    _add_child_subgraph(skill_dir)
    _add_undeclared_content(skill_dir)
    await _register(metadata_store, "keeper", skill_dir)

    await skill_service.update_skill_files(
        "default",
        "keeper",
        _subgraph_files(description="Edited description"),
        LocalFilesystemBackend(tmp_path),
        metadata_store,
    )

    assert "Edited description" in (skill_dir / "GRAPH.md").read_text(encoding="utf-8")
    _assert_child_subgraph_intact(skill_dir)
    _assert_workspace_and_git_intact(skill_dir)
    _assert_no_residue(skill_dir)


@pytest.mark.anyio
async def test_rejected_write_leaves_the_skill_untouched(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A write the lint rejects changes nothing on disk and leaves no residue."""
    skills_root = _isolate_roots(tmp_path, monkeypatch)
    skill_dir = skills_root / "keeper"
    _write_files(skill_dir, _flat_files())
    _add_undeclared_content(skill_dir)
    await _register(metadata_store, "keeper", skill_dir)
    graph_before = (skill_dir / "GRAPH.md").read_text(encoding="utf-8")

    with pytest.raises(HTTPException):
        await skill_service.update_skill_files(
            "default",
            "keeper",
            {
                "GRAPH.md": "---\nthis is not a valid manifest\n",
                "tools/helper.py": "def helper():\n    return 2\n",
            },
            LocalFilesystemBackend(tmp_path),
            metadata_store,
        )

    assert (skill_dir / "GRAPH.md").read_text(encoding="utf-8") == graph_before
    # The second file of the rejected batch must not have landed either.
    assert (skill_dir / "tools" / "helper.py").read_text(encoding="utf-8") == _HELPER_PY
    assert (skill_dir / "phases" / "setup" / "LOGIC.md").is_file()
    _assert_workspace_and_git_intact(skill_dir)
    _assert_no_residue(skill_dir)


@pytest.mark.anyio
async def test_create_skill_still_scaffolds_and_inits_repository(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The create path writes into an empty directory and still gets its git repo."""
    skills_root = _isolate_roots(tmp_path, monkeypatch)

    summary = await skill_service.create_new_skill(
        "default",
        "fresh-skill",
        {},
        LocalFilesystemBackend(tmp_path),
        metadata_store,
    )

    skill_dir = skills_root / "fresh-skill"
    assert summary.id == "fresh-skill"
    assert (skill_dir / "GRAPH.md").is_file()
    assert (skill_dir / "phases" / "init" / "SKILL.md").is_file()
    assert (skill_dir / ".git").is_dir()
    assert GitLocalService().log(skill_dir), "expected the initial-skill commit"
    _assert_no_residue(skill_dir)
