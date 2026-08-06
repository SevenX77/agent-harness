# VERIFY.md · agent-harness 验证档案(fill-once)

> 本仓"构建 / 测试 / 验收"的唯一权威档案(源模板:ah-scenario-pack `VERIFY.md`)。
> master 派单 brief、worker 执行、审阅复核只引用这里,**不允许现场重新推导编译测试命令**。
> 档案变更(命令/约束变了)= 一次显式 PR,别悄悄漂移;与 `AGENTS.md`「CI Gates」冲突时以 AGENTS.md 为准并回改本档案。

## 1. 构建与测试命令

依赖安装(workspace 级,接入时一次):

- Python:`uv sync --all-packages --all-extras --group dev`(单 uv workspace、单根 `uv.lock`;改依赖走模块 `pyproject.toml` + `uv lock`,禁手改 `uv.lock`)
- 前端:`npm ci`(在 `apps/studio/frontend`)

| 用途 | 命令 | 何时用 |
|---|---|---|
| **迭代测试(定向,后端)** | `uv run pytest <受影响的测试文件或目录>` | 红绿循环中间每一轮。**按文件/目录定向**,禁按名(`-k`)瞎过滤 |
| **迭代测试(定向,前端)** | `npm --prefix apps/studio/frontend test -- <受影响测试文件>` | 同上 |
| 静态快查 | `uv run ruff check <改动的包>` | 每轮顺手跑 |
| **收口(全量交付门)** | 下表 9 条全部绿 | 任务收尾跑一次;严禁用定向结果替代 |

收口全量清单(= `main` CI 必过门禁,与 `AGENTS.md`「CI Gates」一致):

```bash
uv run ruff check packages/graph-agent packages/graph-agent-gateway apps/studio/backend  # 覆盖实际改动的包
uv run mypy --strict packages/graph-agent/src
uv run mypy --strict packages/graph-agent-gateway/src
uv run mypy apps/studio/backend/app
uv run pytest apps/studio/backend/tests          # 必须整套,禁子集
uv run pytest packages/graph-agent-gateway/tests
uv run pytest packages/graph-agent/tests
npm --prefix apps/studio/frontend run lint \
  && npm --prefix apps/studio/frontend run typecheck \
  && npm --prefix apps/studio/frontend test \
  && npm --prefix apps/studio/frontend run build
uv run --with pip-audit pip-audit                # 必须 0 CVE
```

## 2. 资源与环境约束

- **后端三套 pytest 必须整套跑**:存在 full-suite-only 失败模式(fixture ScopeMismatch、audited 设计 doc 哈希锁 `test_doc_hash_lock` 等),"子集绿" ≠ 门禁绿。
- **编码铁律(三平台)**:文本一律 UTF-8 + LF;`subprocess`/文件 IO 显式 `encoding="utf-8"`;禁止仅大小写不同的路径。详见 `docs/development/CROSS_PLATFORM.md`。
- **audited-ready MVP1 设计 doc 有哈希锁**:改这类 doc 必须同 PR 重钉对应 `_audited-ready-hashes.json`(LF 归一化 sha256),否则后端全量红。
- **前端 `src/lib/` gitignore 陷阱**:`apps/studio/frontend/src/lib/` 下新增文件默认被忽略(整目录 ignore + 逐文件 `!` allowlist),每个新文件必须加 `!` 行;否则本地 tsc 绿、CI fresh-checkout 红。
- **Git 纪律**:`main` 受保护且 PR-only;实施只发生在任务 worktree(`scripts/wt-new.sh`)的分支上,绝不在主仓根 main 工作树改文件;push/PR/合并归 operator。
- **桌面 app vendor 快照**:engine/gateway 源码改动对桌面 app 不即时生效(sidecar 永远 import `apps/studio/tauri/vendor/site-packages` 冻结快照)。开发期验证用 wt-dev 私有 sidecar;合并后要真机验证必须重跑 `build_vendor.py` + 预热 pyc + 重启 app(AGENTS.md 工作流第 7 条)。
- **本机(Windows devbox)**:仓根 `.venv`/`node_modules` 是 Windows 原生产物,WSL 侧的 ah workers 不可复用,需自建环境——见 `.ah/README.md`「首跑清单」(该路径尚未实测)。

### Rust / Tauri crate(`apps/studio/tauri`)的构建门(2026-07-10 排查落档)

改动 `apps/studio/tauri/src/*.rs`(Rust 原生 fs 层 / ah 集成)时按此节验证,别再现场重排查。

- **rustup 空列表陷阱(已修)**:sandbox 里 `cargo`/`rustc` 本体存在,但 `rustup
  toolchain list` 曾报 `no installed toolchains`。根因是 **sandbox 把 HOME 重定向**,
  导致 rustup 找不到宿主机上已装的工具链(工具链实际在 `/root/.rustup` +
  `/root/.cargo`,并非真的没装)。
