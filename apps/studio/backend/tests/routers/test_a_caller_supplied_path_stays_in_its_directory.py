"""A path or id a CALLER supplies may not name a file outside its own directory.

Every case here drives the traversal through the public HTTP route rather than
the helper underneath it, because the helper is not what an attacker reaches:
the question each test asks is whether the REQUEST is refused, and a helper
tested in isolation can be bounded while the route in front of it still hands
the helper something it never had to prove.

Three shapes of the same defect, found in adversarial review on 2026-08-31 and
independently by CodeQL (``py/path-injection``):

- a caller-supplied ID joined into a directory (``input_ids`` for a batch run);
- a caller-supplied ABSOLUTE path accepted as "which directory am I editing"
  (``workspace_root`` on graph/serialize and on lint), where the only checks
  were that the directory exists and holds a ``GRAPH.md`` — both true of any
  directory on the machine that happens to hold one;
- a caller-supplied absolute path read as content (``input_file_path`` on
  validate_input), whose file-reading contract is deleted rather than bounded.

Each assertion is in two parts on purpose: the status must be a 4xx, AND the
secret's content must not appear anywhere in the response body. A route that
refuses with the file's text in the error message has still disclosed it.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SECRET_CONTENT = "TOP-SECRET-CANARY-VALUE"


def _outside_secret_json(tmp_path: Path) -> Path:
    """A JSON file outside every directory Studio manages."""
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    secret = outside / "secret.json"
    secret.write_text(json.dumps({"input_text": SECRET_CONTENT}), encoding="utf-8")
    return secret


def _outside_graph_dir(tmp_path: Path) -> Path:
    """A directory outside every managed skill root that still holds a GRAPH.md.

    Holding a ``GRAPH.md`` is exactly what the old check tested for, so this is
    the directory that passed it while belonging to nobody.
    """
    outside = tmp_path / "outside-graph"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "GRAPH.md").write_text(
        f"---\nschema_version: \"v0.3.0\"\nname: stolen\n---\n\n{SECRET_CONTENT}\n",
        encoding="utf-8",
    )
    return outside


def _assert_refused_without_leaking(response: object) -> None:
    body = getattr(response, "text", "")
    status = getattr(response, "status_code", 0)
    assert 400 <= int(status) < 500, f"expected a 4xx refusal, got {status}: {body[:400]}"
    assert SECRET_CONTENT not in body, f"the refusal leaked the file's content: {body[:400]}"


def _assert_refused_over_the_input_id(response: object) -> None:
    """Refused BECAUSE OF the id — not refused later for an unrelated reason.

    A batch run also has a predict gate in front of it, and before this fix the
    traversal read the file and then met that gate: the request failed with 409
    ``RUN_REQUIRES_PREDICT`` while the escape had already succeeded. A bare
    "some 4xx" assertion passes on that, which is why the reason is asserted
    here and not only the status class.
    """
    body = getattr(response, "text", "")
    status = getattr(response, "status_code", 0)
    assert int(status) == 422, f"expected 422 over the input id, got {status}: {body[:400]}"
    assert "input_id" in body, f"the refusal does not name the offending field: {body[:400]}"
    assert SECRET_CONTENT not in body, f"the refusal leaked the file's content: {body[:400]}"


@pytest.mark.parametrize(
    "traversal_id",
    [
        "../../../secret",
        "..\\..\\..\\secret",
        "../secret",
        "/etc/passwd",
        "..",
    ],
)
def test_a_batch_run_refuses_an_input_id_that_climbs_out(
    client: TestClient,
    tmp_path: Path,
    traversal_id: str,
) -> None:
    """``input_ids`` names a file inside the skill's own import_files, or nothing.

    The id was joined straight onto ``.workspace/import_files`` and the JSON it
    reached was then fed to a run as its input data, so an id that climbs out
    both reads a file and runs a skill over its contents.
    """
    _outside_secret_json(tmp_path)

    response = client.post(
        "/api/skills/text-segmentation/runs/batch-run",
        json={"input_ids": [traversal_id]},
    )

    _assert_refused_over_the_input_id(response)


def test_a_batch_run_refuses_an_input_id_reaching_a_real_file_outside(
    client: TestClient,
    tmp_path: Path,
    studio_roots: tuple[Path, Path],
) -> None:
    """The same refusal when the climbed-to file really exists and really parses.

    The parametrized cases above are refused whether or not anything is there;
    this one proves the refusal is the boundary talking and not the filesystem.
    """
    skills_dir, _ = studio_roots
    secret = _outside_secret_json(tmp_path)
    import_files = skills_dir / "text-segmentation" / ".workspace" / "import_files"
    import_files.mkdir(parents=True, exist_ok=True)
    climb = os.path.relpath(secret, import_files).replace(os.sep, "/")

    response = client.post(
        "/api/skills/text-segmentation/runs/batch-run",
        json={"input_ids": [climb]},
    )

    _assert_refused_over_the_input_id(response)


def test_a_batch_run_refuses_an_input_id_that_is_a_symlink_out(
    client: TestClient,
    tmp_path: Path,
    studio_roots: tuple[Path, Path],
) -> None:
    """A name with no ``..`` in it can still resolve outside, via a symlink.

    This is why containment is asserted AFTER ``Path.resolve()``: a rule that
    only inspects the SPELLING of an id accepts ``escape.json`` and follows it
    wherever it points.
    """
    skills_dir, _ = studio_roots
    secret = _outside_secret_json(tmp_path)
    import_files = skills_dir / "text-segmentation" / ".workspace" / "import_files"
    import_files.mkdir(parents=True, exist_ok=True)
    link = import_files / "escape.json"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - platform privilege
        pytest.skip(f"this platform/account cannot create symlinks: {exc}")

    response = client.post(
        "/api/skills/text-segmentation/runs/batch-run",
        json={"input_ids": ["escape"]},
    )

    _assert_refused_over_the_input_id(response)


def test_graph_serialize_refuses_a_workspace_root_outside_the_managed_roots(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """``workspace_root`` names a drilled subgraph, not any directory on disk.

    The route answers a hash mismatch with the file's full text in
    ``current_markdown_content``, so an unbounded ``workspace_root`` plus a
    deliberately wrong ``expected_hash`` is a read primitive for any GRAPH.md.
    """
    outside = _outside_graph_dir(tmp_path)

    response = client.post(
        "/api/skills/text-segmentation/graph/serialize",
        json={
            "phases": [],
            "expected_hash": "not-the-current-hash",
            "workspace_root": str(outside),
        },
    )

    _assert_refused_without_leaking(response)


def test_graph_serialize_still_serializes_the_skill_it_names(client: TestClient) -> None:
    """The boundary must refuse the outside, not the legitimate request.

    Paired with the test above so a fix that simply rejects every
    ``workspace_root`` cannot pass: the parent graph's own directory is inside
    the boundary and keeps working.
    """
    response = client.post(
        "/api/skills/text-segmentation/graph/serialize",
        json={"phases": [{"id": "setup", "src": "phases/setup", "depends_on": []}]},
    )

    assert response.status_code == 200, response.text


def test_graph_serialize_still_serializes_a_drilled_subgraph_by_path(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    """The shape ``workspace_root`` exists for: a child graph inside the skill tree.

    MVP1 identifies a subgraph by PATH rather than by registry id, and the id the
    canvas sends alongside it is DERIVED from that path
    (``workspace-identity.ts::skillIdFromWorkspaceRoot``), so it need not be in
    the skill index at all. That is why the bound is "a workspace Studio has
    open" and not "the named skill's own tree" — and this test is what keeps the
    bound from quietly becoming the latter.
    """
    skills_dir, _ = studio_roots
    child = skills_dir / "text-segmentation" / "subgraphs" / "child-graph"
    shutil.copytree(skills_dir / "text-segmentation", child)

    response = client.post(
        "/api/skills/child-graph/graph/serialize",
        json={
            "phases": [{"id": "setup", "src": "phases/setup", "depends_on": [], "output": True}],
            "workspace_root": str(child),
        },
    )

    assert response.status_code == 200, response.text
    assert "setup" in response.json()["markdown_content"]


def test_lint_refuses_a_workspace_root_outside_the_managed_roots(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """The lint route carries the same field, so it carries the same rule.

    It also fed the raw value to ``logger.info`` on the way to its fallback,
    which is CodeQL alert 581 (``py/log-injection``): a value nobody had proved
    was a path becomes a line in a log people read as a record of what happened.
    """
    outside = _outside_graph_dir(tmp_path)

    response = client.post(
        "/api/skills/text-segmentation/lint",
        json={"workspace_root": str(outside)},
    )

    _assert_refused_without_leaking(response)


def test_lint_of_unsaved_markdown_refuses_a_workspace_root_outside(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """Same field, same route, other request shape — the editor-typing branch.

    That branch copies the resolved directory into a sandbox before linting it,
    so an unbounded root there reads a whole tree rather than one file.
    """
    outside = _outside_graph_dir(tmp_path)

    response = client.post(
        "/api/skills/text-segmentation/lint",
        json={
            "markdown": "---\nname: probe\n---\n",
            "file_path": "GRAPH.md",
            "workspace_root": str(outside),
        },
    )

    _assert_refused_without_leaking(response)


def test_validate_input_no_longer_accepts_a_file_path(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """The contract is a submitted payload; the file-reading branch is gone.

    ``input_file_path`` is not hardened, it is removed — the request model
    forbids extras, so naming a path is now a request-shape error and no read
    is attempted at all.
    """
    secret = _outside_secret_json(tmp_path)

    response = client.post(
        "/api/skills/text-segmentation/validate_input",
        json={"input_file_path": str(secret)},
    )

    _assert_refused_without_leaking(response)
