# 决议:一个 run 只有一个身份,活着死了都是它

日期:2026-08-16
分支:`fix/engine-run-identity`
台账行:W2-25

---

## 一、决策

`run_skill` 在**开跑之前**决定这次 run 的身份(`run_id`)和它的目录(`run_dir`),两条
出口路径——成功返回与 `except GraphAgentError`——都用这同一份决定;身份不再在函数内层
被第二次铸造,也不再从内层返回的字典里读回来。

连带确定三件事:

1. 失败结果的 `trace_path` 不再写死 `None`。trace 文件由 sink 在**构造那一刻**创建
   并清空,所以「这个文件在不在」就是「这次 run 到底开没开 trace」的直接答案:开了就
   指向它,没开(图还没装配就被拒)就诚实地留 `None`。
2. `trace.jsonl` 这个文件名收敛到 `graph_agent/io/run_layout.py` 的 `TRACE_FILENAME`
   常量,原先散在三处的字面量全部改引用它。
3. `_resume_failed_result` 是同族第三处,**是同一个毛病的一半**——详见第四节。

---

## 二、论据

### 2.1 现场:同一次 run 的产物落在两个目录,结果里没有任何东西指向证据

`story-deconstruction-v3-lab` 在带 #838/#843/#844 的 main 上真跑,第 23 个相位死掉。
`ls -la D:/coding/skills/story-deconstruction-v3-lab/.workspace/runs/` 实测输出:

```
drwxr-xr-x 1 test 197121 0 Aug 16 01:57 485af68a-9bfa-4667-902a-674db5fd19d2
drwxr-xr-x 1 test 197121 0 Aug 16 00:35 75be98c1-3711-4e12-a69c-6d118170a73a
drwxr-xr-x 1 test 197121 0 Aug 16 02:04 a7b0aeed-c2c3-4df6-8531-18ad96a166a8
```

两个目录各自的内容(同一次 run,文件 mtime 都是 `02:04`):

```
=== 485af68a-9bfa-4667-902a-674db5fd19d2 ===
-rw-r--r-- 1 test 197121 1467792 Aug 16 02:04 trace.jsonl

=== a7b0aeed-c2c3-4df6-8531-18ad96a166a8 ===
-rw-r--r-- 1 test 197121       2 Aug 16 02:04 final_state.json
-rw-r--r-- 1 test 197121      99 Aug 16 02:04 metrics.json
-rw-r--r-- 1 test 197121    1753 Aug 16 02:04 result.json
```

`a7b0aeed/result.json` 的字段实测:

```
success   = False
run_id    = 'a7b0aeed-c2c3-4df6-8531-18ad96a166a8'
skill_id  = 'story-deconstruction-v3-lab'
trace_path = None
source    = 'run'
error     = {'code': '[F-v3-agent-validator-failed]', 'level': 'FATAL', ...}
```

对照同一台机器上**成功**的那次 `75be98c1-3711-4e12-a69c-6d118170a73a`,一个目录装齐四件:

```
-rw-r--r-- 1 test 197121  201920 final_state.json
-rw-r--r-- 1 test 197121     180 metrics.json
-rw-r--r-- 1 test 197121  211890 result.json
-rw-r--r-- 1 test 197121 4188382 trace.jsonl
```

即:**恰恰在 run 死掉、最需要 trace 的时候,结果与证据被分到两个目录,而结果里没有
任何东西指向证据。**

### 2.2 机制:身份在两个地方各铸了一次

以下行号取自 `origin/main` 的
`packages/graph-agent/src/graph_agent/core/runner.py`(`git show origin/main:... | sed -n`
逐行核对过):

- `:2086`(内层,真正跑图的 `_run_v030_skill_dict`)自己铸一个:
  ```python
      run_id = thread_id or str(uuid.uuid4())
  ```
  紧接着 `:2087` `trace_output = run_root / run_id` —— trace 与 run 目录都写在**这个** id 下。

- `:502`(外层成功路径)把内层那个捞回来:
  ```python
          run_id=str(raw.get("run_id") or thread_id or str(uuid.uuid4())),
  ```
  `:506` `trace_path=raw.get("trace_path")`、`:512`
  `run_dir = Path(raw.get("run_dir") or runs_root(workspace_root) / workflow_result.run_id)`。

- `:482`(外层失败路径)**压根拿不到 `raw`**——异常在 `_run_skill_dict` 返回之前就抛了:
  ```python
              run_id=thread_id or str(uuid.uuid4()),
  ```
  同一处 `:486` 还把 `trace_path=None` 写死。

