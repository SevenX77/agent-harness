import sys
from pathlib import Path

# Add src to Python path if needed, but for now we just import the local tool
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from skill_workspace.tools.technical_io import load_chapter_text

def test_load_chapter():
    ctx = {}
    content = load_chapter_text(ctx, 1)
    assert not content.startswith("ERROR"), f"Failed to load chapter: {content}"
    assert "姜宁睁开眼猛地从床上坐起" in content
    print("✅ test_load_chapter passed. First 100 chars:")
    print(content[:100])
    print("...")

if __name__ == "__main__":
    test_load_chapter()
