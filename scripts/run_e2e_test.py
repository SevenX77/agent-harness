#!/usr/bin/env python3
"""Run E2E test for story-deconstruction skill."""

import json
import subprocess
import sys
from pathlib import Path


def main():
    # Load test input
    input_file = (
        Path(__file__).parent.parent / "skills/story-deconstruction/data/e2e_test_input.json"
    )
    if not input_file.exists():
        print(f"Error: {input_file} not found")
        sys.exit(1)

    inputs = json.loads(input_file.read_text(encoding="utf-8"))

    # Run graph_agent
    skill_path = Path(__file__).parent.parent / "skills/story-deconstruction/SKILL.md"
    cmd = [
        sys.executable,
        "-m",
        "graph_agent",
        "--skill",
        str(skill_path),
        "--inputs",
        json.dumps(inputs, ensure_ascii=False),
    ]

    print(f"Running E2E test with {len(inputs['chapters'])} chapters...")
    print(f"Project ID: {inputs['project_id']}")

    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
