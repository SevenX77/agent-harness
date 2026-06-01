#!/usr/bin/env python3
"""build_tree.py - 结构化代码体检清单生成器

扫描指定代码库源文件，递归建立结构化 Markdown 文件树清单，
并将所有节点的状态初始化为待审计状态 `[ ]`。
"""

from __future__ import annotations

import os
from pathlib import Path

from diag_paths import default_report, ensure_output_path

# 扫描的源目录与目标包
SCAN_TARGETS = {
    "graph-agent": Path("packages/graph-agent/src/graph_agent"),
    "graph-agent-gateway": Path("packages/graph-agent-gateway/src/graph_agent_gateway"),
    "studio-backend": Path("apps/studio/backend/app"),
}

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", "dist", "build"}


def get_py_files(dir_path: Path) -> list[Path]:
    """递归获取目录下所有有效的 Python 文件"""
    py_files: list[Path] = []
    if not dir_path.exists():
        return py_files

    for root, dirs, files in os.walk(dir_path):
        # 排除忽略目录
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file.endswith(".py"):
                py_files.append(Path(root) / file)
    return sorted(py_files)


def build_markdown_tree(repo_root: Path) -> str:
    """自动生成结构化任务清单内容"""
    lines = [
        "# 仓库代码健康度自动体检任务清单 (基准分: 100)",
        "",
        "> [!IMPORTANT]",
        "> 本文档由 `code-diagnostics/build_tree.py` 动态扫描代码库并生成。",
        "> 任务状态：`[ ]` 待体检，`[/]` 体检中，`[x]` 已完成并成功录入证据。",
        "",
        "## 1. 待审计代码源文件清单",
        "",
    ]

    for label, relative_path in SCAN_TARGETS.items():
        target_path = repo_root / relative_path
        if not target_path.exists():
            continue

        lines.append(f"- [ ] **{label}** (`{relative_path}`)")
        py_files = get_py_files(target_path)
        
        # 建立模块级和文件级的树状缩进结构
        for py_file in py_files:
            rel_file = py_file.relative_to(target_path)
            parts = rel_file.parts
            indent = "  " * len(parts)
            
            # 显示相对包路径
            lines.append(f"{indent}- [ ] `{rel_file}`")

    lines.append("")
    lines.append("## 2. 历次体检扣分细则与证据明细")
    lines.append("")
    lines.append("<!-- SYSTEM_DIAGNOSTICS_EVIDENCE_START -->")
    lines.append("<!-- SYSTEM_DIAGNOSTICS_EVIDENCE_END -->")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    import argparse
    from datetime import datetime

    parser = argparse.ArgumentParser(description="生成结构化代码体检清单")
    parser.add_argument("--file", type=str, default=None, help="目标报告文件路径")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]

    if args.file:
        target_md = ensure_output_path(args.file)
        target_md.parent.mkdir(parents=True, exist_ok=True)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_md = default_report(timestamp)

    markdown_content = build_markdown_tree(repo_root)
    target_md.write_text(markdown_content, encoding="utf-8")
    print(f"[build_tree] 成功生成体检清单模板: {target_md}")


if __name__ == "__main__":
    main()
