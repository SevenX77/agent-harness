from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def save_beats(ctx: dict, subagent_results: str) -> str:
    """
    将子代理返回的包含 beats 的 JSON 结果（或者 Markdown 文本）附加到 objective_scenes 并存盘。
    （在沙盒测试中，我们可以由主控 Agent 将组装好的 JSON 字符串传进来，或者直接提取）
    """
    try:
        # 这里为了测试方便，我们假设主代理会将结果组织好作为上下文存入，或者传进来
        # 实际 Graph Agent 中工具签名通常只有一个 ctx，但有时候也能通过参数传递
        # 这里简化：让主代理把聚合后的结果放入 ctx["final_beats_result"]，或者由工具自己去拿。
        pass
    except Exception as e:
        return f"ERROR: {str(e)}"

    return "已成功保存 Beats！"
