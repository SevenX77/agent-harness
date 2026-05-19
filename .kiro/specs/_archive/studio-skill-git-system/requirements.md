# Studio Skill 项目 Git 协作系统 — Requirements

> Status: Draft v3 (round 7 收敛)
> Date: 2026-05-13

## §1 项目诉求

Studio Skill 项目旨在为非技术背景的内容创作者（短剧 PM 等）提供一个顺滑、无痛且高度自治的工作环境。随着系统演进，单机调试已经无法满足需求，迫切需要引入版本控制与云端协同能力。核心诉求在于，既要利用 Git 强大的版本演进与分布式特性保障数据安全与协作，又要完全向用户屏蔽诸如 "Repository"、"Commit"、"Push/Pull" 等晦涩的技术名词，将其转化为符合业务直觉的操作体验。

这套系统的核心面向**公司内部使用**。由企业内网的 IT 运维团队部署统管的 Gitea 承担团队级协作枢纽（L2），实现 PM 之间的数据流转、审批合并与跨终端工作接力；同时设立独立的制品注册中心（Artifact Registry，L3），提供纯净的业务逻辑包供给生产端使用。这种三层剥离的架构，有效避免了海量运行时测试数据（Runs）塞爆线上 Git 仓库。

## §2 Use Cases (按用户视角)

### UC1: 新建 Skill 项目
短剧 PM 在任意本地磁盘位置创建项目，Studio 自动完成本地项目的环境初始化。背后不仅生成了规范的 `SKILL.md`，还会由引擎隐式执行 Git 仓库的拉起，并注册到全局的系统路由表中。

### UC2: 跨终端继续工作
下班前，PM 点击 UI 上的 "Save to Team"。Studio 会把今天所有的代码配置修改、黄金基线 (Golden) 以及批测报告 (Predict) 等核心迭代态，静默地推送到企业 Gitea 上专门为其准备的个人开发分支。
- **附带最新测试现场**: 该保存操作还会强制带上最后一次执行的测试断点 (Phase context) 与输出。回到家换了一台电脑，PM 打开 Studio 选择该项目点击 "Sync from Team"，不仅拉取了代码，还自动恢复了最新的运行中间态，点 "Run" 即可无缝接续，不必从头跑起。

### UC3: 多 PM 协作 (PR + admin 审批)
当一个复杂的 Skill 涉及多名 PM 共同调试时，如果某个 PM 觉得自己调优的特性已稳定，点击 "Submit for Review"。Studio 后台自动将该 PM 的个人分支上的代码压缩成一个整洁的提交（Squash），并向主干（Main）发起 Pull Request。仓库管理员审核并同意后才并入主干。

### UC4: 单 PM 直推 main
如果该 Skill 被配置为由单人全权负责（类似独狼开发者），当他们点击 "Save to Team" 时，系统判断没有保护分支限制（或非协作者），直接将修改推入主干，简化不必要的繁文缛节。

### UC5: Publish 到生产端 (L3 Registry)
当 Skill 经过所有层级的验证准备上线时，PM 点击 "Release to Production"。Studio 会摘除所有的开发测试中间件（包括 Runs 和 Golden），将纯净的核心配置文件打包。附加上执行此操作的 PM 身份信息与变更时间，统一发送给企业生产端的 Artifact Registry。

### UC6: Revert 到 Local History 某点
PM 在反复试错提示词并运行的过程中，Studio 会在后台不断地执行自动提交（Auto-commit）。如果发现最新的一组 Prompt 修改效果极差，PM 可以在 "Local History" 面板中查看此前的本地变更轨迹，并一键回滚到较好的历史态。

### UC7: zip Bug Report 分享
若在调试中遇到极难定位的引擎异常，常规的 Golden 快照已经不够用。PM 可通过菜单执行导出 Bug Report 操作。Studio 会把连同海量 `runs` 记录在内的整个项目完全打成一个大 Zip 包。这个包**不经过 Git**，PM 可通过企业 IM 手动发给研发寻求支援。

## §3 非目标 (明确不做)

- **v1 不做**: 内置复杂的 Diff 对比查看器 (Diff viewer)、完整的分支切换界面 (Branch switch)，以及对第三方公共 Git 托管平台（如 GitHub/GitLab.com）的原生接入适配。
- **永远不做**: Studio 厂商提供跨企业的 SaaS 级多租户 Gitea 托管服务（Multi-tenant），或引入复杂的 API Key 等技术感极强的鉴权体系暴露给 PM。

## §4 约束

- **跨平台兼容**: Studio 架构构建于 Tauri 桌面端之上，核心文件操作和 Git 命令调度必须在 Mac、Windows 以及 Linux 系统上有一致表现。
- **极简心智模型**: 目标受众（短剧 PM 等）绝大多数缺乏 Git 经验。用户界面（UI）绝对不可以直接暴露底层 Git 术语，所有流程须被抽象包装成业务名词。
- **系统运维边界**: 公司 IT 必须负责 Gitea 的部署、账号发放与网络维护。Studio 软件仅承担 API 调用的客户端角色，绝不触碰 Gitea 后端及运维相关事项。