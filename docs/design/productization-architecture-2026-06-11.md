# Graph Studio / Engine / Gateway 产品化架构 —— 最终全局方案

> **日期**: 2026-06-11 | **状态**: 架构方案(多轮与 PM 细化 + Gemini 评审一轮,模块/adapter/管道模型为最新锁定态) | **性质**: 在 MVP1 设计基础上为"产品化"做的全局架构确认 + 修正
> **真理来源**: MVP1 设计文档 `docs/engine/mvp1/`、`docs/graph-agent-gateway/mvp1/`、`docs/studio/mvp1/`(本文只做全局综合 + 产品化修正,不复制各模块 SSOT)。

## 0. 产品目标(PM 定)

1. **Studio = skill 的创作/编译/测试工具**;真正的**生产执行**由另一个 app(或服务器)用**同一套 engine+gateway** 跑。
2. **engine+gateway 可部署到服务器、Studio 留本地**(前端+本地文件);也要能全本地(开发态)。
3. **凭证**:支持"用远端凭证 or 本地输入凭证"切换。

## 1. 结论

MVP1 核心架构**合理**,产品化需要的"插座"它早设计好了。产品化 = 把已有插座**做实** + 按"SDK + adapter + 管道"模型把边界划清 + 补发布流水线 + 把部署拓扑显式化,**不是重新设计**。

## 1.5 设计逻辑底座(无代号 —— 这是底,后面技术命名只是它的实现映射)

**底座一:单一真相源,会变的真相不缓存。**
每类数据只有**一个真相源**,谁拥有谁读写。会变的真相(凭证、设置、角色)**绝不允许旁路缓存**(缓存让真相分叉是踩过的 bug)。凭证真相在 gateway(本地模拟远端=借 studio 后端专门接口写本地文件 / 真远端=写库),写入只走"FastAPI → gateway → 唯一真相",前端只投影、不持第二份。

**底座二:三种性质不同的数据,按性质分治,不塞一个万能接口。**
① **配置真相**(小、强一致、读多写少)② **运行产物**(大、一次写成、写完不改)③ **运行中的活状态**(临时、要快、单实例独占)。三者读写方式/一致性/生命周期都不同,各自一个内聚、互不耦合的存储职责;硬塞一个"通用存储接口"= 四不像 = 图实现便捷,要避免。

**底座三:创作与运行彻底解耦,运行端只认冻结成品(且成品库只装 publish)。**
创作端把源码编译成**冻结成品**(不可变、内容寻址);运行端**只认成品 + 版本,不碰源码**。**两个版本命名空间分清**:**设计/源码版本走 git**(设计期迭代历史);**发布产物版本走成品库**(只装 publish 给产品端跑的)。设计期的临时编译产物**绝不进成品库**(否则成品库乱套)。详见 §3.4。

**底座四:模块是 SDK,API 是 adapter,二者同进退、不双层。**
engine、gateway **是纯库(SDK),没有自己的 API**。**adapter 才是 API**——它把 SDK 的能力包成 API 服务。**一个部署单元 = SDK + adapter**:挪到远端就 SDK+adapter 一起挪(或远端重写一个服务端 adapter)。**绝不让 SDK 自带一层 API、再被 studio 包一层**(那是两段 HTTP,没必要)。

**底座五:能力 = 管道,场景 = 管道接线 + 事件,没有 per-场景编排器。**
每个能力是一条**位置无关的管道**(输入→输出)。场景(copilot 对话、发布、跑 skill)是**几条独立管道 + 事件流动**接出来的,**不是为每个场景写一个 `XxxOrchestrator`**。出现"为某场景写一个编排"= 解耦没做干净。

**底座六:engine 产"原材料",studio 做"产品特定消费"。**
engine 只产出**契约数据**(编译产物的结构、运行的输出);**渲染、判定、产品策略**都是 studio 的。判据:**换个 headless 生产 runner 还需要这个吗?——渲染/判断/产品策略不需要(=studio);编译/运行/产出契约数据需要(=engine)。**

## 2. MVP1 已有的产品化 enablers(设计意图,核实过)

| enabler | 设计原文要点 |
|---|---|
| **gateway `storage seam`** | gateway 定数据 schema + 读写契约,"存哪个介质"由 ③a 注入;settings/凭证"永不 Rust",**预留 `user_id`、为未来远端服务化对齐形状** |
| **engine `workspace_dir` 注入 + Protocol DI** | "Studio 是土地局决定地皮、Engine 是施工队只在传入目录盖户型";`skill_resolver`/`model_resolver`/`event_subscriber`/`artifact_saver` 全可注入;engine"不知道宿主是本地还是服务器" |
| **D10 后端三分** | gateway、engine 做成 Python sidecar"服务形式";native-fs Rust |
| **创作/执行分离 + 复用** | Studio=创作/编译/测试;engine 可脱离 gateway 独立采用;gateway"考虑复用其他 app" |
| **skill 可移植** | skill = 源码 + 编译产物 |

