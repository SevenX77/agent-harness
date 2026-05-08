from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from story_forge.core.llm_client_manager import call_llm_with_fallback

logger = logging.getLogger(__name__)


def dispatch_writer_drafting(ctx: dict) -> str:
    """
    编剧并发调度工具：注入 voice_and_rhythm_rules.md 的灵魂，输出原生的 JSON 剧本数组。
    """
    scenes = ctx.get("objective_scenes", [])
    if not scenes:
        return "ERROR: objective_scenes 为空。"

    producer_global_analysis = ctx.get("producer_global_analysis", "")

    from pathlib import Path

    rules_dir = (
        Path(__file__).resolve().parent.parent / "subskills" / "producer_strategy" / "references"
    )
    voice_rhythm_rules = (
        (rules_dir / "voice_and_rhythm_rules.md").read_text(encoding="utf-8")
        if (rules_dir / "voice_and_rhythm_rules.md").exists()
        else ""
    )

    sys_prompt = f"""你是一个拥有千万粉丝的【爆款短剧解说大V】。
你的任务是将原著小说的情节，改写为极具网感的“解说驱动型（Narration-Driven）”短剧分镜脚本。

## 观众心理学（决定了你该怎么说话）
{producer_global_analysis}

## 第一性原理：声音与视觉节奏（核心法则）
请严格遵照以下法则，精准分配 VO、OS、对白和视觉节奏：
{voice_rhythm_rules}

## 编剧红线警告
1. **音画分离：坚决不准“看图说话”！**
   - 画面是在演动作，VO/OS 是在讲剧情逻辑和未来伏笔！
   - 【错误示范】画面：[姜宁拿起水杯喝水] 旁白：“我拿起水杯喝了一口。”（这是废话！）
   - 【正确示范】画面：[姜宁拿起水杯喝水] 旁白：“只要我不进这个空间，这里的保鲜期就是永久。”

2. **区分旁白(VO)和独白(OS)的格式**：
   - VO是“未来的我”对观众说书：【VO】“距离台风只有三天了。”
   - OS是画面中“此刻的我”内心流淌的声音：【OS】“好疼……这不是梦。”
   - 对白是与物理世界互动：【对白】姜宁：“你确定？”

3. **镜头时长的控制**
   - 【情绪轰炸蒙太奇】只有在制片人明确要求时才能使用，时长必须在 0.5s - 1.5s 之间，
     配合极其碎裂的画面描述。
   - 【稳态叙事长镜头】是绝大多数时间的常态，时长必须在 3.0s - 5.0s 左右。
     确保观众在听 VO 时画面足够稳定。

## 输出 Schema
输出一段合法的 JSON 数组，包含该场戏的多个分镜。
[
  {{
    "video_audio": "[客观场景描述 | X.Xs] (严禁写心理活动)",
    "voice_text": "【VO】解说内容 \\n或\\n【OS】内心独白 \\n或\\n【对白】角色名：台词"
  }}
]
"""

    results = []

    def _run_subagent(scene: dict) -> dict:
        prod_strategy = scene.get("producer_strategy", {})
        beats_text = "\n".join(
            [f"- [{b['beat_id']}] {b['content']}" for b in scene.get("beats", [])]
        )
        prod_notes = (
            f"【制片人宏观指导】\n{prod_strategy.get('producer_directives', '')}\n\n"
            f"【武器库分配意见】\n{prod_strategy.get('beats_treatment', '')}"
        )

        user_prompt = (
            f"当前场景：{scene['meta']['location']}\n\n"
            f"【原始动作节拍 (Beats)】\n{beats_text}\n\n"
            f"【原著截取文本】\n{scene.get('segmented_text', '')}\n\n"
            f"{prod_notes}\n\n"
            f"请严格按照制片人分配的声音武器和视觉节奏，输出纯 JSON 数组剧本！"
        )

        try:
            output_dict = call_llm_with_fallback(
                task_id=f"write_{scene['scene_id']}",
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                llm_role="screenwriter",
                temperature=0.7,
            )
            output_text = output_dict.get("content", "").strip()

            if output_text.startswith("```json"):
                output_text = output_text[7:]
            elif output_text.startswith("```"):
                output_text = output_text[3:]
            if output_text.endswith("```"):
                output_text = output_text[:-3]
            output_text = output_text.strip()

            script_json = json.loads(output_text)
            return {"scene_id": scene["scene_id"], "script": script_json}
        except Exception as e:
            logger.error(f"编剧子技能执行失败 ({scene['scene_id']}): {e}")
            return {
                "scene_id": scene["scene_id"],
                "script": [{"video_audio": f"ERROR: {e}", "voice_text": ""}],
            }

    logger.info(f"派发任务至 Writer，并发处理 {len(scenes)} 个场景...")
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_run_subagent, sc): sc for sc in scenes}
        for future in as_completed(futures):
            results.append(future.result())

    script_map = {r["scene_id"]: r["script"] for r in results}
    for sc in scenes:
        sc["script_draft"] = script_map.get(sc["scene_id"], [])

    ctx["objective_scenes"] = scenes
    return "所有场景的剧本草稿编写完毕。"
