# .ah/ · ah 编程 SOP(agent-harness 实例)

用 [ah](https://github.com/SevenX77/ah)(≥ 1.4.0)在本仓编排 agent 团队做工程的配置实例,源自
[ah-scenario-pack](https://github.com/SevenX77/ah-scenario-pack) v0.5.1 `dual-lane/` 模板(双泳道并发拓扑;沿用 v0.5.0 执笔权铁律:gate 文档——design/spec/tasks/TDD 框线/验收测试——一律严谨 agent 执笔,发散型只有辩论席位与实施位)。
协作方法论(三层拓扑 / SOP 闭环 / 设计管线 / 代理实践 / 纪律清单)读 pack 的 `GUIDE.md` / `ROLES.md`,
**operator(用户代理)角色规范读 pack `OPERATOR.md`**——那是人读层;本目录只放注入 agent 的实例层。

## 内容

- `ah.toml`(仓根)——拓扑(双泳道):**治理链 = 用户 → operator(代理 CEO,监督管理 PM)→
  master(项目经理,全体 agents 由其管辖调配)→ 各 agent**。master=claude + 泳道1(g1=claude 闸门 +
  g1-m1=antigravity 实施)+ 泳道2(g2/g2-m1 对称)+ o1=antigravity 设计辩论席。
  泳道内技术事务由本泳道闸门终裁——这是 master 的**裁决下放**,不是脱离管辖(实施者阻塞落盘
  `.lane-question`,收件人=其闸门),派单调配权始终在 master;
  闸门执笔 RED 验收测试,实施者纯变绿、不得改测试文件;实施位首选 codex,配额恢复后替换 g*-m1 provider;
  d1=claude 设计执笔席(design 稿 + spec/tasks 转写,master 不兼笔)。
- `.ah/rules/<id>.md`——各 slot 场景规则(ah 注入时自动前置协调内核,勿复述内核)
- `.ah/VERIFY.md`——本仓验证档案(fill-once):命令 / 约束 / 验收矩阵 / 红灯处置

## 与 pack 模板的有意差异

0. **执笔席按本机资源加强**:v0.5.1 模板的「设计者主笔」措辞/五步管线是 VPS 资源受限
   环境的刻意妥协(用户 2026-07-10 拍板:该环境由 master 兼执笔,与双泳道实施并行提效,
   不是回退)。本机内存充足,实例增设专职设计执笔席 `d1-claude` 替代 master 兼笔——
   管线保持发散输入(o1 意见书)与执笔(d1)分离;「发散型不执笔 gate 文档」铁律两版一致。
0b. **dual-lane 模板的 `ah.toml.example` 有客观损坏**(缺 `version`、master 写成
   `[agents.master]`、`hook_push_*` 裸挂在 `[agents.o1]` 表下),实测 `ah config validate`
   一行就挂;本实例按 ah 官方语义写(顶层 `[master]` + `[completion]` 表),已报上游。

1. **master 用顶层 `[master]` 表**,不是 pack 示例里的 `[agents.master]`。后者在 ah v1.4.0 语义下会
   孵化一个名叫 "master" 的普通 worker,真 master 反而落在默认配置上。依据:ah 官方模板
   `examples/scenarios/dev-programming/ah.toml`、保真测试 `tests/dev_scenario_template.rs`
   (直接断言 `config["master"]["cmd"]`)、模板 README 原文 "The master provider is determined
   by `[master] cmd` in `ah.toml`, not by the master slot file"。
2. `[completion]` hook_push 三行:provider Stop hook 直推 ahd,是 pack GUIDE §11
   「内部后台任务型假完成」的编排器侧根治(ah 官方模板同样开启)。
3. 规则文件与 VERIFY.md 已按本仓适配(worktree/PR 纪律、CI Gates、已知坑)。

## CLI 层配置(模型 / effort / statusline)

`ah.toml` 末尾是 pack v0.4.0 实战拍板的 CLI 层配置:`[master.settings]` / `[agents.a4.settings]`
深合并进该角色沙箱的 `.claude/settings.json`。**仅 claude provider 支持**(ah v1.4.0);
antigravity(a1/a3)的模型/effort 配在宿主全局 `~/.gemini/antigravity-cli/settings.json` 的
model 名里内嵌(本机实测 "Gemini 3.5 Flash (High)"),随沙箱物化继承。分档:**a4 审计 =
Opus 4.8 + xhigh**(质量门不偷懒;effortLevel 持久化上限就是 xhigh)、**master = Sonnet 5 +
medium**(编排是短视野决策,质量门在审计与 operator 物理验证)、实施走便宜模型。statusline
按 operator 监控需求配(角色 · 模型+effort · context%),**依赖 WSL 侧装 `jq`**(本机已装)。
生效时机:沙箱**物化(spawn)时**——改了 ah.toml,在跑的 agent 要 kill+up / 重启栈才带新配置。

## 怎么跑(标准形态)

一个任务 = 一个 worktree = 一个 ah 会话(ah 按 cwd 向上找 `ah.toml`,project-id 取自其所在目录):

```bash
scripts/wt-new.sh <type>/<short-desc>   # operator 切任务树(树里自带 ah.toml)
cd .worktrees/<type>-<desc>
ah start --wait                          # 拉起 master + workers,cwd = 本 worktree
ah attach master                         # 进 master 对话;Ctrl-b d 离开不停机
```

**不要在主仓根起会话**——workers 的 cwd 会落在 main 工作树,违反「main 禁实施」铁律。
外部观察/驱动:`ah ps` / `ah ask <id> "..."` / `ah watch` / `ah logs` / `ah events --format json`。

## 本机(Windows devbox)已知事实与首跑清单

ah 只跑 Linux/WSL2。本机 WSL = Ubuntu-24.04(root 用户;claude 与 ah 已装)。**claude 凭据 =
symlink 单一真相源**:Windows `%USERPROFILE%\.claude\.credentials.json` 是唯一凭据文件,WSL
`~/.claude/.credentials.json` 与 ah 沙箱 HOME 全部 symlink 指向它——所有环境同一份文件,
永不产生第二份 OAuth 链,WSL 里跑 claude 是安全的(设计:`ah-orchestration-design.md` §4.5;
实现:PR #476。**绝不复制**该文件——复制出第二份才会轮转互踩;旧的 CLAUDE_CODE_OAUTH_TOKEN
env 路线已废弃)。**已知脆弱点(2026-07-10 实证)**:claude 刷新失败进入登出态时,会把
`{expiresAt:0}` stub 以普通文件原子写回,把写回路径上的 symlink 盖掉(链上逐级、包括
`~/.claude/` 的);见到某 HOME 下它变回普通文件,先查 Windows 真相源是否过期,重登后
从链头到链尾重建 symlink。清单随实测滚动回写(`[x]` = 已在本机验证过):

- [x] ah ≥ 1.4.0:2026-07-09 已升(installer → `/root/.cargo/bin`);`/usr/bin/{ah,ahd}`
      的旧 1.3.0-rc.1 已改为指向 cargo 版的 symlink,消除双位置版本 skew。
- [x] antigravity:**CLI 真名是 `agy`**(ah 对该 provider spawn 的命令就是
      `agy --dangerously-skip-permissions`,别按 antigravity 找二进制),WSL 已装
      (`/root/.local/bin/agy`,`/usr/local/bin/agy` 加了 symlink 兜 PATH)。鉴权已通:
      **Windows 侧 agy 把 token 存在凭据管理器(`gemini:antigravity`),文件系统里没有
      可 symlink 的文件**——用 CredRead 读出 blob(UTF-8 JSON,键 `token`/`auth_method`)
      写成 WSL `~/.gemini/antigravity-cli/antigravity-oauth-token`(chmod 600)即可;
      `agy models` 与 `agy -p` 实测通(Google refresh token 不轮转,双端共用可行,
      不同于 claude)。`.gemini/GEMINI.md` 风险实际很低:它未跟踪,worktree 天然不带它,
      而 ah 会话只允许在 worktree 里跑。
- [x] **ah 栈全功能已在本机测通**(2026-07-09,bash 冒烟栈 + claude master/agy worker 真栈):
      start/ps/status/ask(同步+异步)/pend/cancel/logs/watch/events/kill/up/tell master/
      doctor/stop、hook_push、DB 直读、pane 物理验证全过;agy worker 2.3s 真实往返,
      claude master 收 tell 真实回复。root master 用 `IS_SANDBOX=1 claude
      --dangerously-skip-permissions` 实测有效(worker 侧 ≥1.3.4 自动注入)。
- [ ] ah 用的 worktree 从 **WSL 侧**跑 `scripts/wt-new.sh` 创建(Windows 侧建的 worktree,
      gitdir 指针是 Windows 绝对路径,WSL git 读不了)。
- [ ] 仓根/worktree 的 `.venv`、`node_modules` 是 Windows 原生产物,WSL 不可复用:WSL 侧
      需要自己的 `uv sync` / `npm ci`(Python 可用 `UV_PROJECT_ENVIRONMENT` 把 venv 指到
      树外,避免与 Windows venv 打架)。
- [ ] `/mnt/d` 跨界 IO 慢是已知代价;确认过慢再评估 WSL 原生 clone 形态。

### WSL 侧运行地基(2026-07-09 已搭好并 standby 实证)

真任务的标准形态 = **在 WSL 原生 clone `~/agent-harness` 里跑 ah 编队**(不在 /mnt/d:
GUIDE 明令 WSL 项目放原生盘,避跨界 IO)。已就位(实测 `wt-new → ruff → ah config validate`
首环全通):uv/node(v22 原生 Linux,非 /mnt/c 的 Windows node)/gh/jq 装齐;WSL git push
认证 = Windows 的 `ghp_` classic PAT(**不轮转,复制安全**)配进 gh + git helper。
真任务时:`cd ~/agent-harness && git pull && scripts/wt-new.sh <type>/<desc>` → 拉栈 →
在树里跑 CI Gates(uv run …)。**operator 与编队共用这份 WSL 仓,Windows 侧的
D:\coding\agent-harness 只做 operator 亲手活(spec 编辑、pack 同步),两份仓经 main 汇合。**

### 拉栈前一行漂移自检(时区/语言与 Windows 对齐)

`/etc/localtime` 是手工 symlink,Windows 改时区不会自动跟。拉栈前跑一行确认没漂:

```bash
# Windows 时区 vs WSL,应一致(本机=Pacific/America_Los_Angeles);locale 应是 UTF-8
tzutil /g   # (Windows 侧) ↔  readlink -f /etc/localtime | sed 's|.*/zoneinfo/||'  (WSL 侧)
```

漂了则 `ln -sf /usr/share/zoneinfo/<Area/City> /etc/localtime`(编码策略见
`docs/development/CROSS_PLATFORM.md`:一律 UTF-8,勿 GBK)。

### 本机拉栈的四条实测配方(2026-07-09,不照做必踩)

1. **worker 必须注入代理 env**:本机出网走 Clash(`127.0.0.1:7897`,WSL mirrored 网络)。
   master 经 login shell 拿到 `/etc/profile.d` 的代理变量,**worker 走 systemd scope 干净
   环境拿不到**——antigravity worker 会卡在"Signing in…"最后掉进登录菜单(token 明明已
   材料化)。每个 worker 加:
   ```toml
   [agents.<id>.env]
   HTTP_PROXY = "http://127.0.0.1:7897"
   HTTPS_PROXY = "http://127.0.0.1:7897"
   NO_PROXY = "localhost,127.0.0.1,::1"
   ```
2. **驱动栈期间必须保持一个长活 WSL 会话**(如后台 `wsl -e bash -c "sleep infinity"`):
   没有任何交互会话时 WSL 空闲关机(vmIdleTimeout),整栈(ahd+tmux+agents)全带走,
   事后盘面只剩 CRASHED 尸体和 ACTIVE 幽灵会话。
3. **state dir 有解析不一致陷阱**(1.4.0 发现;2026-07-10 于 1.5.0 复验仍在且换边:
   同一含 ah.toml 的 cwd 下无 --config 时,`status`/`ps` 落 `default`、`events` 走
   project discovery;已提上游 [ah#15](https://github.com/SevenX77/ah/issues/15))——
   驱动栈的每条 ah 命令统一显式 `AH_STATE_DIR`。钉到该 worktree 的规范项目目录
   (`timeout 3 ah events --format json | head -1` 输出里的 `state_dir`,形如
   `$HOME/.local/state/ah/<hash>`)优于钉 `default`:任务间隔离,且与 ah 自身
   project discovery 对齐(2026-07-10 真栈实测配方)。
   **例外——`ps` 恰好相反(2026-07-11 实测,1.5.0)**:`AH_STATE_DIR=<hash目录> ah ps`
   返回**空表**(活栈 7 pane、agent BUSY 时也如此);`ps` 必须在 worktree cwd **裸跑**
   (不带该 env)才出全表。即:`events` 等要钉 env,`ps`/`status` 要裸跑 + cwd 定位,
   监控脚本按子命令分姿势(数据点已补进 ah#15)。
4. **`ah stop` 不清持久 unit**:`~/.config/systemd/user/ah-*.service` 留存且 enabled,
   WSL 重启即复活旧 daemon。停栈后手动 `systemctl --user disable --now` + 删 unit 文件
   (上游修复前的操作项)。已知上游问题另见:kill→up 重生偶发单 agent CRASHED;
   `~/.cache/ah/sandboxes/` 尸体累积无 GC。

### 栈重建/复活的三条追加配方(2026-07-11 凭据事故复盘实测)

5. **`ah start` 必须在 login shell 里跑**(`wsl -- bash -lc '... ah start --wait'`):
   daemon unit 的 Environment 是从 start 时的客户端环境烤进去的,再传给全部 spawn scope。
   非 login shell(`bash -c`/裸脚本)的 PATH 没有 `/root/.local/bin` → master 落地
   `sh: claude: not found`(exit 127)秒死 → daemon 的 master-death cleanup 把刚 spawn
   的全部 worker 连坐杀光,客户端只看到一个 `AGENT_NOT_FOUND`,极难反查(实测 4 连败)。
   `ah` 自己不受影响纯属侥幸(`/usr/bin/ah` 有 symlink),别被"ah 能跑"骗过。
6. **master 的 root cmd 变体必须用 `env` 承载**:写
   `cmd = "env IS_SANDBOX=1 claude --dangerously-skip-permissions"`,不要裸
   `IS_SANDBOX=1 claude ...`——spawn 走 systemd-run 直连路径时 `VAR=1` 前缀
   **不展开**(systemd 明确警告"not expanded by default"),claude 拿不到
   IS_SANDBOX 就触发 root 检查 `--dangerously-skip-permissions cannot be used with
   root`(exit 1)秒死,一样级联全灭。`env` 形式在 sh 与 systemd-run 两条路径下都成立。
7. **每次 start 前先验运行时注入还在**:worktree ah.toml 的未提交注入(master cmd 变体 +
   worker 代理 env)会被"延迟蒸发"(本仓实测一天两例,pack CHANGELOG 已记 git-clean 事故;
   本次为第二次复现,蒸发路径待抓)。拉栈前一行自检:
   `grep -c HTTP_PROXY ah.toml`(应=worker 数)+ `grep -n '^cmd' ah.toml`(应含 env 变体),
   少了就重跑注入脚本再 start。凭据事故后复活栈的完整顺序:用户 /login →
   验 token(`expiresAt` 未过期)→ 验注入 → login shell 里 stop/清 tmux/清本栈 state →
   `ah start --wait` → 验到 pane(登录态+statusline)→ 注入带进度的重启简报。
   注意:**长跑中的 claude 席位不会重读凭据文件**,登出态卡在进程内,凭据复活后必须
   重生席位(kill+up 或整栈重建;`ah up` realign 非原子,ah#16,整栈重建更稳)。

首跑踩坑回写进本 README 与 `.ah/VERIFY.md` §2——档案错了改档案,一处生效。
