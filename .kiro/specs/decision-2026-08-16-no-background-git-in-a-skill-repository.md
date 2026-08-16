# 决议 2026-08-16:skill 仓的对象库归 Studio 独占,git 不许往里派后台进程

状态:已实施(本 PR)
影响模块:Studio backend(`apps/studio/backend`)+ Studio Tauri native-fs
(`apps/studio/tauri`)
发现方式:必需门禁 `quality-gates` 上的存量 flaky
`test_publish.py::test_publish_idempotency_retry_finds_release_marker_beyond_default_history_window`
(台账 W2-23),两天内咬中三次

**先说清本决议的性质**:这**不是**一份"根因已坐实、按根因修掉"的决议。
根因**没有坐实**,而且本次复核**推翻了**上一位调查席根因假设里的关键一环
(见 §2.4)。本决议做的是两件能各自独立成立的事:①把"谁在写这个仓的对象库"
这件事收成**只有 Studio 一个答案**——这是一条不依赖 flaky 是否被修好的正确性
要求;②把这条用例守的契约,同时用一条**完全不碰文件系统**的测试钉住,使得
它下次再红时,"是代码回归还是环境"能一眼分清。

---

## 一、决策

**一句话**:Studio 自己派出的每一个 git 进程,都必须带上
`-c maintenance.auto=false -c gc.auto=0`——skill 仓的对象库只有 Studio 一个写者,
git 不得往里 fork 它自己的后台维护进程。

具体三条:

1. **落在调用处,不落在仓配置**。Studio 的两个 git 出口——Python 侧
   `apps/studio/backend/app/services/git_local.py` 的 `run_git`、Rust 侧
   `apps/studio/tauri/src/native_fs.rs` 的 `git_command`——在子命令**之前**
   无条件加上这两个 `-c`。不往 skill 仓的 `.git/config` 里写任何东西。
2. **两个键都给,不做版本分支**。`maintenance.auto` 管 git ≥2.29 的
   `git maintenance run --auto`,`gc.auto` 管更老的 `git gc --auto`;git 对不认识
   的配置键静默忽略,所以不需要判断 git 版本。
3. **这条保证由测试直接观测,不靠"配置写对了"间接推断**。判据是
   `GIT_TRACE=1` 下 git 自报的子进程清单里没有 maintenance / gc——即
   **没有派出后台写者**这个事实本身,而不是某个配置键等于某个值。

---

## 二、论据

### 2.1 两种 CI 报错是同一件事:一个 loose 对象从磁盘上消失了

三次咬中,两种 stderr:

- run 31929887431(`main`,2026-08-16T05:54),`gh run view --log-failed` 原文:
  ```
  apps/studio/backend/tests/routers/test_publish.py:687: in test_publish_idempotency_retry_finds_release_marker_beyond_default_history_window
  E   app.services.git_local.GitCommandError: git commit --allow-empty -m manual-padding-7 failed with exit code 128: fatal: could not parse HEAD
  ```
- run 31900653780(`main`,2026-08-15T18:21),原文:
  ```
  apps/studio/backend/tests/routers/test_publish.py:692: ...
  apps/studio/backend/tests/routers/test_publish.py:1297: in _release_marker_commit_count
  E   app.services.git_local.GitCommandError: git log --format=%s failed with exit code 128: error: Could not read 0d8b504041db9c40b68ddd15c2caed661780161c
  E   fatal: Failed to traverse parents of commit 48070eb7a950dab12be1392faa93995374ab0661
  ```
