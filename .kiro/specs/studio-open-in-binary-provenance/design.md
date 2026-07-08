# Design: Open in Codex/Claude — 二进制来源守卫(binary provenance guard)

> 前置:research.md(同目录)。事故根因与穿透机理已实证坐实,本文只定修复设计。
> 状态:Implemented(2026-07-07)。agent-harness 侧 D1-D3 已落地;D4 是 ah/ccbd-rust 纵深防线,不在本次范围。

## §1 铁律(设计矩阵增补,最高层结论)

写入 `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md` §4.5,
与「绝不复制含 refresh token 的凭据文件」同级:

> **master/worker 可执行文件必须是执行侧 OS 的原生二进制。**
> ah 的沙盒是环境变量级协作式隔离,其成立前提是子进程与 daemon 同 OS;
> 跨 binfmt interop 边界执行(WSL 内 exec `/mnt/*` 下的 PE)= 沙盒契约作废,
> 且失效是静默的(见 research §5)。因此对解析出的二进制必须做来源校验,
> 命中跨界二进制时 **fail loud(拒绝启动 + 打印修复指引),绝不静默降级**。
> 凭证搬运矩阵管"登录态数据从哪来",本铁律管"二进制从哪来"——两个正交维度,
> 新增 assistant 两个都必须回答。

## §2 目标与验收

| # | 目标 | 验收 |
|---|---|---|
| G1 | 被劫持的入口不再被 exec | 手动:软链指向 `/mnt/*` 时 Open in Codex → 终端停在明确指引,不启动 Windows codex |
| G2 | codex 解析优先命中不可被劫持的位置 | 单测:master cmd 含 standalone 稳定路径探测,且顺位在 `~/.local/bin` fallback 之前 |
| G3 | claude 同等设防 | 单测:`claude_master_cmd` 含同一守卫 |
| G4 | 安装脚本能自愈劫持 | 脚本:B1 检出 `/mnt/*` 指向即修回原生并打印 repaired |
| G5 | 设计源成文 | §4.5 铁律落盘(§1 原文) |

非目标:不做跨 OS env 转发(WSLENV/UNC 注入方案已否决,见 §5);不改 ah 沙盒
模型本身;不负责阻止 Windows Codex 未来再次翻链(那是上游行为,我们保证的是
翻了也**穿不透、能自愈、有指引**)。

## §3 组件设计

### D1 master cmd 来源守卫 + 稳定路径优先(`apps/studio/tauri/src/lib.rs`)

`codex_master_cmd`(lib.rs:637)解析顺序改为:

1. `$HOME/.codex/packages/standalone/current/bin/codex`
   (官方 install.sh 的 `STANDALONE_ROOT` 布局;Windows Codex 的 WSL 集成只改写
   `~/.local/bin` 入口,不碰这里——research §3 实证 0.142.5 在劫持后完好)
   注意此处 `$HOME` 是 sandbox home,须用 `$STUDIO_AH_HOST_HOME/.codex/...`;
2. `command -v codex`;
3. `$STUDIO_AH_HOST_HOME/.local/bin/codex`(现状 fallback,保留但不再裸信任)。

对**最终解析结果**(无论来自哪一步)统一过守卫后才 exec:

```sh
codex_target=$(readlink -f "$codex_real" 2>/dev/null || printf '%s' "$codex_real")
case "$codex_target" in /mnt/*)
  printf '%s\n' "codex resolves to a Windows binary ($codex_target)." >&2
  printf '%s\n' "A Windows process cannot run inside ah's sandbox (it ignores HOME injection)." >&2
  printf '%s\n' "Fix: re-run scripts/install-claude-code-wsl.ps1 (it repairs the native install)." >&2
  exit 127 ;;
esac
```

`claude_master_cmd`(lib.rs:622)加同一守卫(路径换 claude;无 standalone 布局,
只加守卫不加顺位)。守卫以 `readlink -f` 归一后按**路径前缀**判定,不做 PE 魔数
嗅探——`/mnt/*` 判据已覆盖本机理(interop 只对 Windows 卷下的 exe 生效),魔数
嗅探对 9p 挂载还有额外 IO 成本。

**测试**(TDD,先红后绿,`lib.rs` 测试 mod):
- `codex_master_cmd_rejects_interop_binaries`:cmd 字符串含 `case ... /mnt/*` 守卫
  与 standalone 优先路径;
