from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ABS_ROOT = ROOT
FORBIDDEN_TOKENS = {
    "target_skill",
    "inputs_mapping",
    "on_item_failure",
    "all_segmentations",
    "per_chapter_events",
    "story_assets",
    "parallel_analysis",
    "_llm_call",
}
EXPECTED_GRAPHS = {
    ROOT / "GRAPH.md": ["segmentation", "event_timeline", "story_analysis", "global_synthesis"],
    ROOT / "subgraph/text-segmentation/GRAPH.md": ["setup", "segment", "review"],
    ROOT / "subgraph/event-timeline/GRAPH.md": ["extract", "stitch"],
    ROOT / "subgraph/event-timeline/subgraph/event-extraction/GRAPH.md": [
        "setup",
        "aggregate",
        "review",
        "settings",
    ],
    ROOT / "subgraph/story-analysis/GRAPH.md": [
        "discover_dimensions",
        "prepare_batches",
        "analyze_batches",
        "finalize",
    ],
    ROOT / "subgraph/story-analysis/subgraph/batch-analysis/GRAPH.md": [
        "prepare",
        "entity_and_characters",
        "tension",
        "system",
        "prop",
        "arc",
        "foreshadow",
        "spatiotemporal",
        "format_continuity",
        "continuity",
        "assemble",
    ],
    ROOT / "subgraph/global-synthesis/GRAPH.md": [
        "global_analysis",
        "retroactive",
        "scene_assembly",
        "export",
    ],
}
EXPECTED_DEPENDS = {
    ROOT / "GRAPH.md": {
        "segmentation": "input",
        "event_timeline": "segmentation",
        "story_analysis": "event_timeline",
        "global_synthesis": "story_analysis",
    },
    ROOT / "subgraph/text-segmentation/GRAPH.md": {
        "setup": "input",
        "segment": "setup",
        "review": "segment",
    },
    ROOT / "subgraph/event-timeline/GRAPH.md": {
        "extract": "input",
        "stitch": "extract",
    },
    ROOT / "subgraph/event-timeline/subgraph/event-extraction/GRAPH.md": {
        "setup": "input",
        "aggregate": "setup",
        "review": "aggregate",
        "settings": "review",
    },
    ROOT / "subgraph/story-analysis/GRAPH.md": {
        "discover_dimensions": "input",
        "prepare_batches": "discover_dimensions",
        "analyze_batches": "prepare_batches",
        "finalize": "analyze_batches",
    },
    ROOT / "subgraph/story-analysis/subgraph/batch-analysis/GRAPH.md": {
        "prepare": "input",
        "entity_and_characters": "prepare",
        "tension": "entity_and_characters",
        "system": "entity_and_characters",
        "prop": "entity_and_characters",
        "arc": "entity_and_characters",
        "foreshadow": "entity_and_characters",
        "spatiotemporal": "entity_and_characters",
        "format_continuity": "entity_and_characters",
        "continuity": "format_continuity",
        "assemble": "tension,system,prop,arc,foreshadow,spatiotemporal,continuity",
    },
    ROOT / "subgraph/global-synthesis/GRAPH.md": {
        "global_analysis": "input",
        "retroactive": "global_analysis",
        "scene_assembly": "retroactive",
        "export": "scene_assembly",
    },
}
EXPECTED_SUBGRAPHS = {
    ROOT / "phases/segmentation/SUBGRAPH.md": (
        "segmentation",
        ABS_ROOT / "subgraph/text-segmentation",
    ),
    ROOT / "phases/event_timeline/SUBGRAPH.md": (
        "event_timeline",
        ABS_ROOT / "subgraph/event-timeline",
    ),
    ROOT / "phases/story_analysis/SUBGRAPH.md": (
        "story_analysis",
        ABS_ROOT / "subgraph/story-analysis",
    ),
    ROOT / "phases/global_synthesis/SUBGRAPH.md": (
        "global_synthesis",
        ABS_ROOT / "subgraph/global-synthesis",
    ),
    ROOT / "subgraph/event-timeline/phases/extract/SUBGRAPH.md": (
        "event_extraction",
        ABS_ROOT / "subgraph/event-timeline/subgraph/event-extraction",
    ),
    ROOT / "subgraph/story-analysis/phases/analyze_batches/SUBGRAPH.md": (
        "batch_analysis",
        ABS_ROOT / "subgraph/story-analysis/subgraph/batch-analysis",
    ),
}
EXPECTED_LOOP_IO = {
    ROOT / "subgraph/event-timeline/phases/stitch/SKILL.md": {
        "inputs": {"chapter_event_timeline", "chapter_events", "global_timeline"},
        "outputs": {"stitched_timeline", "global_timeline"},
        "accumulate": {
            "var": "global_timeline",
            "from": "stitched_timeline",
            "init": {"events": []},
            "merge": "replace",
        },
    },
    ROOT / "subgraph/story-analysis/phases/analyze_batches/SUBGRAPH.md": {
        "inputs": {
            "event_batches",
            "current_batch",
            "analysis_state",
            "para_text_lookup",
            "dynamic_dimensions",
        },
        "outputs": {"updated_state", "analysis_state"},
        "accumulate": {
            "var": "analysis_state",
            "from": "updated_state",
            "init": {
                "entity_registry": {},
                "entity_aliases": {},
                "character_latest_states": {},
                "open_foreshadowing": [],
                "active_arcs": [],
                "batch_history": [],
            },
            "merge": "merge",
        },
    },
}


