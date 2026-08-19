# 决议 2026-08-19:改动入库文件的测试,必须按字节还原它

状态:已实施(本 PR)
影响模块:engine 测试(`packages/graph-agent/tests`)
发现方式:后台任务提示「Fix test that rewrites spec YAML with CRLF on Windows」,
由用户在 2026-08-19 指派修复。另有独立现场证据:本仓这一轮每次 `wt-ship` 前都要
先跑一次 `git checkout -- packages/graph-agent/spec/round28-manifest-schema.yaml`,
仓规文档里也把它当成"CRLF 幽灵 diff"当作既定事实绕着走 —— 绕了很久,没人问过它从哪来。

---

## 一、决策

`test_task7_hash_lock_detects_mutated_schema_fixture` 会**真的改写**一个入库文件
(`packages/graph-agent/spec/round28-manifest-schema.yaml`)来验证哈希锁抓得住篡改。
改写它是这条测试的手段,**按字节还原它是这条测试欠下的债**。

具体两条:

1. 读写一律走字节:`read_bytes()` / `write_bytes()`,变异也在 `bytes` 上做。
2. 测试自带后置断言 `_sha256(SCHEMA_PATH) == original_hash` —— 「跑完之后这个文件
   和跑之前一模一样」由测试自己声明并检查,而不是靠人事后 `git status` 发现。

---

## 二、论据

### 2.1 缺陷(修前代码原文)

```python
original_content = _read(SCHEMA_PATH)                 # _read = path.read_text(encoding="utf-8")
...
finally:
    SCHEMA_PATH.write_text(original_content, encoding="utf-8")
```

`read_text()` 走 **universal newlines**:文件里的 `\r\n` 与 `\n` 一律读成 `\n`。
`write_text()` 是文本模式,默认 `newline=None`,写出时把 `\n` 翻成 `os.linesep`
—— Windows 上就是 `\r\n`。于是一次"读出来再写回去"把一个以 LF 入库的文件改写成 CRLF。

### 2.2 实测(本机 Windows,修前代码)

```
before: CRLF=0    lone LF=358
1 passed in 9.78s
after : CRLF=358  lone LF=0
 M packages/graph-agent/spec/round28-manifest-schema.yaml
```

**测试报 `1 passed`,同时把一个入库文件全文改了行尾。** 这是本条最要紧的一点:
它不是"测试失败了",是"测试通过了并且留下了破坏",所以没有任何门禁会喊。

### 2.3 后果为什么值得单修

`git` 的 `core.autocrlf=true`(本机系统级配置)在 `git add` 时把 CRLF 归一化回 LF,
所以 blob 从未变过 —— 这正是它表现为**幽灵 diff** 的原因:`git status` 说文件改了,
`git diff` 却看不出内容差异,`git add` 之后又消失。代价不是数据损坏,是**噪声**:
每个人在每次 ship 前都要先判断一次"这个 M 是不是我干的",而这个判断没有信息量。
仓规里那条"ship 前先 `git checkout --` 它"是绕行,不是修复。

### 2.4 只有这一处

全仓搜过 `packages/graph-agent/tests` / `apps/studio/backend/tests` /
`packages/graph-agent-gateway/tests` 里写入**入库**路径(`PACKAGE_ROOT`/`BACKEND_ROOT`
派生)的测试:除本条外全部是只读(`read_text`),其余 `write_text` 都写在
`tmp_path` 造出来的 fixture 里。所以不抽公共 helper —— 没有第二处可共享(「三次成律」)。

---

## 三、借了什么,拒了什么

**借 `git` 自己的分工**:内容在仓里以 LF 规范化保存,行尾转换只发生在 checkout/add
这一层,任何**内容处理**环节都不该顺手改行尾。同理,本仓
`docs/development/CROSS_PLATFORM.md` 立的是「文本一律 UTF-8 + LF」。

**拒绝**在 `write_text` 上加 `newline=""`:那能修好这一处,但把「不要翻译行尾」表达成
一个容易在下次编辑时被删掉的关键字参数;字节 I/O 让"不翻译"成为**结构上的事实** —— 
`write_bytes` 没有可以翻译行尾的地方。

**拒绝**给测试加 `@pytest.mark.skipif(windows)`:那是把缺陷改称平台限制,而这条测试
在 Windows 上验的东西和别处一样有效(`cross-platform-smoke (windows-latest)` 是必需门禁)。

**拒绝**在 `conftest.py` 里加一个"跑完自动 checkout 脏文件"的 fixture:那会让**任何**
测试都能悄悄改坏入库文件而不被发现,把一个具体缺陷换成一道全局的掩盖机制。

---

## 四、验收判据与实测

| # | 判据 | 修前 | 修后 |
|---|---|---|---|
| a | 跑完这条测试后,spec 文件字节与跑前完全一致 | CRLF=358 / LF=0(**坏**) | CRLF=0 / LF=358 |
| b | 跑完后工作区没有因它产生的改动 | `M …round28-manifest-schema.yaml` | 无 |
| c | 测试原本验的东西不变:哈希锁抓得住篡改 | passed | passed |
| d | 后置断言在还原被破坏时会红 | —— | 由 `assert _sha256(...) == original_hash` 承担 |

修后整份 `test_round28_contract_manifests.py`:`18 passed in 62.66s`,
文件字节 `CRLF=0 lone LF=358` 与跑前相同。

---

## 五、已知遗留(明写,不装作解决)

1. **判据 d 没有做变异验证。** 我没有在仓外副本里把 `write_bytes` 改回 `write_text`
   再跑一次去证明那条后置断言会红 —— 它的因果链只有一步(还原写坏 → sha 不等),
   而 §2.2 的实测已经直接给出了"写坏之后字节确实不同"这一半。如实记在这里,
   不写成"已验证"。
2. **仓规文档里那句"ship 前 `git checkout --` 它"没有一并删掉。** 那句话散落在
   多个 agent 指令模板与 `AGENTS.md` 语境里,属于文档面的收尾;本 PR 只改代码,
   一个 PR 一件事。它现在是**多余但无害**的一步。
3. **测试仍然改写一个入库文件。** 更彻底的做法是把 spec 复制到 `tmp_path` 再让哈希锁
   去查那份副本 —— 但哈希锁测试读的是固定路径常量,改它要动被测对象本身,
   超出本条范围。本 PR 只保证"改完能还原干净"。
