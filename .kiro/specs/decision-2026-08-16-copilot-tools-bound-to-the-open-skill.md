# 决议:Copilot 的结构化工具绑定到"这条会话打开的那个 skill",skill_id 不再由模型给出

- 日期:2026-08-16
- 范围:`apps/studio/backend/app/services/copilot_skill_binding.py`(新)·
  `copilot_tools.py` · `copilot.py` · `cli_mcp_surface.py` · `skills.py`
- 相关 PR:本决议同 PR 落地
- 触发:2026-08-15 两次实证,Studio Copilot 打开一个工作区、却对**另一个** skill 目录
  发起写入,两次都只被人工审批卡拦下

## 一、现象与根因

### 现象(实测参数,原样抄录)

Copilot 打开工作区 `D:\coding\skills\story-deconstruction-v3-lab`,读该工作区的
`GRAPH.md` 看到 `name: story-deconstruction-v3`,于是拿这个值当 `skill_id` 调
`write_skill_file`:

```json
{"skill_id": "story-deconstruction-v3",
 "path": "subgraph/global-synthesis/phases/export/actions/export_story_framework.py",
 "expected_hash": "skip", "content": "..."}
```

该 skill_id 在 `%APPDATA%\AgentStudio\skill_index.json` 里解析到的是**另一个目录**
`D:\coding\skills\story-deconstruction-v3`。

### 根因不是"模型猜错了",是"我们逼它猜"

会话本身**早就知道**权威答案:`stream_query(skill_id, ...)`
(`app/services/copilot.py:1109`)从前端拿到打开的 skill,并据它解析出唯一 cwd
(`_resolve_copilot_workspace_dir`,同文件 986-1031 行)。也就是说"我在哪个 skill 上
工作"这件事**有唯一 owner**。

而工具契约却把它列成模型必填项:

- `copilot_tools.py`(修复前 256-266 行)`write_skill_file` 的 input_schema 把
  `"skill_id"` 写进 `required`;
- 同文件 272 行 `skill_id = str(args.get("skill_id", "")).strip()` 直接采信模型给的值,
  与会话打开的工作区没有任何关系。

一个模型面对一个自己没有权威来源的必填字段,只能从手边找一个看起来像答案的东西 ——
打开的 `GRAPH.md` 里那行 `name:` 就是最像的那个。复制 skill 目录时不会改写
`name:`,于是副本的 manifest 一直在宣称源 skill 的 id,猜测就必然落到别人家。

这一条在本仓**已经被判定过一次**。CLI 会话侧的同类事故写在
`apps/studio/tauri/src/native_fs.rs:1455-1461`,原文:

> A CLI session used to be told nothing about which skill it was bound to, so the
> model guessed one from the manifest `name:` — and once guessed the id of a
> DIFFERENT, protected skill and edited that instead (exp-B R0, 2026-07-31). The
> index is the registry that answers this, so the id is read from there rather
> than accepted from whoever opened the session.

面板 copilot 的 MCP 工具面从未做同样的收口,这次补上。

## 二、决策

### D1 · 会话工具面按 skill 绑定,`skill_id` 从模型面前的 schema 里删掉

新增 `CopilotSkillBinding{skill_id, workspace_root}`,由
`get_or_create_session` 在建 SDK 会话时用**它自己已有的两个事实**构造(会话的
skill_id + 那次解析出的 workspace 目录),再交给
`build_copilot_mcp_servers(binding)`。绑定层对**每一个声明了 `skill_id` 的工具**做两件事:

1. 从 input_schema 里摘掉 `skill_id`(JSON-schema 形态同时摘 `required`);
2. 调用时无条件写入 `args["skill_id"] = binding.skill_id`。

没声明 `skill_id` 的工具(LLM 配置、fetch_web_page)原样透传,不被牵连。

### D2 · 每次调用前重新核对 (id, 目录) 这一对

绑定记的是**两件事**,不是一件。调用前 `resolve_skill_dir(binding.skill_id)` 必须仍然
解析到 `binding.workspace_root`,否则工具直接返回结构化错误、**工具体一行都不跑**。

理由是索引 key 可变:key 由**裸目录名**派生
(`native_fs.rs:1272-1290` `skill_id_from_workspace_root`),而 `upsert_skill_index_entry`
(同文件 1482-1500)是直接 `insert` 覆盖 —— 后打开的同名目录会把这个 key 顶走。只绑 id
的会话会跟着漂到顶替者那棵树上;绑住 (id, 目录) 这一对,漂移就变成一次可观察的拒绝。

### D3 · 要铸**新** skill 的工具改用 `new_skill_id`

`create_skill` 的参数由 `skill_id` 改名 `new_skill_id`。它给的是一个**新名字**,不是对
已有 skill 的引用,模型无从猜起,也不该被绑定覆盖。改名之后分界线可以一句话说清,不需要
维护例外表:

> `skill_id` 在整个 MCP 工具面上永不由模型给出;要铸新 skill 的工具用 `new_skill_id`。

`fork_skill` 的源自此固定为"当前打开的 skill",描述同步改写。

### D4 · `GRAPH.md` 的 `name:` 与注册 id 不一致时,发一条 Studio-owned preflight 告警

诊断码 `STUDIO_MANIFEST_NAME_NOT_REGISTERED_ID`,severity=warning,落在
`GRAPH.md` 的 `name` 字段那一行,由 `_studio_preflight_lint_errors` 产出。

- **为什么归 Studio 而不是 engine**:`skill_index.json` 是 Studio 私有的注册表,engine
  从来不知道它存在。按 AGENTS.md「Compile/lint 单出口 + 全量聚合 + 同一份诊断」,这正是
  "Studio 自有 preflight"的定义域,不得在 engine 里发明 Studio-only 编译规则。
