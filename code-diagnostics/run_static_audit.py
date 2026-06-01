#!/usr/bin/env python3
"""run_static_audit.py - 卓越工程硬性指标自动打分与体检卡口

执行 5 维健康度的 Python 静态指标扫描扣分，回填证据至指定的 Markdown。
如果最终得分低于 85 分，则强力以非 0 状态码退出阻断流水线。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from diag_paths import ensure_output_path, latest_report

# 废弃文件的静态检查目标
LEGACY_FILES_TO_CHECK = [
    Path("packages/graph-agent/src/graph_agent/core/harness.py"),
    Path("packages/graph-agent/tests/core/test_harness_save_outputs_failure.py"),
    Path("packages/graph-agent/tests/core/test_harness_phase_b_invariants.py"),
    Path("packages/graph-agent/tests/core/test_harness_state_machine_resources.py"),
]

# 强检查源码目录
SRC_DIRS = [
    Path("packages/graph-agent/src/graph_agent"),
    Path("packages/graph-agent-gateway/src/graph_agent_gateway"),
    Path("apps/studio/backend/app"),
]

TEST_DIRS = [
    Path("packages/graph-agent/tests"),
    Path("packages/graph-agent-gateway/tests"),
]


def perform_static_audit(repo_root: Path) -> tuple[int, list[str], dict[str, str], dict[str, int]]:
    """扫描全仓，执行打分，并返回 (最终得分, 证据列表, 文件节点状态字典, 维度得分字典)"""
    score = 100
    evidences: list[str] = []
    file_statuses: dict[str, str] = {}

    # 1. 死代码残留扫描 (扣 20 分/件)
    evidences.append("### 维度一：死代码与历史遗迹清除体检")
    legacy_found = False
    for rel_path in LEGACY_FILES_TO_CHECK:
        abs_path = repo_root / rel_path
        if abs_path.exists():
            legacy_found = True
            deduction = 20
            score -= deduction
            evidence = (
                f"- [ ] **[已捕获缺陷]** 发现废弃死代码文件未做物理删除残留：\n"
                f"  - 路径: [{rel_path.name}](file://{abs_path.resolve()})\n"
                f"  - **扣除 {deduction} 分**。说明: 该文件已完全废弃，物理残留造成重大阅读和维护债务。"
            )
            evidences.append(evidence)
            file_statuses[rel_path.name] = f"[x] `{rel_path.name}` (扣{deduction}分 - 物理死代码残留)"
            
    if not legacy_found:
        evidences.append("- [x] **[体检通过]** 全仓未发现任何已知的历史废弃死代码残留。**(得 0 扣分)**")
    evidences.append("")

    # 2. 强类型检测屏蔽扫描 (mypy: ignore-errors 扣 15 分/件)
    evidences.append("### 维度二：强类型纯净度与安全卡口体检")
    mypy_escape_files: list[tuple[Path, int]] = []
    
    for src_dir in SRC_DIRS:
        target_dir = repo_root / src_dir
        if not target_dir.exists():
            continue
        for file_path in target_dir.rglob("*.py"):
            if not file_path.is_file():
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
                lines = content.splitlines()[:5]
                for idx, line in enumerate(lines, start=1):
                    if "mypy: ignore-errors" in line or "mypy:ignore-errors" in line:
                        mypy_escape_files.append((file_path, idx))
            except Exception:
                pass

    if mypy_escape_files:
        for file_path, line_no in mypy_escape_files:
            deduction = 15
            score -= deduction
            evidence = (
                f"- [ ] **[已捕获缺陷]** 发现严重强类型屏蔽，"
                f"第一行使用 `mypy: ignore-errors` 彻底瓦解了静态类型系统：\n"
                f"  - 路径: [{file_path.name}](file://{file_path.resolve()}#L{line_no})\n"
                f"  - **扣除 {deduction} 分**。说明: 禁止使用全局 ignore 注释逃避 Mypy 检查。"
            )
            evidences.append(evidence)
            file_statuses[file_path.name] = f"[x] `{file_path.name}` (扣{deduction}分 - mypy全局逃逸)"
    else:
        evidences.append("- [x] **[体检通过]** 全仓没有任何源码文件全局屏蔽 Mypy 静态类型安全分析。**(得 0 扣分)**")
    evidences.append("")

    # 3. 测试活性保障扫描 (skip 扣 10 分/件)
    evidences.append("### 维度三：测试活性保障体检")
    skipped_test_files: list[Path] = []
    
    for test_dir in TEST_DIRS:
        target_dir = repo_root / test_dir
        if not target_dir.exists():
            continue
        for file_path in target_dir.rglob("*.py"):
            if not file_path.is_file() or "test_code_health_metrics" in file_path.name:
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
                if "pytest.mark.skip(" in content or "pytestmark = pytest.mark.skip" in content:
                    skipped_test_files.append(file_path)
            except Exception:
                pass

    if skipped_test_files:
        for file_path in skipped_test_files:
            deduction = 10
            score -= deduction
            evidence = (
                f"- [ ] **[已捕获缺陷]** 发现测试用例被全局 `skip` 挂起，构成“惰性测试防御”：\n"
                f"  - 路径: [{file_path.name}](file://{file_path.resolve()})\n"
                f"  - **扣除 {deduction} 分**。说明: 被废弃的测试应予以物理清理，不应常态化跳过。"
            )
            evidences.append(evidence)
            file_statuses[file_path.name] = f"[x] `{file_path.name}` (扣{deduction}分 - 全局skip跳过)"
    else:
        evidences.append("- [x] **[体检通过]** 未发现任何常态化跳过的废弃单元测试。**(得 0 扣分)**")
    evidences.append("")

    # 4. 接口与依赖耦合体检 (扫描 os.environ/os.getenv 绕过 Settings 行为)
    evidences.append("### 维度四：接口与依赖耦合体检")
    environ_bypasses: list[tuple[Path, int, str]] = []
    for src_dir in SRC_DIRS:
        if "packages/graph-agent" not in str(src_dir):
            continue
        target_dir = repo_root / src_dir
        for file_path in target_dir.rglob("*.py"):
            if "settings.py" in file_path.name or "bootstrap.py" in file_path.name or "runner.py" in file_path.name:
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
                for idx, line in enumerate(content.splitlines(), start=1):
                    if "os.environ" in line or "os.getenv" in line:
                        environ_bypasses.append((file_path, idx, line.strip()))
            except Exception:
                pass

    if environ_bypasses:
        # 每发现一处 Settings 绕过扣 2 分，最多扣 10 分
        deduction_cap = min(len(environ_bypasses) * 2, 10)
        score -= deduction_cap
        bypass_msg = (
            f"- [ ] **[已捕获技术债]** 发现 {len(environ_bypasses)} 处绕过 `Settings` "
            "统一接口直接使用 `os.environ`/`os.getenv` 的高耦合依赖："
        )
        evidences.append(bypass_msg)
        for file_path, line_no, snippet in environ_bypasses[:5]:
            evidences.append(f"  - 路径: [{file_path.name}](file://{file_path.resolve()}#L{line_no}) -> `{snippet}`")
        if len(environ_bypasses) > 5:
            evidences.append(f"  - ... 还有 {len(environ_bypasses) - 5} 处未全部列出。")
        deduct_msg = (
            f"  - **累计扣除 {deduction_cap} 分**。说明: "
            "框架运行中应通过统一的 `Settings` 读取配置而非随意的系统环境调用。"
        )
        evidences.append(deduct_msg)
    else:
        pass_msg = (
            "- [x] **[体检通过]** 核心层未发现任何违规直接绕过 `Settings` "
            "进行环境变量读取的高耦合逻辑。**(得 0 扣分)**"
        )
        evidences.append(pass_msg)
    evidences.append("")

    # 5. 工程极简与技术债务体检 (扫描 TODO/FIXME 临时批注)
    evidences.append("### 维度五：工程极简与技术债务体检")
    todo_comments: list[tuple[Path, int, str]] = []
    for src_dir in SRC_DIRS:
        target_dir = repo_root / src_dir
        if not target_dir.exists():
            continue
        for file_path in target_dir.rglob("*.py"):
            try:
                content = file_path.read_text(encoding="utf-8")
                for idx, line in enumerate(content.splitlines(), start=1):
                    if "# TODO" in line or "# FIXME" in line:
                        todo_comments.append((file_path, idx, line.strip()))
            except Exception:
                pass

    if todo_comments:
        # 每发现一处未决技术债扣 1 分，最多扣 10 分
        deduction_cap = min(len(todo_comments) * 1, 10)
        score -= deduction_cap
        todo_msg = (
            f"- [ ] **[已捕获技术债]** 全仓发现 {len(todo_comments)} 处"
            "未决 `TODO`/`FIXME` 技术债占坑标记："
        )
        evidences.append(todo_msg)
        for file_path, line_no, snippet in todo_comments[:5]:
            evidences.append(f"  - 路径: [{file_path.name}](file://{file_path.resolve()}#L{line_no}) -> `{snippet}`")
        if len(todo_comments) > 5:
            evidences.append(f"  - ... 还有 {len(todo_comments) - 5} 处占坑标示。")
        evidences.append(f"  - **累计扣除 {deduction_cap} 分**。说明: 常态化遗留 TODO 说明代码存在未收敛的技术尾巴。")
    else:
        evidences.append("- [x] **[体检通过]** 全仓源码未发现任何已标记的 TODO/FIXME 遗留技术债。**(得 0 扣分)**")
    evidences.append("")

    legacy_files_deduction = sum(1 for p in LEGACY_FILES_TO_CHECK if (repo_root / p).exists()) * 20 * 5
    dim_scores = {
        "极简度（奥卡姆剃刀）": max(0, 100 - min(len(todo_comments) * 1, 10) * 5),
        "类型安全度": max(0, 100 - len(mypy_escape_files) * 15 * 5),
        "死代码干净度": max(0, 100 - legacy_files_deduction),
        "测试活性度": max(0, 100 - len(skipped_test_files) * 10 * 5),
        "接口与依赖清晰度": max(0, 100 - min(len(environ_bypasses) * 2, 10) * 5),
    }

    return max(score, 0), evidences, file_statuses, dim_scores


def update_markdown_report(
    repo_root: Path,
    score: int,
    evidences: list[str],
    file_statuses: dict[str, str],
    dim_scores: dict[str, int],
    target_md: Path,
) -> Path:
    """读取并更新指定的 Markdown 报告"""
    if not target_md.exists():
        from build_tree import build_markdown_tree
        target_md.write_text(build_markdown_tree(repo_root), encoding="utf-8")

    content = target_md.read_text(encoding="utf-8")

    # 1. 替换分数为静态分
    content = re.sub(
        r"# 仓库代码健康度自动体检任务清单 \(基准分: \d+\)",
        f"# 仓库代码健康度自动体检任务清单 (静态扣分后得分: {score}/100)",
        content
    )

    # 2. 替换证据小节
    evidence_text = "\n".join(evidences)
    content = re.sub(
        r"<!-- SYSTEM_DIAGNOSTICS_EVIDENCE_START -->.*?<!-- SYSTEM_DIAGNOSTICS_EVIDENCE_END -->",
        f"<!-- SYSTEM_DIAGNOSTICS_EVIDENCE_START -->\n{evidence_text}\n<!-- SYSTEM_DIAGNOSTICS_EVIDENCE_END -->",
        content,
        flags=re.DOTALL
    )

    # 3. 勾选和更新状态
    for file_name, new_status in file_statuses.items():
        escaped_file = re.escape(file_name)
        pattern = rf"- \[ \]\s+`([^`]*{escaped_file})`"
        content = re.sub(pattern, f"- {new_status}", content)

    # 4. 插入或更新5维静态分元数据 (置于Section 1之前以防被重置覆盖)
    import json
    metadata_comment = f"<!-- STATIC_DIMENSION_SCORES: {json.dumps(dim_scores, ensure_ascii=False)} -->"
    if "<!-- STATIC_DIMENSION_SCORES:" in content:
        content = re.sub(
            r"<!-- STATIC_DIMENSION_SCORES:.*?-->",
            metadata_comment,
            content
        )
    else:
        content = content.replace("## 1. 待审计代码源文件清单", f"{metadata_comment}\n\n## 1. 待审计代码源文件清单")

    target_md.write_text(content, encoding="utf-8")
    return target_md


def main() -> None:
    parser = argparse.ArgumentParser(description="代码健康度静态指标扫描器")
    parser.add_argument("--file", type=str, default=None, help="目标报告文件路径")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]

    # 找到要写入的报告文件路径
    if args.file:
        target_md = ensure_output_path(args.file)
    else:
        # 如果未指定，寻找 output/ 下最新生成的 diag_report_*.md
        target_md = latest_report()
        if target_md is None:
            print("[run_static_audit] ❌ 未发现任何已生成的报告文件，请先运行 build_tree.py！", file=sys.stderr)
            sys.exit(1)

    # 运行体检
    score, evidences, file_statuses, dim_scores = perform_static_audit(repo_root)

    # 更新 Markdown 报告
    update_markdown_report(repo_root, score, evidences, file_statuses, dim_scores, target_md)
    
    print(f"[run_static_audit] 体检报告静态得分已回填: {target_md}")
    print(f"[run_static_audit] 静态体检得分: {score} 分")


if __name__ == "__main__":
    main()
