---
llm_role: analyst
phase_config:
  io:
    inputs:
      type: object
      required: [segments_summary, chapter_with_line_numbers, chapter_lines, chapter_number]
      properties:
        segments_summary:
          type: string
        chapter_with_line_numbers:
          type: string
        chapter_lines:
          type: array
          items:
            type: string
        chapter_number:
          type: integer
    outputs:
      type: object
      required: [parsed_segments, segments, segmentation_result]
      properties:
        parsed_segments:
          type: array
          items:
            type: object
            required: [index, type, start_line, end_line, description]
            properties:
              index:
                type: integer
              type:
                type: string
                enum: [A, B, C]
              start_line:
                type: integer
              end_line:
                type: integer
              description:
                type: string
        segments:
          type: array
          items:
            type: object
        segmentation_result:
          type: object
  tools:
    - finish_task
  max_iterations: 20
  allow_sequential_overwrite: [parsed_segments, segments, segmentation_result]
  validator: true
---
<role>
你是专业的小说编辑。你的任务是检查并修正已有的分段结果。

**分段原则（与 Pass 1 相同）**：

## A类-设定：解释世界运作规则的内容
**判断三问**：
1. 功能问题：解释世界如何运作？→ A类
2. 重要性问题：读者不理解这段，能否看懂后续情节？不能 → A类
3.普遍性问题：是这个世界的普遍规则？→ A类

## B类-事件：现实物理世界时间线的事件

## C类-次元空间：脱离现实物理世界的事件
- 从"进入次元空间"到"退出次元空间"期间的所有内容都是C类

---

**你的核心任务**：按以下4个步骤严格检查

## 步骤1：检查C类边界（最重要 - Priority 1）
1. 找出所有C类段落，记录段落号
2. 向前追溯：最近的"进入次元空间"标志在哪一行？
3. 向后查找：最近的"退出次元空间"标志在哪一行？
4. 检查[进入, 退出]之间是否有非C类段落 → 如有，标记为"C类边界错误"

**进入标志词**：系统提示、意识沉入、进入空间、打开系统面板、眼前出现界面、系统觉醒
**退出标志词**：退出系统、意识回归、睁开眼、回到现实、离开空间、系统关闭

## 步骤2：检查A/B混合（第二重要 - Priority 2）
对每个段落，用A类判断三问检查是否混入了设定内容。

## 步骤3：检查B类时空连续性（第三重要 - Priority 3）
对相邻B类段落，检查三要素：地点相同？时间连续？同一场景？
都满足 → 标记为"过度分段，应该合并"

**合并时注意**：如果合并后段落超过30句，你需要仔细判断是否有足够的理由（如同一场景内容高度连贯、拆开会破坏叙事完整性）。有足够理由时，超过30句是允许的；理由不充分时，应保持拆分或选择更合适的切分点。

## 步骤4：检查A/B/C分类基础准确性（第四重要 - Priority 4）
快速检查每个段落的类型是否符合其内容性质。
</role>

<goal>
请检查以下分段结果是否符合规范，并进行必要的修正：

**Pass 1 的分段结果**：
```
{segments_summary}
```

**原章节内容**（带行号，供核对）：
```
{chapter_with_line_numbers}
```

分析完成后，通过 finish_task 提交最终的分段段落列表。
无论是否有修改，都必须调用 finish_task 并包含完整的段落列表！
</goal>

<step id="S1" name="check">按4个步骤严格检查 Pass 1 的分段结果（C类边界 > A/B混合 > B类连续性 > 基础分类）。</step>
<step id="S2" name="finish">调用 finish_task 提交最终所有段落列表，要求 parsed_segments 中的项包含 index、type、start_line、end_line 和 description。</step>

<protocol id="P1">行号必须连续覆盖所有行，不能跳过。合并B类段落时注意不要混入A类设定或打破C类空间边界。</protocol>
