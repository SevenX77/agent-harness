#!/usr/bin/env python3
"""diag_paths.py - code-diagnostics 产出物路径策略（单一出口）

所有诊断产出物（报告 .md、分批清单 .txt、findings JSON、指令文件等）**只允许**写入
`code-diagnostics/output/` 下；该目录整体已被 .gitignore 忽略，不入库。

任何脚本写盘前必须经 `ensure_output_path` 校验，越界路径直接拒绝并退出，
从根上杜绝诊断产出物散落污染仓库。每次体检的产物归拢到 `output/{run_id}/`。
"""

from __future__ import annotations

from pathlib import Path

# diag_paths.py 位于 code-diagnostics/ 下，parents[1] = 仓库根
REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "code-diagnostics" / "output"


def run_dir(run_id: str) -> Path:
    """某次体检的产出目录 output/{run_id}/（按需创建）。"""
    target = OUTPUT_ROOT / run_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def default_report(run_id: str) -> Path:
    """该次体检的标准报告路径 output/{run_id}/diag_report_{run_id}.md。"""
    return run_dir(run_id) / f"diag_report_{run_id}.md"


def latest_report() -> Path | None:
    """递归查找 output/ 下最新生成的 diag_report_*.md（按路径排序取末位）。"""
    if not OUTPUT_ROOT.exists():
        return None
    candidates = sorted(OUTPUT_ROOT.rglob("diag_report_*.md"))
    return candidates[-1] if candidates else None


def ensure_output_path(path: str | Path) -> Path:
    """校验 path 落在 OUTPUT_ROOT 下；越界则拒绝写入并以非 0 退出。"""
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(OUTPUT_ROOT.resolve())
    except ValueError:
        raise SystemExit(
            f"[code-diagnostics] ❌ 产出物只允许写入 {OUTPUT_ROOT}/ 下，拒绝越界路径: {resolved}"
        )
    return resolved
