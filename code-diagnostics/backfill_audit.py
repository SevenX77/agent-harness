#!/usr/bin/env python3
"""backfill_audit.py - 子代理诊断结果回填与严重度加权惩罚折算引擎（模型无关）

主控调度子代理对全仓 Python 文件做 5 维微观体检、并为每条缺陷标注 severity，
结论以 JSON 落盘。本脚本不调用任何外部大模型，只负责：
  1. 合并 output/{run_id}/findings/ 下所有 subagent 产出的（含 severity 的）findings JSON；
  2. 将每个文件的健康分与就地内嵌微观证据回填进 diag_report_{run_id}.md；
  3. 按"严重度加权缺陷密度"惩罚制折算出全仓最终健康分。

评分口径（可在下方常量调节）：
  - 每条缺陷按 severity 赋权：critical=5 / major=2 / minor=0.5（缺失按 major）。
  - 单文件健康分 = clamp(round(10 - 该文件加权缺陷量), 0, 9)，零缺陷=10。
  - 全仓惩罚分 = round(100 * exp(-λ * 加权缺陷密度))，密度 = Σ权重 / 已审文件数。
  - 最终分 = max(0, 惩罚分 - 静态扣分)。静态卡口只作纯扣分项，绝不正向加权抬分。

惩罚制相对"平均分"的关键优势：对缺陷的数量与严重度真正敏感，且指数曲线在
"很差"区间仍可区分（永不假性归零），便于后续追踪整改进展。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from diag_paths import ensure_output_path

# 与报告内 package 标题一一对应（仅用于校验，回填按 (package, subpath) 精确匹配）
KNOWN_PACKAGES = {"graph-agent", "graph-agent-gateway", "studio-backend"}

# 严重度权重：一条 critical 抵 10 条 minor，杜绝被 docstring 级 nitpick 砸穿分数
SEVERITY_WEIGHTS = {"critical": 5.0, "major": 2.0, "minor": 0.5}
DEFAULT_SEVERITY_WEIGHT = 2.0  # severity 缺失/非法时按 major 计

DECAY_LAMBDA = 0.18    # 惩罚陡峭度：加权密度每+1分数约×0.84；调大更狠
# 静态卡口只作纯扣分项：final = max(0, 惩罚分 − 静态扣分)，绝不正向加权抬分

# severity → 报告内中文标签
SEVERITY_LABEL = {"critical": "严重", "major": "重要", "minor": "轻微"}


def finding_weight(finding: dict[str, Any]) -> float:
    """单条缺陷的严重度权重。"""
    sev = str(finding.get("severity", "")).lower()
    return SEVERITY_WEIGHTS.get(sev, DEFAULT_SEVERITY_WEIGHT)


def file_weighted_defects(findings: list[dict[str, Any]]) -> float:
    """单文件的加权缺陷量 = Σ 各缺陷严重度权重。"""
    return sum(finding_weight(f) for f in findings)


def file_health(findings: list[dict[str, Any]]) -> int:
    """单文件健康分：零缺陷=10；否则 clamp(round(10 - 加权缺陷量), 0, 9)。"""
    if not findings:
        return 10
    return max(0, min(9, round(10 - file_weighted_defects(findings))))


def load_findings(findings_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """合并 findings 目录（或单个文件）中所有 subagent 的 findings JSON。

    每个 JSON 形如 {"results": [{"package","subpath","score","findings":[...]}, ...]}。
    以 (package, subpath) 为键去重，后写入者覆盖先写入者。
    """
    if findings_path.is_dir():
        json_files = sorted(findings_path.glob("*.json"))
    elif findings_path.is_file():
        json_files = [findings_path]
    else:
        print(f"[backfill_audit] ❌ findings 路径不存在: {findings_path}", file=sys.stderr)
        sys.exit(1)

    results_map: dict[tuple[str, str], dict[str, Any]] = {}
    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[backfill_audit] ⚠️ 跳过无法解析的发现文件 {jf.name}: {exc}")
            continue
        for item in data.get("results", []):
            pkg = item.get("package")
            subpath = item.get("subpath")
            if not pkg or not subpath:
                print(f"[backfill_audit] ⚠️ {jf.name} 中存在缺少 package/subpath 的条目，已跳过")
                continue
            if pkg not in KNOWN_PACKAGES:
                print(f"[backfill_audit] ⚠️ {jf.name} 中出现未知 package={pkg}，仍按原样回填")
            results_map[(pkg, subpath)] = item
    print(f"[backfill_audit] 📥 已从 {len(json_files)} 个 findings 文件合并 {len(results_map)} 条文件级结论")
    return results_map


def render_evidence_nodes(nested_indent: str, subpath: str, findings: list[dict[str, Any]]) -> list[str]:
    """将单个文件的诊断结论渲染为缩进悬挂的微观证据节点（含严重度标签）。"""
    lines: list[str] = []
    if not findings:
        lines.append(f"{nested_indent}- [x] **[体检通过]** 未发现明显架构美学债务。")
        return lines

    file_name = Path(subpath).name
    for finding in findings:
        sev = str(finding.get("severity", "")).lower()
        sev_label = SEVERITY_LABEL.get(sev, "重要")
        dim = finding.get("dimension", "架构美学")
        loc = finding.get("line_range", "未知行")
        snippet = (finding.get("code_snippet") or "").strip()
        desc = (finding.get("description") or "").strip()
        lines.append(f"{nested_indent}- [x] **[{sev_label}·{dim}]** `{file_name}:{loc}`: {desc}")
        if snippet:
            lines.append(f"{nested_indent}  ```python")
            for s_line in snippet.splitlines():
                lines.append(f"{nested_indent}  {s_line}")
            lines.append(f"{nested_indent}  ```")
    return lines


def backfill_report(
    content_lines: list[str], results_map: dict[tuple[str, str], dict[str, Any]]
) -> tuple[list[str], dict[str, Any]]:
    """逐行扫描清单，回填健康分与微观证据，并累计加权缺陷统计。"""
    new_lines: list[str] = []
    current_package: str | None = None
    n_covered = 0
    total_weight = 0.0
    sev_counter: Counter[str] = Counter()

    for line in content_lines:
        m_pkg = re.match(r"^\s*-\s*\[\s*[x]?\s*\]\s*\*\*([^*]+)\*\*", line)
        if m_pkg:
            current_package = m_pkg.group(1).strip()
            new_lines.append(re.sub(r"-\s*\[\s*\]", "- [x]", line))
            continue

        m_file = re.match(r"^(\s*)-\s*\[\s*\]\s*`([^`]+)`", line)
        if m_file and current_package:
            indent, subpath = m_file.group(1), m_file.group(2)
            result = results_map.get((current_package, subpath))
            if result:
                findings = result.get("findings", [])
                score = file_health(findings)
                new_lines.append(f"{indent}- [x] `{subpath}` (健康分: {score}/10)")
                new_lines.extend(render_evidence_nodes(indent + "  ", subpath, findings))
                n_covered += 1
                total_weight += file_weighted_defects(findings)
                for f in findings:
                    sev = str(f.get("severity", "")).lower()
                    sev_counter[sev if sev in SEVERITY_WEIGHTS else "major"] += 1
                continue

        new_lines.append(line)

    stats = {"n_covered": n_covered, "total_weight": total_weight, "sev": sev_counter}
    return new_lines, stats


def compute_summary(content: str, stats: dict[str, Any], model_label: str) -> str:
    """按严重度加权密度惩罚制折算最终分，更新标题并追加总报告。"""
    n = stats["n_covered"]
    total_weight = stats["total_weight"]
    sev: Counter[str] = stats["sev"]
    density = total_weight / n if n else 0.0
    penalty = round(100 * math.exp(-DECAY_LAMBDA * density))

    static_score = 100
    m_static = re.search(r"\(静态扣分后得分: (\d+)/100\)", content)
    if m_static:
        static_score = int(m_static.group(1))
    static_deduction = max(0, 100 - static_score)

    final = max(0, penalty - static_deduction)
    c, mj, mn = sev.get("critical", 0), sev.get("major", 0), sev.get("minor", 0)

    content = re.sub(
        r"# 仓库代码健康度自动体检任务清单 \(.*?\)",
        f"# 仓库代码健康度自动体检任务清单 (最终得分: {final}/100)",
        content,
    )

    summary = f"""## 👑 全仓终极架构体检与诊断总报告

