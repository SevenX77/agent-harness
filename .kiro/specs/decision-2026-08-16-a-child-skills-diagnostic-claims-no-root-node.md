# 决议:子 skill 里的诊断不认领根图上的任何节点

- 日期:2026-08-16
- 范围:`apps/studio/frontend/src/components/studio/`
  (`diagnostic-paths.ts` 新增 · `field-compile-errors.ts` · `node-compile-errors.ts`)
- 触发:`.kiro/specs/decision-2026-08-15-compile-diagnostics-name-the-file-they-are-in.md:85`
  「已知未处理(另立)」

## 决策

诊断的文件路径是**相对本次编译根**的答案,因此只能从根往外读:

1. 一条诊断属于哪个根图相位,由它的路径**以 `phases/<id>/` 开头**决定;
   `subgraph/<child>/phases/<id>/…` 属于子 skill,不认领任何根节点。
2. 诊断路径与编辑器打开文件的比对是**整串相等**,不是后缀包含。
3. 一条诊断的 `field_path` 是**文件内部**的定位符,只有当这条诊断本身位于根图
   (`GRAPH.md`)或根本没有文件时,才允许用它去认领根节点。

这三条是同一条规则的三个面,所以它们只有一份定义:新模块
`apps/studio/frontend/src/components/studio/diagnostic-paths.ts`。原先
`field-compile-errors.ts` 与 `node-compile-errors.ts` 各存了一份**逐字相同**的
`PHASE_FILE_RE` 与 `normalizePath`(前者的注释原话:"Mirrors the node channel's
phase-path char class"),这次缺陷正是两份拷贝同时错,所以合并成一份,而不是把同一个
正则改两遍。

## 问题:路径读法搞错了方向,于是指到了别人家的节点

`PHASE_FILE_RE = /(?:^|\/)phases\/([A-Za-z0-9_-]+)\//` 在路径的**任意位置**匹配。
PR #830(2026-08-15 合并)把 `CompileIssue.source_path` 从"锚点截断串"改成真正的根
相对路径之后,嵌套相位第一次以 `subgraph/<child>/phases/<id>/<file>.md` 的完整形状
到达前端——而这条正则照样在中间匹配上 `phases/review/`,得出相位 id `review`,把子
skill 的诊断挂到根图上同名的 `review` 节点。

用 #830 的引擎 fixture
(`packages/graph-agent/tests/core/test_compile_issue_source_path_is_root_relative.py`
的 `_skill()`:根图两个相位 `alpha`/`beta`,各指向子 skill `subgraph/first`、
`subgraph/second`,每个子 skill 有一个相位 `review`)实测两次(2026-08-16):

**实测 A** — 往 `subgraph/first/phases/review/SKILL.md` 的 frontmatter 加一个未知字段:

```
[F-v3-agent-schema-unknown-field] | 'subgraph/first/phases/review/SKILL.md' | 'no_such_field'
[F-v3-agent-subgraph-invalid]     | 'phases/alpha/SUBGRAPH.md'              | 'path'
[F-v3-graph-dataflow-source-missing] | 'phases/alpha/SUBGRAPH.md'           | 'alpha.io'
[F-v3-graph-dataflow-source-missing] | 'phases/beta/SUBGRAPH.md'            | 'beta.io'
[F-v3-graph-dataflow-source-missing] | 'GRAPH.md'                           | 'io.outputs.required.answer'
```

**实测 B** — 让 `subgraph/first/GRAPH.md` 声明一个它的相位不产出的输出:

```
[F-v3-graph-io-schema-invalid] | 'subgraph/first/GRAPH.md' | 'io.outputs.required'
[F-v3-agent-subgraph-invalid]  | 'phases/alpha/SUBGRAPH.md' | 'path'
（其余同上）
```

两条真实的误挂:

- A 的第一行被读成根节点 `review`(该 fixture 的根图根本没有 `review` 节点;在
  真实 skill 上,根图恰好有同名相位时就是挂到**另一个 skill 的相位**上);
- B 的第一行 `field_path='io.outputs.required'` 说的是**子图**的输出块,却被
  `boundaryNodeIdFromField` 读成根图的全局 Output 节点,在根画布的 Output 上亮红。

## 为什么规则落在"路径读法"这一层,而不是给子图加特判

路径是"从某个被说明的根数出来的第几层第几个文件"这一问题的答案。#830 已经把
"根是谁"这件事钉死在引擎的编译出口(`SkillLoader.compile_skill`),前端拿到的每条
路径都带着同一个隐含前提:**从根开始数**。既然如此,读它的唯一正确方式就是从第一
个 segment 开始读;在中间任取一段来匹配,问的是另一个问题,自然得到另一个文件的
答案。所以修的是"怎么读一条路径",而不是"遇到 `subgraph/` 就跳过"——后者会把子
skill 的目录名写死成关键字,而子 skill 放在哪个目录由作者的 `SUBGRAPH.md`
`path:` 字段决定,可以叫任何名字。

同理,`field_path` 是文件**内部**的定位符,它的含义依赖"这是哪个文件"。文件已经
说了"我在子 skill 里",就不能再拿文件内部的定位符去认领根图的节点。

参考对象:这一条照抄 C 预处理器/编译器诊断对 `#include` 的处理——诊断记的是**真实
文件**,不会因为某个头文件被别处包含就把错误算到包含它的那个文件的行号上;GCC/Clang
用 `In file included from …` 的调用链把上下文补回来。本次**借**的是"位置属于真实
文件、不允许按片段重新归属"这一半,**拒绝**的是调用链呈现:Studio 现在的诊断契约
只有一个 `source_path` 字段,加调用链要先改前后端契约(#830 决议里已经记下同样的
取舍)。

## 关键设计决定

### D1. 子 skill 的诊断在画布上不挂任何节点,只留在 Compile 抽屉

**设计源未规定。** 查过
`docs/studio/mvp1/02_capabilities/compile-lint/mvp1-alignment.md`(全文无
"subgraph"/"子图")、`docs/studio/mvp1/01_workflows/03_compile.md`、
`docs/studio/mvp1/03_regions/properties/mvp1-alignment.md`(只有 SUBGRAPH 节点自身
frontmatter 字段的规定,与诊断归属无关),没有关于"诊断来自子图时怎么呈现"的条款。

**本次按"不挂节点、只进抽屉与编辑器"处理,理由有三:**

1. **挂不上去,不是不想挂。** 承载子 skill 的根相位叫 `alpha`,子 skill 的目录叫
   `first`(见上文 fixture),路径里没有任何东西能说出 `alpha` 这个名字。要把子图
   诊断挂到承载它的那个 SUBGRAPH 节点上,得由引擎在诊断里带上"我是被哪个根相位
   引进来的",那是引擎契约的扩展,不是前端能推出来的——凭路径猜就是重犯这次的错。
2. **画布不会因此变哑。** 实测 A/B 都显示,子 skill 一坏,引擎**自己**就在根节点上
   报了 `[F-v3-agent-subgraph-invalid] Subgraph compile failed: … at path
   subgraph/first`,`source_path='phases/alpha/SUBGRAPH.md'` → 正好落在 `alpha`
   节点。作者在根画布上照样看到"这个子图节点有问题",而且这条消息里直接写着
   `subgraph/first`,指向真正的位置。
3. **完整清单没有丢。** Compile 抽屉拿的是未按节点分组的全量列表
   (`Workspace.tsx:2938` `<CompileErrorDrawer errors={currentCompileErrors} …>`),
   子图诊断带着完整路径 `subgraph/first/phases/review/SKILL.md` 原样呈现;编辑器
   打开那个文件时,`lintErrorsForFile` 现在也能精确匹配到它(#830 之前这个文件从来
   没有过行内 marker,见 #830 决议第 45-49 行)。所以这条决定不减少任何信息,只是
   不再把信息放到错误的地方。

**未做、留给后续的**:把子图诊断聚合到承载它的 SUBGRAPH 节点(需要引擎先在诊断里
说明引入它的根相位),以及下钻进子图后是否用子图自己的编译结果渲染子画布徽章。这两
项都是新方向,需要先写进 MVP1 设计源。

### D2. 删掉 `lintErrorsForFile` 的"绝对沙箱路径泄漏"容忍

原实现 `candidate === target || candidate.endsWith("/" + target)`,注释说后半段是为了
兜住"realtime lint 的临时沙箱前缀泄漏成绝对路径"。**核对后确认这条泄漏已经不可能
发生**,证据三条(均为当前 `main` 的代码):

1. `apps/studio/backend/app/services/skills.py:480-495`
   `_relocate_lint_files_to_skill_root` 在 changed-markdown lint 返回前无条件剥掉
   沙箱前缀,函数 docstring 原话就是 "only guards against an absolute sandbox path
   leaking into the response";
2. `apps/studio/backend/app/services/skills.py:2296-2302` `_relative_compile_path`
   永远不会输出绝对路径:相对进相对出;绝对且不在根下时只返回 `candidate.name`
   (纯文件名);
3. #830 之后 `source_path` 本身就是根相对的,沙箱前缀根本不会出现在里面。

而**保留**它现在是有害的:根相对路径下,孙 skill 的文件天然以子 skill 文件的整条
路径结尾——`subgraph/event-timeline/subgraph/event-extraction/phases/review/SKILL.md`
以 `/subgraph/event-extraction/phases/review/SKILL.md` 结尾。打开后者时会把前者的
诊断一并划红,这正是本决议要消除的那一类错误归属。比对的两边都是同一个根下的相对
路径(编辑器那一侧就是 `LazyMonacoPanel.tsx:97` 传给 `writeSkillFile` 的同一个串),
整串相等是唯一正确的判据。分隔符归一化保留。

### D3. `phase_name` 仍然是第一优先,未加护栏

`LintError.phase_name` 排在文件路径之前。聚合路径
(`skills.py:2118` `_lint_error_from_issue`)恒定写 `phase_name=None`,子 skill 的
诊断正是从这条路径来的;只有"没有聚合 issues、退化到单条主异常"的
`_lint_error_from_exception`(`skills.py:2142`)才会从 `payload.phase_id` 取值。
没有实测到子 skill 诊断带着 `phase_name` 到达前端的情形,所以不为一个没有证据的
通道加护栏(呼应「论据先行」:说不出实例就是在猜)。发现实例时按同一条规则处理。

## 验收判据

`apps/studio/frontend/src/components/studio/field-compile-errors.test.ts`:

1. `lintErrorsForPhase(errors, "review")`:`subgraph/first/phases/review/SKILL.md`
   的诊断**不返回**,`phases/review/SKILL.md` 的**返回**;
2. 三层嵌套 `subgraph/event-timeline/subgraph/event-extraction/phases/review/SKILL.md`
   同样不返回;
3. `fieldErrorsByKey` 对子图相位的 `field_path` 返回空表;
4. `lintErrorsForBoundary`:`subgraph/first/GRAPH.md` + `io.inputs.…` 不进根输入边界;
5. `lintErrorsForFile`:孙 skill 的同名文件不被子 skill 的打开文件认领;分隔符
   归一化仍然成立。

`apps/studio/frontend/src/components/studio/node-compile-errors.test.ts`:

6. `compileErrorsByNode` / `lintErrorsByNode` 对子图相位文件返回空表;
7. `subgraph/first/GRAPH.md` + `field='io.outputs.required'` 不挂根 Output 节点;
8. 同一事件里引擎自己那条 `phases/alpha/SUBGRAPH.md` 诊断**仍然**挂在 `alpha` 上。

前端四门:`npm run lint` · `npm run typecheck` · `npm test` · `npm run build`。
