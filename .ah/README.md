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

ah 只跑 Linux/WSL2。本机 WSL = Ubuntu-24.04(root 用户;claude 与 ah 已装,claude 凭据走
`CLAUDE_CODE_OAUTH_TOKEN` env 通道——**不要**跨 Windows/WSL 拷 `.credentials.json`,
refresh token 轮转会互踩)。以下路径**尚未在本机实测**,首跑逐条落地并回写本节:

- [ ] `wsl -e ah version` 确认 ≥ 1.4.0,旧了重跑官方 installer。
- [ ] ah 用的 worktree 从 **WSL 侧**跑 `scripts/wt-new.sh` 创建(Windows 侧建的 worktree,
      gitdir 指针是 Windows 绝对路径,WSL git 读不了)。
- [ ] 仓根/worktree 的 `.venv`、`node_modules` 是 Windows 原生产物,WSL 不可复用:WSL 侧
      需要自己的 `uv sync` / `npm ci`(Python 可用 `UV_PROJECT_ENVIRONMENT` 把 venv 指到
      树外,避免与 Windows venv 打架)。
- [ ] root 用户要 bypass 权限的 master 用 `IS_SANDBOX=1 claude --dangerously-skip-permissions`
      (`ah.toml` 里有现成注释行;worker 侧 ah ≥ 1.3.4 已自动注入 `IS_SANDBOX`)。
- [ ] antigravity CLI 在 WSL 的安装/登录;并处置本地未跟踪的 `.gemini/GEMINI.md`——它写着
      「未经用户确认禁止写代码」,若 antigravity 读项目级 GEMINI 规则,会掐死 a1/a3 的自主实施。
- [ ] `/mnt/d` 跨界 IO 慢是已知代价;确认过慢再评估 WSL 原生 clone 形态。

首跑踩坑回写进本 README 与 `.ah/VERIFY.md` §2——档案错了改档案,一处生效。
