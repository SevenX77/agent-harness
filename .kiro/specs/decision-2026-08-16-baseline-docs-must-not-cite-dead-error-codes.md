# 决议:baseline 文档不得把"已停用的错误码"写成活着的编译闸

- 日期:2026-08-16
- 范围:engine 文档(`docs/engine/mvp1/`)+ 一条新的机械门禁
  (`packages/graph-agent/tests/test_baseline_doc_error_code_liveness.py`)
- 状态:已实施

## 1. 问题

`docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/baseline.md` 有两处
描述与代码不符。`baseline.md` 的**唯一职责就是描述当前实现状态**,所以描述错了
本身就是缺陷,不是"文档没跟上"的小事。

原文第 54 行:

> - **子图 outputs 仍严校**(编译期):同函数继续要求父 `SUBGRAPH.md io.outputs`
>   与子 `GRAPH.md io.outputs` 整个 schema 相等;不一致报
>   `[F-v3-subgraph-io-mismatch]`,错误信息标明 `outputs do not match`。

原文第 86 行:

> - **子图 io 现状**:inputs 已放宽(`loader.py:528` 不再比较 inputs);outputs
>   仍强制相等并用 `[F-v3-subgraph-io-mismatch]` fatal。

两句都是假的。机械核验(在本决议实施前的树上执行):

```
$ grep -rn "outputs do not match" packages/graph-agent/src/
(无匹配,退出码 1)

$ grep -rn --include=*.py "subgraph-io-mismatch" packages/graph-agent/src/
packages/graph-agent/src/graph_agent/core/error_registry.py:95: ...
(只剩 registry 一处)
```

## 2. 事实链(为什么现状是"没有这道闸")

