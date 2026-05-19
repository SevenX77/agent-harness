# Studio Skill 项目 Git 协作系统 — Design

> Status: Draft v3 (round 7 收敛)
> Date: 2026-05-13

## §1 26 条核心决策

1. 砍隐式 fork, 直接改本体
   - **Why:** 桌面单机且无多 User 交叉污染场景下，隐式 Fork (Copy-on-Write) 造成认知割裂。开发者期望像传统代码开发一样，修改了组件就能立刻全局生效。
   - **How to apply:** 废除后端 `services/skills.py` 中的 `_writable_skill_dir_async` 拷贝逻辑，取消基于工作区的私有副本生成。所有读写路由均直接导向原始物理存储位置，真正做到所见即所得。

2. `.workspace/` 嵌 skill 文件夹
   - **Why:** 增强项目目录的便携性与自包含性，符合现代开发工具（如 `.vscode`、`.git`）对于项目私有配置存放的直觉。方便用户随意移动文件夹而不丢失状态。
   - **How to apply:** 本地调试生成的一切非公开制品（包括 Log、黄金测试基线、本地 UI 偏好等）均必须统一落入 `<skill_root>/.workspace/` 隐藏目录内，与代码业务文件严格物理隔离。

3. Skill 本体位置 user 自由, 系统给 OS-specific 默认
   - **Why:** 强加固定的全局路径反而会使用户无所适从，违背本地工具的灵活性，且对多盘符用户不友好。但同时为了降低门槛，需提供各平台最符合习惯的默认 AppData 路径。
   - **How to apply:** 初始新建弹窗默认路径为 Mac 的 `~/Library/Application Support/AgentStudio/Skills/` 或 Linux 的 `~/.local/share/AgentStudio/Skills/`，同时允许用户点击“浏览”自定义到任意磁盘。

4. `skill_index.json` 索引 (一 skill 一 git 仓)
   - **Why:** 在允许用户自由选择存储位置后，系统需要一个全局权威路由表来映射 Skill ID 与用户的任意物理路径，并统一管理每个仓库的关联状态。
   - **How to apply:** 在 OS 的应用全局配置目录下维护该 JSON 文件，记录形式如 `{skill_id: {"absolute_path": "...", "l2_remote_url": "..."}}`，作为启动时定位项目的唯一信源。

5. Auto-commit 强制 (L1 每次 run)
   - **Why:** 确保能够得出输出结果的每一次 Prompt 实验态，均可以在本地被绝对安全地复现与回溯。这避免了 PM 在反复微调中错失曾经表现最好的某个版本。
   - **How to apply:** 在每一次引发引擎执行的操作钩子生命周期结束时，后台静默发起 `git add -A && git commit -m "auto-run-<id>"`，将当前有效工作区固化为 L1 历史的一个节点。

6. `.studio.json` 抛弃
   - **Why:** 失去 Fork 源记录等特殊元数据挂载需求后，该文件已无保留价值。剩余仅存的项目级 UI 状态（如面板折叠）应收敛至隔离区。
   - **How to apply:** 彻底删除代码中一切针对该文件存在的读写与 Schema 检查逻辑，将其历史职责移交至 `.workspace/local_settings.json`。

7. example/ 是 skill 规范可选目录
   - **Why:** 绝大多数轻量级 Skill 无需挂载繁重的外部参考样例，新建即强制生成会显得项目结构过度臃肿，增加新手的理解负担。
   - **How to apply:** 去掉新建项目模板里的该默认目录。仅当用户确有 RAG 挂载数据或引用需要时才自行建立并存入，该目录一旦存在便会跟随进入云端。

8. Golden 在 `.workspace/golden/` (不在 skill 本体目录)
   - **Why:** 黄金基线数据 (Golden) 是帮助开发者度量当前 Prompt 质量的局部测试尺子，它不属于发往生产端运行所需的业务文件，不可直接交由生产端消费。
   - **How to apply:** 修改原先放置于根目录或数据库的存储函数，将落盘路径硬编码限制在 `.workspace/` 内，但通过特例放行使其能参与版本控制共享。

9. User ID 全局配置, publish 时挂 author
   - **Why:** 确保发布到云端的不可篡改产物有准确的追责人（PM ID）。但该 ID 不应硬编码入本地文件，以防止被其他同事 Copy 文件夹后引发的身份歧义。
   - **How to apply:** 只在执行 Publish 发行到 L3 的那一刻，后端通过读取系统的 `app_settings.json` 动态获取全局 ID，并组装进发版 Payload 或 Metadata JSON 中。

