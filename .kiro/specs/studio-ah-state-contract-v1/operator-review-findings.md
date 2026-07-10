---
spec: studio-ah-state-contract-v1
doc: operator-review-findings
date: 2026-07-09 (evidence re-verified 2026-07-10 on ah 1.5.0)
verdict: 方向批准、细节返工——按 F1–F9 修订 requirements/design/tasks 后才可进实施
---

# Operator 评审发现(studio-ah-state-contract-v1)

评审方法:spec 五件套逐句核对真实代码(apps/studio/tauri/src/lib.rs @ main)与
真实 ah CLI 行为(WSL 实测,评审时 1.4.0,以下标注处已在 1.5.0 复验)。
所有行号以 2026-07-09 main 为准。

## 总判

spec 的诊断正确:Studio 在 Tauri 层维护了第二套更弱的状态机(`ah ps` 文本解析 +
tmux 名字前缀猜活性 + 直杀 tmux),必须换成 ah 结构化状态合约。这个方向不动。
但 requirements/design 把新合约降维使用,并留有结构性缺口,逐条见下。

## F1(阻塞)· `ah status --json` daemon-absent 是非结构化错误

实测(1.4.0 与 1.5.0 相同):daemon 不存在时 `ah status --json` exit 1,
stderr 输出人话 "ahd daemon is not running at ...",**无 JSON**;
而 `ah events --format json` 同场景输出结构化快照
`{"reason":"daemon_absent","runtime_state":"inactive","ahd_alive":false,...}`。
后果:design 的 open 流程在最常见状态(首次打开、无 daemon)拿到的是错误而非
"inactive 可启动";close 流程 stop 成功后复查 status 也会 exit 1——成功被判失败。
若 Studio sniff stderr 文本区分,等于再造一个文本解析,违背 Req 2.3 精神。
处置:①上游 ah 修 status 输出与 events 一致的 daemon_absent 快照(issue 由
operator 提交);②Studio 侧以 events 流为主决策面(见 F5),status 仅兜底/诊断。

## F2(阻塞)· 状态机死角:degraded 下用户无任何可用操作

真实快照实测存在该状态:`active:false, runtime_state:"degraded"`,一条 session
`status:"ACTIVE"`(live_agents=10、master tmux 死、cleanup_required:true)。
按 Req 3.1(Attach/Close 仅 active=true)与 Req 3.2(Open 仅全 session 终态),
degraded 时三个按钮全灭;tasks.md task 5 还明文"inactive 或 terminal 时才允许
start"。用户永久卡死,而这正是要修的原始 bug 场景。现有代码的 CleanupStale 路径
(lib.rs:357-368、2358-2361)今天反而能自愈——照 spec 字面实施是功能回退。
上游已给答案(ah 1.3.4 CHANGELOG 原文):"Consumers such as Studio should clean
up only `degraded` runtimes; `starting` means startup is still in progress and
must be left alone." spec 通篇未出现 starting/degraded 两词。
处置:requirements 补显式语义——`degraded` → 暴露 Open(先按快照清理再启动);
`starting` → hands-off,UI 显示启动中;并以 runtime_state 相位取代
"active 布尔 + session 终态"的自行推导。

## F3(高)· 前端事件 payload 表达力不足,design 自相矛盾

现 payload `{claude: bool, codex: bool}`(lib.rs:63-73)。design 一边要求 UI 呈现
error/unsupported-contract/starting(task 7、Req 2.4),一边说保持现有事件形状
(design.md "the existing frontend event shape at the UI boundary")——不可能同时成立。
另有 lib.rs:1244-1246 `if status.claude { status.codex = false; }` 对 UI 谎报,
而前端本身支持双活(copilot-panel.tsx:303-306 有 "Close assistants" 复数分支)。
处置:payload 扩为 per-assistant 状态枚举(inactive/starting/active/degraded/error)
+ reason/diagnostic 字段;删 claude-wins 抑制(本仓 no-backward-compat,直接改);
requirements 显式回答「一个 workspace 只允许一个 Studio-managed ahd」不变量
(ah-orchestration-design.md:12)在新模型下是否保留。

## F4(高)· 两个所有权安全漏洞

**4a** `find_ah_config` 向上爬目录(lib.rs:203-218)且优先于 temp config
(lib.rs:828-833)。本仓根自 PR #478 有 ah.toml → 在本仓树下任何 skill workspace
打开 Studio,Close/quit 会对**用户自己的 operator 编队**执行 ah stop + 强杀。
Req 4.4/4.5 未覆盖 workspace 自带 config 的归属。
处置建议:workspace 自带 config 仅允许 attach(观察);生命周期管理(start/stop/kill)
只对 Studio temp namespace(%TEMP%\skill-studio-ah)的 config 生效。requirements 落条款。

