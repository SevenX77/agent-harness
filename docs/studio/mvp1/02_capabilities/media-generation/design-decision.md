---
module: 02_capabilities/media-generation
doc: design-decision
role: workflow-record
status: drafted（用户批准 2026-08-13；本文档为决议落盘，未进入 63 档审计冻结体系；实现随同一 PR 交付）
aligns_with: 01_workflows/00_settings-ux-spec.md（Settings shell 交互范式）· ../../../graph-agent-gateway/mvp1/14-media-generation/design-decision.md（gateway 媒体域契约）
---

# media-generation — 媒体生成设置页设计决议

> **Tier**: capability | **Owns**: Studio Settings「媒体生成」页（媒体生成服务商凭据、模型目录展示、连通性测试、每模型设置）的 UI/API 切面 | **决策来源**: 用户裁决 2026-08-13（会话决议，本文档为落盘）

## 1. 决策（用户裁决原文要点）

1. 这一类模型统称**媒体生成模型**，系统内类别标识 `media_generation`（用户批准「可以」）。
2. 媒体生成模型**不进入** API Keys 页；原「API Keys」页改名 **「LLM API-Key」**（tab 与页标题同步改）。
3. 新增独立设置页 **「媒体生成」（Media Generation）**，承载：服务商凭据、模型目录、连通性测试、每模型能力展示与默认参数。
4. 首个服务商为 **RunningHub**（`https://www.runninghub.cn`），模型目录来自用户 AI-story-forge 仓 `docs/api/runninghub/` 已核验的 10 篇文档 + RunningHub 官方文档索引（llms.txt）逐条对照过的端点/价格证据。

## 2. 关键设计决定

### D1. 真相归属：gateway 持有媒体生成域真相

媒体生成服务商的凭据/模型设置真相由 `graph-agent-gateway` 新增的 `media` 域持有（schema/目录/探活），Studio backend 只做文件存储注入与 HTTP 透传（`/api/media/*`）。与 LLM registry 分离存储（`media_generation.json`），**媒体模型对 LLM role→route 体系不可见**——图生视频模型不可能被 LLM 角色选中（让非法状态不可表示）。

### D2. 连通性测试三层，费用边界显式

- **L1 凭据探活（零成本，可自动）**：`POST {base_url}/uc/openapi/accountStatus`（RunningHub 官方「获取账户信息」接口，文档 api-425748943），一次调用同时验证 key 有效性、网络连通，并取回**账户余额**展示在服务商卡头部。触发时机：保存 key 成功后自动一次 + 「测试连接」按钮显式触发。不做定时轮询（SSOT 读取原则）。
- **L2 目录在册（零成本）**：模型清单为内置声明式目录（gateway `media/catalog.py`），状态点灰色=「目录在册」，含义是"官方文档声明存在，未实测"。
- **L3 真实生成测试（有成本，只能手动）**：每模型显式触发、按钮标预估费用、走真实异步任务链（提交→轮询→结果文件）、留存证据（taskId/耗时/消耗/缩略图）。**本期不实现**——它本质是一次最小调用，与媒体调用运行时（提交/轮询/文件上传）同属下一设计单元 `media-invocation-runtime`；页面本期不渲染生成测试按钮（不留死控件）。

### D3. 能力是目录声明的事实，不是用户设置的选项

每个模型条目携带声明式参数 schema（枚举/范围/图片数量与大小上限），来源于官方文档逐篇核验。UI 能力胶囊、默认参数下拉、边界校验共用这一份 schema（diagnostics SSOT 同款原则）。用户可设置的只有：**模型启用/停用** + **每模型默认参数**（只能在 schema 枚举内取值，后端 PATCH 时按目录校验，非法值 fail fast 400）。

### D4. 命名与徽章语义

- 模态：`image` / `video`；任务：`t2i` 文生图 / `i2i` 图生图 / `i2v` 图生视频 / `flf2v` 首尾帧生视频 / `ref2v` 参考（多模态）生视频。
- 渠道：`economy`「低价渠道」（官网自述"价格远低于官方稳定版，不稳定"）/ `official`「官方稳定版」（端点带 `-official` 后缀）。同一模型两渠道 = 两条目录条目。
- 状态点：灰=目录在册（doc-discovered）· 绿=已实测（probe-verified，L3 落地后）· 红=实测失败（probe-failed）。与 LLM 页证据语义对齐。