- **修复配方(operator 已在 ah.toml 运行时注入区落地)**:给需要跑 cargo 的 agent
  角色(g1 gatekeeper、g1-m1 实施者)注入两个 env:
  `RUSTUP_HOME=/root/.rustup` 与 `CARGO_HOME=/root/.cargo`。注入后
  `rustup toolchain list` 能看到 `stable-x86_64-unknown-linux-gnu (active, default)`,
  `cargo`/`rustc` 可用(2026-07-10 实测 cargo 1.96.1;裸 crate `cargo check` 绿,
  证明工具链本身健康,唯一卡点是下条的系统库)。
- **tauri crate 还依赖系统库(operator 机器地基,agent 不自己装)**:
  `cargo check --lib` 目前在依赖 crate `libdbus-sys` 的 build.rs 上 panic 退出
  (exit 101),实测报错:

  ```
  pkg-config exited with status code 1
  Package dbus-1 was not found in the pkg-config search path.
  The system library `dbus-1` required by crate `libdbus-sys` was not found.
  thread 'main' panicked at .../libdbus-sys-0.2.7/build.rs:25:9: explicit panic
  ```

  `dbus-1` 只是构建顺序上第一个失败的;整条 GTK/webkit 栈都缺:2026-07-10
  `pkg-config --exists` 实测 `dbus-1 / gtk+-3.0 / glib-2.0 / gdk-3.0 / gio-2.0 /
  webkit2gtk-4.1 / javascriptcoregtk-4.1 / libsoup-3.0 / cairo / pango / atk /
  gdk-pixbuf-2.0` 全部 MISS(`pkg-config` 本体在 `/usr/bin/pkg-config`,存在)。
  这些系统库由 **operator 在宿主机地基上安装**,不归 agent(`apt install` 是机器
  地基权限)。装完前 `cargo check`/`test` 卡在 build 阶段、连 Rust 源都编不到,是
  **预期未解锁态**,不是环境配错;解锁以 operator 通知为准。下次直接对照上面报错
  定位:若仍卡 `dbus-1` 说明还没装完,若报错换成 `gtk+-3.0`/`webkit2gtk-4.1` 说明
  在往后推进。
- **CI 无 cargo/rust 门(重要)**:`.github/workflows/ci.yml` 的 5 个必过 check
  (`quality-gates` / `graph-agent-tests`×3 / `frontend-gates`)**不含任何
  cargo/rust 门禁**——这个 crate 不进 CI。因此**泳道1 gatekeeper 本地的
  `cargo test`(在 `apps/studio/tauri`)是该 crate 唯一的机器验证门**,不能因为
  "CI 不测"就降低本地验收标准(RED→GREEN 证据、回滚自检、全套 cargo test 整套跑,
  都按对后端一样的从严标准执行)。

## 3. 任务完成后的验收矩阵(按改动类型查表)

| 改动类型 | 验收方式 | 工具 | 人参与? |
|---|---|---|---|
| 纯逻辑 / engine / gateway / studio backend | 自动化:定向迭代 + 收口全量 | pytest / mypy / ruff | 否 |
| **前端 / UI** | 默认 **`agent` 自验**(2026-08-06 决议,取代 2026-07-06「详细点验归 PM」):agent 起 worktree 预览 + 冒烟 + 截图;合并收尾后在主 app 上**自己逐项点验**,交「逐项验证报告 + 截图」,PM 只看报告 | `scripts/wt-dev.sh`(动后端加 `--backend`),验自己端口,绝不验 5173;主 app 点验用 CDP 驱动真窗口(`RUN_AND_SCREENSHOT.md` §5)或 Playwright + sidecar bearer token | 否(PM 看报告,抽查可推翻) |
| 文档 / 纯 markdown | 物理实证:落盘路径 + wc/grep 关键内容;设计 doc 改动查哈希重钉 | ls / wc / grep | 否 |

**验收开关(acceptance-mode)**:涉及 UI 的任务默认 `agent` 自验(2026-08-06 决议);只有 brief 显式写 `user`(需要真人观感等 agent 测不了的维度)才把点验交给 PM,且用户不在场时不允许选 `user` 后干等——把可自动验收的部分先收口,UI 签收作为挂起项上报。

## 4. 红灯处置(收口全量红了怎么办)

1. 先证伪:对照主干(`origin/main`)单跑该测试,分清"既有红"还是"本次引入"。
2. 既有红 → 记录证据(主干同红的输出),不阻塞交付,单独立项修。
3. 本次引入 → 回红绿循环修,不允许"看起来无关"就跳过。
4. 已知 flaky 签名:backend `test_publish.py` 的 git-object "Could not read <sha>" = 重跑一次并留证;其余"同 commit 一红一绿"同理,重跑留证再判。
