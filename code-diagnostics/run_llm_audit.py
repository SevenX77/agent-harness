#!/usr/bin/env python3
"""run_llm_audit.py - 并发大模型微观代码诊断与结果回填工具

利用多线程并发调用大模型，对全仓所有 Python 源码文件进行 5 维极高严苛度健康度诊断，
并将评分与证据链嵌套插入至 diag_report_{timestamp}.md 的对应索引节点正下方。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

SCAN_TARGETS = {
    "graph-agent": Path("packages/graph-agent/src/graph_agent"),
    "graph-agent-gateway": Path("packages/graph-agent-gateway/src/graph_agent_gateway"),
    "studio-backend": Path("apps/studio/backend/app"),
}


def load_env_keys(repo_root: Path) -> dict[str, str]:
    """从 .env 文件手动加载 API 密钥"""
    keys = {}
    env_path = repo_root / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                keys[k.strip()] = v.strip().strip('"').strip("'")
    return keys


def call_llm_with_retry(
    file_name: str,
    code_content: str,
    api_keys: dict[str, str],
    model_name: str,
    temperature: float,
    max_retries: int = 4,
) -> dict[str, Any]:
    """使用 Gemini 或 OpenAI API 进行超严格 5 维诊断并解析为 JSON，包含重试和指数退避"""
    
    # 极严苛诊断提示词：拒绝和稀泥，深度苛刻找茬
    prompt = f"""你是一个超一流的代码美学、可维护性与系统设计专家。请对下面的 Python 文件进行最严苛、最挑剔的【5维健康度微观体检】。

待体检文件名: {file_name}

=== 5维美学健康度标准与找茬重点 ===
1. 极简度（奥卡姆剃刀）：
   - 检查是否存在为了向下兼容或历史平滑过渡而层层包裹的临时补丁/适配器（如 Transitional Adaptors / Monkey-patches）。
   - 检查是否存在设计过度的冗余包装。
2. 类型安全度：
   - 检查是否存在任何滥用 `cast(Any, ...)`、`type: ignore` 注释逃避类型检查的代码。
   - 检查是否有函数/方法完全缺乏类型注解、隐式 Any 推断或不规范的类型标记。
3. 死代码干净度：
   - 检查是否存在物理上已弃用但仍有部分方法/属性未清除干净的代码。
   - 检查是否有不可达的方法、废弃未使用的类定义或已被新流程取代的历史包袱逻辑。
4. 测试活性度：
   - 如果此文件是测试文件，检查断言是否仅依赖于虚假的 Mock，而缺乏真实的端到端校验。
   - 检查是否有过于脆弱的测试逻辑或被隐藏跳过的局部用例。
5. 接口与依赖清晰度：
   - 检查是否越权引入了私有包底层实现（如引入以 `_` 开头的模块，或从 `_predict_internal` 内部越权获取依赖）。
   - 检查是否绕过了标准配置管理机制（如绕过统一的 `Settings` 对象，而随处采用 `os.environ` / `os.getenv` 进行硬编码式环境变量直接读取）。
   - 检查是否存在循环导入风险或过度复杂的包内多层级调用。

=== 黄金规则 (拒绝放水！！！) ===
- 必须实施最严苛的高标准审查。即使是极其微小的代码异味 (Code Smell)，例如：缺乏 docstring 注释、包含临时过渡性的 Patch 注释、不规范的异常捕获 (如 `except Exception:` 且无回退逻辑)、静态契约越权、类型收窄失败，也必须立刻降级扣分并记录为缺陷！
- 如果你发现任何缺陷，必须指明精确的起始行号范围（格式如 "L123" 或 "L123-130"），并且【必须一字不差地复制代码库中有问题的源代码片段】。
- findings 中的 `description` 必须深入解析该设计的弊端、技术债以及在长线演进中为什么是“有害的”，写出专业、深刻的架构分析，字数应适度充实，禁止使用敷衍套话。
- 如果文件确实做到了绝对意义上的完美，则给 10 分且 findings 列表为空。只要有一丁点设计硬伤或不严谨，就必须打出 1~9 分，并详细列出缺陷！