**4b** ah 文档明文 `AH_STATE_DIR` 优先级高于显式 `--config`(README + 1.4.0
CHANGELOG #117 优先序),且 README 推荐用户 pin 它;Studio 拉 ah 用
`wsl.exe -e bash -lc`(login shell,lib.rs:858/879/927)会吃进用户 profile。
用户 pin 过 → Studio 全部 temp config 塌缩到同一 state dir,状态互串、清理越界。
处置:requirements 加两条——①adapter 拉 ah 时钳制 AH_STATE_DIR/CCBD_STATE_DIR/
XDG_STATE_HOME(清除或显式 pin);②快照身份校验:收到的 snapshot 其
config_path/state_dir 不属于所请求 config 即拒绝采信(这是 Req 2.5 的落地牙齿)。

## F5(中)· 双读取面无一致性语义

events 常驻流 + status 一次性读,同一 truth 两个面,spec 未定义谁赢。
快照有 `sequence` 字段(实测在)——K8s resourceVersion 同款解法。
处置:events 流缓存为唯一决策面,写入按 sequence 单调;status 仅在无流时引导读/
诊断。design 明写此仲裁规则。

## F6(中)· 版本门槛已有旧实现,spec 未提,必成双真相

现有版本门在生成的 launcher shell 脚本里,门 >= 1.3.4,同一段 awk 检查 4 份拷贝
(lib.rs:1754/1836/1903/1960)。Req 1.x 的 Rust 层新门(>= 1.4.0)若不收编它们,
两层各说各话。版本门也未覆盖 events 订阅(lib.rs:1355 起流不检版本;老 ah 无
events 子命令 → 3 秒一轮无限重生)。
处置:版本常量单源(Rust 层定义,launcher 脚本模板引用同一值);门槛覆盖 events
订阅;版本检查结果按会话缓存(Windows 下每次 ah 调用是一次 wsl.exe 往返)。
注:实测 `ah version` 输出裸 "1.4.0",`ah --version` 输出 "ah 1.4.0",解析取后者需 awk $2。

## F7(中)· 设计文档与嵌入提示词钉死旧模型,tasks 无回写任务

落地本 spec 必须同 PR 更新,否则设计与代码立刻打架(AGENTS.md:MVP1 design =
source of truth):
- docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md:185-193
  (活跃判定=两布尔;"runtime_state 只有 Active/Degraded/Inactive、没有 Starting"
  ——已被 1.3.4 证伪)、629-644(把 ah ps 解析/tmux 兜底写成必须遵守的规则)、
  553/644("ah status 不是可用命令"——1.4.0 起为假);
- lib.rs:550 moirai-intro skill 文本同句(与 moirai spec 的 cli.md 收缩决策方向一致,
  该 spec 已判此条作废;两 spec 同改 lib.rs,需排序——本 spec 先行)。
处置:tasks.md 增加设计回写任务,列出上述三处锚点。

## F8(中)· 数据模型抄了 README 旧示例;漏关键字段;重复造 ah 已有判断

research.md 自己警告"不能硬编码 README 示例",design 数据模型仍中招:
- `activeAgents` 在真实 v2 快照不存在,实际是 `live_agents`(+`db_tracked_agents`);
- 模型缺 `ahd_alive`——Req 3.3 与测试 5.1 的判定字段,没它无法实现;
- `configPath` 实测可为 null(daemon 无 config 启动),模型标了必填;
- 漏 `sessions[].safe_to_cleanup` / `cleanup_required`——ah 已算好每 session 清理
  资格,Req 4.2 的清理编排应直接消费这两个字段,不自行推导"非终态即 kill"。
另:Req 3.4 防重复启动依赖"ah start 对已活跃 stack 拒绝"这一未验证假设,
实施前需真实 CLI 验证,tasks 列为前置验证项。
新增(2026-07-10 于 1.5.0 实测):state-dir 解析不一致仍在且换边——同一 cwd
(含 ah.toml 的目录)下无 --config 时 `status`/`ps` 落 default、`events` 走
project discovery。佐证 F4b 的快照身份校验必要性;已列入上游 issue。

## F9(低·流程)· INDEX 未登记 + 阶段规则

.kiro/specs/INDEX.md 无本 spec 行(修订时补上,只加本 spec 的行,不动他人未提交内容);
INDEX 阶段规则(2026-05-19)要求 design/tasks 由 PM 解锁——本 spec 四件套一日生成,
修订版提交时由 PM(用户)终审即视为补票。

## 修订完成的验收标准(a4 审计据此判)

1. F1–F8 每条在修订后的 requirements/design/tasks 里有可指认的对应改动(逐条溯源表);
2. 修订版不再含与真实 CLI 冲突的字段/行为断言(以本文档实测记录为准;实施期再采
   真 fixture);
3. degraded/starting 全生命周期(UI 语义、清理资格、测试 fixture)闭环;
4. 每个新增声明都有出处(代码行号 / CLI 实测 / 上游 CHANGELOG),无凭印象断言;
5. tasks.md 保持 TDD 顺序(先 fixture/失败测试后生产代码),并含 F7 设计回写任务
   与 F8 的 ah start 行为前置验证项。