10. Studio User ID = git config user.name
    - **Why:** 减少身份系统的多重映射成本，避免让用户产生“系统登录名与 Git 作者为什么不一样”的困惑。L2 Gitea 与 L1 本地历史均使用这个唯一的身份标识。
    - **How to apply:** 当涉及 Git 初始化的前置操作时，系统优先以该 User ID 执行更新本地的 Git author config，确保产出的 Commit Signature 与身份一致。

11. L2 backend = Gitea (后端 API 静默对接, 前端屏蔽)
    - **Why:** 借助成熟开源工具完成复杂的协作、鉴权与 PR 工作，极大地节省自研轮子成本。同时用企业级 API 服务代理调用，免除 PM 学习 SSH 密钥和 Git Token 的巨大痛苦。
    - **How to apply:** Studio 内部实现一套封装好的网络请求 Client，专门与部署在内网的 Gitea API 对话，将底层复杂逻辑转换为简单的 HTTP 调用。

12. L3 backend = Artifact Registry (非 git)
    - **Why:** 生产端管理不需要开发阶段的冗长历史轨迹，只需要开箱即用、确定性极强且有数字签名的最终业务分发包。Git 对于 L3 是一种过度设计。
    - **How to apply:** Publish 环节彻底摒弃 Git Push 范式，改为将纯净的业务所需文件打包成压缩包 (`.zip` / `.tar.gz`)，通过 POST 接口直接上传至制品服务器。

13. PM 心智 = 4-5 个业务名词按钮
    - **Why:** “Repository”、“Pull Request” 等纯 Git 技术术语对于短剧 PM 等非技术内容创作者是巨大的认知屏障，只有业务名词才能引导正确操作。
    - **How to apply:** 界面 UI 坚决只展现："Local History" (查看回滚)、"Save to Team" (推送保存)、"Submit for Review" (发起合并)、"Sync from Team" (拉取更新)、"Release to Production" (发版)。

14. Studio 面向公司内部使用
    - **Why:** 确立明确的网络安全与应用前提，系统部署不需要考虑公网暴露防护与复杂的跨企业多租户隔离，极大降低运维与鉴权架构的复杂度。
    - **How to apply:** 以内网专线联通作为 L2 同步操作的基础前提，省去复杂的 OAuth 或企业间 SSO 对接流程。

15. 单 PM 项目跳过 PR, 直接 push main
    - **Why:** 针对无管理协作要求的个人全权项目，强行要求自我审核是不合理的形式主义，完全与追求敏捷的效率背道而驰。
    - **How to apply:** 只要该操作者有直推权限且未遇到保护拦截，"Save to Team" 按钮就等价于底层静默执行 `git push origin main`。

16. 强力排斥海量 Runs 入 Git, 放行 Golden 和 Predict (纯本地偏好亦隔离)
    - **Why:** Tracing 产物（Runs）及纯本地 GUI 状态（`local_settings.json`）如果入库 L2 必定导致极差的拉取体验，甚至直接拖垮 Git。但 Golden 和 Predict（批测结果）需要进行协作质量把控。
    - **How to apply:** 初始化 `.gitignore` 时强制写死排除 `/.workspace/*`，并且针对性添加特赦规则 `!/.workspace/golden/` 及 `!/.workspace/predict/`，以豁免高价值数据的同步。明确 `local_settings.json` 永远属于排斥范围，不进 L2。

17. zip 打包作为 Bug Report 平行 channel
    - **Why:** 当面临引擎本身的疑难杂症，需连同海量的 Tracing 现场完整移交底层专家排查时，此需求超脱出正常版本迭代体系之外，不能依靠 Git。
    - **How to apply:** 提供 "Export Bug Report ZIP" 菜单按钮，单纯将含 `runs/` 在内的整个工作区物理打包并输出至桌面供用户通过 IM 外部流转，不入任何版本系统。

18. L2 backend = Gitea 客户自建 (场景 A)
    - **Why:** 面向 ToB 或企业内用场景时，数据绝对不出域是红线级别的合规条件。客户自身 IT 控制的 L2 宿主最符合这一安全诉求。
    - **How to apply:** Studio 默认在 Settings 偏好页提供填入私有 Gitea 部署地址的选框，由用户所属的企业运维去统一分发初始参数并连通。