- `claude_master_cmd_rejects_interop_binaries`:同守卫存在;
- 既有 `transient_ah_config_starts_codex_moirai_team` 断言集同步扩展。
(master cmd 是生成的 shell 字符串,单测锁形状;行为验收走 G1 手动矩阵。)

### D2 安装脚本 B1 自愈(`scripts/install-claude-code-wsl.ps1` L323-329)

现状缺口(research §6):present 判定信 `command -v codex` + `--version` 应答,
Windows exe 也能应答 → 劫持态被误判健康。改为:

1. present 判定后追加指向校验:`readlink -f`(对 `~/.local/bin/codex` 与
   `command -v` 结果)落在 `/mnt/*` → 视为 BROKEN;
2. BROKEN 或 MISSING → 走原有 install.sh 安装(其 `replace_path_with_symlink`
   会把 `~/.local/bin/codex` 重指原生 standalone,天然完成修复),打印
   `repaired hijacked codex entry`;
3. claude 侧(L295-301)同样加指向校验,对称设防。

脚本幂等性保持:健康态重跑仍是 Skip。

### D3 设计矩阵增补(`ah-orchestration-design.md` §4.5)

- 落 §1 铁律原文;
- 矩阵加一列「二进制来源」:claude=原生 install.sh(`~/.local/share/claude/versions/*`),
  codex=原生 install.sh standalone(`~/.codex/packages/standalone/current`),
  并注明 `~/.local/bin` 入口在 Windows+WSL 上**可被上游改写、不可作信任锚**;
- 记录本事故为背景(链到 research.md)。

### D4 ah 侧纵深防线(ccbd-rust,可选,不阻塞 D1-D3)

provider spawn(`src/rpc/handlers/agent.rs` 一带)exec 前校验二进制为 ELF,
非 ELF 时 spawn 报错带明确 reason 上抛到 events。并入既有 handoff
(`docs/reports/studio-open-in-handoff-2026-07-06.md`)T4 杂项,由 ah 侧实施者
排期;Studio 侧 D1 守卫不依赖它。

## §4 止血步骤(实施第一步,不等 PR)

```sh
ln -sfn /root/.codex/packages/standalone/current/codex /root/.local/bin/codex
```

原生 0.142.5 完好(research §7)。注意:Windows Codex 下次自启可能再翻,
止血只保证"现在能用",D1/D2 落地前每次重启后需目检。

## §5 已否决的替代方案

| 方案 | 否决理由 |
|---|---|
| WSLENV 把 `HOME` 转发给 Windows codex | Windows 程序不读 `HOME`,读 `%USERPROFILE%`(Linux 侧不可注入)。转发了也无效 |
| 把 sandbox 路径翻成 `\\wsl.localhost\...` UNC 喂给 Windows codex | 等于重新发明一套跨 OS 沙盒:路径语义、权限、锁行为全不可控,上游一次更新即碎。违背第一性原理(问题是"不该跨界",不是"跨界后怎么补") |
| 安装脚本每次运行强制重装 codex | 症状补丁:不跑脚本就不修,窗口期照样穿透;且掩盖"入口被劫持"这一事实,违背 fail-loud |
| 只修 codex 不动 claude | claude 同构逻辑纯靠运气未踩(research §7),同一 PR 对称设防成本≈0 |
| PE 魔数嗅探替代路径判定 | `/mnt/*` 前缀已充要覆盖 interop 机理;魔数嗅探引入 9p 读 IO 与边角(壳脚本包装)误判 |

## §6 实施切分(单 PR 可容纳,TDD)

1. T1 失败测试:D1 两条守卫单测(红);
2. T2 lib.rs 落 D1(绿);
3. T3 安装脚本落 D2(PowerShell 侧无单测门禁,靠 D2 步骤描述 + 手动矩阵);
4. T4 设计矩阵落 D3(同 PR);
5. T5 止血命令执行 + 手动验收矩阵(PM 点验):
   | # | 场景 | 操作 | 预期 |
   |---|---|---|---|
   | 1 | 劫持态(翻链到 `/mnt/*`) | Open in Codex | 终端停在守卫指引,不启动 Windows codex |
   | 2 | 健康态(止血后) | Open in Codex | master 自报 MoirAI 身份;cwd 为 `/mnt/d/...`;跑 bash |
   | 3 | 健康态 | 重跑安装脚本 | B1 全 Skip(幂等) |
   | 4 | 劫持态 | 重跑安装脚本 | B1 打印 repaired 并修回原生 |
6. D4 写回 ccbd-rust handoff T4(独立小 PR,ccbd 仓)。
