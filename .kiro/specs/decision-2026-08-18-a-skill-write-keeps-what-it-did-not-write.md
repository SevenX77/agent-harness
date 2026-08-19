# 决议 2026-08-18:一次 skill 写入,只动它写的那几个文件

状态:已实施(本 PR)
影响模块:Studio backend(`apps/studio/backend`)
发现方式:W2-23 那次 flaky 调查给后端测试的 `os.unlink` / `rmtree` 打插桩,日志里出现
`.idea-generator.bak-<token>/.git/...` 被逐个 unlink。**本 PR 不采信该转述,已在
本机独立复现,原始输出见 §2.3。**

---

## 一、决策

**一句话**:`write_skill_files_atomic` 的替换单位从**整个 skill 目录**改成
**被声明的那几个文件**;校验对象从**用 payload 拼出来的临时目录**改成
**skill 目录本身**;被拒绝的一批写入靠一份 undo log(改动前的原始字节)整批回退。

具体四条:

1. **不删我没带来的东西。** 请求里能出现的路径由 `validate_skill_file_path`
   (`apps/studio/backend/app/services/skills.py:133-155`)限死;`.git/`、`.workspace/`、
   `subgraph/` **在结构上不可能**出现在 payload 里。因此这个 API 根本无法表达
   "并且把其余的删掉"这个意思,它就一样都不删。
2. **校验要判它真正会加载的那个 skill。** lint 改为对 `skill_dir` 本身跑,不再对
   一个缺了 payload 装不下的内容的假根跑。假根不只是"判得不准",它让**带 subgraph
   的 skill 永远存不下来**(§2.4 实测)。
3. **原子性的粒度降到单文件,批次靠 undo log 回退。** 每个文件经
   `write_text_atomically` 单步发布;lint 判失败就用改动前的原始字节把这一批整个写回去。
4. **崩溃时的行为写明,不含糊。** 进程在批次中途死掉,会留下"一部分新、一部分旧"
   加可能的 `.<name>.*.tmp` 残留;**payload 之外的东西一个都不会少**。详见 §五。

**唯一权威定义落在** `apps/studio/backend/app/services/skills.py:158-243`
(`write_skill_files_atomic` + 三个私有 helper),以及
`apps/studio/backend/app/core/adapters/atomic_file.py:43-86`(新增 `write_bytes_atomically`,
`write_text_atomically` 改为委托给它)。

---

## 二、论据

### 2.1 改前的实现:换掉整个目录

`apps/studio/backend/app/services/skills.py:155-181`(改前,原文):

```python
def write_skill_files_atomic(skill_dir: Path, files: dict[str, str]) -> None:
    for rel_path in files:
        validate_skill_file_path(rel_path)
    token = uuid.uuid4().hex
    tmp_dir = skill_dir.parent / f".{skill_dir.name}.tmp-{token}"
    backup_dir = skill_dir.parent / f".{skill_dir.name}.bak-{token}"
    try:
        tmp_dir.mkdir(parents=True, exist_ok=False)
        for rel_path, content in files.items():
            target = tmp_dir.joinpath(*PurePosixPath(rel_path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        lint = lint_skill_path(tmp_dir, include_studio_preflight=False)
        if lint.status == "failed":
            _raise_manifest_validation_failed(lint)
        if skill_dir.exists():
            os.rename(skill_dir, backup_dir)
        os.rename(tmp_dir, skill_dir)
    except Exception:
        if not skill_dir.exists() and backup_dir.exists():
            os.rename(backup_dir, skill_dir)
        raise
    finally:
        if backup_dir.exists():
            _rmtree_with_retry(backup_dir)
        if tmp_dir.exists():
            _rmtree_with_retry(tmp_dir)
```

`tmp_dir` 是一个**全新的空目录**,只装 `files` 里那几个文件;成功路径把整个
`skill_dir` 改名成 `backup_dir`、把 `tmp_dir` 顶上去,`finally` 再把 `backup_dir`
连同里面的一切 `_rmtree_with_retry` 删掉。

### 2.2 请求里为什么永远不可能包含被删的那些东西

`apps/studio/backend/app/services/skills.py:133-155`(改后行号,函数体未改):

