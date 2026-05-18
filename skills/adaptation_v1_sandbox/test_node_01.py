import sys
from pathlib import Path
import json

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from story_forge.core.graph_agent import run_skill

def test_plan_scenes_node():
    skill_path = Path(__file__).parent / "skill_workspace" / "SKILL.md"
    
    print(f"🚀 Running Skill: {skill_path.name} ...")
    
    result = run_skill(
        skill_path=skill_path,
        thread_id="test_node1_concurrency",
        initial_context={}
    )
    
    print("\n✅ Skill execution finished.")
    print("====================================")
    
    output = result.get("final_output", "No final output found")
    print("Final Output:\n", output)
    
    ctx = result.get("context", {})
    scenes = ctx.get("objective_scenes", [])
    print(f"\nExtracted Objective Scenes with Beats ({len(scenes)}):")
    if scenes:
        # Just print the first one for brevity
        print(json.dumps(scenes[0], ensure_ascii=False, indent=2))
        
if __name__ == "__main__":
    test_plan_scenes_node()
