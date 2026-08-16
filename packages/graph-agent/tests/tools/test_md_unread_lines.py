"""parse_md 说得出它没读懂哪几行。

缺陷实测(2026-08-16,`story-deconstruction-v3-lab` 用 DeepSeek V4 Flash 真跑
`segmentation` 相位,run 09f67b86-eb65-4c97-ba60-deb05e58ce22):模型把
`list[dict]` 字段写成嵌套 bullet ——

    - parsed_segments:
      - index: 1
        type: B
      - index: 2

`parse_md` 把其中一半的行 `logger.warning(... skipping ...)` 掉,返回一个
看起来正常的 `ParsedBlock`,`parsed_segments` 只剩 `['index: 1']`。日志进不了
模型的上下文,所以模型收到的下一条反馈是相位校验器的
"No segments produced. Re-analyze the chapter text." —— 一条指向不存在问题的
建议,模型照着它重新分析、重新写同样的格式,烧完预算然后死掉。

本文件钉住的规则:**丢掉一行就要说出是哪一行**。判据不是"猜这行想表达什么",
而是"这行有没有宣告结构":带 bullet 记号的行、或以 `名字:` 开头的行,是这套
格式书写数据的两种记号;散文、表格、HTML 注释、小标题什么也没宣告,解析器
从未承诺读它们,点它们的名只会制造噪声。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from graph_agent.tools.md_to_json import parse_md


class Segmented(BaseModel):
    parsed_segments: list[dict[str, Any]]
    segments_summary: str


class Flat(BaseModel):
    title: str
    score: int
    tags: list[str]


class DialogueLine(BaseModel):
    speaker: str
    text: str


class Scene(BaseModel):
    beats: list[str]
    dialogue: list[DialogueLine]


# ── (a) 复现输入:没读懂的行必须被指名道姓 ──────────────────────────────────

NESTED_BULLET_MD = """## item-1
- parsed_segments:
  - index: 1
    type: B
    start_line: 1
  - index: 2
    type: B
    start_line: 6
- segments_summary: 两段
"""


def test_nested_bullet_object_lines_are_named_not_silently_dropped() -> None:
    (block,) = parse_md(NESTED_BULLET_MD, Segmented)

    unread_text = [entry.text for entry in block.meta.unread]
    assert unread_text == [
        "    type: B",
        "    start_line: 1",
        "  - index: 2",
        "    type: B",
        "    start_line: 6",
    ]


def test_each_unread_line_carries_its_line_number_in_the_whole_markdown() -> None:
    (block,) = parse_md(NESTED_BULLET_MD, Segmented)

    # 1-based,数的是整份 business_data_md,模型可以直接照着行号定位。
    assert [entry.line_number for entry in block.meta.unread] == [4, 5, 6, 7, 8]


def test_each_unread_line_says_why_it_could_not_be_read() -> None:
    (block,) = parse_md(NESTED_BULLET_MD, Segmented)

    reasons = {entry.reason for entry in block.meta.unread}
    assert reasons, "没有理由的『我没读懂』等于没说"
    assert all(reason.strip() for reason in reasons)


# ── (b) 合法输入零回归:读懂了就不许报『没读懂』 ─────────────────────────────


def test_flat_bullets_report_nothing_unread() -> None:
    (block,) = parse_md(
        "## item-1\n- title: Scene plan\n- score: 3\n- tags: a, b\n",
        Flat,
    )

    assert block.meta.unread == ()
    assert block.data == {"title": "Scene plan", "score": 3, "tags": ["a", "b"]}


def test_plain_indented_children_of_a_list_field_report_nothing_unread() -> None:
    (block,) = parse_md(
        "## item-1\n- beats:\n  - first\n  - second\n- dialogue:\n  - @speaker: a\n  - @text: b\n",
        Scene,
    )

    assert block.meta.unread == ()
    assert block.data == {
        "beats": ["first", "second"],
        "dialogue": [{"speaker": "a", "text": "b"}],
    }


def test_a_json_fenced_block_reports_nothing_unread() -> None:
    (block,) = parse_md(
        '## item-1\n```json\n{"title": "t", "score": 1, "tags": ["a"]}\n```\n',
        Flat,
    )

    assert block.meta.unread == ()
    assert block.data == {"title": "t", "score": 1, "tags": ["a"]}


# ── (c) 本来就该忽略的行不算『没读懂』,不制造噪声 ────────────────────────────


def test_blank_lines_prose_tables_comments_and_subheadings_are_not_unread() -> None:
    md = """## item-1

以下是本章的分段结果

<!-- 内部备注，不属于输出 -->
### 说明
| 字段 | 含义 |
| --- | --- |
| title | 标题 |
---
- title: Scene plan
- score: 3
- tags: a
"""

    (block,) = parse_md(md, Flat)

    assert block.meta.unread == ()
    assert block.data == {"title": "Scene plan", "score": 3, "tags": ["a"]}


# ── 其余丢弃点同样开口说话 ──────────────────────────────────────────────────


def test_an_orphan_indented_bullet_is_named() -> None:
    (block,) = parse_md(
        "## item-1\n  - orphan\n- title: kept\n- score: 1\n- tags: a\n",
        Flat,
    )

    assert [entry.text for entry in block.meta.unread] == ["  - orphan"]


def test_a_non_at_key_child_inside_an_at_key_field_is_named() -> None:
    (block,) = parse_md(
        "## item-1\n- beats:\n  - first\n- dialogue:\n  - @speaker: a\n  - 旁白笑了\n  - @text: b\n",
        Scene,
    )

    assert [entry.text for entry in block.meta.unread] == ["  - 旁白笑了"]