## 3. 最终全局架构

### 3.1 模块与边界

- **两个 SDK 模块**:`engine`(纯库:编译/运行/预测/续跑)、`gateway`(纯库:角色解析/凭证/fallback/注册表加工)。**无自己的 API。**
- **adapter** = 把 SDK 包成 API。本地由 studio 的 sidecar 借作两者的 adapter;某模块挪远端 → 它的 SDK+adapter 一起走。
- **studio = 消费应用**:前端 API + 自己的后端能力(跑 Claude SDK、推仓库、本地源码、渲染、判定)+ 注入给 SDK 的存储 provider + 本地 host 着 adapter + **用事件把管道接起来**(不写编排器)。

**四条边界**:① 前端↔studio(产品主契约)② studio↔engine/gateway(**原语一对一薄 adapter**;studio 专属流在 studio 用管道接,不进 SDK)③ engine↔gateway(模型解析)④ engine/gateway↔存储 provider(本地 Rust / 远程 DB)。

### 3.2 管道清单(位置无关,跨边界由 adapter 传输)

**engine 能力管道**
- 编译:源码 + 子图取用器 → { 冻结成品(含**图结构** + 输入 schema)、版本身份、诊断 }
- 运行:成品版本 + 输入 +〔注入:模型解析、存储 provider、事件订阅〕→ { 运行结果、事件流 }
- 预测/干跑:成品版本 + 输入 + mock 策略 +〔同上〕→ { 运行结果(含 phases/path_diff)、事件流 }
- 续跑:断点引用 + 覆盖/人类答复 +〔注入:存储 provider〕→ { 运行结果、事件流 }
- (消费:模型解析←gateway、成品取用←成品库、存储 provider←host、事件订阅→外)

**gateway 能力管道**
- 角色解析:角色名(+可选指定路线)→ { 有序路线链、跳过诊断 }
- 角色→可调用模型:角色名 → 可调模型(内部封装协议差异 + 内部 fallback)——给"要 gateway 帮我执行"的调用方(engine)
- fallback 决策:当前路线 + 调用状态 → 下一步(重试/换下一条/放弃)——给"自己执行"的调用方(studio-copilot)
- 凭证解析:凭证引用 + 来源(本地输入/远端 vault)→ 执行期密钥
- 注册表加工:materialize / 端点标准化 / 能力归一化 / lint / 6 态投影(**计算**健康态;**渲染**归 studio)
- (消费:存储 provider←host:配置真相线、凭证来源←host)
- 注:`角色→可调用模型` 与 `fallback 决策` **共用同一路由大脑**,engine/studio 只是接口深度不同。

**studio 自己的能力管道**
- 跑 Claude SDK(copilot 执行):路线 + 对话输入 → 对话事件流
- 推远端仓库(发布):冻结成品/包 → 远端仓库
- 本地源码管理:源码 读/写/打开文件夹(背后 Rust)
- **画布渲染/编辑**:读 **skill 源码**声明的图结构 → 画;画布编辑写回源码。**不经编译产物**(编译产物是 engine 跑图用的,与渲染无关)。唯一共享点 = GRAPH.md 源码格式的 parse/serialize(skill 语法契约,单一来源防漂移)
- **golden 评估/判定**:运行产物 + 基线 →(可调 copilot 做语义分析)→ 判定(§底座六,从 engine 移来;golden 基线也归 studio)
- 模板 / 测试输入 / 运行审计视图:都是 studio 的(创作/测试/查看,产品特定)

**存储 provider 管道(三线 + 成品库;本地=Rust / 远程=DB·对象存储,接口不变)**
- 配置真相线:get/put(配置)— 单一真相、**无缓存** — gateway 用
- 运行产物线:put/get(产物)— 写完不改 — engine 用
- 运行态线:快照/恢复(断点)— 单实例独占 — engine 用
- 成品库:put(版本,成品)/ get(版本)— 内容寻址、**只装 publish** — build 写、engine.运行(生产)读

**事件流管道(单向)**:运行事件流(engine→studio→前端)、copilot 对话事件流(studio→前端)、配置/健康变更事件(gateway→studio→前端)

### 3.3 存储三线 + 成品库(§底座一/二的实现映射)

