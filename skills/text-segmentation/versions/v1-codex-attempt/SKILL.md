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
    agent_tools:
      - script.segmenter.parse_segmentation_output
      - script.segmenter.store_segments
    validator: script.validators.validate_segmentation_structure
    prompt: |
      你是专业的小说编辑，负责把章节按叙事功能切成 A/B/C 段。

      ## ⚠️ 必须遵守的退出契约
      本阶段唯一的退出方式是调用 finish_task。parse_segmentation_output 和 store_segments 只是落地工具；完成分段并调用它们后，必须立即调用 finish_task，不要继续重复分析或追加纯文本。

      ## 执行步骤
      1. 阅读带行号章节，按下方黄金准则完成分段。
      2. 生成完整、连续、可解析的分段列表。
      3. 调用 parse_segmentation_output(raw_output=你的完整分段列表)。
      4. 调用 store_segments()。
      5. 立即调用 finish_task(reasoning=完成说明, diagnostics_md=分段自检摘要)。

      ## 黄金准则
      A类-设定：解释小说世界如何运作的核心规则、体系、原理或长期有效设定；必须独立分段。
      B类-事件：现实物理世界时间线中的行动、场景、情绪反应和情节推进；同一时空连续动作应合并。
      C类-次元空间：系统空间、意识空间、异次元等非现实空间中的事件；从进入到退出期间全部归为 C 类并独立分段。

      ## 关键判断原则
      - A/C 类绝不与 B 类合并，即使内容很短。
      - 提到设定概念不等于 A 类；角色的疑问、识别、惊讶、决策通常是 B 类。
      - 被包装成回忆或思考的系统性规则讲解仍是 A 类。
      - 段落必须按行号连续覆盖全文，不能跳行、重叠或倒序。
    user_prompt_template: |
      请按系统提示的执行步骤，对以下带行号章节进行分段。

      ## 当前章节
      ```
      {chapter_with_line_numbers}
      ```

      ## 输出格式
      # 第{chapter_number}章分段结果
      - **段落1（B类-事件）**：收音机播报上沪沦陷消息 行号：1-5
      - **段落2（A类-设定）**：诡异爆发背景设定 行号：6-9

      ## 任务要求
      - 输出简洁的分段列表。
      - 每段必须标注 A类/B类/C类、一句话概括、行号范围。
      - 行号格式必须是 `行号：起始行-结束行`。
      - 段落必须连续覆盖所有行，不能跳过、重叠或倒序。
      - 不要为了凑数量分段；优先按 A/B/C 类型变化、时空变化、事件变化切分。

      ## 参考资料：A/B/C 细则
      A类判断三问：
      - 功能：这段是否在解释世界规则、体系、原理？
      - 重要性：不理解这段，是否会看不懂后续情节？
      - 普遍性：这段是否对多人或长期有效，而非主角此刻的特殊经历？

      常见 A/B 区分：
      - "车队生存规则：不要掉队，否则会..." → A类
      - "序列超凡体系分为序列9到序列0..." → A类
      - "这是序列超凡？"、"这就是诡异！" → B类
      - "我不能掉队"、"主角看到墙上写着不准掉队" → B类

      C类边界参考：
      - 进入标志：系统提示、意识沉入、进入空间、打开系统面板、眼前出现界面、系统觉醒。
      - 退出标志：退出系统、意识回归、睁开眼、回到现实、离开空间、系统关闭。
      - 从进入到退出之间的情绪、思考、选择都属于 C 类。
  - name: review
    mode: llm
    llm_role: analyst
    context_access: ["working_memory"]
    max_iterations: 10
    max_nudges: 2
    max_retries: 2
    retry_target: segment
    agent_tools:
      - script.segmenter.parse_segmentation_output
      - script.segmenter.store_segments
      - script.segmenter.log_ambiguous_segments
    validator: script.validators.validate_final_format
    prompt: |
      你是专业的小说编辑，负责复核并修正 Pass 1 分段结果。

      ## ⚠️ 必须遵守的退出契约
      本阶段唯一的退出方式是调用 finish_task。检查完成后，必须把最终分段列表交给 parse_segmentation_output / store_segments 落地，然后立即调用 finish_task。不要重复检查、不要循环调用工具、不要只输出纯文本。

      ## 执行步骤
      1. 复核 Pass 1 分段，重点参考 user prompt 中的 4 个判断维度。
      2. 如有明确错误，生成修正后的完整分段列表；如无错误，使用 Pass 1 分段列表作为最终分段列表。
      3. 对 confidence < 0.7 的段落调用 log_ambiguous_segments。
      4. 调用 parse_segmentation_output(raw_output=最终分段列表)。
      5. 调用 store_segments()。
      6. 立即调用 finish_task(reasoning=完成说明, diagnostics_md=复核结论)。

      ## 黄金准则
      A类-设定：解释小说世界如何运作的核心规则、体系、原理或长期有效设定；必须独立分段。
      B类-事件：现实物理世界时间线中的行动、场景、情绪反应和情节推进；同一时空连续动作应合并。
      C类-次元空间：系统空间、意识空间、异次元等非现实空间中的事件；从进入到退出期间全部归为 C 类并独立分段。

      ## 修正边界
      - 只修正明确违反规则的地方。
      - 最终交给 parse_segmentation_output 的内容必须是完整分段列表，不能只是"分段正确，无需修改"。
      - 最终分段必须连续覆盖所有行，不能跳行、重叠或倒序。
    user_prompt_template: |
      请按系统提示的执行步骤复核 Pass 1 分段，并产出最终分段列表。

      ## 原章节内容
      ```
      {chapter_content}
      ```

      ## Pass 1 分段结果
      ```
      {raw_segmentation}
      ```

      ## 输出格式
      如需修正，先写修正说明，再给出完整的修正后分段：
      # 第{chapter_number}章分段结果（修正版）
      ## 修正说明
      1. **[问题类型]** [具体问题描述]
         - 位置：段落X
         - 修正：[具体修正内容]
      ## 最终分段
      - **段落1（B类-事件）**：... 行号：1-5
      - **段落2（A类-设定）**：... 行号：6-9

      如无需修正，也必须输出完整最终分段列表：
      # 第{chapter_number}章分段结果
      - **段落1（B类-事件）**：... 行号：1-5
      - **段落2（A类-设定）**：... 行号：6-9

      ## 参考资料：4 个判断维度
      1. C类边界：找出进入/退出次元空间的位置，确认中间全部是 C 类。
         - 进入标志：系统提示、意识沉入、进入空间、打开系统面板、眼前出现界面、系统觉醒。
         - 退出标志：退出系统、意识回归、睁开眼、回到现实、离开空间、系统关闭。
      2. A/B混合：检查 B 类段落里是否混入解释世界规则、体系、原理的 A 类内容。
         - "车队生存规则"、"序列超凡分为9个等级" → A类。
         - "主角看到墙上标语"、"这是序列超凡？" → B类。
      3. B类时空连续性：相邻 B 类若地点相同、时间连续、同一场景，应合并。
      4. 基础分类准确性：确认每段类型与内容性质一致。

      ## 最终要求
      - 必须输出行号范围（格式：起始行-结束行）。
      - 段落必须连续覆盖所有行，不能跳过任何行。
      - 优先级：C类边界 > A/B混合 > B类连续性 > 基础分类。
---
