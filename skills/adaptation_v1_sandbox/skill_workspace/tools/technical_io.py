from __future__ import annotations

import re
from pathlib import Path


def load_chapter_text(ctx: dict, chapter_num: int = 1) -> str:
    """
    纯净的 IO Tool：负责从 novel_standardized.md 中提取指定章节的纯文本。
    作为 Beat 切分的上游原料。
    """
    # 在测试沙盒中，假定当前工作目录在 tests/skills/adaptation_v1_sandbox/
    # 或者从 ctx 里面取路径。为了测试简便，先写相对路径，后续可根据 ctx 动态调整。
    base_dir = Path(__file__).resolve().parent.parent.parent
    novel_path = base_dir / "fixtures" / "novel_standardized.md"
    
    if not novel_path.exists():
        return f"ERROR: 找不到小说源文件 {novel_path}"
        
    text = novel_path.read_text(encoding="utf-8")
    
    # 简单的正则匹配章节：## 第1章 xxx 
    # 匹配从目标章节到下一个章节（或文件尾）的全部内容
    pattern = rf"(## 第{chapter_num}章.*?\n)(.*?)(?=\n## 第|\Z)"
    match = re.search(pattern, text, flags=re.DOTALL)
    
    if match:
        chapter_title = match.group(1).strip()
        chapter_content = match.group(2).strip()
        return f"【{chapter_title}】\n\n{chapter_content}"
    else:
        return f"ERROR: 未找到第 {chapter_num} 章的内容"

