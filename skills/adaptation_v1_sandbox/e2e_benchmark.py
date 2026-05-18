import json
import sys
import time
import threading
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from story_forge.core.graph_agent import run_skill
from story_forge.core.graph_agent.callbacks.metrics import MetricsCallback
from story_forge.core.graph_agent.callbacks.tracing import TracingCallback
import story_forge.core.llm_client_manager as llm_manager

# --- Monkeypatch to track subagent tokens explicitly ---
original_call = llm_manager.call_llm_with_fallback
global_stats = {
    "subagent_prompt": 0, 
    "subagent_completion": 0, 
    "tasks": []
}
stats_lock = threading.Lock()

def tracked_call_llm(*args, **kwargs):
    task_id = kwargs.get("task_id", "unknown_task")
    llm_role = kwargs.get("llm_role", "unknown_role")
    
    t0 = time.time()
    res = original_call(*args, **kwargs)
    t1 = time.time()
    
    usage = res.get("usage", {})
    p_tokens = usage.get("prompt_tokens", 0)
    c_tokens = usage.get("completion_tokens", 0)
    
    with stats_lock:
        global_stats["subagent_prompt"] += p_tokens
        global_stats["subagent_completion"] += c_tokens
        global_stats["tasks"].append({
            "task_id": task_id,
            "role": llm_role,
            "time_sec": t1 - t0,
            "prompt_tokens": p_tokens,
            "completion_tokens": c_tokens,
            "total_tokens": p_tokens + c_tokens
        })
        
    return res

llm_manager.call_llm_with_fallback = tracked_call_llm

def run_benchmark():
    run_id = f"run_{int(time.time())}"
    out_dir = Path(__file__).resolve().parent / "artifacts" / run_id
    out_dir.mkdir(exist_ok=True, parents=True)
    
    metrics = MetricsCallback()
    tracer = TracingCallback(trace_dir=out_dir / "traces")
    
    skill_path = Path(__file__).resolve().parent / "skill_workspace" / "SKILL.md"
    
    print("="*60)
    print("🚀 Launching Main Agent to orchestrate the pipeline...")
    time_start = time.time()
    
    result = run_skill(
        skill_path=str(skill_path),
        thread_id=f"e2e_{run_id}",
        initial_context={},
        callbacks=[metrics, tracer]
    )
    
    total_time = time.time() - time_start
    ctx = result.get("context", {})
    
    print("="*60)
    print("📊 BENCHMARK RESULTS")
    print(f"Total Wall Time: {total_time:.2f} seconds")
    
    main_summary = metrics.summary()
    print("\n👑 MAIN AGENT (Graph Agent Engine Metrics):")
    print(f"  Input Tokens: {main_summary['total_input_tokens']}")
    print(f"  Output Tokens: {main_summary['total_output_tokens']}")
    print(f"  Tool Calls: {main_summary['total_tool_calls']}")
    
    print("\n🛠️ SUBAGENTS (Manual Dispatcher Metrics):")
    print(f"  Input Tokens: {global_stats['subagent_prompt']}")
    print(f"  Output Tokens: {global_stats['subagent_completion']}")
    
    print("\n📝 SUBAGENT TASK BREAKDOWN:")
    print(f"{'TASK ID':<25} | {'ROLE':<15} | {'TIME(s)':<8} | {'PROMPT':<8} | {'COMPLETION':<10} | {'TOTAL':<8}")
    print("-" * 85)
    for t in global_stats["tasks"]:
        print(f"{t['task_id']:<25} | {t['role']:<15} | {t['time_sec']:<8.2f} | {t['prompt_tokens']:<8} | {t['completion_tokens']:<10} | {t['total_tokens']:<8}")
    
    # Save artifacts
    md_file = out_dir / "final_scripts.md"
    json_file = out_dir / "scenes_data.json"
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(ctx, f, ensure_ascii=False, indent=2)
        
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write("# 🎭 全局制片人分析 (Audience Psychology)\n")
        f.write(ctx.get("producer_global_analysis", "None") + "\n\n")
        f.write("---\n")
        
        for sc in ctx.get("objective_scenes", []):
            f.write(f"\n\n## 🎬 Scene: {sc['scene_id']} - {sc['meta']['location']}\n\n")
            f.write("### 📝 Producer Strategy\n")
            f.write(json.dumps(sc.get("producer_strategy", {}), ensure_ascii=False, indent=2))
            f.write("\n\n### 🎥 Final Script Draft\n")
            
            script = sc.get("script_draft", [])
            if isinstance(script, list):
                for shot in script:
                    f.write(f"- **{shot.get('video_audio', '')}**\n")
                    f.write(f"  {shot.get('voice_text', '')}\n\n")
            else:
                f.write(str(script))
            
    print(f"\n📁 Artifacts and Traces saved to: {out_dir}")

if __name__ == "__main__":
    run_benchmark()