def read_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError(f"{path} missing YAML frontmatter")
    end = text.find("\n---", 4)
    if end == -1:
        raise AssertionError(f"{path} has unterminated YAML frontmatter")
    return yaml.safe_load(text[4:end]) or {}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def schema_keys(schema: dict) -> set[str]:
    return set((schema.get("properties") or {}).keys())


def body_phases(path: Path) -> list[str]:
    text = read_text(path)
    return re.findall(r"<phase\s+[^>]*>([a-z0-9_]+)</phase>", text)


def body_depends(path: Path) -> dict[str, str]:
    text = read_text(path)
    matches = re.findall(
        r'<phase\s+depends_on="([^"]+)"(?:\s+output)?>([a-z0-9_]+)</phase>',
        text,
    )
    return {phase: depends_on for depends_on, phase in matches}


def test_required_graphs_have_matching_frontmatter_body_and_phase_dirs() -> None:
    for graph_path, expected_phases in EXPECTED_GRAPHS.items():
        assert graph_path.exists(), f"missing graph: {graph_path}"
        metadata = read_frontmatter(graph_path)
        phase_dirs = sorted(path.name for path in (graph_path.parent / "phases").iterdir() if path.is_dir())

        assert metadata.get("phases") == expected_phases, graph_path
        assert body_phases(graph_path) == expected_phases, graph_path
        assert body_depends(graph_path) == EXPECTED_DEPENDS[graph_path], graph_path
        assert phase_dirs == sorted(expected_phases), graph_path


def test_subgraph_phases_use_mvp1_name_and_absolute_path() -> None:
    name_pattern = re.compile(r"^[a-z][a-z0-9_-]*$")
    for subgraph_path, (expected_name, expected_path) in EXPECTED_SUBGRAPHS.items():
        metadata = read_frontmatter(subgraph_path)
        assert "target_skill" not in metadata, subgraph_path
        assert metadata.get("name") == expected_name, subgraph_path
        assert name_pattern.match(metadata["name"]), subgraph_path
        assert metadata.get("path") == str(expected_path), subgraph_path
        assert Path(metadata["path"]).is_absolute(), subgraph_path
        assert metadata.get("validator") is False, subgraph_path


def test_no_v2_only_tokens_or_implicit_field_names_remain() -> None:
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".py", ".yaml", ".yml"}:
            text = read_text(path)
            if path == Path(__file__).resolve():
                continue
            for token in FORBIDDEN_TOKENS:
                assert token not in text, f"{token} found in {path}"


def test_iterate_blocks_use_only_mvp1_fields() -> None:
    allowed = {"mode", "over", "item_var", "range", "concurrency", "accumulate"}
    for path in ROOT.rglob("*.md"):
        metadata = read_frontmatter(path)
        iterate = metadata.get("iterate")
        if iterate is None:
            continue
        assert set(iterate) <= allowed, path
        assert isinstance(iterate.get("mode"), str), path
        assert isinstance(iterate.get("over"), str), path
        assert isinstance(iterate.get("item_var"), str), path
        if "range" in iterate:
            assert isinstance(iterate["range"], list), path
            assert len(iterate["range"]) == 2, path
            assert all(isinstance(item, int) for item in iterate["range"]), path