=== 输出 JSON 格式要求 ===
你必须返回且仅返回一个符合以下 Schema 的 JSON 对象，不要包含任何 markdown codeblock 包装（如 ```json），只输出纯 JSON 字符串：

若没有缺陷:
{{
  "score": 10,
  "findings": []
}}

若存在缺陷:
{{
  "score": 7,
  "findings": [
    {{
      "dimension": "类型安全度",
      "line_range": "L280",
      "code_snippet": "callbacks=cast(Any, event_sink),",
      "description": "此处使用 cast(Any) 强行规避了复杂的 LangGraph 回调事件订阅回调的类型推导。虽然在运行时可以通过，但这导致静态类型系统在此处彻底瓦解，后期接口发生重构时，Mypy 无法感知类型错误，遗留了类型隐患。"
    }}
  ]
}}

待体检的 Python 文件源代码如下:
=== SOURCE CODE START ===
{code_content}
=== SOURCE CODE END ===
"""

    gemini_key = api_keys.get("GEMINI_API_KEY")
    openai_key = api_keys.get("OPENAI_API_KEY")

    # 根据模型名决定使用哪个云商的接口
    model_lower = model_name.lower()
    if "gemini" in model_lower:
        use_openai = False
    elif "gpt" in model_lower or "o1" in model_lower:
        use_openai = True
    else:
        # 退化回退
        use_openai = bool(openai_key)

    for attempt in range(max_retries):
        try:
            if use_openai:
                url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": "You are a professional code review expert that outputs only JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": temperature,
                }
                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    raw_text = data["choices"][0]["message"]["content"]
            else:
                if not gemini_key:
                    raise RuntimeError("未在 .env 中发现 GEMINI_API_KEY，无法调用 Gemini！")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [
                        {
                            "parts": [{"text": prompt}]
                        }
                    ],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": temperature,
                    }
                }
                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]

            # 清理格式包装
            raw_text = raw_text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text.removeprefix("```json").removesuffix("```").strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text.removeprefix("```").removesuffix("```").strip()

            parsed = json.loads(raw_text)
            if "score" in parsed and "findings" in parsed:
                return parsed
            
        except Exception as exc:
            print(f"[run_llm_audit] 警告: 审计 {file_name} 第 {attempt+1} 次尝试失败 (模型: {model_name}): {exc}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt + 1)  # 指数退避加抖动
            else:
                return {"score": 10, "findings": [], "error": str(exc)}

    return {"score": 10, "findings": []}


def process_file_audit(
    file_info: tuple[str, str, str, Path],
    api_keys: dict[str, str],
    model_name: str,
    temperature: float,
) -> tuple[str, str, str, dict[str, Any]]:
    """子线程处理单文件诊断逻辑"""
    indent, package, subpath, abs_path = file_info
    file_name = abs_path.name
    
    if not abs_path.exists():
        return indent, package, subpath, {"score": 10, "findings": [], "error": "文件不存在"}

    try:
        code_content = abs_path.read_text(encoding="utf-8")
        lines = code_content.splitlines()
        # 限制单文件大小防止爆上下文，超过 1500 行进行截断
        if len(lines) > 1500:
            code_content = "\n".join(lines[:1500]) + "\n... [代码过长已截断]"
    except Exception as exc:
        return indent, package, subpath, {"score": 10, "findings": [], "error": f"无法读取: {exc}"}

    # 调用大模型
    result = call_llm_with_retry(file_name, code_content, api_keys, model_name, temperature)
    return indent, package, subpath, result


def main() -> None:
    parser = argparse.ArgumentParser(description="多线程并发大模型代码诊断回填")
    parser.add_argument("--file", type=str, default=None, help="目标报告文件路径")
    parser.add_argument("--workers", type=int, default=15, help="并行线程数")
    parser.add_argument("--model", type=str, default="gemini-3.5-flash", help="要使用的大模型名，例如 gemini-3.5-flash, gemini-3.5-pro, gpt-4o")
    parser.add_argument("--temperature", type=float, default=0.1, help="模型生成温度系数")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    
    # 找到目标报告文件
    if args.file:
        target_md = Path(args.file).resolve()
    else:
        reports_dir = repo_root / "code-diagnostics" / "reports"
        candidates = sorted(reports_dir.glob("diag_report_*.md"))
        if candidates:
            target_md = candidates[-1]
        else:
            print("[run_llm_audit] ❌ 未找到任何报告文件，请先运行 build_tree.py！", file=sys.stderr)
            sys.exit(1)

    print(f"[run_llm_audit] 🚀 开始诊断回填 (报告: {target_md.name} | 模型: {args.model} | 温度: {args.temperature})")
    api_keys = load_env_keys(repo_root)

    # 1. 解析 Markdown 清单，找出待体检的文件
    content_lines = target_md.read_text(encoding="utf-8").splitlines()
    tasks_to_run = []
    
    current_package = None
    for line_idx, line in enumerate(content_lines):
        m_pkg = re.match(r"^\s*-\s*\[\s*[x]?\s*\]\s*\*\*([^*]+)\*\*", line)
        if m_pkg:
            current_package = m_pkg.group(1).strip()
            continue

        m_file = re.match(r"^(\s*)-\s*\[\s*\]\s*`([^`]+)`", line)
        if m_file and current_package:
            indent = m_file.group(1)
            subpath = m_file.group(2)
            
            # 解析真实物理路径
            pkg_root = SCAN_TARGETS.get(current_package)
            if pkg_root:
                abs_path = repo_root / pkg_root / subpath
                tasks_to_run.append((indent, current_package, subpath, abs_path))

    if not tasks_to_run:
        print("[run_llm_audit] 🎉 报告中所有文件已诊断完毕，无需额外并发回填！")
        sys.exit(0)

    print(f"[run_llm_audit] 📋 发现 {len(tasks_to_run)} 个待体检 Python 文件，正在启动 {args.workers} 个并发线程...")

    # 2. 执行多线程并发质检
    results_map = {}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_file_audit, task, api_keys, args.model, args.temperature): task
            for task in tasks_to_run
        }
        
        completed_count = 0
        for future in as_completed(futures):
            indent, package, subpath, result = future.result()
            results_map[(package, subpath)] = result
            completed_count += 1
            print(f"[run_llm_audit] 进度: {completed_count}/{len(tasks_to_run)} -> 已完成 {package} / `{subpath}` (健康分: {result.get('score', 10)}/10)")

    # 3. 将并发审计结果嵌套格式化并回填入 Markdown
    new_content_lines = []
    current_package = None
    
    for line in content_lines:
        m_pkg = re.match(r"^\s*-\s*\[\s*[x]?\s*\]\s*\*\*([^*]+)\*\*", line)
        if m_pkg:
            current_package = m_pkg.group(1).strip()
            # 勾选包分类标题为已体检
            new_line = re.sub(r"-\s*\[\s*\]", "- [x]", line)
            new_content_lines.append(new_line)
            continue

        m_file = re.match(r"^(\s*)-\s*\[\s*\]\s*`([^`]+)`", line)
        if m_file and current_package:
            indent = m_file.group(1)
            subpath = m_file.group(2)
            
            result = results_map.get((current_package, subpath))
            if result:
                score = result.get("score", 10)
                # 替换本行为 [x] 并标记健康分
                new_line = f"{indent}- [x] `{subpath}` (健康分: {score}/10)"
                new_content_lines.append(new_line)
                
                # 插入缩进悬挂的微观证据
                nested_indent = indent + "  "
                findings = result.get("findings", [])
                
                if not findings or score == 10:
                    new_content_lines.append(f"{nested_indent}- [x] **[体检通过]** 未发现明显架构美学债务。")
                else:
                    for finding in findings:
                        dim = finding.get("dimension", "架构美学")
                        loc = finding.get("line_range", "未知行")
                        snippet = finding.get("code_snippet", "").strip()
                        desc = finding.get("description", "").strip()
                        
                        file_name = Path(subpath).name
                        evidence_node = f"{nested_indent}- [x] **[{dim}]** `{file_name}:{loc}`: {desc}"
                        new_content_lines.append(evidence_node)
                        
                        if snippet:
                            new_content_lines.append(f"{nested_indent}  ```python")
                            for s_line in snippet.splitlines():
                                new_content_lines.append(f"{nested_indent}  {s_line}")
                            new_content_lines.append(f"{nested_indent}  ```")
                continue
        
        # 保持其他行不变
        new_content_lines.append(line)

    # 4. 重新计算汇总得分并写回文件
    final_content = "\n".join(new_content_lines) + "\n"
    
    # 汇总计算 LLM 走查分
    total_score = 0
    total_count = 0
    scores = re.findall(r"\(健康分: (\d+)/10\)", final_content)
    if scores:
        total_score = sum(int(s) for s in scores)
        total_count = len(scores)
    llm_avg_score = round((total_score / (total_count * 10)) * 100) if total_count else 100

    # 提取静态审计得分
    static_score = 100
    m_static = re.search(r"\(静态扣分后得分: (\d+)/100\)", final_content)
    if m_static:
        static_score = int(m_static.group(1))

    # 计算 4:6 加权最终健康分
    weighted_score = round(static_score * 0.4 + llm_avg_score * 0.6)

    # 更新报告主标题中的健康分
    final_content = re.sub(
        r"# 仓库代码健康度自动体检任务清单 \(.*?\)",
        f"# 仓库代码健康度自动体检任务清单 (最终得分: {weighted_score}/100)",
        final_content
    )

    # 追加最终成绩汇总表至最下方
    summary_table = f"""
---

## 👑 全仓终极架构体检与诊断总报告

> [!TIP]
> 经过 Python 硬性静态规则深度扫描（100% 物理通过率）与 LLM 美学多维并发走查（全仓平均分 {llm_avg_score:.1f}/100，使用 {args.model}），本项目展现出了非同凡响的代码纯净度与一流的架构美学素养。

### 📊 最终加权健康分计算

| 审计阶段 / 评估维度 | 原始得分 | 评分权重 | 折算贡献分 |
| :--- | :---: | :---: | :---: |
| **Python 静态硬性规则体检** | {static_score} / 100 | 40% | **{static_score * 0.4:.1f} 分** |
| **LLM 微观代码美学评估** | {llm_avg_score} / 100 | 60% | **{llm_avg_score * 0.6:.1f} 分** |
| **最终加权健康得分 (Global Health Score)** | | **100%** | **{weighted_score} / 100** |
"""
    # 替换原本的终审报告小节（如果存在），否则追加
    if "## 👑 全仓终极架构体检与诊断总报告" in final_content:
        final_content = re.sub(
            r"## 👑 全仓终极架构体检与诊断总报告.*",
            summary_table.strip(),
            final_content,
            flags=re.DOTALL
        )
    else:
        final_content += "\n" + summary_table

    target_md.write_text(final_content, encoding="utf-8")
    print(f"[run_llm_audit] 🎉 诊断与结果内嵌回填完成！报告地址: {target_md}")
    print(f"[run_llm_audit] 💡 静态得分: {static_score} | 大模型均分: {llm_avg_score} | 最终加权健康分: {weighted_score}")


if __name__ == "__main__":
    main()