- **为什么是 warning 不是 error**:注册表卫生问题不是图缺陷,不该把编译判失败。
- **为什么未注册的目录一律静默**:实时 lint 会在 OS 临时目录里编译一份沙箱副本
  (`lint_skill_changed_markdown`);对那份副本报"你没注册"会变成每敲一个键多一条假诊断。

## 三、借了什么、拒了什么

| 参考对象 | 借了什么 | 为什么 |
|---|---|---|
| 本仓 CLI 会话修复(`native_fs.rs` `registered_skill_id_for_root`;`lib.rs:3718-3726` 把 `SessionSkillContext{skill_id, workspace_root}` 注进会话) | "身份从注册表读,不从打开者/模型收";以及**记 id 与目录这一对**的字段形状 | 同一缺陷、同一仓、已被判定过;它记两个字段而不是一个,正是本决议 D2 所需 |
| 现有写边界 hook(`copilot._make_write_boundary_hook`) | 绑定按会话建、**每次调用都查**,而不是建会话时查一次 | 索引在会话存续期间可变,一次性检查证明不了调用当时的事实 |
| **拒绝**:校验模型传来的 `skill_id` 与会话是否一致 | — | 校验让非法状态仍可表达,把结构性保证降级成"未来每个工具都记得比一下"的纪律。删掉字段则错误调用**说都说不出来**(AGENTS.md 编程规范「让非法状态不可表示」) |
| **拒绝**:只绑 id 不绑目录 | — | 见 D2:key 会被顶替,只绑 id 挡不住漂移 |
| **拒绝**:`build_copilot_mcp_servers(binding=None)` 时静默返回空工具面 | — | 一个没有工具的会话在界面上与"MoirAI 决定不用工具"无法区分。改成 `build_options` 在边界直接 `raise`(Fail fast) |

## 四、验收判据

1. 两份内容相同、目录名不同的 skill 副本(副本 `GRAPH.md` 的 `name:` 仍指向源 skill),
   会话绑在副本上时,模型即使传源 skill 的 id,写入仍落在副本、源目录字节不变。
2. 绑定后的工具面上,**没有任何**工具向模型暴露 `skill_id` 参数。
3. 索引把绑定 id 改指到别的目录后,工具调用返回错误且不产生任何写入。
4. `create_skill` 仍能用 `new_skill_id` 铸出新 skill,不被绑定覆盖。
5. 副本的 `name:` 与注册 id 不一致时,lint 给出一条指向 `GRAPH.md` `name` 字段的
   warning,且 `status` 仍为 `passed`;一致时、以及未注册目录静默。

自动化位置:
`apps/studio/backend/tests/services/test_copilot_skill_binding.py`(1-4)·
`apps/studio/backend/tests/services/test_skill_identity_preflight.py`(5)。

## 五、未做的部分(明确不装作已解决)

### 5.1 CLI 表面(`/mcp`)仍不绑定

`app/services/cli_mcp_surface.py` 把同一批工具再挂一份成 streamable HTTP server 给
"Open in CLI" 拉起的 codex/claude 用。它**没有**按会话绑定,因为 `/mcp` 是
`main.lifespan` 建一次的**进程级**挂载,服务任何连上来的 CLI 进程,连接本身不携带
"我打开的是哪个 skill"。

CLI 侧现有对策在启动那一端:`lib.rs:3718-3726` 从注册表反查后把
`SessionSkillContext{skill_id, workspace_root}` 注进会话配置,即**告诉**模型它绑在哪 ——
这正是 2026-07-31 那次事故的既有修复,但它是"告知",不是"不可表达"。要把这条 HTTP 表面
也做成不可表达,得先给 `/mcp` 一个连接级会话身份(握手时携带 workspace,或每条 CLI 会话
一个带 token 的挂载点),那是独立的一件设计工作。

### 5.2 索引 key 仍是裸目录名,嵌套子图仍能占用顶层 key

实测索引里存在:

```
text-segmentation -> D:\coding\skills\story-deconstruction-v3\subgraph\text-segmentation
```

即一个**嵌套子图目录**被注册成顶层 skill,key 是裸目录名。两棵同源 skill 树必然在这个
key 上撞车,而 `upsert_skill_index_entry` 是覆盖写,后开的赢。

本次**没有**改这个派生规则。理由三条,都不是"来不及":

1. 这是**跨三个语言的命名通则**:同一份派生逻辑存在于 Rust
   (`native_fs.rs:1277` `skill_id_from_workspace_root`)、TS
   (`components/studio/workspace-identity.ts:57` `skillIdFromWorkspaceRoot` 与
   `components/welcome/utils.ts:30` `skillIdFromPath`),且 Rust 那份的注释明写"byte-for-byte
   port ... Parity is asserted in tests"。改它属于结构性变更,按全局规则须先呈方案、由用户
   确认后再动手,不能顺手带过。
2. 它造成的**跨 skill 写入**后果已被 D2 挡住:key 被顶替后,会话工具面在动手前就发现
   id 不再指向自己的工作区并拒绝,而不是写到顶替者那里。剩下的是可用性问题(那棵树按 id
   打不开了),不再是静默写错。
3. 本地无法为 Rust 半边把门:tauri 的 `cargo test --lib` 在 CI 里按冷编译 45 分钟预算跑,
   我不能在本机可靠地跑绿它,而"没跑绿就推"违反本仓的门禁纪律。

真要修,方向应当是**让 id 由路径派生且唯一**(例如 `<目录名>-<路径哈希前 8 位>`),
并在三处实现保持 parity —— 这与既有裁决同向:`services/skills.py:1271-1276` 已写明
「MVP1 design: subgraph identity is a path, not a registry id」。这条留给后续独立决议。
