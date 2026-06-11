# Graph Studio / Engine / Gateway 产品化架构 —— 最终全局方案

> **日期**: 2026-06-11 | **状态**: 架构方案(已过 Gemini 技术评审一轮) | **性质**: 在 MVP1 设计基础上为"产品化"做的全局架构确认 + 修正
> **评审**: 方案由 Claude 起草、Gemini(`gemini -p`)独立批判性评审,关键修正已吸收(见 §6 + §7)。
> **真理来源**: MVP1 设计文档 `docs/engine/mvp1/`、`docs/graph-agent-gateway/mvp1/`、`docs/studio/mvp1/`(本文只做全局综合 + 产品化修正,不复制各模块 SSOT)。

## 0. 产品目标(PM 定,本方案对着它评)

1. **Studio = skill 的创作/编译/测试工具**;真正的**生产执行**由另一个 app(或服务器)用**同一套 engine+gateway** 跑。
2. **engine+gateway 可部署到服务器、Studio 留本地**(前端+本地文件);也要能全本地(开发态)。
3. **凭证**:支持"用远端凭证 or 本地输入凭证"切换。

## 1. 结论

**MVP1 核心架构合理,而且已经设计好了产品化需要的"插座"(seam)** —— `storage seam`(gateway 侧)、`workspace_dir` 注入 + Protocol DI 接缝(engine 侧)、D10 把 engine/gateway 做成"服务形式 sidecar"、创作/执行分离、skill 可移植、D12 把 settings 排除在 Rust 之外。**产品化 ≠ 重新设计,而是把已有插座做实 + 补两块缺失机制(发布流水线、运行态 state provider)+ 把部署拓扑显式化。**

但 Gemini 评审纠正了起草版两个错误,已吸收:① 存储插座**不该统一成一个接口**,要按数据性质拆成两/三套;② "源码同步到远程引擎"该升级成**内容寻址的发布流水线**,不是文件同步。

## 2. MVP1 已有的产品化 enablers(设计意图,核实过)

| enabler | 设计原文要点 | 产品化里的作用 |
|---|---|---|
| **gateway `storage seam`** | gateway 定数据 schema + 读写契约,"存哪个介质"由 ③a 注入;settings/凭证"永不 Rust"、走 gateway Python、**预留 `user_id`、为未来远端服务化对齐形状** | metadata 的本地↔服务器可换底座 |
| **engine `workspace_dir` 注入 + Protocol DI** | "Studio 是土地局决定地皮、Engine 是施工队只在传入目录盖固定户型";`skill_resolver`/`model_resolver`/`event_subscriber`/`artifact_saver` 全可注入;engine"不知道宿主是本地 FastAPI 还是服务器" | 运行产物/状态的可换底座 + 引擎纯库可远程 |
| **D10 后端三分** | gateway、engine 做成 Python sidecar"服务形式"(PM:"未来要登录用户、settings 要服务端");native-fs Rust | engine/gateway 天生就是为上服务器准备的 |
| **创作/执行分离** | Studio=创作/编译/测试;Graph Agent=运行时;engine 可脱离 gateway 独立采用(双模);gateway"考虑复用其他 app" | "另一个 app 用同一套 engine+gateway 跑"成立 |
| **skill 可移植** | skill = 源码 + 编译产物 CompiledSkill;golden 在 `.workspace`、与生产 run 解耦 | 跨宿主交接物 |

**成熟度边界(诚实)**:上述插座停在"原则 + 预留 `user_id` 槽 + Path/Protocol 注入"这一档,**没细化成把"DB/对象存储后端"写进去的接口规格**;engine 的 workspace 仍是 `Path` 语义(`artifact_saver` 类型是 `Any` 无协议、trace/result 裸写本地文件无接缝)。

## 3. 最终全局架构(吸收 Gemini 修正后)

### 三段分层

**① 创作客户端(本地桌面)**
- 前端(React):UI + **只投影**(不持第二份真相)。
- Rust/Tauri:**本地 skill 源码唯一写者** + 拉起 sidecar/连远程 + **Build(把源码编译打包)**。
- 拥有:本地源码文件、打开文件夹、把源码编译成发布包。**不拥有** run 运行产物。

**② 计算服务(同一套代码,可本地 sidecar 可远程服务)**
- engine + gateway(库/服务);③a = 传输适配壳(HTTP/WS 端点形状、DTO、job 包装)。
- **逻辑无状态、物理带本地缓存(local scratch)**:任一节点拉起来、拿到 checkpoint 就能跑;热点 session 靠亲和性/HotReload 留在节点。
- gateway 作 **Identity & Resource Proxy**:凭证来源经 `CredentialResolver` 屏蔽(本地从 env/文件,远程从 Vault)。

**③ 存储(按数据性质分三套插座,⚠️ 不统一)**