一句话:**run id 在两个地方各铸了一次**;`thread_id` 非空时两处算出同一个值,恰好对上;
`thread_id` 为空时,成功路径靠读 `raw` 把两者对上,失败路径无 `raw` 可读,于是铸出
第二个、和内层那个完全无关的 uuid。现场那两个目录名(`485af68a` 与 `a7b0aeed`)就是
这两次铸造的产物。

### 2.3 真实调用方确实不传 `thread_id`

`runner.py:2232`(CLI 参数定义)与 `:2298-2305`(调用):

```python
    parser.add_argument(
        "--thread-id", type=str, default=None, help="Thread ID for checkpoint resume"
    )
...
    result = run_skill(
        args.skill,
        workspace_dir=workspace_dir,
        skill_resolver=LocalWorkspaceResolver(search_paths=resolver_roots),
        thread_id=args.thread_id,
        ...
    )
```

`--thread-id` 默认 `None`,所以走 CLI 跑一次 skill 就落在缺陷分支上。

**说准确,不夸大**:Studio 桌面 app 的运行路径不是这一条。它经
`apps/studio/backend/app/core/adapters/engine.py:98-101` 导入的 `run_artifact`,而
`run_artifact` → `_run_compiled_artifact_graph`(`runner.py:922-935`)传的是
`thread_id=run_id`,且 `_artifact_run_id`(`:838-842`)有兜底
`f"run-{artifact_ref.artifact_id}-{idempotency_key}"`,**恒非空**,因此那条路上两次铸造
必然同值,撞不出这个缺陷。现场那份 `result.json` 的 `run_id` 是裸 uuid4 而非
`run-<id>-<key>` 形状,`source='run'`,与 `run_skill(thread_id=None)` 的签名一致。

### 2.4 trace 文件在失败时是存在的

`packages/graph-agent/src/graph_agent/callbacks/emit.py:15-21`(修前):

```python
class _TraceJsonlSink:
    def __init__(self, trace_dir: str | Path) -> None:
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.trace_dir / "trace.jsonl"
        self.path.write_text("", encoding="utf-8")
```

文件在 sink **构造时**就被建出来并清空;`_run_v030_skill_dict` 在 `:2091` 构造 sink,
在 `:2111` 才 `try: compile_skill(...)`。所以任何「进得了图执行阶段」的失败,
`runs/<run_id>/trace.jsonl` 一定已经在盘上——现场那 1,467,792 字节就是它。
失败路径把 `trace_path` 写死 `None` 是**丢弃已知事实**,不是「无从得知」。

---

## 三、修在哪一层,以及为什么不是另一层

### 修在这里:`run_skill` 决定身份,一次

按仓规「显式状态与唯一 owner」(AGENTS.md 通用工程原则第 4 条:重要状态、生命周期与
副作用只有一个权威 owner)。一次 run 的身份是这类状态里最基本的一个,必须在**跑之前**
决定一次,两条出口共用它:

```python
    run_id = thread_id or str(uuid.uuid4())
    run_root = runs_root(workspace_root)
    run_dir = run_root / run_id
    trace_file = run_dir / TRACE_FILENAME
```

然后把它作为 `thread_id=run_id` 传下去。内层 `:2086` 的 `thread_id or uuid4()` 因此
永远走 `thread_id` 那一支——**它不再是第二个铸造点,只是一个接收点**。

这不是新发明的形状:同一个文件里的 `predict_skill` 早就这么写(`:345` 铸一次,`:353`
`thread_id=run_id` 传下去)。本次是把 `run_skill` 对齐到它旁边那个已经正确的兄弟。

### 顺带:`_run_skill_dict` 收 `run_root`,不再自己算

修前 `:772` 是 `run_root=runs_root(workspace_dir)` —— 同一个目录在外层和内层各算一遍,
和 run_id 一模一样的病。改成必填关键字参数 `run_root: Path` 由调用方传入。依据是
`io/run_layout.py` 模块文档自己写的原则:

> Which root an execution belongs to is decided by the caller that knows the
> kind, and carried from there as a plain path.

`_run_v030_skill_dict` 本来就已经收 `run_root`(`:2063`),`_run_compiled_artifact_graph`
也已经在传(`:925`)。这次只是让 `_run_skill_dict` 与它们一致。

### 为什么不在 except 块里「想办法找回 id」

比如把 id 挂到异常对象上、或让内层把 id 写进某个共享位置再由外层捞。那是**在两次铸造
既成事实之后再去缝合它们**——症状补丁。仓规「First-principles fixes, not patches」要求
先问「这个状态为什么能存在」:两个不相干的 uuid 之所以能存在,是因为有两个铸造点。
删掉一个铸造点,缝合的需求就不存在了。