19. 403 HTTP Error 的前端流智能切轨
    - **Why:** 兼顾便捷与严格治理双重可能性。当个人的“草台班子”随着成员增加被升级为带保护的规范库时，工具必须有能力智能重路由，不至于报错卡死。
    - **How to apply:** 全局拦截针对主干推送返回的 403 错误，并在 UI 通过 Toast 提示拦截原因，随后静默自动将底层工作流状态机切换至需审批的 PR 模式。

20. PM 在个人分支提交保留粒度，合并委派 Squash
    - **Why:** 如果过早在本地或提交时 Squash 压扁，则 PM 换机后将彻底丢失跨终端接续修改的颗粒度。细粒度必须保留到合并的最后一刻。
    - **How to apply:** PM 向团队的日常提交推送至专属隔离分支 `dev-<user_id>` 时不做任何改写。精简历史的合并动作全部委派给 Gitea 服务端的 "Squash and Merge" 完成清理。

21. Git 身份局部注入机制与伪邮箱结合
    - **Why:** 绝对不能因为操作 Studio 而污染、篡改宿主机默认的 `~/.gitconfig` 身份，导致研发人员其他的正常代码库 Commit Author 出错。
    - **How to apply:** 在底层明确挂载 `--local` 参数指明仅作用于当前仓库。结合 `<user_id>@studio.local` 的专属伪邮箱设定，完美实现隔离与标记。

22. 配置文件不一致仲裁
    - **Why:** 既然赋予了物理文件夹独立存在的权利，当用户可能手动移动目录或使用其他工具干预 `.git/config` 后，系统不能盲目自大覆写可能合法的设定。
    - **How to apply:** 在启动或加载 Skill 阶段进行探测比对，若遇歧义，在 UI 不打断区域出对话框提示，以 `.git/config` 为基准推荐真值进行仲裁确认。

23. V1 核心支持单线历史点位 Revert
    - **Why:** 提供基础的挽救回退能力即足以对抗大部分的错误试探。对于首发 MVP，更复杂的分支比对切换开发成本高昂且非核心主线。
    - **How to apply:** UI 界面着重设计一条单向时间线的历史快照选择列表与回滚逻辑，将 Diff Viewer、分支选择与高级合并冲突面板规划进后续演进的迭代看板。

24. L3 Metadata 满足审计
    - **Why:** 对于严谨的生产端而言，一份附有“谁、在何时、出于何种目的”签发出的定格证明已经能够充分完成所有合规风控审查与阻断。
    - **How to apply:** 制定一套专有的 L3 上传 Metadata 附带协议，在打包时提取全局配置与最新变动，随同二进制包体直接发往 Registry 对应 Endpoint。

25. 最新执行现场（Latest）的条件放行策略
    - **Why:** Auto-commit 每次收录全量 Latest 及 Phase Context 必然引发 L1/L2 灾难性体积爆炸，且干扰代码本身的微小变更轨迹。但跨端需要 Resume Context 及最后的运行断点。
    - **How to apply:** `/.workspace/runs/latest/` 持续保持被 `.gitignore` 阻断。在用户点击 "Save to Team" (手动同步) 时，底层才特别执行一次 `git add -f .workspace/runs/latest/` 连同本次手动发版将其快照上传 L2。这确保了 L2 在每次共享时总能保留最新现场，但 L1 依然规避了海量体积干扰。

26. 文件外部锁定的非静默弹窗机制
    - **Why:** Windows/VSCode 环境的锁竞争会导致 Git 写入崩溃，若静默掩盖则会吃掉用户的回撤资产（零容忍红线）。
    - **How to apply:** Git 提交操作设 3 次循环重试，若全部挂起失败，则发出带有行动指引的阻断级 Toast：“本次变更入库遭遇外部文件锁拦截，请关闭 VSCode 等程序并手动点击重试”，并在左下角触发红色警告 Badge 提示数据游离状态，交还处理决策。

## §2 三层 Git 架构总览

| 层级 | 实体角色 | 数据内容 | 网络属性 | 参与方 | 核心用途 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **L1 本地** | 本地隐式 Git (脏仓) | 源文件 + Golden + Predict + Auto-run + Latest 现场 | 断网可用 | 单机 PM | 即时保存进度结果，支持频密试错与微调点断点回溯。 |
| **L2 协同仓** | 内网 Gitea 仓 | 源文件 + Golden + Predict + 手动传入的 Latest | 连通内网 | 成员审批人 | 正式主干控制与终端之间状态接力的传输带。 |
| **L3 发布仓** | 生产 Artifact | 纯业务源包 | 连接总线 | 消费端 | 生产端确定性制品的单向提供口。 |