def test_loop_nodes_declare_item_accumulate_inputs_and_outputs() -> None:
    for loop_path, expected in EXPECTED_LOOP_IO.items():
        metadata = read_frontmatter(loop_path)
        assert metadata["iterate"]["mode"] == "loop", loop_path
        assert metadata["iterate"]["accumulate"] == expected["accumulate"], loop_path
        assert expected["inputs"] <= schema_keys(metadata["io"]["inputs"]), loop_path
        assert expected["outputs"] <= schema_keys(metadata["io"]["outputs"]), loop_path


def test_all_phase_files_have_explicit_boolean_validator_field() -> None:
    for path in ROOT.rglob("*.md"):
        if path.name == "GRAPH.md":
            continue
        if path.name not in {"LOGIC.md", "SKILL.md", "SUBGRAPH.md"}:
            continue
        metadata = read_frontmatter(path)
        assert isinstance(metadata.get("validator"), bool), path


def test_story_analysis_and_global_synthesis_use_v3_field_names() -> None:
    story_analysis = read_frontmatter(ROOT / "subgraph/story-analysis/GRAPH.md")
    assert schema_keys(story_analysis["io"]["inputs"]) == {"global_timeline"}
    assert schema_keys(story_analysis["io"]["outputs"]) == {
        "batch_outputs",
        "accumulated_context",
        "entity_registry",
    }

    global_synthesis = read_frontmatter(ROOT / "subgraph/global-synthesis/GRAPH.md")
    assert schema_keys(global_synthesis["io"]["inputs"]) == {
        "batch_outputs",
        "accumulated_context",
        "entity_registry",
    }
    assert schema_keys(global_synthesis["io"]["outputs"]) == {"story_framework"}


def test_batch_analysis_parallel_dimensions_are_real_agent_phases() -> None:
    graph = read_frontmatter(ROOT / "subgraph/story-analysis/subgraph/batch-analysis/GRAPH.md")
    expected = {
        "tension",
        "system",
        "prop",
        "arc",
        "foreshadow",
        "spatiotemporal",
    }
    assert expected <= set(graph["phases"])
    for phase in expected:
        skill_path = ROOT / f"subgraph/story-analysis/subgraph/batch-analysis/phases/{phase}/SKILL.md"
        validator_path = ROOT / f"subgraph/story-analysis/subgraph/batch-analysis/phases/{phase}/validator.py"
        assert skill_path.exists(), skill_path
        assert validator_path.exists(), validator_path
        text = read_text(skill_path)
        assert "<role>" in text and "<goal>" in text, skill_path


def test_action_files_use_v4_inputs_signature_and_no_forbidden_runtime_access() -> None:
    for path in ROOT.rglob("actions/*.py"):
        tree = ast.parse(read_text(path), filename=str(path))
        funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        public_funcs = [node for node in funcs if not node.name.startswith("_")]
        assert public_funcs, f"missing public action function in {path}"
        for func in public_funcs:
            assert len(func.args.args) == 1, path
            assert func.args.args[0].arg == "inputs", path
        forbidden_names = {"context", "run_skill", "open", "exec", "eval"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in forbidden_names, f"{node.id} in {path}"
            if isinstance(node, ast.Attribute):
                assert not (
                    isinstance(node.value, ast.Name)
                    and node.value.id == "sys"
                    and node.attr == "path"
                ), f"sys.path in {path}"


def test_validator_files_are_deterministic_schema_checks_only() -> None:
    forbidden_names = {"_llm_call", "open", "Path", "exec", "eval"}
    forbidden_imports = {"pathlib", "yaml", "subprocess", "requests", "httpx"}
    for path in ROOT.rglob("validator.py"):
        tree = ast.parse(read_text(path), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in forbidden_names, f"{node.id} in {path}"
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
                assert not (names & forbidden_imports), f"{names & forbidden_imports} in {path}"
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".")[0]
                assert module not in forbidden_imports, f"{module} in {path}"


if __name__ == "__main__":
    try:
        for name, obj in sorted(globals().items()):
            if name.startswith("test_") and callable(obj):
                obj()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise
    print("PASS")
