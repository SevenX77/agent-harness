# 决议:编译诊断必须指名它真正所在的那个文件

- 日期:2026-08-15
- 范围:`packages/graph-agent/src/graph_agent/core/loader.py`
- 触发:`story-deconstruction-v3-lab` 缺陷排查——子图里的错误被报在根图上

## 决策

`CompileIssue.source_path` / `ErrorPayload.source_path` 一律**相对于本次编译的
skill 根目录**渲染,渲染动作由 `SkillLoader.compile_skill` 这一个边界完成;深处的
诊断函数只携带完整路径,不再各自猜测。

## 问题:那不是"路径写短了",是"指错了文件"

旧实现 `_payload_source_path` 不做相对化,它做的是**截断**:

```python
if path.name == "GRAPH.md":
    return "GRAPH.md"
for anchor in ("phases", "io"):
    if anchor in parts:
        index = len(parts) - 1 - parts[::-1].index(anchor)
        return Path(*parts[index:]).as_posix()
```

对只有一层的 skill,截出来的串碰巧等于相对路径,所以问题一直没暴露。对带嵌套子图的
skill,它把不同文件压成同一个名字:

在 lab skill 上实测(2026-08-15):41 个 markdown 文件压成 **32 个不同的
`source_path` 串**,其中**只有 5 个**能在根目录下找到同名文件;**8 个不同的
`GRAPH.md` 全部渲染成 `"GRAPH.md"`**;`phases/review/SKILL.md` 同时指两个真实文件
(`subgraph/text-segmentation/phases/review/SKILL.md` 与
`subgraph/event-timeline/subgraph/event-extraction/phases/review/SKILL.md`)。

端到端后果(修复前实测):把 `subgraph/story-analysis/GRAPH.md:19` 弄坏,引擎报

```
[F-v3-graph-schema-unknown-field]   source_path='GRAPH.md'   line=19
```

Studio 的 Compile 抽屉照着这行显示 `GRAPH.md:19`,Monaco marker 落到**根图的第 19
行**——而那一行完全正常。作者按提示去看根图,看到的是健康的内容。这不是信息不足,
是信息错误。

还有一处安静的丢失:`field-compile-errors.ts` 的 `lintErrorsForFile` 用
`candidate === target || candidate.endsWith("/" + target)` 给打开的文件挂行内
marker。打开一个嵌套子图的相位文件时,`target` 是
`subgraph/text-segmentation/phases/segment/SKILL.md`,而引擎给的 `candidate` 是
`phases/segment/SKILL.md`——两条都不成立,**这个文件从来就没有过行内 marker**。

## 为什么修在边界,而不是修那个截断函数

相对路径只有相对于一个**被说明的根**才有意义,而深处那些抛诊断的函数不知道调用方在
编译哪个根:同一个子图相位文件,在子图自己编译时会被读到,在父图编译时也会被读到,
两次的正确答案不同。让每个函数各自猜,就是这次缺陷的成因。

所以责任归给唯一知道根的那个人:`SkillLoader.compile_skill`。内部一律携带完整路径,
出口处统一改写一次。嵌套情形自然成立——子图编译在自己的出口改成子图相对,父图的
`_validate_subgraph_io_contracts` 把它接回绝对路径,父图出口再改成父图相对。

这条取舍照抄编译器诊断的通行做法:GCC/Clang 的 diagnostic 记录的是**真实文件**并在
输出时按当前工作目录渲染,不会因为头文件被别处包含就把错误算到包含它的那个文件头上。
本次拒绝的部分是它们的 include-stack 展示(`In file included from ...` 的调用链),
因为 Studio 现在的呈现面只有一个 `source_path` 字段,加调用链需要先改前端契约。

## 明确保留的行为

- 根相位的诊断路径**一字不变**,仍是 `phases/<id>/<file>.md`。引擎 1495 条既有测试
  全绿,没有一条需要改——这正是"只改错的那一类"的证据。
- 落在根目录**之外**的文件(从别处链接进来的子图)没有相对形式,保持绝对路径,而不是
  硬掰成一个错的相对路径。

## 验收判据

`packages/graph-agent/tests/core/test_compile_issue_source_path_is_root_relative.py`:

1. 子图的 `GRAPH.md` 有错 → 这条错的 `source_path` 是 `subgraph/first/GRAPH.md`,
   且**不是**根的 `GRAPH.md`(根图自己那条级联诊断照常存在,断言按 rule_id + 路径配对);
2. 两个子图各有一个同名相位 `review` 都有错 → 两条诊断的路径互不相同;
3. 根相位有错 → 路径仍是 `phases/alpha/SUBGRAPH.md`(常见情形不许移动)。

真实 skill 复验:同一处子图缺陷,修复后 5 条诊断的 `source_path` **全部**能在根目录
下找到对应文件(修复前只有 5 分之 1 能,且那一条指的是错的文件)。

## 已知未处理(另立)

`field-compile-errors.ts` 的 `PHASE_FILE_RE = /(?:^|\/)phases\/([A-Za-z0-9_-]+)\//`
在路径任意位置匹配,所以子图里的 `review` 相位仍会被归给根图上同名的节点。本次不改:
lab skill 的根相位名与子图相位名没有重合,**没有实测到误挂**;而且这个行为在本次改动
前后完全一致(旧的截断串同样匹配)。它现在才**可以**被修,是因为引擎终于给出了足以
区分的信息。