| 插座 | 服务什么数据 | 性质 | 本地实现 | 服务器实现 |
|---|---|---|---|---|
| **`ConfigRepository`**(metadata) | settings / 凭证 / 角色 / draft 知识库 | 高频读、极小、强一致、结构化 | `~/.studio/` 文件 + SQLite | 按 `user_id` 的 DB(Postgres) |
| **`WorkspaceProvider`**(artifacts) | runs / golden / trace / artifacts | 大文件、高频 IO、非结构化 | 本地 `.workspace` 目录 | 对象存储 + **本地 scratch 缓存**(不能直接对网络存储做高频随机读写) |
| **`StateProvider`**(运行态) | checkpoint / resume / session 上下文 | 运行时状态、低延迟 | 内存 / sqlite | Redis 类分布式缓存(**不靠 Postgres 扛运行态同步**) |

> engine 的 `workspace_dir` 从裸 `Path` 抽象成 `WorkspaceProvider`(操作"逻辑对象" `get_artifact`/`save_checkpoint`,不是裸字节);`artifact_saver` 从 `Any` 定成协议。**关键:抽象时必须带 I/O 批处理 + 缓存,否则 trace 落盘会让远程延迟爆炸。**

### 跨宿主交接 = 内容寻址发布流水线(不是文件同步)

```
Studio(本地) ── Build ──> CompiledSkill + Manifest ──hash──> ObjectStorage
Studio ── run(skill_hash, input) ──> 远程 Engine ──按 hash 拉产物──> 跑
```
- 远程 Engine **只吃不可变发布包,禁止访问本地源码**。
- 内容寻址(hash)天然解决同步 + 版本控制 + 开发态/运行态分清。

### 生产执行 app
另一个 **headless 宿主**,嵌同一套 engine+gateway 服务,按 `skill_hash` 跑,**无创作 UI**。

## 4. 对 MVP1 设计的修正项(设计层要改的,代码照此落)

1. **存储插座拆三套**(不是起草版的"统一一个接口"):`ConfigRepository` / `WorkspaceProvider` / `StateProvider`,各自接口 + 本地/服务器两实现。
2. **D12 精确化**:Rust 只拥有"本地 skill 源码"写入;**run workspace/runs/golden 不归 Rust**,走 `WorkspaceProvider`。两条存储线分清(其实 settings"永不 Rust"已经是这个思路的一半)。
3. **补发布流水线**:Studio 端 Build(源码→CompiledSkill+Manifest+hash→ObjectStorage);远程 Engine 按 hash 取、不碰源码。
4. **部署拓扑显式化**:engine/gateway 传输(进程内 / 本地 sidecar / 远程服务)做成显式维度,消费方对同一套 API 编程,本地/远程是配置。
5. **凭证来源做成配置维度**:`CredentialResolver`(本地 env/文件 vs 远程 Vault),骑在 `ConfigRepository` + `user_id` 上;补远程→本地切换的脱敏/隔离设计。

## 5. 部署拓扑(插座做实后都支持)

- **开发态**:全本地(sidecar + 本地实现插头)。
- **产品态(Studio 本地 + engine/gateway 服务器)**:创作端本地(Rust 拥本地源码 + Build)→ HTTP → 远程 engine+gateway 服务(服务器插头:DB metadata / 对象存储+scratch / Redis state / Vault 凭证,全按 `user_id`)。
- **生产执行 app**:headless 宿主嵌同一套服务,按 `skill_hash` 跑。

## 6. 关键风险(Gemini)

1. **D12 反噬**:过度依赖 Rust 写本地文件——做"远程多人协作"时 Rust 层成最大障碍(它假设单机独占)。
2. **Engine 性能退化**:抽象 `WorkspaceProvider` 若不做 I/O 批处理 + 缓存,trace 记录会让远程调用延迟爆炸。
3. **安全**:"远程凭证↔本地凭证"切换缺脱敏/隔离设计(尤其 sidecar 模式)。
4. **Path 的 POSIX 假设**:现有 `Path` 注入隐含顺序写/随机读/原子重命名;直接换 S3/无状态容器会崩或极慢——必须有 local scratch + block 抽象。

## 7. Gemini 评审摘要(原文存档)

Gemini 一句话建议:**"把'存储插座'降级为'数据契约',把'源码同步'升级为'发布流水线';别在 `Path` 上打补丁,直接定义一套基于 Hash 的 Artifact 交付协议。"**

核心修正(已吸收进 §3/§4):
- 存储**分而治之**:metadata 走 Repository 模式(DB-centric),workspace 走 VFS 模式(File-centric)+ local scratch;运行态单独 `StateProvider`(Redis 类,非 Postgres)。
- 计算服务**逻辑 stateless、物理 local cache**;定义 session 亲和 / 快速 hydration。
- 源码**内容寻址**交付,远程引擎只吃发布包、不碰源码。
- gateway 作 Identity & Resource Proxy,凭证来源经 `CredentialResolver` 屏蔽。

> 完整 Gemini 评审与发送的 prompt 见本次会话记录(2026-06-11)。
