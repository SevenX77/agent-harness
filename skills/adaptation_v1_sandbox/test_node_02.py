import json
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.skills.adaptation_v1_sandbox.skill_workspace.tools.scene_builder import build_objective_scenes
from tests.skills.adaptation_v1_sandbox.skill_workspace.tools.beat_dispatcher import extract_beats_concurrently
from tests.skills.adaptation_v1_sandbox.skill_workspace.tools.producer_dispatcher import dispatch_producer_strategy

def test_producer_node():
    print("🚀 Running Pipeline Step 1 & 2 ...")
    ctx = {}
    
    # Node 1
    build_objective_scenes(ctx)
    extract_beats_concurrently(ctx)
    
    # Node 2
    res = dispatch_producer_strategy(ctx)
    print("Producer Dispatcher Result:", res)
    
    print("Extracted Objective Scenes with Strategies:")
    for sc in ctx.get("objective_scenes", []):
        print(f"\n--- Scene: {sc['scene_id']} ---")
        print(json.dumps(sc.get("producer_strategy", {}), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    test_producer_node()
