# 产品化实施计划(impl_plan · 2026-06-11)

> **依据**:锁定设计 `productization-architecture-2026-06-11.md` + gap `productization-gap-2026-06-11.md`。每个 gap 拆成任务模块,按依赖排序。
> **模块标签**:`[E]`engine `[G]`gateway `[S]`studio-backend `[R]`rust/tauri `[X]`shared/契约
> **状态**:计划草案 → 待 Gemini 验证 → Codex audit → **反写 MVP1 设计 + 决策原因** → 反向链接回本计划(防漂移)。
> **反向链接占位**:每个任务模块完成"反写 MVP1"后,在此标注它对应的 MVP1 设计单元(见末尾 §反向链接表)。

## 阶段 0 — 接口契约先行(地基:只定接口,不写实现)

> 这是所有实现依赖的接口。先钉死,后面三模块各自对着它实现。**这一阶段产出 = 接口定义 + 边界,不含逻辑。**

| ID | 模块 | 做什么 | 依赖 | 验收 |
|---|---|---|---|---|
| **T0.1** | `[X]` | **存储三线接口**:配置真相线(get/put,无缓存)/ 运行产物线(put/get,写完不改,带批处理)/ 运行态线(快照/恢复,单实例独占)。各定"本地实现 vs 远程实现"边界 | — | 三个 Protocol + 边界文档,零实现 |
| **T0.2** | `[X]` | **成品库接口**:put(版本,成品)/get(版本);内容寻址;**只装 publish** | — | 接口 + "设计期临时产物不进库"约束写死 |
| **T0.3** | `[X]` | **编译产物 = 不可变快照 + 版本身份**:内容指纹 + 自包含序列化(脱离源码可寻址) | — | 版本身份 schema + 序列化契约 |
| **T0.4** | `[X/S]` | **adapter 接口骨架**:engine-adapter / gateway-adapter 的**原语一对一**接口 + 传输抽象(本地进程内 / 远程 HTTP) | — | 两份 adapter 接口 + 传输维度抽象 |
| **T0.5** | `[G]` | **凭证来源接口**:`CredentialResolver`,本地输入 / 远端 vault 维度 | — | 协议带"来源"维度 |
| **T0.6** | `[G]` | **fallback 决策接口**:输入(路线链 + 当前路线 + 调用状态)→ 输出(重试/换/放弃 + 下一条) | — | 无状态决策接口 |
| **T0.7** | `[X]` | **GRAPH.md 源码格式 parse/serialize 单一来源**(skill 语法契约;渲染读 + 编辑写共用) | — | 一套 parse/serialize,studio/engine 共用 |

## 阶段 1 — 本地落地(三模块对着阶段 0 接口实现,模块间可并行)

### engine `[E]`
| ID | 做什么 | 依赖 |
|---|---|---|
| **T1.E1** | 存储收口:裸 `Path`/`StorageManager`/直接写 json/checkpointer-env → 运行产物线 + 运行态线接口 | T0.1 |
| **T1.E2** | 编译产物冻结 + 内容指纹实现(让产物能脱离源码序列化/寻址) | T0.3 |
| **T1.E3** | run/predict/resume 入口:**源码路径现编译 → 按版本取成品** | T0.2, T1.E2 |
| **T1.E4** | resume 走运行态线 provider(注入,去 env+全局单例) | T0.1, T1.E1 |
| **T1.E5** | 解 gateway 8 处直连:默认 resolver 外部注入,去掉 engine 对 gateway 具体类型的 import | —(独立) |
| **T1.E6** | golden 判定退役(逻辑迁 studio,见 T1.S5) | T1.S5 |

### gateway `[G]`
| ID | 做什么 | 依赖 |
|---|---|---|
| **T1.G1** | 配置真相存储收口:裸 `Path.read_text` → 配置真相线接口 + 预留 `user_id` | T0.1 |
| **T1.G2** | 凭证来源切换实现(本地输入 / 远端 vault + 脱敏隔离) | T0.5 |
| **T1.G3** | fallback 决策接口实现:导出决策内核 + 把推进逻辑/down-cache 包成可复用 | T0.6 |
| **T1.G4** | 6 态**计算** + materialize 下沉 gateway(从 studio 搬入) | —(牵动 T1.S6) |