**代码侧。** 这道编译闸于 2026-06-20 由 commit `cad7dbc0`
「feat(engine): relax subgraph io.outputs 1:1 compile gate (n2-iopanel#30)」
按 PM 授权删除。该 commit 从 `loader.py:_validate_subgraph_io_contracts` 中
删掉的正是这段:

```python
-        parent_outputs = doc.ast.io.outputs
-        child_outputs = child.manifest.io.outputs
-        if parent_outputs != child_outputs:
-            _fatal(... "[F-v3-subgraph-io-mismatch] " ... "outputs do not match" ...)
```

commit 原文说明了保留错误码的理由:

> The error code is retained in the registry (no longer emitted) to preserve
> the round28 registry↔owner bijection + len==97 count.

该函数今天(`packages/graph-agent/src/graph_agent/core/loader.py:996`,调用点
`:397`)只剩递归编译 child graph 一件事,其 docstring 为
`"""Compile each subgraph's child so a parent compile validates its children."""`。

**设计侧。** 这不是代码擅自漂移,设计源本来就是这么规定的:

- `docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md:78`(§3.4
  「IO 是黑板切片边界」):「每个节点自己的 `io.inputs` 声明从黑板读取哪些字段,
  `io.outputs` 声明允许写回哪些字段。**父图和子图 IO 不需要字段全集一一相等。**」
- 同文件 `:126`(§4 Implementation Drift 清单)把「父子图 IO 1:1 强绑定」明确
  列为 drift——即"若在代码或历史文档中仍出现,只代表历史实现或迁移残留,不代表规范"。

**运行期边界在哪。** `packages/graph-agent/src/graph_agent/runtime/state_mapper.py:318`
的 `_validate_phase_updates_against_schema` 按该 phase 声明的 outputs schema 过滤
写回;越界字段以受控的 `[F-v3-runtime-state-mapping-failed]` 失败(`:328`
`"phase wrote undeclared keys: "`),不是崩溃。所以边界并没有丢,只是从编译期
挪到了运行期。

## 3. 关键设计决定

### 决定一:两处描述按"当前真实状态"重写,并连带修正同段的失效行号

第 54 行所在的整个 §5 小节标题就叫「SUBGRAPH:inputs 放宽 / outputs 严校」——
标题本身就是那句假话的一部分,所以改的是整个小节而不是一句话。同段里的
`loader.py:528` / `:211` / `_build_subgraph_node`(`:363`)三个行号也已全部失效
(实为 `loader.py:996` / `:397` / `graph_assembler.py:1589`)。既然在改这一段,
**留着已知为假的行号等于明知故犯**,一并修正。

### 决定二:错误码表(设计侧)也标注,因为那是设计文档内部自相矛盾

`docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md:307/308` 把
`[F-v3-subgraph-io-mismatch]` 和 `[F-v3-subgraph-io-schema-incompatible]` 列为
「编译期」校验。这与**同一套 MVP1 设计**的 skill-syntax §3.4 + §4 直接冲突。

按 AGENTS.md「MVP1 design = source of truth」,通常不能改设计去迁就代码。但这里
不是代码与设计打架,而是**设计文档内部两处打架**:一处是带完整理由的正面规定
(§3.4 定义了 IO 是切片边界)加一处显式的 drift 判定(§4 点名"父子图 IO 1:1
强绑定"是 drift),另一处只是错误码目录里一行遗留条目。**具体的、带理由的那条
优先**,目录条目是没跟着改的残留。所以标注两行是消除设计内部矛盾,不是拿代码
反推设计。

两码的来历并不相同,标注措辞因此区分:

- `[F-v3-subgraph-io-mismatch]` —— 曾经真的发出过,`cad7dbc0` 移除,标「**不再发出**」。
- `[F-v3-subgraph-io-schema-incompatible]` —— `git log -S` 全源码历史只有
  `c32575fa`(round-17 建 registry)一条,**从来没有过发出点**,标「**从未发出**」。
  把它也写成"不再发出"会是一句我没有证据的历史断言。

### 决定三:配一条机械门禁,而不是只改文字

只改这三处文字,同类漂移下次照样发生——它已经存在了将近两个月而无人发现。
新增 `test_baseline_doc_error_code_liveness.py`,断言的是**两个事实源之间的一致性**
(文档 vs 源码),不是"某段文字存在"式的子串断言:

> `docs/engine/mvp1/**/baseline.md` 里出现的每个 `[F-v3-*]` 错误码,
> 引擎源码中必须存在发出点;否则该行必须自带标记 `无发出点`。

`error_registry.py` 被显式排除在"发出点"之外——它为所有码声明元数据,算进去
会让每个码看起来都活着,门禁就恒真了。

**为什么用"同行标记"而不是"豁免名单"。** baseline 正文有时**必须**提到一个
没有发出点的码,恰恰是为了记录"它没有发出点"这件事。若另立一份允许清单,那份
清单会和它所守护的正文以同样的方式腐烂。让标记就写在那句话里,断言和文档就是
同一个 token,一行没法一边退回"这是活闸"一边保持绿色。

### 决定四:mvp0 与 `docs/studio/_reorg/` 不改

`grep -rn "subgraph-io-mismatch" docs/` 另有 11 处命中,全部不动,理由是它们
描述的对象本来就不是"当前状态":

- `docs/engine/mvp0/**`(7 处)是 MVP0 里程碑的定稿文档(如
  `MVP0-PROGRESS-2026-05-21.md`),对那个里程碑当时的实现描述是准确的。改写它们
  等于篡改已完成里程碑的历史记录。
- `docs/studio/_reorg/**`(3 处)是 MVP1 改造的推导底稿:`alignment-notes.md:239`
  记的是 FROZEN(改造前)状态,而 `workflow-action-catalog.md:27` 紧接着把
  「删 `F-v3-subgraph-io-mismatch` 的 1:1 强制」列为待办变更项。它们成对地
  记录了"改之前是什么 / 打算改成什么",是输入材料而非现状描述。

### 门禁抓不到什么(必须写明,否则会被误当成全覆盖)

门禁的判据是"这一行**引用了某个错误码**",所以它只能抓到带码的句子。**同一条假话
用纯散文写就抓不到。** 这不是假设:本次改动 push 之后、rebase 期间靠人工通读,
又在同一个 `01-graph-exec/baseline.md` 里发现四处漏网,全是不带码的表述——

- `:4` frontmatter `status:` 里的「子图 inputs 已放宽且 outputs 仍严校」;
- `:11`「现状一句话」里的「outputs 仍严格相等」;
- `01-contract/02-skill-syntax/baseline.md:31` 差异表的现状列「部分路径仍有父子
  schema 相等判断」;
- `02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md:28` 的「**outputs 保留**
  相等校验(下游契约)」。

这四处已在本次一并订正。**结论是这条门禁把"有码的漂移"变成不可能,把"没码的漂移"
留给人。** 之所以不把门禁扩成匹配"严校/严格相等/1:1"这类词,是因为那会退化成
按措辞定罪的子串断言——本仓已经因为"只做子串断言的测试"下线过一整套手册门禁
(AGENTS.md §Standard Documents 2026-08-12 条),重蹈一次没有意义。

最后一处 `mvp1-alignment.md:28` 属于**设计与设计打架**,处置同决定二:该文写
"outputs 保留相等校验(下游契约)",而 `01-contract/02-skill-syntax/mvp1-alignment.md`
§3.4/§4 是 IO 语义的权威规定且 PM 已授权移除,故以后者为准并就地订正措辞。

## 4. 顺带发现(同一门禁抓出的第二例,已一并如实登记)

新门禁在 23 个 `baseline.md` 中抓出的不止目标两行,还有第三处:
`docs/engine/mvp1/01-contract/03-compile-rules/baseline.md:42` 把
`[F-v3-mention-unused-registry-entry]` 与已有发出点的 `[F-v3-reference-reader-failed]`
并列成两个 `WARN`,读起来像两个都会报。实测前者全仓
(`packages/` + `apps/`)只有 `error_registry.py:118` 一条 registry 条目,
**没有任何发出点**——这条 WARN 目前不会真的报出来。

该行同时还写着「当前 key set 继续是 96 个」,实测
`len(ERROR_REGISTRY) == 99`。因为门禁强制我必须改这一行,把同一句里另一个
已知为假的数字留着是不诚实的,一并订正并附上取数命令。

**没有做的事**:没有去补 `[F-v3-mention-unused-registry-entry]` 的发出点,也没有
把它从码表退役。全仓 registry 里这样"只有条目、没有发出点"的码共 13 个,逐个
判定"该补发出点还是该退役"需要各自的证据,属于另一个任务;在没做这个判定之前
批量标注它们,就是在编造我没核实过的状态——正是本决议要修的那种错误。

## 5. 参考的成熟做法

- **借了 `test_doc_hash_lock.py` 的形状**(同仓既有实现):纯检查函数 + tmp_path
  合成用例 + 一条跑真实语料的断言。新测试照抄这个分层,好处是检查逻辑本身可单测,
  不是只有一条"跑全仓"的黑盒断言。
- **拒绝了它的 `_doc-exemptions.yaml` 机制。** 那个文件的用途是记录 owner 批准的
  **临时**漂移(字段含 `reason` + `owner_approval`),需要审批链。而"某个错误码已
  停用"是永久且自证的事实,应该写进描述它的那句话里,不该进一个需要人维护的旁挂
  文件。取它的分层,不取它的豁免通道。
- **借了 gRPC 状态码文档的取向**:一个码"存在于码表"与"服务端会不会返回它"是两件
  分开说明的事。本次标注就是把这两件事在码表里显式分开。
- **没借** Java `@Deprecated` 那种"标记后仍可调用、留待将来删除"的语义:本仓
  no-backward-compat,不存在"留给外部使用者的过渡期"。这两个码留下来的**唯一**
  理由是 round28 registry↔owner 双射与计数,和"弃用过渡"无关,文案上必须写清是
  哪一个理由,免得被读成"以后可能会恢复"。

## 6. 验收判据

`packages/graph-agent/tests/test_baseline_doc_error_code_liveness.py`:

1. `test_dead_code_citation_is_reported_unless_the_line_carries_the_marker` ——
   合成语料:同一文件三行,活码行、无标记的失效码行、带标记的失效码行,只有中间
   那行被报。
2. `test_only_baseline_docs_are_scanned` —— `mvp1-alignment.md` 是目标设计,不受
   "必须与当前代码一致"约束,不进扫描。
3. `test_registry_module_alone_does_not_make_a_code_live` —— 只出现在
   `error_registry.py` 的码不算有发出点。
4. `test_engine_baseline_docs_do_not_describe_unemitted_error_codes_as_live` ——
   跑真实语料。修复前实测 3 条违规(graph-exec baseline 第 54、86 行 +
   compile-rules baseline 第 42 行),修复后 0 条。该用例另带一条前提断言:
   若 `[F-v3-subgraph-io-mismatch]` 哪天又被发出,门禁会直接指出"前提已变",
   而不是默默继续绿。

hash lock 未被触发:`docs/engine/mvp1/_audited-ready-hashes.json` 锁定的 16 份
文档不含本次改动的三份,且 `01-contract/03-compile-rules/` 与
`02-mechanism/04-run-outer/01-graph-exec/` 都不是被锁目录,
`uv run pytest packages/graph-agent/tests/test_doc_hash_lock.py` 实测 4 passed。
因此**没有**重钉哈希——重钉一份没被锁的文件只会凭空扩大锁定面。