```python
def validate_skill_file_path(rel_path: str) -> None:
    invalid_message = f"invalid_skill_file_path: {rel_path}"
    path = PurePosixPath(rel_path)
    parts = path.parts
    if (
        not rel_path
        or rel_path.startswith("/")
        or "\\" in rel_path
        or path.suffix not in _ALLOWED_SKILL_FILE_SUFFIXES
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise HTTPException(status_code=422, detail=invalid_message)
    if parts == ("GRAPH.md",):
        return
    if parts in {("io", "inputs.json"), ("io", "outputs.json")}:
        return
    if len(parts) == 2 and parts[0] == "tools" and parts[1].endswith(".py"):
        return
    if len(parts) == 3 and parts[0] == "phases" and parts[2] in _PHASE_NODE_FILES:
        return
    if len(parts) == 4 and parts[0] == "phases" and parts[2] in {"actions", "tools"} and parts[3].endswith(".py"):
        return
    raise HTTPException(status_code=422, detail=invalid_message)
```

`_ALLOWED_SKILL_FILE_SUFFIXES = {".md", ".json", ".py"}`、
`_PHASE_NODE_FILES = {"LOGIC.md", "SUBGRAPH.md", "SKILL.md"}`(`skills.py:85-86`)。

逐一核对被删掉的那几类:

| 被删的东西 | 为什么进不了 payload |
|---|---|
| `.git/**` | 里面绝大多数文件没有 `.md`/`.json`/`.py` 后缀,第一道 `path.suffix not in ...` 就 422;即便个别文件后缀凑巧,`parts[0] == ".git"` 也不匹配下面任何一条放行规则 |
| `.workspace/**`(golden、import_files、local_settings、runs、predicts) | 同上,`parts[0] == ".workspace"` 不匹配任何一条放行规则 |
| `subgraph/<name>/GRAPH.md` | 三段路径,但 `parts[0] == "subgraph"` ≠ `"phases"`,落到最后一行 422 |

**所以"整目录原子替换"这个原子单位选错了**:要替换的是被声明的那几个文件,
而这个目录里装着调用方**根本没有能力提交**的内容。

### 2.3 独立复现:`.git` 确实被删掉了

不采信 W2-23 的转述,本 PR 写了一条 RED 测试
(`apps/studio/backend/tests/services/test_skill_write_preserves_undeclared_files.py`
`test_write_keeps_git_and_workspace_it_never_carried`):建一个 skill,
写齐**全部可提交路径**,再加上 `.git/`(`initialize_skill_repository`)与
`.workspace/{golden,import_files,local_settings.json}`,然后走一次
`update_skill_files` 提交这套完整的可提交路径。

改前代码,`uv run pytest ...::test_write_keeps_git_and_workspace_it_never_carried -q`
的原样输出:

```
        assert "Edited description" in (skill_dir / "GRAPH.md").read_text(encoding="utf-8")
>       _assert_workspace_and_git_intact(skill_dir)

apps\studio\backend\tests\services\test_skill_write_preserves_undeclared_files.py:239:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    def _assert_workspace_and_git_intact(skill_dir: Path) -> None:
>       assert (skill_dir / ".git").is_dir(), ".git was destroyed by a write that never carried it"
E       AssertionError: .git was destroyed by a write that never carried it
E       assert False
E        +  where False = is_dir()
E        +    where is_dir = (WindowsPath('.../default-skills/keeper') / '.git').is_dir
```

注意 `GRAPH.md` 的断言**通过**了:写入本身成功了,`.git` 是在成功路径上没的。
这就是 W2-23 插桩看到的那件事,独立坐实。

### 2.4 同一个病灶的第二个症状:带 subgraph 的 skill 永远存不下来

假根不只在成功之后毁东西,它在成功之前就**判错**。
`test_write_of_a_skill_with_a_subgraph_is_accepted` 建一个 `phases/review/SUBGRAPH.md`
指向 `subgraph/child` 的 skill(`path: subgraph/child`,引擎按 skill 根解析相对路径,
见 `packages/graph-agent/src/graph_agent/core/topology_projection.py:105`
`return str((skill_dir.resolve() / candidate).resolve())`),提交它的全部可提交路径。

改前代码,原样输出(节选,已换行):