### studio-backend `[S]` / rust `[R]`
| ID | 做什么 | 依赖 |
|---|---|---|
| **T1.S1** | adapter 实现:16+ 处直接 import → engine-adapter/gateway-adapter,本地传输 = 进程内直调 | T0.4 |
| **T1.S2** | 存储 provider **本地实现 = Rust** `[R]`:三线本地实现下沉 Rust,注入给 engine/gateway | T0.1, T1.E1, T1.G1 |
| **T1.S3** | 发布流水线:`/publish` → 编译 → 冻结成品 → 入成品库;设计版本走 git、临时产物不进库 | T0.2, T1.E2 |
| **T1.S4** | resume 薄接 engine `resume_skill` | T1.E4 |
| **T1.S5** | golden 判定收敛 studio + 补 copilot 语义判定 | —(配 T1.E6 退役) |
| **T1.S6** | 6 态:渲染留 studio、计算调 gateway | T1.G4 |
| **T1.S7** | copilot fallback 改走 gateway 决策接口 | T1.G3 |
| **T1.S8** | 本地源码 I/O 归 Rust `[R]`(D12) | —(独立) |
| **T1.S9** | 画布渲染/编辑用 GRAPH.md 单一来源 parse/serialize | T0.7 |

## 阶段 2 — 远程拓扑(后续:解锁"engine/gateway 上服务器、studio 本地")

| ID | 做什么 | 依赖 |
|---|---|---|
| **T2.1** | adapter 远程传输实现(HTTP) | T1.S1 |
| **T2.2** | 三线远程实现(DB / 对象存储 + scratch / Redis) | T0.1 |
| **T2.3** | 凭证远端 vault | T0.5, T1.G2 |
| **T2.4** | 成品库远程(对象存储)+ 内容寻址跨宿主取 | T0.2, T1.S3 |

## 关键路径 / 排序

```
阶段0 接口契约(T0.*,全部无前置,先做)
   └─> 阶段1 本地实现(三模块并行,唯一跨模块依赖:T1.S2 依赖 E1+G1)
          └─> 阶段2 远程拓扑(把传输/存储/凭证换远程实现)
位置错(T1.E5/E6、G4、S5/S6/S8)穿插阶段1,不阻塞主线
```

- **硬卡点优先**:T0.1/T0.2/T0.4(存储三线 / 成品库 / adapter 接口)是部署拓扑地基,最先。
- **可并行**:阶段 1 三模块在接口定好后各自推进;注意 T1.S2(Rust 本地存储)要等 E1+G1 的存储收口。
- **可记账待迁**:位置错任务(golden 收敛、6 态下沉、Rust 源码、解直连)不阻塞主线,但要在反写 MVP1 时一并记账。

## Gemini 验证修订(2026-06-11 · 反写前最后一道审)

