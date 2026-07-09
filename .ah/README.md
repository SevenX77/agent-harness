# .ah/ · ah 编程 SOP(agent-harness 实例)

用 [ah](https://github.com/SevenX77/ah)(≥ 1.4.0)在本仓编排 agent 团队做工程的配置实例,源自
[ah-scenario-pack](https://github.com/SevenX77/ah-scenario-pack) v0.1.0 `examples/dev-programming/`
(commit bb41fcf)。协作方法论(三层拓扑 / SOP 闭环 / 设计管线 / 代理实践 / 纪律清单)读 pack 的
`GUIDE.md` / `ROLES.md`——那是人读层;本目录只放注入 agent 的实例层。

## 内容

- `ah.toml`(仓根)——拓扑:master=claude + a1/a3=antigravity + a4=claude(a2=codex 备用)
- `.ah/rules/<id>.md`——各 slot 场景规则(ah 注入时自动前置协调内核,勿复述内核)
- `.ah/VERIFY.md`——本仓验证档案(fill-once):命令 / 约束 / 验收矩阵 / 红灯处置

## 与 pack 示例的有意差异

1. **master 用顶层 `[master]` 表**,不是 pack 示例里的 `[agents.master]`。后者在 ah v1.4.0 语义下会
   孵化一个名叫 "master" 的普通 worker,真 master 反而落在默认配置上。依据:ah 官方模板
   `examples/scenarios/dev-programming/ah.toml`、保真测试 `tests/dev_scenario_template.rs`
   (直接断言 `config["master"]["cmd"]`)、模板 README 原文 "The master provider is determined
   by `[master] cmd` in `ah.toml`, not by the master slot file"。
2. `[completion] hook_push_enabled = true`:provider Stop hook 直推 ahd,是 pack GUIDE §11
   「内部后台任务型假完成」的编排器侧根治(ah 官方模板同样开启)。
3. 规则文件与 VERIFY.md 已按本仓适配(worktree/PR 纪律、CI Gates、已知坑)。

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
env 路线已废弃)。清单随实测滚动回写(`[x]` = 已在本机验证过):

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
3. **state dir 有解析不一致陷阱**(ah 1.4.0):`start/ask/ps` 落 `default`,而
   `events/status` 解析到别处报 `ahd_alive:false` 假死——驱动脚本统一
   `AH_STATE_DIR=$HOME/.local/state/ah/default` 兜平。
4. **`ah stop` 不清持久 unit**:`~/.config/systemd/user/ah-*.service` 留存且 enabled,
   WSL 重启即复活旧 daemon。停栈后手动 `systemctl --user disable --now` + 删 unit 文件
   (上游修复前的操作项)。已知上游问题另见:kill→up 重生偶发单 agent CRASHED;
   `~/.cache/ah/sandboxes/` 尸体累积无 GC。

首跑踩坑回写进本 README 与 `.ah/VERIFY.md` §2——档案错了改档案,一处生效。