```
E       fastapi.exceptions.HTTPException: 422: {'error_code': 'MANIFEST_VALIDATION_FAILED',
  'details': {'errors': [
    {'file': 'phases/review/SUBGRAPH.md', 'error_code': 'F-v3-subgraph-target-skill-invalid',
     'message': "...\\default-skills\\.keeper.tmp-d80e9a8c7e404e25a5a263a02f511833\\phases\\review\\SUBGRAPH.md:3
                 subgraph path 'subgraph/child' is not a directory"},
    {'file': 'phases/review/SUBGRAPH.md', 'error_code': 'F-v3-agent-subgraph-invalid',
     'message': '[F-v3-agent-subgraph-invalid] Subgraph compile failed: skipped cascade check
                 due to poisoned child skill at path subgraph/child'},
    {'file': 'phases/review/SUBGRAPH.md', 'error_code': 'F-v3-graph-dataflow-source-missing',
     'message': "skipped dataflow check for phase 'review' due to poisoned upstream or self
                 compile error (phase 'review' itself is poisoned)"}]}}
```

路径里的 `.keeper.tmp-d80e9a8c...` 就是假根。`subgraph/child` 在**真的 skill 目录里
好端端存在**,只是没法被提交,于是假根里没有它 —— 结论是 422,而且**每次保存都是 422**。

同类的第三条:只提交 `GRAPH.md`(部分提交)时,假根里连 `phases/` 都没有:

```
E       fastapi.exceptions.HTTPException: 422: ... 'error_code': 'F-v3-graph-phases-dir-missing',
  'message': '...\\default-skills\\.keeper.tmp-4eba174e293e4c809aaa190c5366bc0b\\phases:1
              missing phases directory or phase entries'
```

**三条症状同一个病灶**:tmp 被当成了 skill 的全部,而它只是 payload 的全部。

### 2.5 那次 lint 本来就是重复的

改前 `update_skill_files`(`skills.py:1023-1029`,原文):

```python
    write_skill_files_atomic(skill_dir, files)
    for rel_path in files:
        record_api_write(skill_dir.joinpath(*PurePosixPath(rel_path).parts))
    structure_lint = lint_skill_path(skill_dir, include_studio_preflight=False)
    if structure_lint.status == "failed":
        _raise_manifest_validation_failed(structure_lint)
    lint = lint_skill_path(skill_dir)
```

`structure_lint` 与写入函数里那一次是**同一个调用、同样的 `include_studio_preflight=False`、
同样的 `_raise_manifest_validation_failed`**,区别只在于:调用方判的是真目录,
写入函数判的是假根。改后写入函数已经对真目录判过同一件事,`structure_lint` 只可能
重复前一次的结论,故删除(`skills.py:1085-1087`)。这是修复顺带消掉的重复,不是夹带重构。

### 2.6 `create_skill` 那条路径原本就没东西可丢

`create_new_skill`(`skills.py:1266`)在 `write_skill_files_atomic` 之前有
`_directory_is_nonempty` 守着(`skills.py:1253`),之后才
`initialize_skill_repository`;目标目录此前为空或不存在,**没有可丢的东西**。
修法必须不弄坏它 —— 判据 c 与 §四第 3 条。

---

## 三、修在哪一层,为什么不是另一层

### 3.1 修在 Studio backend 的写入函数,不是引擎

被选错的是**替换的原子单位**,这是写入方自己的决定;引擎的 `compile_skill` 只是被喂了
一个不完整的根,它的诊断(`F-v3-subgraph-target-skill-invalid` 等)**完全正确** ——
那个假根里确实没有 `subgraph/child`。喂对了根,诊断就对了。所以这里没有引擎缺陷,
也不该往引擎里加"如果根是临时目录就宽容一点"之类的东西。

### 3.2 为什么不是"把旧目录整个复制进 tmp,再叠 payload"

这是最省事的写法,也是本 PR **拒绝**的写法,两条理由:

1. **贵且危险。** `.git` 是整个 skill 里文件数最多的目录,Windows 上逐文件复制很慢;
   而且它会与并发的 git 操作抢文件。
2. **更要命的是它要求写入方知道"编译器会读哪些东西"。** 要做得便宜就得挑着复制
   (排掉 `.git`,排掉 `.workspace/runs`、`.workspace/predicts`,留下
   `.workspace/runtime_config.json` 和 `.workspace/import_files`……),
   这等于把**引擎 loader 的知识抄一份到 Studio 的写入函数里**。引擎下次多读一个文件,
   这份拷贝就悄悄失效,而且失效的表现正是本次这种"莫名其妙的 422"。
   仓规「Compile/lint 单出口」与「文档事实唯一所有权」在这里指向同一个结论。