### 为什么不把 event sink 提到 `run_skill` 里

那样失败路径就能直接读 `event_sink.trace_path`,比按布局推导更强。但 sink 的构造点
`_run_v030_skill_dict:2091` 同时服务 `predict_skill`、`_run_compiled_artifact_graph`
和 5 个测试文件的直接调用;提上来要改全部调用点的签名,属于「夹带无关重构」(仓规
Coding Standards「一个任务一个 PR」)。而按布局 + `.exists()` 给出的答案是**真话**——
文件在就是在,不在就是不在,没有可被推翻的余地。取小的那个,并把差距明写进遗留。

---

## 四、同族第三处:`_resume_failed_result`

判定:**它有一半是同一个毛病,另一半不是。**

- **不是**「铸两次 id」:`resume_skill` 的 `run_id` 是调用方必填参数(`:521`
  `run_id: str,`),函数内不铸;`trace_output = runs_root(workspace_root) / run_id`
  (`:554`)只算一次。身份从头到尾唯一。
- **是**「丢掉 trace 指针」:`:1936`(修前)同样把 `trace_path=None` 写死。

而它比 `run_skill` 更没有理由这么写:调用点 `:649` 所在的 `except` 块里,`event_sink`
就在作用域内(`:555` 构造),成功路径 `:684` 正是从它取值——
`saved_trace_path = str(event_sink.trace_path) if event_sink.trace_path is not None else None`。
所以这里**不需要推导**,直接把 `event_sink.trace_path` 传给
`_resume_failed_result(trace_path=...)` 即可。已一并修掉。

---

## 五、借了什么,拒了什么,为什么

### 借:OpenTelemetry 的 span 身份模型

一个 span 的 `SpanContext`(trace_id + span_id)在 **span 开始时**生成;`span.end()`、
`span.set_status(ERROR)`、`span.record_exception()` 都不会另生成一个 span,失败只是同一个
span 上的一个**字段**。**借的正是这一条**:结果好坏是身份的一个属性,不是另一个身份。
本次 `run_id` 在 try 之前定,成功与失败共用,`success: bool` 才是区分两者的字段。

**拒:它的 context 传播机制**(W3C traceparent 头、context vars、跨进程 propagator)。
那套东西存在的前提是「身份要跨进程/跨线程边界传给不认识彼此的组件」;本仓这里是**同一个
函数栈内的两层调用**,把 id 放进一个局部变量再作为参数传下去,就是全部所需的传播机制。
引入 context 变量只会把一个显式参数换成隐式全局态——正好违反仓规「显式优于隐式」。

### 借:systemd 的 `InvocationID`

systemd 在 fork 服务进程**之前**为这次启动铸一个 128 位 invocation id,导出为
`$INVOCATION_ID`,journald 用它给日志打标。它的取舍很明确:**id 归监督者、在工作开始
之前产生**,于是一个启动即崩的服务,它的日志和它的状态记录仍然共用同一个 id——正是本次
的失败场景。**借的是「监督者先铸、工作后跑」这个顺序。**

**拒:它把 id 持久化以熬过 manager re-exec 的那部分**(存进 kernel keyring / 管理器状态)。
那个需求来自「监督者是长命守护进程,可能自己重启」;本仓的「监督者」是 `run_skill` 这个
**函数调用**,它的生命周期不长于这次 run,id 活在栈帧里就够了,不需要任何持久化载体。
这条前提在这里不成立,所以只取顺序,不取机制。

### 关于 `trace.jsonl` 名字收敛:不是抽象,是止损

修前这个字面量有三处(`emit.py:19`、`tracing.py:64`、`runner.py:414`),本次改动会
产生第四处。按仓规「DRY,但三次成律」——同一事实第三次出现且确认同一业务含义时抽公共层
——收敛到 `run_layout.py` 的 `TRACE_FILENAME`。之所以放在这个模块而不是新建一个:该模块
的职责本来就是「一次执行把产物放在哪」,文件名是这个问题的一部分。**没有**顺手抽
`trace_file(run_dir)` 这类 helper——`run_dir / TRACE_FILENAME` 已经足够清楚,多一层
间接是 KISS 的反面。

---

## 六、验收判据与实测

TDD:测试先写,`packages/graph-agent/tests/runner/test_run_keeps_one_identity.py`。
RED 实测(修生产代码之前)`3 failed, 3 passed`:

