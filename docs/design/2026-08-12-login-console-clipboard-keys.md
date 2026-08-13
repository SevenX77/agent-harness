# 决议:登录界面的剪贴板快捷键(c 复制链接 / v 粘贴)+ 链接自动复制(2026-08-12)

状态:已批准(用户 2026-08-12 原话:「我需要在所有登录界面上加上 c 和 v 的快捷键,
c 就是直接 copy 网页,v 就是把剪贴板的内容复制上去」),本文即实施依据。
关联:`docs/design/2026-08-12-cli-settings-revision.md`(行内「登录」按钮的来历)。

## 1. 背景与问题

`claude auth login` / `codex login` 在本机 WSL 里跑时**打不开 Windows 浏览器**,
只能打印一条 5 行长的授权 URL 并等用户把 code 粘回来(真机截图 2026-08-12)。
用户需要:鼠标框选跨行折行的 URL → 浏览器打开 → 复制 code → 粘回控制台。
框选折行长 URL 是真实痛点;粘贴虽有右键,但用户点名要单键 `v`。

## 2. 环境事实(实测 2026-08-12,决定实现路线)

1. **WSL 进程互通关闭**:`/etc/wsl.conf` `[interop] enabled=false`
   (ah e2e 测试床的既定配置,不改动)。`clip.exe`/`powershell.exe` 在 WSL 内
   `Exec format error`——WSL 侧调不了 Windows 剪贴板。
2. **OSC 52 不可用**:即便用 `wt.exe` 强制 Windows Terminal 承载,发送
   OSC 52(BEL 与 ST 两种终结符)剪贴板均无变化——终端转义序列这条带内通道也不通。
3. **挂载互通可用**:`/mnt/c` 正常读写——文件是 WSL 与 Windows 之间唯一可靠通道。

结论:剪贴板读写必须由 **Windows 侧的 Studio 进程**完成,WSL 侧经 /mnt 挂载的
交换文件与它握手。

## 3. 决议

1. **登录命令统一包一层 pty 包装器**(python3,以 heredoc 落进启动脚本,无分发):
   - **链接自动复制**:扫描 CLI 输出,第一次出现 `https://` URL 时自动送 Windows
     剪贴板并打一行确认——比 `c` 更进一步,零按键。
   - **`c`**:重新复制最近一次出现的 URL。
   - **`v`**:把 Windows 剪贴板内容注入 CLI 的输入(用于粘 OAuth code)。
   - 按键判定规则(修订 2026-08-12 晚,用户实测裁决「keep it simple」):
     **孤立按键即命令**——单字节 `c`/`v` 且 60ms 内无后续字节;粘贴突发与转义
     序列都是多字节读,天然透传。初版还叠了一层「输入行为空」判定,首次真实
     使用即翻车:claude 登录是 Ink TUI,终端对它的查询回的应答(光标位置报告
     等)流经 stdin 被记成"已开始输入",v 永久失效(已复现+回归钉死)。登录
     控制台不存在自由打字场景,该判定只有误伤没有收益,删除。
   - 反馈从简(同一裁决):不做复制确认握手等待;仅首次复制打一行提示两个
     快捷键的存在,复制成没成用户一试便知。`v` 桥无应答时保留一行右键提示
     (否则按键无声失败无从排查)。
2. **剪贴板桥**:每次拉起登录界面,Rust 侧在
   `%LOCALAPPDATA%\AgentStudio\login-bridge\<nonce>\` 建交换目录,并起一条
   **心跳驱动的看护线程**:
   - 协议:包装器写 `copy.txt`+`copy.seq` → 看护读文件设剪贴板 → 回 `copy.ack`;
     `v` 反向走 `paste.req` → 看护把剪贴板落 `paste.txt`(用后即删)→ `paste.ack`。
   - 生命周期:包装器每 ~2s touch `alive`,命令结束写 `done`;看护线程在
     done / 心跳陈旧 / 45 分钟上限三者任一时退出并删目录。**不依赖进程句柄**,
     所以外部控制台与内嵌终端两类承载完全同构,无需穿 spawn 管线。
   - 剪贴板读写用隐藏 `powershell -NoProfile`(CREATE_NO_WINDOW),不引新依赖。
3. **覆盖的登录界面**(全部走同一个包装函数,shell 函数 + python 常量各一份定义):
   - Settings → CLI 区「登录」按钮的外部控制台(claude / codex);
   - Open in CLI 启动脚本里的 login-doorman(claude / codex,内嵌终端承载)。
   「更新”控制台无 URL/code 交互,不挂桥。
4. **降级语义**:桥目录建不出 / python3 缺失 / 看护未应答(2s 超时)——一律回落
   到现行为(裸跑命令 / 打一行提示"手动框选或右键粘贴"),不阻塞登录。

## 4. 验收判据

1. 点 Settings「登录」(claude):控制台出 URL 后 **不按任何键** Windows 剪贴板即
   为该 URL(Get-Clipboard 实证),控制台出现"已复制"确认行。
2. 包装器行为测试(真 python3 + 真文件握手,CI unix 跑):URL 检测→copy 握手、
   `c` 重复制、`v` 注入(子进程回显剪贴板内容)、孤立键与粘贴突发的区分、
   子进程退出码透传。
3. 看护线程协议测试(注入假剪贴板,免 powershell):copy/paste 两向握手、
   心跳陈旧退出、done 退出、目录清理。
4. 无桥/无 python3 时脚本与现行为一字不差(降级测试)。
5. 全部 CI 门禁绿。

## 5. 证据清单

- interop 关闭:`/etc/wsl.conf` 实读 + `cmd.exe` Exec format error(2026-08-12)。
- OSC 52 失效:wt.exe 强制承载下 BEL/ST 两种终结符实测,剪贴板保持 sentinel。
- 登录界面清单:`cli_console_action_script`(设置页按钮控制台)、
  `wsl_payload_script` 的 codex_auth_sync / claude_auth_bridge(doorman)。
- 内嵌终端 = `cli_terminal.rs`(ConPTY)+ 裸 `@xterm/xterm`,无自定义剪贴板接线。