- run 31934149432(PR #843,attempt 1)与第二条同型。

本次**第一手**把这两种 stderr 复现出来了,手法是确定性的:在一个正常的 git 仓里
**删掉一个 loose 对象文件**,别的什么都不做。实测输出:

```
PROBE A -> git commit --allow-empty -m manual-padding-7
fatal: could not parse HEAD
rc=128

PROBE B (deleted ancestor=9c13f7e10ff71dd20363003bcf195a39645a38a0 child=7b47c91fe49a61be3b9c5aed7f6079958bdfbc94) -> git log --format=%s
manual-padding-5
error: Could not read 9c13f7e10ff71dd20363003bcf195a39645a38a0
fatal: Failed to traverse parents of commit 7b47c91fe49a61be3b9c5aed7f6079958bdfbc94
rc=128
```

删的是 HEAD 自己的 commit 对象 → 第一种;删的是祖先链上的 commit 对象 → 第二种,
两行、同序、同措辞。**所以 CI 那三次红,磁盘上的状态是同一个:ref 还指着某个
对象,而那个对象的文件不在了。**

### 2.2 git 2.54 每次 `git commit` 都往这个仓里 fork 一个脱离的后台进程

CI runner 的 git 版本,来自 run 31929887431 自己的日志:`git version 2.54.0`。
本机同版本(`git version 2.54.0.windows.1`)。`GIT_TRACE=1` 下一次普通 commit 的
实测输出:

```
03:10:33.525254 run-command.c:673       trace: run_command: git maintenance run --auto --no-quiet --detach
03:10:33.525254 run-command.c:934       trace: start_command: git maintenance run --auto --no-quiet --detach
03:10:33.647390 git.c:502               trace: built-in: git maintenance run --auto --no-quiet --detach
```

`--detach` 的意思是这个子进程**脱离父进程独立活下去**:`git commit` 返回时它可能
还在跑,而 Studio(以及测试)既不等它、也不知道它存在、更不回收它。它和前台命令
操作的是**同一个对象库**。

这台机器上 global/system 的 `gc.*` / `maintenance.*` 全为空(`git config --global
--get-regexp '^(gc|maintenance)\.'` 与 `--system` 同一命令均 rc=1,无输出),
所以上面是 git 2.54 的**默认行为**,不是本机配置造成的。

### 2.3 关掉它是有效的,而且是 git 自己提供的开关

`git help -c` 里两个键都在:

```
gc.auto
maintenance.auto
```

实测(同一个仓,同一条 commit):

| 命令 | trace 里 maintenance/gc 相关行数 |
|---|---|
| `GIT_TRACE=1 git commit --allow-empty -m control` | 3 |
| `GIT_TRACE=1 git -c maintenance.auto=false -c gc.auto=0 commit --allow-empty -m flagged` | 0 |

并且这两个 `-c` **不会**在仓里留下任何痕迹,也不影响 `git config --local` 的写入:
实测在带 `-c` 前缀的前提下依次跑 `init` / `config --local user.name alice` /
`config --local user.email alice@studio.local` / `add -A` / `commit -m initial-skill`,
结果是

```
user.name=alice  email=alice@studio.local
persisted maintenance.auto: [] gc.auto: []
d563f69 initial-skill
```

### 2.4 **本次复核推翻了上一位调查席根因链里的一环**——不能拿它当结论

上一位调查席给的链条是:101 次 padding commit 把 loose 对象顶过 100 → git 的
loose-objects 维护任务打包并 unlink → 前台命令读不到对象。**这一环在本次复核里
对不上,有两处硬证据**:

1. **run 31929887431 是在 `manual-padding-7` 上死的**——padding 循环才走到第 8 次,
   仓里的 loose 对象大约二三十个,离 100 差得远。它不可能是"越过 100 才触发"
   造成的。
2. 本机 git 2.54 上直接量:按用例的样子造一个仓(1 次真实 commit + 101 次
   `--allow-empty`),**loose 对象 106 个**;此时**前台**跑一次默认的
   `git maintenance run --auto --no-quiet`,trace 只有一行 `built-in`,没有任何子任务,
   跑完 `loose after: 106  packs after: 0`——**什么也没做**。上一位调查席测出
   "99 次 commit 之后打包"用的是显式 `--task=loose-objects`,那不是 `--auto`
   默认会走的路径。

所以:**"谁删了那个对象"至今没有第一手证据**。已知的只有 §2.1(删除确实发生了)
和 §2.2(有一个我们不掌握、也不等待的后台 git 进程在同一个仓里)。本决议不宣称
后者就是前者的元凶。

### 2.5 那为什么还要修它——因为它本身就是一处不该存在的状态

Studio 对 skill 仓的用法是**读-改-写序列**,而且明写着自己在做原子推进:
`git_local.py:229-282` 的 `_commit_empty_snapshot_once` 先
`rev-parse --verify HEAD^{commit}` 拿到 head_sha,再 `rev-parse <head>^{tree}`,
再 `commit-tree <tree> -p <head>`,最后 `update-ref` 带 CAS 比对;
`:189-227` 的 `commit_empty_snapshot` 外面还套着 `self._snapshot_lock(skill_dir, message)`(`:197`)。
这套东西的前提是:**在我这几步之间,没有别人在动这个对象库。**

而 §2.2 说明这个前提今天不成立:每一次 commit 都会派出一个我们看不见、不等待、
不回收的写者。这不是"可能有 bug",这是**显式状态与唯一 owner** 这条仓规
(AGENTS.md「Coding Standards」)在这里被破坏了——对象库有两个写者,其中一个
Studio 根本不知道它的存在。修掉它,与 flaky 是否因此消失是两件事:

- 如果 flaky 消失 → 说明它就是元凶(那时才可以把 §2.4 的空缺补上);
- 如果 flaky 仍在 → 说明删除者在 pytest 和 git 之外,而候选池已经少了一个,
  下一步取证的方向也就窄了(见 §六)。

两种结局下,这个改动都不需要回滚。

---

## 三、修在哪一层,为什么不是另一层

**修在"Studio 怎么起 git 进程"这一层**,即两个 `run_git`/`git_command` 出口。
Python 侧 `git_local.py:615-617` 是全后端唯一的 git 子进程出口(逐项核实:
`grep -rn "subprocess" apps/studio/backend/app` 里与 git 相关的只有
`git_local.py:7/615/625` 三处,`git_collab.py` 不起子进程);Rust 侧
`native_fs.rs` 非测试代码里的 git 出口只有 `run_git`(`:1416`)与
`git_has_staged_changes`(`:1456`),本 PR 把后者也并到 `git_command` 上,于是
Rust 侧也只剩一个出口。

**为什么不是"往 skill 仓写 `git config --local gc.auto 0`"**(即 §四要借的那个
工程的原始做法):

- 那样保证的是**仓的状态**,而仓的状态可以不存在。Studio 会打开**不是它建的**
  目录(`skills.py:1204` 的 `create_skill` 之外,还有用户自己的目录、拷贝进来的
  bundled skill),init 没跑过的仓就没有这条配置。落在调用处则不存在"忘了配"的
  状态可表达。
- skill 仓是**用户自己的长期 git 仓**,用户可能在终端里直接用它。把 Studio 的
  运行策略写进他的 `.git/config`,是 Studio 把自己的关切泄漏进不归它管的数据。

**为什么不是改那条用例**(减少 commit 数 / 换写法绕开):101 次是那条用例的
**判据本身**——它守的是"marker 查找不带历史窗口",而默认窗口是 100
(`git_local.py:370` `def list_history(self, skill_dir: Path, *, limit: int = 100)`)。
少于 101 就守不住任何东西。把用例改小等于把门禁调松,是拿测试迁就环境。

**为什么不是给失败加重试 / `pytest.mark.flaky`**:仓规明禁"用 try/except 把坏状态
吞进深处",重试装饰器是同一类回避——它把"对象消失了"这个事实变成看不见,
下一次以真实缺陷的形式出现时同样看不见。

---

## 四、借了什么、拒了什么、为什么

### 借:actions/checkout「驱动 git 的工具,先把 git 的后台维护关掉」

参照对象是 `actions/checkout`,证据就在本仓自己的 CI 日志里——每次 checkout 都有
一组
```
##[group]Disabling automatic garbage collection
[command]/usr/bin/git config --local gc.auto 0
```
它的取舍很清楚:一个工具要在一个仓上跑一串有序的 git 命令时,它把 git 自发的
后台重写关掉,宁可让仓"不被维护"也不要"被别人在中途改"。**借的是这个取舍**:
维护的收益远小于并发重写的风险,skill 仓又小又本地,不维护没有代价。

### 拒:它的落地机制(写进仓的 `.git/config`)

checkout 操作的是**一次性的 CI workspace**,那个仓跑完就删,往它的配置里写什么
都无所谓——这个前提在本仓不成立(理由见 §三)。所以只取"关掉"的判断,机制换成
每次调用带 `-c`。

### 拒:自己发明一套"给 git 加锁 / 等后台进程结束"的机制

git 自己提供了 `maintenance.auto` / `gc.auto` 两个开关(§2.3 的 `git help -c`),
问题在上游就有出口。自建互斥(等 detached 进程、扫 PID、加文件锁)在本仓还多一重
不成立的前提:Windows 主力机 + Git Bash 下 PID 不可见(仓规原话),而且我们要
挡住的那个进程**本来就不该被派出来**——不派出来,就没有需要协调的对象。

### 拒:把这条保证做成"断言配置键的值"

`assert git config --get maintenance.auto == "false"` 只能证明配置写对了,证明不了
**没有后台进程被派出去**。换一个 git 版本换一个键名,这种断言会继续绿。所以判据
选 `GIT_TRACE=1` —— git 自己报出它派了哪些子进程,是对"有没有并发写者"的直接
观测。这一条借的是**因果验证**这条仓规:动作成功由动作之后的可观察结果证明,
不由状态标签证明。

---

## 五、验收判据

1. **Python 侧行为**:`test_run_git_commit_spawns_no_background_git_process`
   ——经 `run_git` 发出的一次真实 commit,`GIT_TRACE=1` 的输出里不含
   `maintenance`,也不含 `gc --auto`。修前 RED 实测(节选):
   ```
   E       AssertionError: ...
   E         trace: run_command: git maintenance run --auto --no-quiet --detach
   E         trace: start_command: git maintenance run --auto --no-quiet --detach
   E         trace: built-in: git maintenance run --auto --no-quiet --detach
   ```
2. **Rust 侧行为**:`native_fs::tests::studio_git_commit_spawns_no_background_git_process`
   ——同一判据,`GIT_TRACE` 只挂在这一个子进程上(不动进程级环境变量,所以
   cargo 并行跑测试不会互相干扰)。修前 RED 实测:
   ```
   thread '...studio_git_commit_spawns_no_background_git_process' panicked at src\native_fs.rs:2998:9:
   background git spawned: ...
   trace: run_command: git maintenance run --auto --no-quiet --detach
   ```
3. **argv 契约**:`test_run_git_success_captures_output` 与
   `test_git_service_wrappers_build_expected_commands` 断言**每一条**经过
   `GitLocalService` 的命令都带着这个前缀(后者在 fake 里对每次调用校验前缀,
   再比对剥掉前缀后的子命令)。
4. **不碰文件系统的契约测试**:`test_release_marker_lookup_scans_unbounded_history`
   ——`find_empty_snapshot_commit_with_exact_subject` 发出的 `git log` 不带
   `-n` / `--max-count`。**如实说明:这条测试从写下第一刻就是绿的**,它不是缺陷
   复现,而是把 W2-23 那条用例守的契约,搬到一条不依赖真实 git、不依赖磁盘、
   不依赖时序的测试上。它的价值在下一次:若那条昂贵用例再红而这条仍绿,红的
   就不是契约回归。
5. **原用例**:`test_publish_idempotency_retry_finds_release_marker_beyond_default_history_window`
   本机连跑 20 次全绿。**这不构成 flaky 已修好的证据**——它在本机从来就没有
   失败过(上一位调查席 14 次、本次 20 次,合计 34 次零失败),本机唯一能证明的是
   没有引入回归。

---

## 六、已知遗留(明写,不装作解决)

1. **根因未坐实**。谁在 CI 上删掉了那个 loose 对象,没有第一手证据;而且上一位
   调查席给出的"越过 100 个 loose 对象触发打包"这一环,已被 §2.4 的两处证据
   推翻,**不得再作为结论转述**。本决议只主张:少了一个不该存在的并发写者。
2. **下一步取证方式已经想好,本 PR 没有做**:在 CI 的 pytest 步骤前 export
   `GIT_TRACE2_EVENT=<目录>`,失败时把该目录和失败仓的 `.git` 一起上传。
   git 的 trace2 会带时间戳记下每个子进程(含 detached maintenance、pack-objects、
   prune-packed),能直接看出失败瞬间谁在跑。之所以现在不加:它只有在这次修完
   **仍然复发**时才付得出收益,现在加等于为一个可能不发生的事件常驻一份 CI 配置。
   若 W2-23 在合并后再次咬中,这是第一件该做的事。
3. **本 PR 不做真机点验**。改动只影响 Studio 自己起的 git 进程的命令行,没有 UI
   面。证据是离线的:两侧单测 + 全套后端 pytest + `cargo test --lib`。
4. **测试里模拟"外部并发写者"的那几处仍用裸 `git`**
   (`test_git_local.py` 两条 CAS 用例里 `original_run(["git", "commit", ...])`,
   以及 `test_skill_git_history.py:113` 的 `_git` 帮手)。这是**故意**的:它们扮演的
   就是 Studio 之外的写者,给它们套上 Studio 的标志会让它们不再像被模拟的那个东西。
5. **上一位调查席顺带报出的另一处缺陷未处理**:`skills.py:155-181` 的
   `write_skill_files_atomic` 用 `os.rename(skill_dir → backup)` + `os.rename(tmp → skill_dir)`
   + `_rmtree_with_retry(backup)` 换目录,而 tmp 目录里没有 `.git`,所以一次
   `PUT /api/skills/{id}` 会把该 skill 的整个 git 仓连历史一起删掉。本次复核确认它
   **与本 flaky 无关**(它的调用点只有 `update_skill_files`(`:1023`)与
   `create_skill`(`:1204`),publish 路径不经过),因此按"一个任务一个 PR"不夹带,
   单独立项。
