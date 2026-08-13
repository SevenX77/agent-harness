# 决议:ah 随 Studio 打包 + 运行期自动布署(2026-08-12)

状态:已批准(用户 2026-08-12 裁决"做"),本文即实施依据。
关联:`docs/design/2026-08-12-cli-settings-revision.md`(同批次用户反馈,其中第 1 条
"ah 怎么会没有安装"引出本决议)。

## 1. 背景与问题

用户裁决原话要点:

> 作为第一次使用这个应用的用户,他们到底要装多少外部应用才能使用这个 app?
> ah 是我自己开发的,不能作为依赖包装进来吗?

现状的两个真实故障模式:

1. **首次使用者门槛**:Open in CLI 依赖 WSL 里装好 ah,缺了只给一句
   "Install it from https://github.com/SevenX77/ah then reopen Studio",把安装
   动作甩给用户。ah 是本项目自有产物,没有理由要求用户手动安装。
2. **环境重建抹除**(2026-08-11/12 真机发生):实验性环境重建删掉了 WSL 的
   `~/.cargo`,ah 随之消失,Studio 只能报"未安装"。当前设计没有自愈能力。

另有一个实测发现的既有缺陷,与本决议直接相关:Rust 侧启动前置检查
`check_ah_version_cached()`(`apps/studio/tauri/src/lib.rs`,5 个 Open in CLI
入口都先过它)用 `OnceLock` 把**失败也永久缓存**——用户装好 ah 之后必须重启
Studio 才能启动会话。自动布署若只做在 bash payload 里会死在这道 Rust 门禁前面,
所以布署必须落在 Rust 前置检查内,缓存语义同步修正。

## 2. 决议

1. **构建期 vendor**:钉住版本的 ah Linux 二进制(`ah` + `ahd`)进
   `apps/studio/tauri/vendor/ah/`,与 vendored Python 运行时同一模式:
   lock 文件钉版 + sha256,provisioning 脚本下载解压,`bundle.resources` 的
   现有 `vendor/**/*` 条目让它自动进打包产物。
2. **运行期自动布署(Rust 前置检查内)**:Open in CLI 的 Rust 侧 ah 检查从
   "失败即拒绝"改为"失败先尝试把 vendored 二进制拷进 WSL,再复查";复查仍不过
   才拒绝。检查结果**只缓存成功**。
3. **bash payload 兜底自愈**:WSL 启动脚本里现有的 `command -v ah` + 版本门禁
   之前,插入同一布署逻辑的 shell 版,覆盖"app 运行中环境被抹掉"的窗口
   (Rust 侧已缓存成功、不再复查的时段)。原 `command -v` 检查与版本门禁
   原样保留作最终兜底。
4. **面板语义**:Settings → CLI 区的 ah 行在 missing/outdated 时提供「部署」
   动作,调用同一条布署链,完成后前端重新探测。ah 不再是"用户去装的外部依赖",
   而是"app 自带、可一键修复的运行时组件"。

## 3. 关键设计决定

- **钉版单源**:`apps/studio/tauri/ah-vendor.lock.json` 是钉版唯一事实源
  (version + artifact url + sha256),仅被 provisioning 脚本消费。Rust 运行期
  读的是 `vendor/ah/VERSION`(脚本在校验+解压成功后最后写入)——运行期比较
  基于"实际 vendor 了什么",不基于"打算 vendor 什么",两者由脚本保证一致。
  钉版资产(v1.14.3):`ah-x86_64-unknown-linux-gnu.tar.xz`,官方 sha256
  `d328a8e88d9ca6c0590c41cb71c972e4e78d9103017a8bc6f9c927a806d387ec`,
  tarball 内含 `ah` 与 `ahd` 两个二进制(安装器即从此单一资产装出两者)。
- **只升不降**:已装 ah 版本 ≥ vendored 版本时不布署(ah 的开发者自己的机器上
  可能装着更新的开发版,Studio 不得降级覆盖)。缺失或更旧才拷。
- **布署目标路径**:`command -v ah` 能解析到旧二进制时,覆盖其所在目录
  (避免 `~/.cargo/bin` 里的旧版继续遮蔽新拷贝);解析不到(全新环境)时落
  `~/.local/bin/`。两个二进制一起拷,拷后 `chmod +x`。
- **Windows→WSL 路径换算**:纯函数 `盘符:\path` → `/mnt/盘符小写/path`,
  换算不出(UNC 等)则视为 vendored 不可用,整体降级为现行为。
- **降级语义**:vendored 目录缺失/不完整、路径换算失败、拷贝失败——一律不
  阻塞,落回现行为(现有报错与 remediation 文案)。vendor 是增强,不是新的
  单点故障。
- **provisioning 脚本失败策略**:dev 链(beforeDevCommand)失败只警告不阻塞
  (离线机器照常开发);build 链(beforeBuildCommand)传 `--strict` 失败即
  构建失败(发布产物缺 vendored ah = 决议未达成)。
- **范围**:自动布署仅 Windows/WSL 路径(产品当前只发 Windows;vendored
  二进制是 linux-gnu 目标,恰好是 WSL 要的)。unix launcher 路径保持现状。
- **AH_VERSION_MIN 与 vendored 版本的关系**:MIN 仍是兼容性地板(门禁文案、
  outdated 判定不变);vendored 版本必须 ≥ MIN(lock 文件升版时人工保证,
  vendored < MIN 会被现有门禁如实拦下,不做额外机制)。

## 4. 验收判据

1. `node apps/studio/tauri/scripts/ensure_ah_vendor.js` 在联网机器上产出
   `vendor/ah/{ah,ahd,VERSION}`,VERSION 内容等于 lock 版本;重复执行秒级跳过;
   篡改缓存 tarball 触发 sha256 拒绝。
2. WSL 里把 ah/ahd 移走后,不重启 Studio,Open in CLI 能拉起会话(Rust 侧
   自动布署生效),布署后 `ah version` 等于 vendored 版本。
3. WSL 里放一个版本号更高的假 ah 时,布署链不覆盖它(只升不降)。
4. Settings → CLI 区 ah 行 missing 时出现「部署」按钮,点击后行状态变 ok,
   无需重启 app。
5. vendored 目录不存在时,一切行为与本决议实施前一致(降级验证)。
6. 全部 CI 门禁绿(含 `apps/studio/tauri/scripts` 的 node --test 新增用例,
   离线可跑,不真实下载)。

## 5. 证据清单

- 发布资产与 sha256:GitHub Releases v1.14.3(dist-manifest.json 列出
  `ah-x86_64-unknown-linux-gnu.tar.xz`;`.sha256` 资产给出上述哈希)。
- 打包通道:`apps/studio/tauri/tauri.conf.json` `bundle.resources` 含
  `vendor/**/*`。
- Rust 前置门禁的 5 个调用点与失败缓存:`apps/studio/tauri/src/lib.rs`
  `check_ah_version_cached`(OnceLock 缓存 `Result`,Err 亦被缓存)。
- bash 门禁插入点:`wsl_payload_script` / `wsl_attach_payload_script` 中
  `command -v ah` 检查与 `ah_version_gate_script` 产物。
- provisioning 范式:`apps/studio/tauri/scripts/download_runtime.js`
  (lock 钉版 + sha256 校验 + 缓存 + tar 解压)。
