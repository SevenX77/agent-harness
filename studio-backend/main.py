from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import json
import asyncio
from pathlib import Path
import time
import re

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"
WORKSPACES_DIR = PROJECT_ROOT / "workspaces"

# Ensure directories exist
SKILLS_DIR.mkdir(exist_ok=True)
WORKSPACES_DIR.mkdir(exist_ok=True)

class CompileRequest(BaseModel):
    code: str

class RunRequest(BaseModel):
    input_path: str
    output_path: str

@app.get("/api/skills")
async def list_skills():
    """List all available skills in the skills directory."""
    skills = []
    if SKILLS_DIR.exists():
        for item in SKILLS_DIR.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                skills.append({
                    "id": item.name,
                    "name": item.name,
                    "path": str(item)
                })
    return {"skills": skills}

import re

def resolve_refs(content: str, base_dir: Path) -> str:
    """Recursively resolve <ref path="..." /> tags in the content."""
    ref_pattern = re.compile(r'<ref\s+path="([^"]+)"\s*/>')
    
    def replace_ref(match):
        ref_path = match.group(1)
        target_file = base_dir / ref_path
        
        if not target_file.exists():
            return f"<!-- Error: Could not resolve ref {ref_path} -->"
            
        with open(target_file, "r", encoding="utf-8") as f:
            ref_content = f.read()
            
        # Recursively resolve refs in the included content
        # The base_dir for the recursive call should be the directory of the included file
        return resolve_refs(ref_content, target_file.parent)

    return ref_pattern.sub(replace_ref, content)

@app.get("/api/skills/{skill_id}")
async def get_skill(skill_id: str):
    """Get the content of a specific skill, resolving <ref> tags."""
    skill_dir = SKILLS_DIR / skill_id
    skill_path = skill_dir / "SKILL.md"
    
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail="Skill not found")
    
    with open(skill_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Resolve <ref> tags
    resolved_content = resolve_refs(content, skill_dir)
        
    return {
        "id": skill_id,
        "content": resolved_content
    }

@app.post("/api/skills/{skill_id}/compile")
async def compile_skill(skill_id: str, req: CompileRequest):
    """Mock compilation endpoint."""
    # In a real implementation, this would call graph_agent.compile_skill
    await asyncio.sleep(0.8) # Simulate work
    
    if "至少举3个具体使用场景" in req.code:
        return {"status": "success"}
    else:
        return {
            "status": "error", 
            "message": "编译错误: Phase 'write_scenarios' 缺少具体的场景数量约束。请在 system_prompt 中明确指定。"
        }

@app.websocket("/ws/run/{run_id}")
async def run_skill_ws(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for streaming run traces."""
    await websocket.accept()
    
    # Simulate a run with delays
    traces = [
        {"type": "system", "message": "[System] 验证输入 schema: 成功"},
        {"type": "phase_start", "phase": "extract_highlights", "message": "[Phase 1] extract_highlights 开始执行..."},
        {"type": "llm_call", "phase": "extract_highlights", "tokens": 120, "message": "调用 LLM 提取亮点..."},
        {"type": "phase_end", "phase": "extract_highlights", "message": "[Phase 1] 提取亮点完成 (耗时: 3.2s)"},
        
        {"type": "phase_start", "phase": "write_scenarios", "message": "[Phase 2] write_scenarios 开始执行..."},
        {"type": "llm_call", "phase": "write_scenarios", "tokens": 450, "message": "调用 LLM 生成场景..."},
        {"type": "phase_end", "phase": "write_scenarios", "message": "[Phase 2] 生成场景完成 (耗时: 4.1s)"},
        
        {"type": "phase_start", "phase": "synthesize_report", "message": "[Phase 3] synthesize_report 开始执行..."},
        {"type": "llm_call", "phase": "synthesize_report", "tokens": 890, "message": "调用 LLM 合成报告..."},
        {"type": "phase_end", "phase": "synthesize_report", "message": "[Phase 3] 报告合成完成 (耗时: 2.8s)"},
        
        {"type": "system", "message": "[System] 验证输出 schema: 成功"},
        {"type": "system", "message": f"[System] 产出已保存至配置路径"}
    ]
    
    try:
        for trace in traces:
            await asyncio.sleep(1.0) # Simulate processing time
            await websocket.send_json(trace)
            
        await websocket.send_json({"type": "complete", "message": "Run finished successfully"})
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8787)
