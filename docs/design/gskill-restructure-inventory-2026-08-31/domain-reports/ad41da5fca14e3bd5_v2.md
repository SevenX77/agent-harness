修订已落盘并推上去了,但有一个流程事实需要先说清楚。

**#1074 在我开始修订之前就已经 auto-merge 合入 `main` 了**(合入提交 `2ae16455`),远端分支随之删除。所以"在同一分支上 push、让原 PR 带上修订"这条路已经不成立——我 push 时 git 是新建了一个同名分支,不会回到已合并的 #1074。按仓规 `main` 只能通过绿色 PR 进入,唯一可行的落法是把修订提交 rebase 到最新 `main` 之上、单独开一个 PR。已这么做:

- **修订 commit**:`44cf1ffa docs(design): 执行模型收敛——host-native 移除,Studio 门禁六改五`(rebase 到 `origin/main` 之后的哈希;rebase 前为 `5ab51beb`)
- **PR**:https://github.com/SevenX77/agent-harness/pull/1075(auto-merge/squash 已武装,CI 绿即自动合入)
- **改动范围**:相对 `main` 只有两个文件、46 增 33 删——`docs/design/gskill-restructure-decision-2026-08-31.md` 与 `docs/development/DELIVERY_LEDGER.md`,没有把 #1074 的内容重复带进来。

**门禁结果**:rebase 后重跑 `uv run pytest apps/studio/backend/tests/docs/` → **181 passed**(修订过程中共跑三次,均全绿)。

**落盘内容(按追加裁决原样,未改其他节)**
- §5 整节改写:executor 闭集缩为 `embedded`、`ah`,`host-native` **删除、不存在**。新增 §5.1 裁决理由四条(宿主模型/版本/上下文钉不死违北极星-1;服务端无宿主可言违北极星-4;宿主是**驾驶员**——经 MCP/CLI 调 compile/predict/run/inspect、读结果、改源文件——永远不是相位执行者;单独用 Claude Code/codex 同样走 embedded 或 ah)。
- 决定 a 解析链与"不进可移植源"保留,闭集改两成员;决定 b 改为"缺省=embedded(ModelResolver Port,gateway 权威实现;无可用角色供给时 compile/preflight 报错引导配置,与 J-X.10 同构、不静默)、ah=显式选择(受监督 vendor CLI 进程,CLI 自持登录,optional extra)";c(preflight + 无自动 fallback)与 d(失败语义)原样保留。
- 新增 e 删除清单五项(host-native executor、`agent-handoffs.sqlite3`、`submit_agent_result` MCP 工具、`checkpoint_ref` handoff 形状、Phase 3b backlog 整体,附"embedded 本就支持全形状"的理由)、f 异步 run 任务模型(与实时事件订阅并为同一 Port)、g 被接受的代价(无零配置路径,用户已知悉并接受)、h 四步实施顺序。
- §4.5 门禁**六改五**(新①吸收原①Phase 3b 与原④ModelResolver;新③把实时事件订阅并进异步 run 任务模型)。
- §11 追加修订记录行;台账同名任务块的范围描述同步改为"五条门禁 + 闭集只有 embedded 与 ah,host-native 经用户裁决移除",避免台账留下过期事实。

残留检查:全文 `host-native` 只出现在 §5.1(裁决理由)、§5.6(删除清单)、§5.8(代价)、§11(修订记录);`Phase 3b` 只出现在删除清单与修订记录;无"六条门禁""三个 adapter"残留。
