---
schema_version: "2.0"
name: text-segmentation
description: >
  ABC paragraph segmentation with Two-Pass validation. Classifies chapter paragraphs as A(setting)/B(event)/C(system).
  Use when analyzing raw chapter text for story deconstruction.
type: graph
context_mapping:
  chapter_content: "{input.chapter_content}"
  chapter_number: "{input.chapter_number}"
  chapter_with_line_numbers: ""
  chapter_lines: ""
  # 由于框架 finish_task(business_data_md=...) 自动将解析结果放入 _finish_task_result["business_data_parsed"]
  # 这里保留向下兼容，可以在后续 logic phase 通过 context 获取
io:
  inputs:
    - name: chapter_content
      type: str
      source: runtime
    - name: chapter_number
      type: int
      source: runtime
  outputs:
    - name: segmentation_result
      type: dict
      target: file
      path: "output/text-segmentation/chapter_{context.chapter_number}_segments.json"
      source: "_finish_task_result.business_data_parsed"
phases:
  - name: setup
    mode: logic
    execute_steps:
      - script.segmenter.prepare_chapter
  - name: segment
    mode: llm
    llm_role: analyst
    max_iterations: 10
    max_nudges: 2
    output_schema: "script.schemas.Segment"
    references:
      - references/segmentation-guide.md
    agent_tools: []
    # validator removed: md_to_json + Pydantic SegmentationResult schema replaces
    # the structural check (frame already validates business_data_md content
    # via finish_task → md_to_json before exiting the phase)
    prompt: |
      ## ⚠️ 退出契约（最高优先级）
      本阶段**唯一**的退出方式是调用 `finish_task`。
      
      调用 finish_task 时**必须**提供以下 3 个字段：
      - reasoning: 完成说明（至少 30 字）。
      - diagnostics_md: 自检诊断 markdown（请简述是否有拿不准的地方）。
      - business_data_md: 完整分段结果，markdown 格式。框架会自动进行 Pydantic 校验并落盘，这是你上交结果的唯一途径。

      ## 核心任务
      你是专业的小说编辑。将章节内容严格切分为 A/B/C 三类段落。遇到不确定的边界，必须先通过 `read_file` 阅读 `references/segmentation-guide.md` 获取完整判例。

      ## 黄金准则
      - **A类-设定**：解释世界如何运作的核心规则、体系、原理；**必须独立分段**。
      - **C类-次元空间**：系统空间、意识空间等非现实事件；**必须独立分段**。
      - **B类-事件**：现实物理世界中的行动、场景、情绪；同一时空的连续动作应**合并**。

      ## 执行步骤
      1. 提取当前任务的章节文本。
      2. 整体判断 A/C 类独立区块位置。如有疑问，阅读 `references/segmentation-guide.md`。
      3. 立即调用 `finish_task`，将完整的 Markdown 格式分段结果填入 `business_data_md`。
    user_prompt_template: |
      请按系统提示的执行步骤，对以下带行号章节进行分段。如需 A/B/C 详细判别规则，请 read_file references/segmentation-guide.md。

      ## 当前章节
      ```
      {chapter_with_line_numbers}
      ```

      **`business_data_md` 输出格式范例（必须严格遵守）**：
      ## segments
      - index: 1
      - type: B
      - start_line: 1
      - end_line: 5
      - content: 收音机播报上沪沦陷消息
      - confidence: 0.95

      ## segments
      - index: 2
      - type: A
      - start_line: 6
      - end_line: 9
      - content: 诡异爆发背景设定
      - confidence: 0.85
  - name: review
    mode: llm
    llm_role: analyst
    context_access: ["working_memory"]
    max_iterations: 10
    max_nudges: 2
    max_retries: 2
    retry_target: segment
    output_schema: "script.schemas.Segment"
    references:
      - references/segmentation-guide.md
    agent_tools:
      - script.segmenter.log_ambiguous_segments
    # validator removed: md_to_json + Pydantic schema is the structural gate;
    # business_data_md from finish_task drives the segment list, no longer
    # populated via parse_segmentation_output → ctx["segments"]
    prompt: |
      ## ⚠️ 退出契约（最高优先级）
      本阶段**唯一**的退出方式是调用 `finish_task`。

      调用 finish_task 时**必须**提供以下 3 个字段：
      - reasoning: 完成说明（至少 30 字，说明是否做了修正）。
      - diagnostics_md: 自检诊断 markdown（列出你发现的边界问题）。
      - business_data_md: 最终版的完整分段结果（Markdown 格式），框架会自动校验落盘。

      - 如果扫描后分段结果**整体合理**（仅 1-3 处小修正或无需修正），**立即**将最终结果填入 `business_data_md` 并调用 `finish_task`。
      - 如果存在明显错误，将修正后的结果填入 `business_data_md` 并调用 `finish_task`，**不要**做第二轮复核。

      ## 核心任务
      你是专业的小说编辑，负责**快速扫描**并纠正 Pass 1 分段结果的**致命边界错误**。不要试图做到完美，只抓关键。遇到判别分歧，必须先 `read_file` 查阅 `references/segmentation-guide.md`。

      ## 执行步骤
      1. 整体扫描 Pass 1 结果，关注：C类边界是否干净、A/B类是否混合、B类时空是否连续。
      2. 仅对**最关键的错误**（typically 1-3 处）在脑海中编写修正。
      3. 若 confidence < 0.7，调用 `log_ambiguous_segments` 记录但不阻断流程。
      4. 立即调用 `finish_task`，在 `business_data_md` 中提交完整（包括未修改的和修正后的）分段列表。
    user_prompt_template: |
      请按系统提示的执行步骤检查 Pass 1 结果。如需详细 A/B/C 鉴别清单，请 read_file references/segmentation-guide.md。

      ## 原章节内容
      ```
      {chapter_content}
      ```

      ## Pass 1 分段结果
      ```
      {raw_segmentation}
      ```

      **`business_data_md` 输出格式范例（需输出最终的全集）**：
      ## segments
      - index: 1
      - type: B
      - start_line: 1
      - end_line: 5
      - content: 收音机播报上沪沦陷消息
      - confidence: 0.95
---