> [!TIP]
> 评分口径：**严重度加权缺陷密度惩罚制**（走查器: {model_label}）。每条缺陷按 critical=5 / major=2 / minor=0.5 赋权，全仓惩罚分 = 100·e^(−{DECAY_LAMBDA}·加权密度)；静态卡口只作**纯扣分项**（最终分 = 惩罚分 − 静态扣分，绝不正向抬分）。指数曲线对缺陷数量与严重度真正敏感，且在"很差"区间仍可区分整改进展。

### 🔬 缺陷严重度构成（共 {c + mj + mn} 条 / {n} 文件）

| 严重度 | 条数 | 单条权重 | 加权小计 |
| :--- | :---: | :---: | :---: |
| 🔴 critical | {c} | 5.0 | {c * 5.0:.1f} |
| 🟠 major | {mj} | 2.0 | {mj * 2.0:.1f} |
| 🟡 minor | {mn} | 0.5 | {mn * 0.5:.1f} |
| **合计** | **{c + mj + mn}** | | **{total_weight:.1f}** |

**加权缺陷密度 = {total_weight:.1f} / {n} = {density:.2f} 加权缺陷 / 文件**

### 📊 最终健康分计算（惩罚分 − 静态扣分）

| 评估项 | 数值 | 作用 |
| :--- | :---: | :---: |
| **严重度加权惩罚分** `100·e^(−{DECAY_LAMBDA}·{density:.2f})` | {penalty} / 100 | 基准分 |
| **Python 静态硬性卡口扣分** | −{static_deduction} | 直接扣减 |
| **最终健康得分 (Global Health Score)** | **{final} / 100** | |
"""

    if "## 👑 全仓终极架构体检与诊断总报告" in content:
        content = re.sub(r"## 👑 全仓终极架构体检与诊断总报告.*", summary.strip(), content, flags=re.DOTALL)
    else:
        content = content.rstrip() + "\n\n---\n\n" + summary

    print(f"[backfill_audit] 💡 严重度 crit={c}/major={mj}/minor={mn} | 加权密度 {density:.2f} | 惩罚分 {penalty} | 静态扣分 −{static_deduction} | 最终 {final}/100")
    return content


def main() -> None:
    parser = argparse.ArgumentParser(description="子代理诊断结果回填与严重度加权惩罚折算引擎")
    parser.add_argument("--file", type=str, required=True, help="目标报告文件路径 diag_report_{ts}.md")
    parser.add_argument("--findings", type=str, required=True, help="含 severity 的 subagent findings JSON 文件或目录")
    parser.add_argument("--label", type=str, default="orchestrated-subagents", help="走查器标识，仅用于总报告展示")
    args = parser.parse_args()

    target_md = ensure_output_path(args.file)
    if not target_md.exists():
        print(f"[backfill_audit] ❌ 报告文件不存在: {target_md}", file=sys.stderr)
        sys.exit(1)

    results_map = load_findings(ensure_output_path(args.findings))
    if not results_map:
        print("[backfill_audit] ❌ 未加载到任何有效的 subagent 结论，请检查 findings 产出。", file=sys.stderr)
        sys.exit(1)

    content_lines = target_md.read_text(encoding="utf-8").splitlines()
    backfilled, stats = backfill_report(content_lines, results_map)
    final_content = compute_summary("\n".join(backfilled) + "\n", stats, args.label)

    target_md.write_text(final_content, encoding="utf-8")
    print(f"[backfill_audit] 🎉 子代理诊断结果回填完成！报告地址: {target_md}")


if __name__ == "__main__":
    main()
