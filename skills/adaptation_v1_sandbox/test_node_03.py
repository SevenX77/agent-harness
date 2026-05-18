import json
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.skills.adaptation_v1_sandbox.skill_workspace.tools.scene_builder import build_objective_scenes
from tests.skills.adaptation_v1_sandbox.skill_workspace.tools.beat_dispatcher import extract_beats_concurrently
from tests.skills.adaptation_v1_sandbox.skill_workspace.tools.producer_dispatcher import dispatch_producer_strategy
from tests.skills.adaptation_v1_sandbox.skill_workspace.tools.writer_dispatcher import dispatch_writer_drafting

def test_writer_node():
    print("🚀 Running Pipeline Step 1 (Beats) ...")
    ctx = {}
    build_objective_scenes(ctx)
    extract_beats_concurrently(ctx)
    
    print("\n🚀 Running Pipeline Step 2 (Producer Strategy) ...")
    dispatch_producer_strategy(ctx)
    
    print("\n🚀 Running Pipeline Step 3 (Writer Drafting) ...")
    res = dispatch_writer_drafting(ctx)
    print("Writer Dispatcher Result:", res)
    
    print("\n" + "="*50)
    print("🎬 FINAL SCRIPT DRAFTS")
    print("="*50)
    for sc in ctx.get("objective_scenes", []):
        if sc["scene_id"] in ["OBJ_SC_01", "OBJ_SC_03"]:  # 挑两场最有代表性的打印
            print(f"\n\n🔶 【Scene: {sc['scene_id']} - {sc['meta']['location']}】 🔶")
            print("-" * 50)
            print(sc.get("script_draft", "NO SCRIPT FOUND"))
            print("-" * 50)

if __name__ == "__main__":
    test_writer_node()
