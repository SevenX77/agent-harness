from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pydantic import BaseModel
from story_forge.core.llm_client_manager import call_llm_with_fallback
from story_forge.core.md_parser import md_to_json

logger = logging.getLogger(__name__)


class BeatSchema(BaseModel):
    beat_id: str
    content: str
    emotion: str


def extract_beats_concurrently(ctx: dict) -> str:
    """
    Graph Agent Tool:
    读取 objective_scenes 中的 segmented_text，并发调用 LLM 提取 beat。
    为了绕过 JSON 转义 bug，直接调用 call_llm_with_fallback 获得纯 Markdown 文本。
    提取完毕后，使用 md_to_json 进行解析与格式自愈，确保存入的 beats 是强类型 JSON。
    """
    scenes = ctx.get("objective_scenes", [])
    if not scenes:
        return "ERROR: objective_scenes 为空，请先调用 build_objective_scenes。"

    subskill_path = (
        Path(__file__).resolve().parent.parent / "subskills" / "beat_extractor" / "SKILL.md"
    )

    # 临时从 SKILL.md 解析 system prompt
    with open(subskill_path, encoding="utf-8") as f:
        content = f.read()

    sys_prompt = content.split("<system_prompt>")[1].split("</system_prompt>")[0].strip()

    results = []

    def _run_subagent(scene: dict) -> dict:
        text = scene.get("segmented_text", "")
        if not text:
            return {"scene_id": scene["scene_id"], "output": ""}

        user_prompt = f"请将以下小说章节拆解为 Raw Beats：\n\n{text}"
        try:
            # 临时绕过 graph agent 框架，直接调大模型吐 Markdown
            output_dict = call_llm_with_fallback(
                task_id=scene["scene_id"],
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                llm_role="writer",
                temperature=0.3,
            )
            output_text = output_dict.get("content", "")
            return {"scene_id": scene["scene_id"], "output": output_text}
        except Exception as e:
            logger.error(f"提取 beat 失败: {e}")
            return {"scene_id": scene["scene_id"], "output": f"ERROR: {e}"}

    logger.info(f"开始并发提取 {len(scenes)} 个场景的 beats...")
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_run_subagent, sc): sc for sc in scenes}
        for future in as_completed(futures):
            res = future.result()
            results.append(res)

    # 把结果合并回 scenes，使用 md_to_json 强转为 JSON 对象
    res_map = {r["scene_id"]: r["output"] for r in results}
    for sc in scenes:
        out_str = res_map.get(sc["scene_id"], "")
        if out_str and not out_str.startswith("ERROR"):
            try:
                # 核心魔法：解析大模型吐出的 Markdown 为结构化 JSON 对象
                beats_json = md_to_json(out_str, BeatSchema)
                sc["beats"] = [beat.model_dump() for beat in beats_json]
            except Exception as e:
                logger.error(f"md_to_json 解析 {sc['scene_id']} 失败: {e}\nText:\n{out_str}")
                sc["beats"] = []  # 降级保留为空
        else:
            sc["beats"] = []

    ctx["objective_scenes"] = scenes

    return (
        "子代理并发提取完毕。所有 beats 已存入 objective_scenes。你可以开始进行制片人汇总策略了。"
    )
