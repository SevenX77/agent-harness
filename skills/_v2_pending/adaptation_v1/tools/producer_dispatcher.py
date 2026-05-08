from __future__ import annotations

import json
import logging
from pathlib import Path

from story_forge.core.llm_client_manager import call_llm_with_fallback

logger = logging.getLogger(__name__)


def dispatch_producer_strategy(ctx: dict) -> str:
    """
    制片人全局调度工具。
    提供大纲(Synopsis)、受众DNA(Drama DNA)、事件框架(Framework) 等上游资产，
    并把所有物理场的 Beats 合并给模型。
    """
    scenes = ctx.get("objective_scenes", [])
    if not scenes:
        return "ERROR: objective_scenes 为空。"

    # Load context assets
    base_dir = Path(__file__).resolve().parent.parent.parent
    fixtures_dir = base_dir / "fixtures"

    synopsis = (
        (fixtures_dir / "synopsis.txt").read_text(encoding="utf-8")
        if (fixtures_dir / "synopsis.txt").exists()
        else "无"
    )
    framework = (
        (fixtures_dir / "framework.md").read_text(encoding="utf-8")
        if (fixtures_dir / "framework.md").exists()
        else "无"
    )

    drama_dna = "无"
    if (fixtures_dir / "drama_dna.json").exists():
        try:
            dna_data = json.loads((fixtures_dir / "drama_dna.json").read_text(encoding="utf-8"))
            drama_dna = json.dumps(dna_data.get("core_dna", {}), ensure_ascii=False, indent=2)
        except Exception:
            pass

    # Build full scene context
    global_overview = []
    for sc in scenes:
        beats_text = "\n".join(
            [
                f"  - [{b['beat_id']}] {b['content']} (情绪: {b['emotion']})"
                for b in sc.get("beats", [])
            ]
        )
        global_overview.append(
            f"【Scene: {sc['scene_id']} | Location: {sc['meta']['location']}】\n"
            f"Beats:\n{beats_text}"
        )
    overview_text = "\n\n".join(global_overview)

    # Load Voice & Rhythm Rules
    rules_dir = (
        Path(__file__).resolve().parent.parent / "subskills" / "producer_strategy" / "references"
    )
    voice_rhythm_rules = (
        (rules_dir / "voice_and_rhythm_rules.md").read_text(encoding="utf-8")
        if (rules_dir / "voice_and_rhythm_rules.md").exists()
        else ""
    )

    sys_prompt = f"""你是一个爆款 AI 短剧制片人。
短剧的底层逻辑是：**解说推动（Narration-Driven）**。

你的任务是仔细阅读我提供的【故事大纲】、【受众DNA】和【幕结构框架】，
然后纵观本章节的所有场景 Beats，进行全局改编批注。

请严格遵照以下《声音武器库与第一性原理》进行批注：
{voice_rhythm_rules}

## 输出要求
输出必须是标准的 JSON，格式如下：
{{
  "audience_psychology_analysis": "（字符串）你结合【受众DNA】对这几场戏观众心理预期的深度分析。\
解释清楚观众想要看到什么。",
  "scene_strategies": [
    {{
      "scene_id": "OBJ_SC_01",
      "producer_directives": "宏观指导方向。说明这是什么类型的戏（设定/过渡/情绪爆发）。",
      "beats_treatment": "基于视听武器库的精准分配。例如：'b1-b2 使用[全知旁白VO]快速推进；\
b3 使用[蒙太奇]制造瞬间刺激；b4 插入[OS]拉长节奏慢品。'"
    }}
  ]
}}
"""
    user_prompt = f"""
## 故事大纲 (Synopsis)
{synopsis}

## 核心受众与爽点分析 (Drama DNA)
{drama_dna}

## 剧作幕结构 (Framework)
{framework}

## 本章分场节拍 (Scenes & Beats)
{overview_text}

请结合上述资产，并严格遵照视听武器库分配原则，输出你的制片人全局批注 JSON。
"""

    logger.info("开始请求全局 Producer 策略...")
    try:
        output_dict = call_llm_with_fallback(
            task_id="producer_plan_global",
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

        strategy_json = json.loads(output_text)

        ctx["producer_global_analysis"] = strategy_json.get("audience_psychology_analysis", "")

        try:
            strategy_map = {s["scene_id"]: s for s in strategy_json.get("scene_strategies", [])}
        except Exception:
            strategy_map = {}
        for sc in scenes:
            sc["producer_strategy"] = strategy_map.get(sc["scene_id"], {})

        ctx["objective_scenes"] = scenes
        return "全局制片人策略批注完成。"
    except Exception as e:
        raw_output = output_text if "output_text" in locals() else "None"
        logger.error(
            f"全局 Producer 执行失败: {e}\n"
            f"Raw Output: {raw_output}"
        )
        return f"ERROR: {e}"