### A. 已采纳的修订(整合进上面阶段表)
1. **T0.3 前置 T0.2**:成品库 put/get 的负载就是编译产物,"产物=不可变快照+指纹"要先定。
2. **新增 T0.0 锁定原语签名**(尤其 run-by-version):E3 改了 run 的核心签名,adapter(T0.4)是原语一对一,必须等签名定,否则 adapter 是空中楼阁。
3. **新增 T0.8 engine LLM-provider SPI**:E5 解直连靠依赖倒置——engine 定自己要的 LLM SPI(已有 `ModelResolverProtocol`,补"默认路径也注入"),studio 注入 gateway 实现。
4. **新增 T0.9 事件流/流式契约(跨 adapter 边界)**:engine 输出+中间态是流式,adapter 走 HTTP 要定**反压/断线重连/多路复用**,否则只能同步一问一答。(漏掉的关键任务)
5. **T0.3 加 Source Map**:engine 跑成品、studio 渲染源码——错误/节点高亮要能从成品映射回 GRAPH.md 行号/节点 id,编译器必须产 source map,否则 trace/调试瘫痪。
6. **T0.3 拆执行拓扑 vs UI 元数据**:GRAPH.md 的 UI 坐标(x,y)不进指纹,否则拖动节点触发无效重编译;指纹只算执行拓扑。
7. **新增临时产物旁路 resolver**:E3 改"按版本取成品"后,设计期本地测试走 **Ephemeral Artifact Resolver**(本地、按内容指纹、**不进 publish 成品库**),否则每次调试触发全局 publish。
8. **T0.1 运行态线加 Lease+Heartbeat**:远程多副本下"单实例独占"靠租约+心跳防脑裂/接管死锁,不能只 K/V。
9. **E3 加过渡包装 `run_dev(source)`**:别直接删旧接口,保留内部做"源码→临时编译→临时存储→按指纹跑"的包装器,平稳过渡再剥离(否则瞬间打断所有现有 E2E)。
10. **S8 Rust 只管写权+watcher+锁**:大文件读留编译/解析所在语言,避免 FFI 跨语言传全量大字符串(D12"唯一写者"指写权,不强制读)。

### B. 2 个"冲突"经 PM 澄清后消解(Gemini 原 premise 有误)
1. **6态**:Gemini 误把 6态当"业务交互状态机";**实际 6态 = route 能不能用(基础设施健康),与业务/copilot 无关**。所以**不拆、无偏离,MVP1 原样**:
   - **G4 = gateway 计算并输出 6态**(从自己的事实:route 状态/凭证在否/熔断冷却 → 映射成 `ready/untested/cooling_down/off` 等可用性状态)+ materialize(角色意图→有序 route 链)。
   - **S6 = studio 只渲染**(把 6态画成颜色/文案/重试提示);不算状态。
2. **golden**:**engine 不带 golden 跑**;golden diff 是 engine 批量跑完产出结果**之后**的独立操作。Gemini 把"批量跑"和"比对"搅一起了。正确:
   - 批量跑 = engine 自己的事(N 输入跑 N 次出 N 结果,engine 不知为 golden)。
   - **E6/S5 = golden 是独立的 headless diff/判定组件**(lib/CLI):吃**已产出结果 + 基线 → diff → 判定(可含 copilot)**;**不跑/不编排 engine**,只消费结果。headless = 不依赖桌面 UI,studio UI 与 CI 共用同一套判定。engine 内置那套退役。

### C. 流程
✅ 2 个冲突经澄清消解(6态无偏离=MVP1原样;golden 与"产品判定"一致、明确为独立 headless 组件)→ 写 Codex audit prompt → 通过后反写 MVP1 设计+决策原因 → 反向链接回本计划。

## 反向链接表(占位 · 反写 MVP1 后填)

| 任务模块 | 对应 MVP1 设计单元(反写后填) | 反写状态 |
|---|---|---|
| T0.1 存储三线 | engine `physical-layout` / `06-seam`;gateway `storage seam`(03/04) | ⏳ |
| T0.2 成品库 / T0.3 冻结成品 | engine `03-api-contract` / `physical-layout`;studio `04_platform` | ⏳ |
| T0.4 adapter | studio `04_platform`(后端三分 / D10) | ⏳ |
| T0.5 凭证来源 | gateway `03-orch-credentials-endpoints` | ⏳ |
| T0.6 fallback 决策 | gateway `07-orch-fallback-circuit-probe` / `06-error-classification` | ⏳ |
| T0.7 GRAPH.md 单一来源 | engine `02-skill-syntax` | ⏳ |
| T1.* 位置错 | 各对应单元 + `module-disposition` | ⏳ |

> 反写规则:MVP1 设计单元是 FROZEN 带哈希锁,改它走 `studio-doc-exemptions.yaml` / `_audited-ready-hashes.json` 豁免登记;每条改动在"决策原因"里注明来自本计划哪个任务 + 为什么(产品化诉求)。反写完回填本表,确保 impl ↔ MVP1 双向锚定、不漂移。
