# 血止批(批A)真机点验报告(2026-08-31)

> 点验对象:血止批 7 个 PR(#1076 M0 / #1077 T1 / #1078 T2 / #1079 BOM / #1080 M1 / #1081 X0 / #1082 M2),
> 合并至 `main @ ae3a5aa5` 并完成 vendor 重建后,由独立点验席在真 Tauri 窗口(CDP 9222)上逐项验证。
> 证据等级:第一手真机(dev 模式真窗口 + vendor 解释器 sidecar + 一次性隔离配置目录);
> 报告正文为点验席原文,仅「截图证据」一行由协调方改写为持久证据页链接。

七项点验全部完成。结论:六项 verified,一项(V7)如实标注「真机层面无独立可观察效果」。逐项报告如下。

## 环境（第一手核实）

| 项 | 事实 |
|---|---|
| 仓状态 | `main @ ae3a5aa5`（血止批 7 个 PR 已全在） |
| app 形态 | dev 模式真 Tauri 窗口（`studio-dev.ps1` → `cargo tauri dev`），WebView2 `Edg/151.0.4129.107`，CDP 9222；页面里 `isTauri=true`，非浏览器 web 模式 |
| sidecar | `apps/studio/tauri/vendor/python/x86_64-pc-windows-msvc/python.exe -m uvicorn app.main:app --port 8787` —— 证明跑的是新 vendor 快照 |
| 配置目录 | **一次性隔离**：`…/scratchpad/verify-bloodstop/config`（`get_sidecar_config` 回读的 `configDir` 就是它；目录内 `Skills/ llm/ media/ app_settings.json` 全新生成，Recent 起始为空）。用户真实凭据/skill 全程未被读写 |
| 黑板 | `WT_BOARD_AGENT=verify-bloodstop-1788228780`；`claim cdp-9222` + `claim main-app`（19:13 起，TTL 1h）→ 收尾 `release` 两者，`status` 已回「无占用」 |
| 收尾 | 隔离实例整棵进程树已 kill；`9222`/`8787`/`5173`/`8899` 四个口 curl 均 `000`。会话开始时机器上**本就没有 app 在跑**，所以未另起主 app（留机器如初） |
| 截图证据 | 全部 14 张已固化为证据页(截图原件在会话临时目录,会被清理):https://claude.ai/code/artifact/d2b213ae-b441-4fae-80ba-26edb67668d5 |

## 逐项结果

**V1（#1076 M0）protocol_unsupported 不销毁数据 —— verified**
操作：本地替身（`GET /v1/models`→200 三个模型；`POST /chat/completions`→404 空包体）录入为第三方 provider `StubProto`（base_url `http://127.0.0.1:8899`，假 key），UI 点 Test；再用 `PUT /api/llm/roles/verify_stub_role` 把 `fallback_chain` 指到 route `127-0-0-1-8899-openai-b6024fe773:stub-beta`；`force=true` 复测；最后把替身翻成 200 再 force 复测。
实测：① 首次 Test 后卡片徽章 = **Protocol not supported**，同屏仍列 **Available Models: stub-alpha/beta/gamma**；盘上三个 endpoint 全部 `status=failed / last_error_code=protocol_unsupported`，而 **6 条 route 一条没少**（`stub-alpha` 为 `failed`＝它自己那次被拒的探测，其余 `unverified_manual`——格子级判定没动任何 route 状态）。② 带角色引用做 force 复测（替身仍 404，替身日志确认真跑了 `/v1/models` + `/chat/completions`）：**6 条 route 仍在，`verify_stub_role` 对 `:stub-beta` 的引用计数仍为 1**。③ 替身翻 200 后 force 复测：endpoint `status=verified`、`last_error_code=None`，UI 徽章变 **Connected**，模型三条仍在，角色引用未动。
截图：`V1-01-after-first-test.png`、`V1-02-second-test-with-role.png`、`V1-03-after-force-revive.png`

**V2（#1078 T2）误杀拦截 —— verified**
操作：健康运行时经 CDP 原样合成 `window.dispatchEvent(new Event('studio-backend-http-unavailable'))`（事件名取自 `api/client.ts:99` 的 `BACKEND_UNAVAILABLE_HTTP_EVENT`），100ms 采样 banner 时间线；随后 `taskkill /F` 真杀 sidecar。
实测：伪信号 —— banner 在 **111ms** 出现（"Backend unavailable — some features are disabled. (Backend connection lost. Reconnecting…) [Retry]"），**1086ms 自行消失**回 ready；sidecar PID **10308 → 10308 不变**、端口 8787 不变（第二次重复实验：32920 → 32920 不变）。真杀 —— banner 出现，**约 8.7s** 后自动消失，新 sidecar PID 32920，**token 轮换实证**：旧 token 打 `/api/llm/registry` 得 **401**、新 token 得 **200**（`p5uWWb9QFpEy…` → `nAolDyWQB5Sw…`，均 64 位）。**端口没轮换，仍是 8787**——原因是 `studio-dev.ps1` 把 `STUDIO_SIDECAR_PORT=8787` 钉住了（日志原话 `sidecar: using pinned STUDIO_SIDECAR_PORT=8787 from env`），属 dev launcher 行为，不是缺陷。
截图：`V2-01-spurious-event-banner.png`（banner 在场且 PID 未变的同帧）、`V2-02-after-restart-recovered.png`

**V3（#1079 BOM）—— verified**
操作：隔离实例里新建 skill `bom-probe`，用 `[System.IO.File]::WriteAllBytes` 把 `EF BB BF` 拼到 `GRAPH.md` 前（241→244 字节，首四字节实测 `EF BB BF 2D`），`location.reload()` 后从 Recent 冷开。
实测：画布照常画出 **Input → init(AGENT) → Output**，phases 不空；Compile 只报 **一条**错误 `phases/init/SKILL.md:1 - llm_role - [F-v3-agent-llm-role-missing]`——那是 #1072 给新 skill 定的既有行为，而它本身就证明**编译器读到了 frontmatter 与 phase 列表**，没有任何 BOM/无 frontmatter/零 phase 类错误。追加了最锋利的那一档：经 Properties → graph properties 改 `description` 触发 GRAPH.md 写入（乐观锁路径），面板显示 **Saved**，界面与 console 均无 `snapshot_conflict`／conflict 字样，文件重写后 BOM 被写入侧按规范去掉（首四字节回到 `---\n`）。
截图：`V3-02-reopened-with-bom.png`、`V3-03-compile-with-bom.png`、`V3-04-graph-write-ok.png`

**V4（#1077 T1）统一信封 + CORS —— verified（自然触发成功）**
操作：把隔离实例里 `config/media/media_generation.json` 换成**同名目录**（Windows 上 open 目录抛 `PermissionError`，属 `OSError` 但不在已注册的 `FileNotFoundError` 处理器覆盖内 → 无人接管），带 `Origin: tauri://localhost` curl `GET /api/media/registry`。
实测：`HTTP/1.1 500`，body 正是形状 A 信封 `{"error_code":"STUDIO_INTERNAL_ERROR","http_status":500,"message":"Internal server error","details":null,"retry_strategy":"not_retryable"}`，`content-type: application/json`，响应头带 **`access-control-allow-origin: tauri://localhost`** + `vary: Origin` + `access-control-allow-credentials: true`，异常原文未泄漏。并做了因果那一半：保持破坏状态在 UI 打开 Settings → Media Generation，界面只出**局部**错误「Failed to load media generation config / Internal server error」，**没有 backend-unavailable banner**，sidecar PID **10308 → 10308 未变**（即"一个未捕获异常不再被当成整机掉线"）。验完已把文件还原，端点回 200。
截图：`V4-01-broken-media-ui.png`

**V5（#1081 X0）媒体保存 —— verified**
操作：Settings → Media Generation 填假 key（`stub-media-key-AAA111`），onBlur 提交；再改 `base_url` 为 `http://127.0.0.1:8899` 保存。
实测：配置目录新出 `config/media/`（先前不存在）+ `media_generation.json`，内容合法 JSON、含 key 与 base_url。改 base_url 后文件更新成功、`json.load` 通过、无损坏；额外实证 X0 的「谁让观察失效谁作废它」：`last_probe` 被置 **null**（旧凭据下的观察被作废）。目录 0700 在 Windows 上不可观察（`os.chmod` 只切只读位），据实标注。
截图：`V5-01-media-saved.png`

**V6（#1082 M2）新 vendor 下 registry 读端点 —— verified**
`GET /api/llm/registry` → **200**，body 为完整 registry 形状（`provider_endpoints` / `provider_routes` / `runtime_policy` / `roles`）；`/api/llm/roles`、`/api/media/registry`、`/api/settings` 同为 200，全部带正确 CORS 头。请求由 vendor 解释器起的 sidecar 服务（进程命令行已核）。

**V7（#1080 M1）—— 真机层面无独立可观察效果**
线协议校正是 gateway 内部判定，UI 无独立观察面。证据 = 单测 7 条 + 变异测试 + 协调方在 vendor Python 里的第一手 import 验证。未硬造场景。

## 附带发现（不在七项内，值得单独修）

**studio-verify 的 launcher 占位守卫会失守（fail open）。** `assert-claim.ps1` 是被 **dot-source** 进 `launch-studio-cdp.ps1` 的，它的 `exit 4` 拦不住调用方。用安全替身（不涉及真 app）两种拒绝路径都复现了：

```
✗ cdp-9222 is not claimed
GUARD: refusing
CALLER: PROCEEDED TO LAUNCH        <-- 本不该到这
exit=0
```

含 SKILL.md 文档的那种 `powershell -File` 调用形式。也就是说**没占黑板也照样会重启共享 app**——正是 2026-08-15 那次事故要防的事。已开后台任务 `task_21e8c0d6` 记录复现配方与修法方向（把守卫改成被调用+查退出码，或 `throw` + `ErrorActionPreference=Stop`；并顺手解决 detached PowerShell 不继承 Git Bash 造成 `bash` 找不到而误入拒绝分支的问题）。`lease-guard.mjs`（click/emulate）不受影响，它的 `process.exit(4)` 在同一进程里生效。

**一次对外请求需要报备**：V5 存入假 media key 时，界面**自动**发起了一次 runninghub 账户探测（免费查询类，返回 `auth_failed / APIKEY_USER_NOT_FOUND`），不是我点的 Test，无费用、无真实凭据。发现后我立刻把 base_url 改到本地替身，后续探测全部留在 127.0.0.1。全程零真实付费 LLM 请求。

**一处观察没坐实原因**：V1 第二次用 UI 点 Test 时后端**没有收到任何请求**（sidecar 日志与替身日志都无新行）。可能是 30 天半衰期/近期已测的短路，也可能是模型列表出现后布局变化让我按索引选中的元素不是卡片级 Test。我没有把因果钉死，所以不作结论——V1 的决定性一步改走了指名 endpoint id 的 `force=true` API。

**坐标漂移**：StubProto 的 Test 按钮随徽章/模型列表出现从 y≈569 漂到 y≈450；`click.mjs` 每次按表达式现算坐标，所以没受影响。破坏性点击前都先只读打印过目标归属（走 depth-4 祖先文本判定，确认只含 StubProto、不含任何 Official provider）才下手。