**判真目录不需要这份知识**:lint 看到的就是引擎将要加载的那个目录,零漂移可能。

### 3.3 为什么不是"保留备份目录以防万一"

任务已经明禁,理由本身也成立:留在用户盘上的 `.<name>.bak-<token>` 没有任何东西
负责清理它,下一次写入再留一个,它们会一直堆积。**能被回退用到的信息必须是
有界的、写入结束就消失的** —— 本 PR 的 undo log 是内存里的一批 `bytes`,
函数返回即释放。

### 3.4 为什么不是"引入一份文件所有权账本"

`dpkg` 敢删旧版本留下的文件,是因为它**记着**哪些文件属于这个包。本 PR 没有这样的
账本,所以**一个都不删** —— 这正是判据 a 要的行为,不需要为了删而先造一本账。
「KISS / YAGNI」:今天没有"删掉用户手动加进 skill 的文件"这个需求。

---

## 四、借了什么、拒了什么、为什么

### 借:`rsync` 的默认语义 —— 「删掉我没带来的」必须是显式选择

`rsync` 默认只**新增和覆盖**源端带来的文件,目的端多出来的东西原样留着;要删,
调用方必须显式写 `--delete`。

**借来的**:这条缺省选择本身。本缺陷的题眼正在这里 —— 改前的写入路径相当于
**永远带着 `--delete` 且不给关**,而调用方连"我这次带了全部"都无从表达
(payload 里装不下 `.git`)。改后:这个 API 没有 `--delete`,它删不了任何
它没带来的东西。

**拒绝的**:`rsync` 的整体语义里还有"目的端多余文件是脏东西"这层预设(所以才提供
`--delete`)。这里不成立 —— `.git`/`.workspace`/`subgraph` 不是脏东西,它们是
skill 的正经组成部分,只不过由别的写入者(git、runtime_config、subgraph 编辑)拥有。

**借来的第二条**:`rsync` 也**没有**跨文件的崩溃原子性,它的恢复姿势是
"再跑一遍,它是幂等的"。本 PR 的崩溃恢复姿势相同(§五)。

### 借:git lockfile 的「写临时同级文件,再 rename 顶上」

git 写 `index`/ref 时先写 `<name>.lock`,写完 rename 覆盖目标;rename 在同一文件系统内
是原子的,读者要么看到旧的、要么看到新的,永远看不到写了一半的。

**借来的**:单文件发布的形状。本仓已经有这个东西的现成实现 ——
`apps/studio/backend/app/core/adapters/atomic_file.py`,而且它把**本仓特有的**
那道难关解掉了(该文件 doc 原文):

> `os.replace` 调 `MoveFileExW`,当目标上有任何打开的句柄时会以 `ACCESS_DENIED` 拒绝

所以它在 Windows 上改用 `FileRenameInfoEx` + `FILE_RENAME_FLAG_POSIX_SEMANTICS`。
本仓 Windows 主力机、文件监视器和 Monaco 随时持有这些文件的句柄,
**git 那套 rename 的前提在这里需要额外工作才成立,而这份工作已经做完了** ——
直接复用,不自己再写一遍(仓规 DRY / 底座一)。

**拒绝的**:git 的 `.lock` 同时还是一把**互斥锁**(第二个写者创建 `.lock` 失败即退出)。
本 PR 不借这一半:这条写入路径没有并发写者契约要执行,加锁就得连带解决
"进程崩了留下陈旧锁文件谁来清"这个新问题(YAGNI)。因此临时名用 `mkstemp` 的
随机名而非固定的 `.lock`,两次并发写入不会卡在对方的残留锁上。

### 借:`dpkg` 解包的「旧文件先挪作回退副本」

`dpkg` 解包时把新文件落成 `<file>.dpkg-new`,把旧文件挪成 `<file>.dpkg-tmp`,
再改名顶上;中途失败就从 `.dpkg-tmp` 把旧的放回去。

**借来的**:失败要能**逐文件**放回原样,所以动手之前必须先把"原样"留下来。
本 PR 的 undo log 就是这个,只不过留在内存里(skill 源文件是小文本,一批几 KB),
不落盘 —— 落盘就回到 §3.3 那个"谁来清理"的问题。