```text
[PM 本机 (L1 脏仓)]               [L2 协作仓 (Gitea)]                   [L3 发布中心 (Artifact Registry)]
       │                                 │                                    │
       ├─(1) 新建Skill ─────────────────>│(API 静默建仓)                        │
       │                                 │                                    │
       ├─(2) 修改代码/跑测试             │                                    │
       │  (L1 Auto-Commit 略去 Latest)   │                                    │
       │                                 │                                    │
       ├─(3) 保存工作接续态 / 审批       │                                    │
       │───(带上Latest 快照向远端Push)──>│ (直入 main 或推入 dev-branch)        │
       │                                 │                                    │
 [Admin审批端]                           │                                    │
       ├─(4) Web 审核合并                │                                    │
       │───(点击 Approve & Merge)───────>│ (Squash 压扁并合并到 main)           │
       │                                 │                                    │
 [PM 本机]                               │                                    │
       ├─(5) 点击 Publish 发生产 ────────┼───────────────────────────────────>│ (6) 本地打包发包
       │                                 │                                    │ POST /api/v1/publish
```

## §3 完整目录树

### §3.1 L1 本地 (含 L2 remote 配置)

```text
<user_chosen_skill_root>/story-deconstruction/
├── .git/                          # L1 脏仓 (含 L2 remote)
├── SKILL.md
├── script/
├── example/                       # 可选
├── .gitignore                     # 规则：`/.workspace/*` 与反向放行 `!/.workspace/golden/`, `!/.workspace/predict/`
└── .workspace/
    ├── golden/                    # 调试基线快照 (跟云走)
    ├── predict/                   # 批测结果输出 (跟云走)
    ├── runs/
    │   ├── latest/                # 最新的一次执行与断点 Resume Context。受限入Git。
    │   └── <timestamp_id>/        # 海量历史记录 (绝对隔离在本地，防塞爆)
    └── local_settings.json        # 纯本地设定 (绝对隔离)
```

### §3.2 OS 级 (Studio 全局配置 + skill index)

```text
~/.local/share/AgentStudio/
├── app_settings.json              # 核心配置，内含 {"User ID": "sevenx"}
└── skill_index.json               # 映射表 {"skill_id": {"absolute_path": "..."}}
```

### §3.3 L2 Gitea sync repo 结构

```text
<sync-git-host>/<owner>/<skill_id>/
├── SKILL.md
├── script/
├── example/                       
└── .workspace/                    
    ├── golden/
    ├── predict/                   
    └── runs/latest/               # 同步上传的终端衔接工作断点与报告。
```

### §3.4 L3 Artifact Registry 结构

```text
<cloud-release-host>/packages/<skill_id>/
├── SKILL.md
├── script/
└── example/
# [注意]: 彻底没有 .workspace 的任何痕迹。
```

## §4 数据流图

### §4.1 新建 Skill 项目流程
1. PM 选定任意物理存储路径生成并建立项目；
2. Studio 后台生成基本模板后拉起 `git init` 为该工程配置 L1 ；
3. Studio API 代理对接内网的 Gitea 服务器，根据 `skill_id` 自动划拨对应的线上版图并附着于 Local 的 `.git/config`；
4. 全局 OS `skill_index.json` 更新最新绑定情况。

### §4.2 跨终端继续工作 (衔接 Latest 态)
1. PM 在终端 A 内进行了一日工作（期间经历了 N 次剔除 Latest 的本地 Auto-commit），预备离开时按 “Save to Team”；
2. 系统使用 `git add -f .workspace/runs/latest/` 把最热乎的一刻执行断点与产物吸入快照并发送至远端分支；
3. 返回家中开启终端 B，Sync from Team 后，`.workspace/runs/latest/` 内自动恢复上次保存的 phase context (中间状态)，点 Run 直接从该状态接续，不必从头跑起。

### §4.3 多 PM 协作流程 (PR + admin 审批)
1. 项目主分支被管理员设置成保护状态，PM 点 "Save to Team" 试图推送到 `main` 时收到服务器 403 拒绝；
2. UI 组件抛出拦截通告，按钮功能翻转为 “Submit for Review” 面貌；
3. 状态自动绕开阻挡退回 `dev-<user_id>` 分支推送，并同时召唤 Gitea 拉取一条关联主干的 Pull Request；
4. 审批人在 V1 阶段将接到外部系统或邮件发起的提示并前往 Web 端进行审核操作；
5. 在 Gitea 管理端完成确认，代码经过 Squash 压扁精简合规并挂靠 `main` 线上正式主分支。

### §4.4 Publish 到生产端流程
1. 由 PM 核定本地最新的工作完全达标；
2. 触发主界面的 “Release to Production” 按钮；
3. 核心文件层进行压缩打包重构（彻底刨除无关测试及记录的 `.workspace/`）；
4. 追加了自身全局 User 信息的载体包通过 Client 向 Registry POST。

### §4.5 Revert 流程
1. “Local History” 面板展现一条条由 Auto-run 汇集形成的可回溯点。
2. 对于误入歧途的状态选择前序节点 “Revert” 重载状态；
3. 如未报错冲突则该次状态通过 Git Reset 被覆写回活动工程面板中继续开发。

## §5 用户视角操作手册

1. **Local History**
   - *触发条件*: 任何本地开启了项目的时刻。
   - *后台机制*: 读取 L1 `git log`，剔除特殊记录。
   - *失败处理*: 若本地 `.git` 库损毁导致无法读取，界面展示空列表，并出现 "版本记录已损坏，请重新初始化" 提示。

2. **Save to Team**
   - *触发条件*: 想要在多台电脑间周转，或保存最新状态。
   - *后台机制*: 
     - 执行强制携带 Latest 工作台状态入列快照：`git add -f .workspace/runs/latest/`。
     - 单 PM 模式直接推送 `main`，团队模式推送 `dev-<user_id>` 以周转同步状态。
   - *失败处理*: 网络断开时提示 "无法连接服务器，已保存本地"；若遇到远程变更造成的严重代码冲突无法通过快速 Rebase 解决时，弹出要求介入的手工修复对话框；被服务器设限拒收（非 403 保护，而是其他致命验证失败）时原样呈现拦截信息。

3. **Submit for Review**
   - *触发条件*: 被管理员设限阻拦后明确向主分支提交集成。
   - *后台机制*: 确保隔离分支稳定推进，拉起 Pull Request 请求合并动作。
   - *失败处理*: 如果当前没有新内容或分支被删，提示 "无变更可供合并"；若 Gitea 返回创建 PR 失败，给出 "合并请求提交失败，请联系管理员" 并暂存未决状态。

4. **Sync from Team**
   - *触发条件*: 恢复至其他终端环境或其他同事有新的特性并入主干。
   - *后台机制*: 执行包含带下 Latest 复原及 Rebase 处理等特性的操作。
   - *失败处理*: 若下拉时遇到本地有未完成的工作态导致的覆写污染冲突，给出 "本地有修改，同步将覆盖当前操作：[强制覆盖] [稍后再试]" 对话框供抉择。

5. **Release to Production**
   - *触发条件*: 生产上线条件满足。
   - *后台机制*: 剥离环境并 HTTPS 投递打包物件。
   - *失败处理*: 制品库 Registry 如果返回 401 拒权或 500 崩溃，抛出 "发版校验失败或网络异常，当前版本仍留存在草稿区"，不中断后续开发。

## §6 实现路径 (现状代码 → 这套架构)

### §6.2 实施路径概述
本次架构重构将彻底摒弃原有的隐式拷贝机制，使一切读写操作直达以 `skill_index.json` 为基准的物理源目录。核心产物将分类收口于 `.workspace` 内，配合新增的自动监听 Commit 基建，以及基于 Gitea 和 Registry 的内网双轨推送 Client，最终构建出对 PM 无感的“保存-审批-发版”全业务态流转链路。

### §6.3 关键改动与顺序 (P0/P1/P2)
- **P0**: 基建改造。落盘目录变轨；实施 `.gitignore`（放行 `golden/`, `predict/`，排除其外一切 `/.workspace/*`），停用旧时伪副本。
- **P1**: L1 版本基座建设。完善携带重试告警容错能力的 Auto-Commit 工具链。
- **P2**: 系统连接扩展 (详细执行清单)。
  - **P2.1 GitCollaborateService**: 创建 `apps/studio/backend/app/services/git_collab.py` (从现有 Service 如 `skills.py` 借鉴依赖注入)。修改 `apps/studio/backend/app/routers/skills.py` 约 15 行引入区域附近，增加 `POST /skills/{skill_id}/sync` API Endpoint 以对外发送 Gitea 交互指令及拉起 PR。
  - **P2.2 Artifact Registry Client**: 创建 `apps/studio/backend/app/services/artifact_registry.py`，并在 `apps/studio/backend/app/routers/skills.py` 中增加 `POST /skills/{skill_id}/publish` 对接云端注册表。
  - **P2.3 GUI Settings 更新**: 查改 `apps/studio/uikit/src/components/studio/settings-page.tsx` 约 45 行附近（配置表单区域），新增 "Studio User ID" 和 "Gitea Host" 对应的 Input 字段进行 Context 持久化映射。
  - **P2.4 网络全局防护**: 创建 `apps/studio/uikit/src/lib/api-client.ts` 封装全局 Fetch，在响应拦截器中捕获 Status === 403 并在 catch 块中联动 `use-toast` 抛出提示并触发切换审核模式的界面重定向。

## §7 TODO 
- [ ] 系统层 Gitea SSO 与独立本地局域 User 伪邮箱 `<user_id>@studio.local` 之间的映射拉取优先级交接逻辑（已部分收敛: 参见 §8.4 SSO Token 方案, 但需在实施时 verify 单 PM 多终端的 Token 同步行为）。
- [ ] Token 失效期的自动唤醒边界: 当 PM 开启 Studio 长达几天未动，若点击 "Release to Production" 遇到 `401 Unauthorized`，重新拉起 SSO Webview 可能会打断上传的进行态，造成状态丢失，需细化重入补偿机制。
- [ ] Gitea Git CLI OIDC 免密: 尽管 L3 可以透传 OIDC Token，在 L2 Gitea Pull/Push 中如果无法完全规避 `git` CLI，如何将 SSO Token 自动转换成 Git CLI 能认的免密凭证仍需通过 GitCollaborateService 实施时验证。

## §8 L3 Artifact Registry API 契约

### §8.1 设计原则
1. **不可变与确定性 (Immutability)**: 发布的产物版本（Artifact Version）一旦成功推入 Registry，即被视为最终防篡改快照。同版本号禁止二次覆盖推送，如有修改必须发起 Version Bump 升级。
2. **重载 Metadata 与解耦二进制**: `multipart/form-data` 是兼顾传输大体积打包文件与结构化元数据的最优解，保证流式处理时不因等待 JSON 体载入而造成内存瓶颈。
3. **强源头溯源 (Auditability)**: 制品除了自身必须纯净外，强制要求包含操作者 User ID（从统一下发的 `app_settings` 中剥离）以及对应在协作 L2 Git 上的 Commit SHA，确保出问题时能在代码线上双向溯源。
4. **无感与自动推进 (Frictionless)**: 为了适应缺乏研发心智的非技术型 PM（短剧编导等），严禁暴露复杂的 API Key 机制与手动 Semantic Version 选号框。系统通过自动追加内部补丁号实现无感推进。

### §8.2 Endpoint 总览表
| Method | URL | 用途 | v1/v2 |
|---|---|---|---|
| POST | `/api/v1/skills/{skill_id}/publish` | 上传业务包及发布 | v1 (MVP必备) |
| GET | `/api/v1/skills/{skill_id}` | 列出所有发布的 Version 摘要 | v1 |
| GET | `/api/v1/skills/{skill_id}/{version}` | 下载特定版本的二进制 Zip | v1 |
| GET | `/api/v1/skills/{skill_id}/{version}/metadata` | 仅取版本 Metadata 不下载实体 | v2 |
| DELETE | `/api/v1/skills/{skill_id}/{version}` | 撤回(Yank)废弃有毒版本 | v2 |

### §8.3 Publish (核心)
由于 PM 无版本心智，推荐后端采用自动累计补丁号 (Auto-Bump) 或者 时间戳后缀 (Timestamp-based) 模式生成。因此 Endpoint 设置为通用的 `POST /publish`，不把 version 置于 URL Path 中强制要求指定。

#### Request
- **URL**: `POST /api/v1/skills/{skill_id}/publish`
- **Content-Type**: `multipart/form-data`
- **Headers**:
  - `Authorization`: `Bearer <OIDC_Token_from_SSO>` (见鉴权方案)
  - `User-Agent`: `AgentStudio-TauriClient/1.0.0`
- **Body**: 
  采用表单提交双部分构成：
  - `file`: 二进制 Zip 文件流 (`application/zip`)
  - `metadata`: JSON 字符串，囊括全部审计需要字段

**metadata schema 示例**:
```json
{
  "version_strategy": "auto", // "auto" 意味着服务器根据历史最大 version 自动 +1; 或者 "2026.05.13-1"
  "author_id": "sevenx",
  "commit_sha": "a1b2c3d4e5f6g7h8i9j0", // Studio 自动获取当前 L1 HEAD
  "published_at": "2026-05-13T10:00:00Z",
  "changelog": "Update main prompts for better character arc handling.",
  "dependencies": {}, // 预留，如果 SKILL.md 解析出其他 sub-skills 则带入
  "client_environment": {
    "os": "linux",
    "studio_version": "v1.2.0"
  }
}
```

#### Response 2xx
- **201 Created**: 成功接受并注册发布新版本。
```json
{
  "code": "SUCCESS",
  "message": "Skill successfully published.",
  "data": {
    "skill_id": "story-deconstruction",
    "version": "1.0.15",
    "artifact_url": "https://registry.internal.company.com/api/v1/skills/story-deconstruction/1.0.15",
    "file_size_bytes": 1048576,
    "checksum_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "published_at": "2026-05-13T10:00:05Z"
  }
}
```

#### Response 4xx/5xx
- **400 Bad Request** (格式错 / Zip内容不符合结构): `{"code": "INVALID_PAYLOAD", ...}`
- **401 Unauthorized** (Token 丢失或失效): `{"code": "UNAUTHORIZED", ...}`
- **403 Forbidden** (无发布权限): `{"code": "PERMISSION_DENIED", ...}`
- **409 Conflict** (如果允许指定 Version 且已存在，不可变约束): `{"code": "VERSION_CONFLICT", ...}`
- **413 Payload Too Large** (强制限制单次 Artifact 包积不能超过 100MB): `{"code": "PAYLOAD_TOO_LARGE", ...}`

### §8.4 鉴权方案
- **硬约束**: 不使用 API Key 这种让非技术人员手足无措的开发者基建。
- **推荐方案**: **公司 SSO Token 转发透传 (OIDC / OAuth 2.0)**。
- **Studio 客户端获取流程**:
  1. Studio 桌面端在首次启动时，触发内置的 Webview 跳转至企业内部 SSO 中心登录页。
  2. 登录成功后，Tauri 后台接管回调提取到一条短效的 OIDC JWT Token。
  3. 客户端在内存中维护此 Token，并在 Token 快过期时调用 Refresh 接口静默刷新。
  4. 当 PM 点击“Release to Production”时，Studio 将此 Token 作为 `Authorization: Bearer <Token>` 挂载于 HTTP 请求头，一并发往 L3 Registry。
  5. 这种机制同时也为 L2 Gitea SSO 提供底层复用，彻底做到账号全打通。

### §8.5 Version 方案
- **唯一性与防重**: 同一 `skill_id + version` 强制实施不可变性 (Immutability)。相同包上传报错 `409`。紧急热修复靠推进新版本并 `DELETE (yank)` 旧版本解决。
- **Bump 策略**: Payload 中 `version_strategy` 传入 `"auto"`。L3 服务端检索最大 version，默认累加 Patch 位（如 `1.0.1` -> `1.0.2`）。

### §8.6 其他 endpoint
- **LIST** (`GET /api/v1/skills/{skill_id}`): 向生产系统或前端返回该技能发行简报。
- **GET** (`GET /api/v1/skills/{skill_id}/{version}`): 返回 `application/zip` 文件下载流。
- **DELETE** (`DELETE /api/v1/skills/{skill_id}/{version}`): 标记为 `yanked: true`，在常规 LIST 与 Pull Latest 时被剔除，阻断新节点拉取。

### §8.7 实施关联 (跟 §6.3 P2 L3 mapping)
- **T4.1**: 组装表单将 `.workspace` 剔除，输出 `multipart/form-data` 的 Buffer。
- **T4.2**: 封包 Buffer 和 OIDC Token 调用 POST，并在触发 413 / 401 失败时拦截呈现。
- **T4.3**: 后端实现路由与校验结构及自动推演版本 (Auto-Bump)。

### §8.8 L3 契约 unresolved
(已移至 §7 TODO)