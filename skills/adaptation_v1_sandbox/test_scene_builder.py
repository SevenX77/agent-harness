import sys
from pathlib import Path
import json

# Add src to Python path if needed
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from skill_workspace.tools.scene_builder import build_objective_scenes

def test_build_objective_scenes():
    ctx = {}
    summary = build_objective_scenes(ctx)
    print("Summary:")
    print(summary)
    
    scenes = ctx.get("objective_scenes", [])
    print(f"\nExtracted {len(scenes)} scenes.")
    if scenes:
        print("\nFirst Scene sample:")
        print(json.dumps(scenes[0], ensure_ascii=False, indent=2))

if __name__ == "__main__":
    test_build_objective_scenes()