**为什么 undo log 存的是 `bytes` 而不是 `str`**:回退必须**逐字节**还原。
文本往返只对"已经符合写入方换行约定"的内容才是逐字节的 —— 旧文件若是 CRLF
(改前的 `target.write_text(content, encoding="utf-8")` 在 Windows 上写出的正是 CRLF),
用文本回写会把它变成 LF,那就不叫"什么都没变"。为此在
`atomic_file.py:43` 新增 `write_bytes_atomically`,`write_text_atomically`
(`atomic_file.py:78`)改为 `write_bytes_atomically(path, text.encode("utf-8"))`。

**这次改写没有改变 `write_text_atomically` 的字节行为**:它原先用
`open(..., "w", encoding="utf-8", newline="\n")`,而 `newline="\n"` 在写入侧
按 Python 文档是"不做任何转换",与 `text.encode("utf-8")` 逐字节等价。

**拒绝的**:`dpkg` 有 journal,断电后 `dpkg --configure -a` 能接着做完。本仓没有,
也不打算为一次 skill 保存造一个(§五写明代价)。

---

## 五、崩溃与中途失败时的行为(明写,不含糊)

改后的执行顺序(`skills.py:185-206`):

1. 校验全部 `rel_path`;
2. 读下每个目标文件的**当前字节**(不存在记 `None`)= undo log;
3. 记下这次写入**将要创建**的目录(`_directories_this_write_creates`,`skills.py:209`);
4. 逐个 `write_text_atomically` 发布;
5. 对 `skill_dir` 本身跑 lint,失败即 `_raise_manifest_validation_failed`;
6. 4 或 5 抛出任何异常 → 用 undo log 回退已发布的文件、收回本次创建的空目录,再 `raise`。

由此,四种结局:

| 情形 | 结果 |
|---|---|
| 全部成功 | payload 落盘;**payload 之外一个字节没动**;无残留 |
| 第 4 步中途失败(磁盘满 / 权限) | 已发布的逐个写回原始字节;新建的空目录收回;抛原异常。目录回到调用前的样子 |
| 第 5 步 lint 判失败 | 同上。这就是"先 lint 通过再落盘"在本设计下的含义:**通过才算提交**,不通过就逐字节撤销 |
| **进程在第 4/5 步之间被杀 / 断电** | **一部分文件是新的、一部分是旧的**,可能残留一个 `.<name>.*.tmp`。`.git`/`.workspace`/`subgraph`/其它未声明文件**一个不少**。没有自动修复,恢复动作是**再保存一次**(幂等) |

**最后一行是本设计相对改前的取舍,必须说清楚,而它是往好的方向变的**:
改前那两次 `os.rename`(`skill_dir`→`backup_dir`,`tmp_dir`→`skill_dir`)之间若被杀,
`except` 根本没机会跑,留下的是 **skill 目录整个消失**,东西全在一个名叫
`.<name>.bak-<token>` 的隐藏目录里,用户界面上这个 skill 直接不见了。
改后最坏是"几个文件新旧混着,再存一次就好"。**两者都不是崩溃原子的,后者的最坏情况轻得多。**

真要做到跨文件的崩溃原子性,需要一份写前日志(write-ahead log)和一个启动时的恢复步骤
—— 那是 `dpkg` 有而本仓没有的东西,为一次 skill 保存引入它不成比例。**这条限制是
已知的、被接受的,不是被忽略的。**

**为什么"lint 之前字节已经落在真目录上"可以接受**:
`write_skill_files_atomic` 与 `lint_skill_path` 都是同步函数,`update_skill_files`
在它们之间没有 `await`,所以整个"发布 → 判定 → 回退"对事件循环是不可分的,
同进程的其它请求看不到中间态。看得到的只有外部观察者(文件监视器线程、用户的编辑器),
而回退结束后磁盘内容与调用前逐字节相同。用这一点点可见的中间态,换掉了 §3.2 那份
必然漂移的"编译器读什么"的知识拷贝 —— 这是本设计最核心的一次取舍。

---

## 六、验收判据

测试文件:`apps/studio/backend/tests/services/test_skill_write_preserves_undeclared_files.py`

