#!/usr/bin/env python3
"""verify_report.py - 卓越工程代码诊断强卡口与验收工具

严格扫描 diag_report_{run_id}.md 报告：
1. 必须确保 Section 1 中的所有 Python 文件都被勾选为 `[x]`。
2. 必须包含 `(健康分: X/10)` 格式的健康评分。
3. 必须在文件条目正下方以缩进节点的形式内嵌微观证据或“体检通过”描述。

若校验失败，必须清晰输出“漏检的文件清单”与“漏检的索引条目”，以非 0 状态码退出阻断流水线。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from diag_paths import latest_report


def parse_and_verify_report(report_path: Path) -> tuple[bool, list[str], list[str]]:
    """深度解析并校验报告内容，返回 (是否通过, 漏检文件列表, 漏检索引行内容列表)"""
    if not report_path.exists():
        return False, ["[报告文件不存在]"], [f"找不到路径: {report_path}"]

    lines = report_path.read_text(encoding="utf-8").splitlines()
    
    # 查找 Section 1 的起止点
    start_idx = -1
    end_idx = -1
    for idx, line in enumerate(lines):
        if line.startswith("## 1. 待审计代码源文件清单"):
            start_idx = idx
        elif start_idx != -1 and line.startswith("## 2. "):
            end_idx = idx
            break

    if start_idx == -1:
        return False, ["[Section 1 缺失]"], ["报告未包含 '## 1. 待审计代码源文件清单' 小节"]
    
    if end_idx == -1:
        end_idx = len(lines)

    tree_lines = lines[start_idx:end_idx]
    
    uncompleted_files: list[str] = []
    uncompleted_entries: list[str] = []
    
    # 逐行扫描待体检的文件索引
    current_package = None
    for relative_idx, line in enumerate(tree_lines):
        line_no = start_idx + relative_idx + 1  # 真实文件行号
        
        # 匹配包目录 `- [ ] **graph-agent**` 类似行
        m_pkg = re.match(r"^\s*-\s*\[\s*[x]?\s*\]\s*\*\*([^*]+)\*\*", line)
        if m_pkg:
            current_package = m_pkg.group(1).strip()
            continue

        # 匹配 Python 源码文件项
        m_file = re.match(r"^(\s*)-\s*\[\s*(.*?)\s*\]\s*`([^`]+)`", line)
        if m_file and current_package:
            indent = m_file.group(1)
            checkbox = m_file.group(2).strip()
            subpath = m_file.group(3).strip()
            
            # 判断是否通过了静态与LLM双重审计
            is_checked = (checkbox == "x")
            has_score = "(健康分:" in line
            
            # 查找该文件节点下的子证据节点
            has_evidence = False
            next_idx = relative_idx + 1
            while next_idx < len(tree_lines):
                next_line = tree_lines[next_idx]
                # 遇到同级别或更浅级别的缩进（如新文件节点或包节点），说明证据区间结束
                next_indent_m = re.match(r"^(\s*)-", next_line)
                if next_indent_m:
                    next_indent = next_indent_m.group(1)
                    if len(next_indent) <= len(indent):
                        break
                
                # 检查是否包含子证据标记如 `  - [x] **[` or `  - [x] **[体检通过]**`
                if re.match(r"^\s*-\s*\[x\]\s*\*\*\[", next_line):
                    has_evidence = True
                next_idx += 1

            # 只要未勾选、无评分、或无子证据内嵌，均判定为漏检
            if not is_checked or not has_score or not has_evidence:
                uncompleted_files.append(f"{current_package} / `{subpath}`")
                uncompleted_entries.append(f"Line {line_no}: `{line.strip()}` (缺失健康分或下方证据)")

    is_passed = (len(uncompleted_files) == 0)
    return is_passed, uncompleted_files, uncompleted_entries


def main() -> None:
    parser = argparse.ArgumentParser(description="体检大图强力卡口卡点工具")
    parser.add_argument("--file", type=str, default=None, help="目标报告文件路径")
    args = parser.parse_args()

    if args.file:
        target_md = Path(args.file).resolve()
    else:
        # 默认寻找 output/ 下最新生成的 diag_report_*.md
        target_md = latest_report()
        if target_md is None:
            print("[verify_report] ❌ 未发现任何已生成的体检报告文件！", file=sys.stderr)
            sys.exit(1)

    print(f"[verify_report] 🔍 正在执行体检大图覆盖率强卡口验收: {target_md.name}")
    
    is_passed, uncompleted_files, uncompleted_entries = parse_and_verify_report(target_md)
    
    if not is_passed:
        print("\n❌ ========================================================", file=sys.stderr)
        print("❌ 架构美学体检大图强卡口验收失败！发现未审计或证据缺失的条目。", file=sys.stderr)
        print("❌ ========================================================\n", file=sys.stderr)
        
        print("📋 1. 【漏检的文件清单】:", file=sys.stderr)
        for u_file in uncompleted_files:
            print(f"  - {u_file}", file=sys.stderr)
            
        print("\n📌 2. 【漏检的索引条目】:", file=sys.stderr)
        for u_entry in uncompleted_entries:
            print(f"  - {u_entry}", file=sys.stderr)
            
        tip_msg = (
            "\n💡 提示: 漏检批次需由主控补派 subagent 重新走查并落盘 findings JSON，"
            "再运行 `python3 code-diagnostics/backfill_audit.py --file <报告> --findings <findings目录>` 回填。\n"
        )
        print(tip_msg, file=sys.stderr)
        sys.exit(1)
    else:
        print("\n🎉 ========================================================")
        print("🎉 强力卡口卡点校验成功！全仓 100% 文件诊断全部完成，且就地内嵌微观证据！")
        print("🎉 ========================================================\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
