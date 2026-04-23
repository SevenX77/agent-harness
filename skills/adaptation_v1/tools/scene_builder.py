from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def build_objective_scenes(ctx: dict) -> str:
    """
    Graph Agent Tool: 
    将上游的 Events 聚合成客观物理场 (Objective Scenes)，并从 segmentation 提取分段原文。
    """
    base_dir = Path(__file__).resolve().parent.parent.parent
    events_path = base_dir / "fixtures" / "chapter_001_event.json"
    seg_path = base_dir / "fixtures" / "chapter_001_segmentation.json"
    
    if not events_path.exists() or not seg_path.exists():
        return "ERROR: 找不到 fixtures 中的事件或 segmentation 源文件。"

    # 1. 加载事件
    events_data = json.loads(events_path.read_text(encoding="utf-8"))
    events = events_data.get("event_timeline", {}).get("events", [])
    
    if not events:
        return "ERROR: 事件列表为空。"

    # 2. 加载原文段落 (Segmentation)
    seg_data = json.loads(seg_path.read_text(encoding="utf-8"))
    paragraphs = seg_data.get("paragraphs", [])
    seg_map = {p["index"]: p["content"] for p in paragraphs}
    
    # 3. 按 Location 和 Time 合并同类项生成 Objective Scenes
    objective_scenes = []
    current_scene = None
    
    for ev in events:
        loc = ev.get("location", "未知")
        time_period = ev.get("time", "未知")
        
        if current_scene and current_scene["meta"]["location"] == loc and current_scene["meta"]["time"] == time_period:
            current_scene["source_events"].append(ev)
            current_scene["all_paragraph_indices"].extend(ev.get("paragraph_indices", []))
        else:
            if current_scene:
                objective_scenes.append(current_scene)
            
            current_scene = {
                "scene_id": f"OBJ_SC_{len(objective_scenes) + 1:02d}",
                "meta": {
                    "location": loc,
                    "time": time_period
                },
                "source_events": [ev],
                "all_paragraph_indices": list(ev.get("paragraph_indices", []))
            }
            
    if current_scene:
        objective_scenes.append(current_scene)
        
    # 4. 组装每个客观场的 Segmented Text
    for sc in objective_scenes:
        indices = sorted(list(set(sc["all_paragraph_indices"])))
        sc["paragraph_indices"] = indices
        
        segments = []
        for idx in indices:
            content = seg_map.get(idx)
            if content:
                segments.append(content)
                
        sc["segmented_text"] = "\n\n".join(segments)
        del sc["all_paragraph_indices"]

    ctx["objective_scenes"] = objective_scenes
    
    # 6. 返回给 LLM 的 observation，必须包含原文，才能让它派发给子代理
    summary = f"成功生成 {len(objective_scenes)} 个客观物理场。请将以下内容分别放入 task_tool 中并发执行提取：\n\n"
    for sc in objective_scenes:
        summary += f"### 场景 ID: {sc['scene_id']}\n"
        summary += f"- 地点: {sc['meta']['location']} | 时间: {sc['meta']['time']}\n"
        summary += f"- 原文内容:\n```text\n{sc['segmented_text']}\n```\n\n"
        
    return summary