| # | 判据 | 覆盖用例 | 改前状态 |
|---|---|---|---|
| a | 提交全部可提交路径后,`.git`(含 history)、`.workspace/{golden,import_files,local_settings.json}` 全部还在,`GRAPH.md` 是新内容 | `test_write_keeps_git_and_workspace_it_never_carried` | **RED**(§2.3 原始输出) |
| a' | 只提交 `GRAPH.md`,未提交的**已声明**文件(`phases/setup/LOGIC.md`、`phases/setup/actions/run.py`、`tools/helper.py`)也一并留下 | `test_partial_write_keeps_the_declared_files_it_did_not_carry` | **RED**(`F-v3-graph-phases-dir-missing`,§2.4) |
| a'' | 带 subgraph 的 skill 存得下来,且 `subgraph/child/**` 完好 | `test_write_of_a_skill_with_a_subgraph_is_accepted` | **RED**(`subgraph path 'subgraph/child' is not a directory`,§2.4) |
| b | lint 失败时旧内容原样(含同批次里**另一个**本来合法的文件也没落地),无 tmp/bak 残留 | `test_rejected_write_leaves_the_skill_untouched` | 改前已 GREEN,本 PR 加锁防回归 |
| c | `create_skill` 行为不变:scaffold 写出、`initialize_skill_repository` 仍跑出初始 commit | `test_create_skill_still_scaffolds_and_inits_repository` | 改前已 GREEN,本 PR 加锁防回归 |
| d | 崩溃行为 | §五整节 | — |
| e | 全套后端测试绿,且**没有**改松任何既有断言 | `1736 passed, 5 skipped`;`git status` 显示本 PR 只改 2 个源文件 + 新增 1 个测试文件,未触碰任何既有测试 | — |

判据 a/a'/a'' 的"无残留"由 `_assert_no_residue` 兜底:它扫 `skill_dir` 的**父目录**,
断言除 skill 自己外没有别的条目 —— 改前那套 `.tmp-<token>` / `.bak-<token>` 正是落在那里。

**本地门禁(全绿)**:`ruff check apps/studio/backend` · `mypy apps/studio/backend/app`
(134 files) · `mypy --strict packages/graph-agent/src`(114 files) ·
`mypy --strict packages/graph-agent-gateway/src`(59 files) ·
`pytest apps/studio/backend/tests`(1736 passed / 5 skipped) ·
`pytest packages/graph-agent/tests`(1572 passed) ·
`pytest packages/graph-agent-gateway/tests`(618 passed) · `pip-audit`(0 CVE)。
前端零改动(`git status` 为证),故不跑前端门禁。

---

## 七、已知遗留(明写,不装作解决)

1. **跨文件的崩溃原子性没有,且不打算有。** 理由与代价见 §五。
2. **回退期间文件监视器会看到写入与回退两轮事件。** `record_api_write`(用于抑制
   监视器回声)由调用方在 `write_skill_files_atomic` **返回之后**才调
   (`skills.py:1089-1090`),所以被回退的那一批不会被抑制,监视器可能广播一次
   "变了"再广播一次"变回来了"。净内容不变,监视器本身是 advisory 的。
   要根治得把 `record_api_write` 挪进写入函数 —— 但 `create_new_skill` 这条路径
   今天并不调它,挪动会顺带改掉 create 的行为,属于另一件事,不夹带。
3. **`io/inputs.json` 仍在 `validate_skill_file_path` 的放行名单里,而引擎已经拒收它。**
   写本 PR 的测试夹具时实测到:提交 `io/inputs.json` 会拿到
   `F-v3-graph-io-physical-file-deprecated`「physical root IO file 'io/inputs.json'
   is not supported」。即 Studio 的路径白名单与引擎的当前契约已经对不上 ——
   一条**永远无法通过校验**的合法路径。这是既有 drift,与本缺陷无关,
   一个 PR 一个任务,单独立项。
4. **`write_text_atomically` 发布的文件是 owner-only(0600)。** 这是
   `atomic_file` 既有的、有意为之的性质(该模块 docstring 说明是为了 API key 类文档),
   本 PR 复用它,于是 skill 源文件在 POSIX 上从默认权限变成 0600。桌面单用户 app、
   文件属主就是运行 app 的人,影响是"更严一点";Windows 上不适用。
   记在这里是因为它是一次**行为变化**,不是因为它是个问题。