### D5. 数据契约（Studio backend `/api/media`）

- `GET  /api/media/registry` — 目录+凭据状态+每模型设置的合并视图（api_key 打码）。
- `PUT  /api/media/providers/runninghub/credential` — 保存 key/base_url，返回权威快照。
- `GET  /api/media/providers/runninghub/credential/secret` — 显式取回明文 key（与 LLM 页 reveal 同款）。
- `POST /api/media/providers/runninghub/probe` — L1 探活，落盘探活结果（状态/延迟/余额/时间），返回快照。
- `PATCH /api/media/models/{model_id}/settings` — 启用/停用 + 默认参数；按目录 schema 校验，非法值 400。

前端读取遵循 SSOT：媒体页首次挂载冷加载一次 registry；此后仅在「写成功返回快照」「显式探活」两类触发下更新。

## 3. 目录条目证据基线（2026-08-13 核验）

10 条条目全部与 RunningHub 官方文档页端点逐一对照命中（会话记录）；价格取自官网标准模型市场页当日快照：

| 目录 id（端点核验） | 显示名 | 任务 | 渠道 | 价格 |
|---|---|---|---|---|
| `rhart-image-n-g31-flash/text-to-image` | 全能图片V2-文生图-低价渠道版 | t2i | economy | ¥0.19/张 |
| `rhart-image-n-g31-flash/image-to-image` | 全能图片V2-图生图-低价渠道版 | i2i | economy | ¥0.19/张 |
| `rhart-image-n-pro/text-to-image` | 全能图片PRO-文生图-低价渠道版 | t2i | economy | ¥0.4/张 |
| `rhart-image-n-pro/edit` | 全能图片PRO-图生图-低价渠道版 | i2i | economy | ¥0.4/张 |
| `seedream-v4/text-to-image` | seedream-v4-文生图 | t2i | official | ¥0.14/张 |
| `seedream-v4.5/text-to-image` | seedream-v4.5-文生图 | t2i | official | ¥0.2/张 |
| `rhart-video-g/image-to-video` | 全能视频X-图生视频-低价渠道版-v1.5 | i2v | economy | ¥0.04/秒 |
| `rhart-video-v3.1-pro/start-end-to-video` | 全能视频V3.1-pro-首尾帧生视频-低价渠道版 | flf2v | economy | ¥0.9/次 |
| `seedance2.0/图生视频`（ai_app） | seedance2.0/图生视频 | i2v | official | ¥0.6/秒 |
| `seedance2.0/多模态视频`（ai_app） | seedance2.0/多模态视频 | ref2v | official | ¥0.6/秒 |

参数 schema 证据：全能图片V2 图生图（参考图 ≤10 张/每张 30MB、分辨率 1k/2k/4k、宽高比 14 档）、全能图片PRO 图生图（参考图 ≤10 张/每张 10MB）、全能视频X（480p/720p、时长 6-30s、宽高比 5 档）、全能视频V3.1-pro 首尾帧（首帧+尾帧、720p/1080p/4k、时长固定 8s、宽高比 16:9|9:16），均摘自 AI-story-forge 仓对应文档参数表。

## 4. 验收判据（逐项点验目标）

1. Settings 左侧 nav：「API Keys」已显示为「LLM API-Key」；新增「媒体生成」tab。
2. 媒体生成页打开不报错；RunningHub 服务商卡呈现 key（密文）/base_url 输入。
3. 输入 key 保存后自动探活；「测试连接」按钮显式触发探活；探活结果（成功含余额，失败含错误说明）呈现在卡片上。
4. 模型列表按「图像模型 / 视频模型」分组，逐条显示任务徽章、渠道徽章、价格、状态点（本期全部灰=目录在册）。
5. 模型行展开显示能力胶囊（从目录 schema 渲染）与默认参数选择（选项=schema 枚举）；修改默认参数持久化，重开页面仍在。
6. 后端对非法默认参数（不在枚举内）返回 400，前端不写入。
7. L3 生成测试按钮**不出现**（本期范围外，见 D2）。

## 5. 后续设计单元（本期显式不做）

- `media-invocation-runtime`：异步任务提交/轮询/文件上传、L3 真实生成测试、skill 侧消费。
- 官方稳定版渠道条目、更多服务商（火山引擎/阿里百炼）与目录同步机制。
