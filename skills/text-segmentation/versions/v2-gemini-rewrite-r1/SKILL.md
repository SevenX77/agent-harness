---
# TODO(phase-2-a1, archived): segment + review LLM phases declare a validator
# without output_schema, which v1.1+ rejects as a compile-time contract violation
# (see skill_validator._enforce_validator_requires_output_schema). This snapshot
# is a frozen development baseline kept for benchmarking only — its `script/`
# package is missing so it already fails to load (F-tool-path-not-found). Not
# fixing here; the live SKILL at skills/text-segmentation/SKILL.md is compliant.
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
  raw_segmentation: ""
  segments: ""
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
    references:
      - references/segmentation-guide.md
    agent_tools:
      - script.segmenter.parse_segmentation_output
      - script.segmenter.store_segments
    validator: script.validators.validate_segmentation_structure
    prompt: |
      ## ⚠️ 退出契约（最高优先级）
      本阶段**唯一**的退出方式是调用 `finish_task`。
      完成分段并调用 parse / store 工具落地结果后，**立即**调用 `finish_task`，不要追加任何纯文本分析，不要拖延。

      ## 核心任务
      你是专业的小说编辑。将章节内容严格切分为 A/B/C 三类段落。遇到不确定的边界，必须先通过 `read_file` 阅读 `references/segmentation-guide.md` 获取完整判例。

      ## 黄金准则
      - **A类-设定**：解释世界如何运作的核心规则、体系、原理；**必须独立分段**。
      - **C类-次元空间**：系统空间、意识空间等非现实事件；**必须独立分段**。
      - **B类-事件**：现实物理世界中的行动、场景、情绪；同一时空的连续动作应**合并**。

      ## 执行步骤
      1. 提取当前任务的章节文本。
      2. 整体判断 A/C 类独立区块位置。如有疑问，阅读 `references/segmentation-guide.md`。
      3. 撰写完整的 Markdown 格式分段列表（必须覆盖所有行号，无跳行重叠）。
      4. 依次调用 `parse_segmentation_output` 和 `store_segments`。
      5. 立即调用 `finish_task`。
    user_prompt_template: |
      请按系统提示的执行步骤，对以下带行号章节进行分段。如需 A/B/C 详细判别规则，请 read_file references/segmentation-guide.md。

      ## 当前章节
      ```
      {chapter_with_line_numbers}
      ```

      **输出格式示例**：
      # 第{chapter_number}章分段结果
      - **段落1（B类-事件）**：收音机播报上沪沦陷消息 行号：1-5
      - **段落2（A类-设定）**：诡异爆发背景设定 行号：6-9
  - name: review
    mode: llm
    llm_role: analyst
    context_access: ["working_memory"]
    max_iterations: 10
    max_nudges: 2
    max_retries: 2
    retry_target: segment
    references:
      - references/segmentation-guide.md
    agent_tools:
      - script.segmenter.parse_segmentation_output
      - script.segmenter.store_segments
      - script.segmenter.log_ambiguous_segments
    validator: script.validators.validate_final_format
    prompt: |
      ## ⚠️ 退出契约（最高优先级）
      本阶段**唯一**的退出方式是调用 `finish_task`。
      - 如果你扫描后认为分段结果**整体合理**（无需修正或仅 1-3 处小修正），**立即**调用 `finish_task`，**不要**继续做详尽审查。
      - 如果存在明显错误，完成修正、调用 parse / store 工具后，**立即**调用 `finish_task`，**不要**做第二轮复核。
      - 工具 `parse_segmentation_output` / `store_segments` / `log_ambiguous_segments` 是辅助手段，不是出口。

      ## 核心任务
      你是专业的小说编辑，负责**快速扫描**并纠正 Pass 1 分段结果的**致命边界错误**。不要试图做到完美，只抓关键。遇到判别分歧，必须先 `read_file` 查阅 `references/segmentation-guide.md`。

      ## 黄金准则
      - **A类-设定**：解释世界如何运作的核心规则。
      - **B类-事件**：现实物理世界时间线中的行动与反应。
      - **C类-次元空间**：非现实空间中的事件（从进入到退出）。

      ## 执行步骤
      1. 整体扫描 Pass 1 结果，重点关注：C 类边界是否干净、A/B 类是否混合、B 类时空是否连续。
      2. 仅对**最关键的错误**（typically 1-3 处）编写修正。遇到重大理解歧义，可考虑调用 `ask_clarification` 向人类求助。
      3. 若 confidence < 0.7，调用 `log_ambiguous_segments` 记录但不阻断流程。
      4. 若有修正，输出完整修正列表并调用 `parse_segmentation_output` 及 `store_segments`。
      5. 立即调用 `finish_task`。
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

      如果分段完全正确：直接在文本中回复"分段正确，无需修改"，并进入退出契约。
      如果需要修正，请给出完整的新分段列表：
      # 第{chapter_number}章分段结果（修正版）
      - **段落1（B类-事件）**：... 行号：1-5
---