| 线 | 数据 | 性质 | 本地 | 远程 | 缓存 |
|---|---|---|---|---|---|
| 配置真相线 | 凭证/角色/设置/draft | 小、强一致 | studio 后端专门接口写本地文件 | 按 `user_id` 的 DB | **无缓存** |
| 运行产物线 | runs/golden 产物/trace/artifacts | 大、写完不改 | 本地目录 | 对象存储 + 本地 scratch | 仅**不可变内容**的本地副本 |
| 运行态线 | checkpoint/resume/session | 活状态、单实例独占 | 内存/本地 | Redis 类 | 单实例独占,非他处真相缓存 |
| 成品库 | 已发布的冻结成品 | 不可变、内容寻址 | 本地发布库 | 对象存储 | 只装 publish |

> engine 的存储从裸 `Path` 抽象成"逻辑对象"接口(产物线带 I/O 批处理,否则远程 trace 延迟爆炸——但缓存只对不可变产物,不碰配置真相)。凭证来源经 `CredentialResolver` 屏蔽(本地 env/文件 vs 远程 Vault)。

### 3.4 版本与冻结成品(钉死歧义)

- **不变量:engine 永远跑"编译产物",从不跑源码。** 任何一次跑(设计期 predict/run、生产执行)吃的都是编译产物。
- 编译产物**一经编译就是不可变快照**(内容指纹标识)——天生"冻结",不是 publish 才冻结。
- **设计期**:改源码(**走 git 源码版本管理**)→ 编译临时产物 → 跑(predict/run)。临时产物**绝不进成品库**。
- **publish**:把某个产物**挂发布版本号 + 入成品库**(成品库**只装 publish**),产品端按版本取来跑。
- **两个版本命名空间**:设计/源码版本(git) vs 发布产物版本(成品库),互不污染。

### 3.5 场景 = 管道接线(验证:无编排器)

- **跑一个 skill**:〔取成品版本〕→ `engine.运行`(注入 `gateway.角色→可调用模型` + `运行产物线`)→ 运行事件流 → 前端
- **copilot 对话**:`gateway.角色解析` → `studio.跑ClaudeSDK` → 对话事件流→前端;失败 → `gateway.fallback 决策` → 下一条
- **发布**:`studio.本地源码` → `engine.编译` → `成品库.put(发布版本)` → `studio.推远端仓库`
- **golden**:`engine.运行`产物 + `studio` 存的基线 → `studio.golden 判定`(可调 copilot)

## 4. 对 MVP1 设计的修正项(设计层要改的,代码照此落)

1. **engine/gateway = SDK + adapter**(底座四),不是各自带 API 的服务;adapter 同进退、不双层 HTTP。
2. **存储按性质拆三线 + 成品库**(底座二),各自接口 + 本地/远程两实现。
3. **D12 精确化**:Rust 只拥有"本地 skill 源码";run 产物走运行产物线、不归 Rust。
4. **成品库只装 publish**;设计期走 git 源码版本 + 临时产物(底座三 / §3.4)。
5. **画布渲染/编辑 = studio 读写源码,不经编译产物**(纠正:编译产物只给 engine 跑,与渲染无关)。唯一共享点 = GRAPH.md 源码格式的读写(skill 语法契约),要**单一来源**防 studio/engine 解析漂移。**`golden 评估/判定`→studio**(底座六),engine 那套退役。**逻辑上归 studio;若现长在 engine,可临时不动、标"待迁",不丢账。**
6. **部署拓扑显式化** + **凭证来源做成配置维度**(`CredentialResolver`,本地/远端切换 + 脱敏隔离)。

## 5. 部署拓扑

- **开发态**:全本地(SDK+adapter 同进程 + 本地存储插头 + git 源码版本)。
- **产品态(Studio 本地 + engine/gateway 服务器)**:创作端本地(Rust 源码 + Build)→ HTTP → 远程 SDK+adapter(服务器存储插头,按 `user_id`)。可单独把 gateway 切远端、engine 留本地。
- **生产执行 app**:headless 宿主嵌同一套 SDK+adapter,按发布版本从成品库取来跑,无创作 UI。

## 6. 关键风险(Gemini 评审)

1. **D12 反噬**:过度依赖 Rust 写本地——远程多人协作时 Rust 层成障碍(假设单机独占)。
2. **Engine 性能退化**:产物线抽象不做 I/O 批处理+缓存,远程 trace 延迟爆炸。
3. **安全**:远程↔本地凭证切换缺脱敏/隔离(尤其 sidecar 模式)。
4. **Path 的 POSIX 假设**:直接换对象存储会崩或极慢,必须 local scratch + 逻辑对象抽象。

> Gemini 一句话:"把存储插座降级为数据契约,把源码同步升级为发布流水线;别在 `Path` 上打补丁,直接定义基于 hash 的 artifact 交付协议。" 完整评审见 2026-06-11 会话记录。