```
FAILED test_run_keeps_one_identity.py::test_failed_run_without_thread_id_files_result_next_to_its_trace
E       AssertionError: assert ['226815ee-d3...07e41325559d'] == ['45405bf8-b1...07e41325559d']
E         At index 0 diff: '226815ee-d3c3-4d7e-8dc2-f75df883f3b2' != '45405bf8-b131-4e33-822d-07e41325559d'
E         Left contains one more item: '45405bf8-b131-4e33-822d-07e41325559d'

FAILED test_run_keeps_one_identity.py::test_failed_run_with_thread_id_keeps_the_caller_identity
E       AssertionError: assert None is not None
E        +  where None = WorkflowResult(success=False, run_id='caller-chosen-id', ...).trace_path

FAILED test_run_keeps_one_identity.py::test_failed_resume_points_at_the_trace_it_opened
E       AssertionError: assert None is not None
E        +  where None = WorkflowResult(success=False, run_id='resume-that-dies', ...).trace_path
```

第一条失败**逐字复现了现场**:两个目录,结果落在其中一个,trace 落在另一个。

| 判据 | 覆盖它的测试 | 修后 |
|---|---|---|
| a. 不传 `thread_id` 的失败 run,`result.run_id` == trace 所在目录名 | `test_failed_run_without_thread_id_files_result_next_to_its_trace`(断言 `runs/` 下**只有一个**目录且等于 `result.run_id`) | 通过 |
| b. 失败的 `result.json` 与 `trace.jsonl` 同目录 | 同上(两个 `is_file()` 断言 + 读回 `result.json` 核对 `run_id`/`trace_path`) | 通过 |
| c. 失败结果 `trace_path` 指向真实存在的 trace | 同上 + `test_failed_run_with_thread_id_keeps_the_caller_identity` | 通过 |
| c'. trace 根本没开时诚实报 `None` | `test_run_that_dies_before_a_trace_exists_reports_no_trace_path`(缺 `GRAPH.md`,sink 未构造) | 通过 |
| d. 成功路径零回归 | `test_successful_run_without_thread_id_keeps_one_identity` + 全套 1546 用例 | 通过 |
| e. 传了 `thread_id` 的成功与失败都覆盖 | `test_successful_run_with_thread_id_keeps_the_caller_identity` + `test_failed_run_with_thread_id_keeps_the_caller_identity` | 通过 |
| f. resume 失败也指向它开的那份 trace | `test_failed_resume_points_at_the_trace_it_opened` | 通过 |

---

## 七、已知遗留(明写,不装作解决)

1. **失败路径的 trace 指针是推导出来的,不是 sink 交给它的。** `run_skill` 的 `except`
   块按 `run_dir / TRACE_FILENAME` 算出候选再用 `.exists()` 确认,而不是像成功路径和
   resume 路径那样读 `event_sink.trace_path`。原因见第三节末:把 sink 提到 `run_skill`
   要改 5 个测试文件加 2 个内部调用方的签名,超出本 PR 范围。**这条推导今天成立**,因为
   `_run_skill_dict` 收到的 `run_root` 和 `run_skill` 算 `run_dir` 用的是同一个变量;
   但它是**约定**而非类型系统保证的。彻底解法是让 sink 的所有权上移一层,留作独立议题。
2. **`_run_compiled_artifact_graph` 仍然从 `raw` 读回身份**(`:939`
   `run_id=str(raw.get("run_id") or run_id)`、`:949`
   `run_dir = Path(raw.get("run_dir") or ...)`)。查过了:那条路上 `run_id` 由
   `_artifact_run_id` 保证非空,两次计算必然同值,**不是缺陷**;它失败时压根不写
   `result.json`(异常一路抛到 `run_artifact:1225` 的 `except` 返回
   `RunArtifactErrorResult`),所以本次的现场在那条路上不成立。本 PR 不动它,理由是
   零行为收益换 Studio 主运行路径的回归风险不划算。代价是同一个文件里两种写法并存,
   如实记在这里。
3. **Studio 真机上没有复验。** 本 PR 只交离线证据(单测 + 现场目录取证)。上文已论证
   桌面 app 的 `run_artifact` 路径撞不出这个缺陷,所以真机点验对本条不构成有效验证面;
   要复验得走 CLI(`python -m graph_agent.core.runner --skill ... ` 不带 `--thread-id`)。
   **没做,不声称做了。**
4. **失败 run 的 `final_state.json` 仍然是空 `{}`。** 现场那份 2 字节的文件说明失败时
   业务上下文整个丢掉了——`run_skill` 的 `except` 分支写 `context={}`。这是另一个议题
   (「死掉的 run 该不该带走它已经产出的东西」),本次不动,不与身份问题混为一谈。
