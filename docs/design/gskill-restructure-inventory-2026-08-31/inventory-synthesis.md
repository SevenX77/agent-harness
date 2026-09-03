# gskill 重整 · 全局盘点交付物(v5,五轮对抗审收敛版;域树与批次 DAG 待用户批准)

> 域树 + 系统旅程/失败传播 + 工单 DAG。汇总自 2026-08-31 七路域级对账及订正(证据包:`domain-reports/MANIFEST.md`;file:line 证据在域报告,本文只引用)。
> 上位:`docs/design/gskill-restructure-decision-2026-08-31.md`(main;§5 按 #1075:executor 闭集 {embedded, ah},§5.6 删除清单,§5.9 四步固定顺序)。
> v5:codex(GPT-5.6-sol xhigh)五轮对抗审(8+10+5+1+1 条发现)全部裁定并落实后收敛;裁定记录 `adjudication-record.md`。门② 12 项以两仓对比报告 §6.3 原始清单为固定基线。

---

## 0. 一句话结论

十四个域,每个域都有同一形状的病:一个概念被多个 owner 各抄一份(base_url 9 份、错误信封 5 份、skill index 6 份、stale 判据 4 份、冲突策略 4 份、golden schema 3 套写在同一目录上),抄本漂移,漂移被吞错(`except→None` 5 份)和名不副实的门禁掩盖,暴露为三类事故:**误伤用户数据**(protocol_unsupported 删光端点 route——真机观测,当次删除量=模型列表长度 124,前后快照未存档)、**空洞通过风险**(engine 读 Studio 写的 golden 基线 → 0 case → passed——代码级可达链,待实跑复现)、**误杀活进程**(无 CORS 兜底 500 → 判死 → 杀健康 sidecar——七环静态因果链闭合,浏览器行为待打包版真机复现)。修法:按域树给每个概念唯一 owner,把纪律换成结构(门禁进 CI、约束进类型)。

---

## 1. 系统旅程与失败传播(应然,系统层;域责任轴的推导源)

每条旅程按步标注 own 域;"失败传播"是该旅程的应然失败行为(违反即缺陷)。

**J1 创作→编译**:作者经三个编辑面(域8)改源 → 写闸单点(写闸候选 B8)落盘 → 格式域(域1)parser 产 AST → 编译域(域2)一次全量诊断 → 四投影面同一份列表(域2→域8)。失败传播:非法输入=全量聚合诊断不截断、修一个不许"露出"下一个;并发写=统一冲突流,改动绝不静默丢/静默换;IO 故障必须与"skill 未注册"可区分(域9)。
**J2 配模型→可用角色**:录入 key+URL(域6)→ UrlPlan 唯一拼址 → ProbeChannel 真实询问 → Verdict 判定带证据 → route/role 物化 → 角色链供图消费(域3 经 ModelResolver)。失败传播:判定失败钉真因、任何 verdict 无销毁数据权限;探测证据必须携带真实 request_url;打包缺依赖属域13,不得表现为"provider 不兼容"。
**J3 predict→run→观测**:resolve_run preflight(域3,起跑前拒绝不中途炸)→ executor {embedded|ah}(embedded 经 ModelResolver→域6;ah 经 agent-hypervisor)→ 事件流(域4:完整/准确/高效,LiveEventStream 连续编号可重放)→ trace/报告/画布同源投影。失败传播:执行者失败以 `GSKILL_*` 归因到相位入 trace;无自动 executor fallback;事件写盘失败必须抛;run 终局判定唯一 owner(域3),前端只投影。
**J4 评测**:run sealed 产物(域3)→ GoldenVerdict(域5,engine own)diff/score/stale → UI 渲染与导出(判据可解释到字段)。失败传播:schema drift=stale 闭合枚举,不 compile fatal;0 case 不得 passed;基线身份来自内容不来自路径正则。
**J5 委托代写**:面板对话(域10)→ 42 工具封闭面+审批 → 写经写闸+checkpoint → 创作域 reload/冲突流。失败传播:名单外工具一律挂起;拒绝=从 checkpoint 还原不反向覆盖;审批卡永不裸奔工具名;探测绿勾不得暗示生产护栏已验证。
**J6 发布→复用**:publish 内容寻址(域11)→ release 身份可见 → run-from-release(→域3 start_run_from_artifact)。失败传播:artifact 取不到就不跑;包写不覆盖;"锁定"与"复用"缺一即北极星④未兑现。
**J7 打包→安装→运行**(全域证据前提):vendor 物化(域13:三类物分目录、新鲜度戳、装后验证)→ sidecar 起动(域12)→ 全部旅程在装出来的包里成立。失败传播:vendor 与源不一致=响亮报错,绝不静默跑旧码;sidecar 活着永不被杀、真死才报死;任何未捕获异常=统一信封+CORS 可读(域14)。

域间依赖边(主干):域8→域1/域2;域9→域1;域5→域3;域3→域2(CompiledSkill);**域3→域6(运行时直接边:embedded 每次执行 AGENT 相位经 ModelResolver 解析角色,不是只经编译期传递)**;域4←域3;域10→{域3,域6,域11}+平台能力(写闸 B8、native-fs/checkpoint/CLI 终端——owner 待资格审,不以域12 兜底);域11→域3、←域6(autoshare,方向待反转 D2-5);全域→域13(证据前提)、→域14(信封/码册/DTO)。

---

## 2. 域树(十四域;"四带"只是导航分组,不是 ownership 层级)

北极星(§2 五条):①流程可靠可重现 ②比裸写简单 ③engine+AST 核心、其余辅助 ④本地=服务端 ⑤去黑盒。

> 各域 L3 名单为**待资格审查候选**(立项时逐个过三向反事实+膜/原子性分审,决议 §7.2);§2.1 owner 矩阵同为**拟归属**——资格审查通过才生效,审查不过则回炉,不得先按矩阵实施。

**核心带**
| 域 | Effect | 锚 | 病情一句话 | L3 候选 |
|---|---|---|---|---|
| 1 gskill 格式域 | 目录→唯一 typed manifest/AST | ①②④ | parser 4 owner、`<phase>` 形状知识 5 处、模板 5 owner;新仓已收敛 | F1 format-authority、F2 scaffold(只 own 最小合法骨架)、F3 migration |
| 2 编译诊断域 | 一次全量、可定位、带注册码;全系统同一份诊断 | ①②⑤ | 四面两面单通道;三份 preflight 子集;正则刮码 `F-v21-compile`;新仓 4 码词表;**DEFAULT_LLM_ROLE 回归违 #1072** | D1 kernel、D2 error-catalog、D3 diagnostic-dto、D4 studio-preflight |
| 3 执行域 | predict 不花钱;run 确定性可断点续跑;executor=运行时参数闭集 {embedded,ah} | ①③④ | 闭集实为 host-native/cli/embedded;fallback_executors 零消费;preflight 绑在待删 cli;run_id 裸 str;批跑失控;checkpoint validity 双实现 | E1a/E1b/E1c、E2 ExecutorPort、E3 RunIdentity、E4 前端控制器、E5 node-runtime-overrides(自域8迁入) |
| 4 观测域 | 事件完整/准确/高效(北极星⑤主承载) | ⑤① | 闭集 4 份手抄 1 份门禁;新仓无订阅(RuntimeEvent 零构造/EventSink 零实现);6 agent 事件无读者;写盘失败只 log;O(n²) | O1 EventContract、O2 LiveEventStream、O3 TraceProjection |
| 5 评测域 | 已验证运行钉成基线,判决可解释、语义唯一 | ①③⑤ | 三套 schema 同一目录(0 case=passed 代码级可达);分叉被红测试钉死;score 两量纲;stale 四定义 | V1 GoldenVerdict(engine)、V2 GoldenStore |

**供给带**
| 域 | Effect | 锚 | 病情 | L3 候选 |
|---|---|---|---|---|
| 6 模型供给域 | key+URL→带证据的可用模型;判定说得出凭什么 | ①⑤ | base_url 9 owner;两次探测两个 URL→404→删光 route+30 天锁;码 5 套词表+前端回推;两执行器;[google] 缺失 | S1 UrlPlan、S2 Verdict、S3 ProbeChannel、S4 ModelResolver Port |
| 7 媒体供给域 | 与模型域同等诚实 | ①⑤ | 生成能力字面不存在;5 类失败压成 auth_failed;无锁无 chmod 明文 key | S5 MediaCatalog、S6 MediaProbe(复用 S1/S2) |

**工作面带**
| 域 | Effect | 锚 | 病情 | L3 候选 |
|---|---|---|---|---|
| 8 创作域 | 三条路改同一份源,快且写不出编译不过的东西 | ② | 409 四套策略两套静默;rename 孤儿化运行期数据;前端第二序列化器;1287 行孤儿;无撤销 | A1 writeback、A2 conflict、A3 phase-identity、A4 form、A5 editor-buffer |
| 9 工作台域 | 资产全生命周期不丢数据;一 skill 一 git 仓 | ②① | index 6 owner 全吞错;K7-BOM 活;模板两代前;fork/delete 无前端而 UI 指示;新建双实现分叉 | W1 skill-registry、W2 authored-markdown(解码)、W3 产品起点(Studio) |
| 10 委托域 | 代写可见可否决;42 工具封闭 | ②⑤ | 探测路≠聊天路;3 写工具裸标签;5 付费工具零审批(待裁);**MoirAI 资产 own 于此域记账:目标 owner=新仓 integrations,Studio=装载投影读者;现状双 owner 100% 漂移+KB 槽位撞名** | C1 copilot-permission |
| 11 发布共享域 | publish=内容寻址、版本锁定、可独立运行的资产 | ④① | run-from-release 无前端(④只兑现一半);package schema 双写者;零真机 e2e | P1 release-artifact(先补真机证据) |

**地基带**
| 域 | Effect | 锚 | 病情 | L3 候选 |
|---|---|---|---|---|
| 12 运行时底座域(收窄:sidecar 进程生命周期+liveness) | app 起得来;真死才报死、活着永不被杀 | ⑤ | setup() 同步阻塞 90s;预算 3 份手抄;liveness 不查 /health;stderr 无出口 | B1-B4(Process/Supervisor/Budget/Liveness) |
| — 写闸(独立候选,域归属待资格审) | 磁盘写单闸+登记表全量 | ① | 登记表只覆盖 2 条路由,golden 4 写点在表外;三份护栏实现已漂移 | B8 workspace-writer(吸收 G5 L3-E3≡L3-W4;候选域 12 或独立域,资格审时定,**不预并入域12**) |
| 13 发货平台域 | 装完包的行为=验过的行为(证据环境=发货环境) | ④ | vendor 无新鲜度戳(三起事故同源);两个 Python 世界;仅 windows;updater 零表达;**桌面 app 永远跑 vendor 冻结快照** | V4 shipping-vendor |
| 14 契约基建域(横切:跨语言契约+错误治理) | DTO 单一事实源漂移即红;任何失败=统一信封+入册码+唯一文案出口 | ①⑤ | 生成链不存在、210 手抄已漂移(paused_at/auto_commit 前端全盲);5 信封形状、122 绕册、55 无码 | B5 ErrorEnvelope、B6 ReasonCodeRegistry(含联合导出)、B7 ApiContractCodegen |

### 2.1 跨域概念 owner 矩阵(**拟归属**,资格审查通过后生效)

| 概念/状态 | 域 | 目标 owner | 写者→读者 | 现状 | 迁移态 |
|---|---|---|---|---|---|
| URL 计划 | 6 | S1 | gateway 写;四通道+运行时+前端读 | 9 owner | 待 M4 |
| 供给失败原因码 | 6 | S2 | gateway 判;Studio/前端投影 | 5+1 套 | 待 M6 |
| golden 判决 | 5 | V1(engine) | engine 判;Studio 渲染 | 3 套+钉分叉红测试 | 待 E-T2→E-T1 |
| golden 磁盘 schema | 5 | V2 | 唯一版本;engine/Studio 共读 | 2 读 3 写同目录 | 待 E-T2 |
| 事件闭集(含枚举层) | 4 | O1 | engine 定义生成;gateway/前端消费 | 4 份手抄 | 待 T-O2 |
| 编译错误码 `[F-v3-*]` | 2 | D2(engine) | engine 注册;宿主投影 | 新仓 4 词表 | 待 D-T13 |
| HTTP 原因码+信封 | 14 | B6+B5 | backend 唯一 raise 入口;前端唯一文案出口 | 5 形状+177 绕册/无码 | 待 T8/T9 |
| 两册联合导出 | 14 | B6 联合 catalog Port | B6 聚合(engine 投影+studio 册);i18n/审批卡/banner/抽屉/trace 五个投影面(闭集) | 交集=0 | 与 T8 同批 |
| skill index | 9 | W1 | metadata Port 唯一;Rust 对等契约测试 | 6 owner 全吞错 | 待 W-T1 |
| 作者文本解码(BOM/编码) | 9 | W2 | 各仓 twin+跨仓一致性测试 | 4 实现+1 违规调用点 | 待 W-T2/W-T9 |
| frontmatter/正文解析 | 1 | engine parser(`parse_markdown_parts`) | engine 解析;Studio 消费 | 3 份土法 | 待 W-T2 |
| 磁盘写闸 | 待资格审 | B8 | Rust 唯一写者+登记表 | 覆盖 2/多 | 待立项 |
| scaffold 最小骨架 | 1 | F2(engine) | engine 产;Studio/Rust 调用 | 3 代码+2 文档副本 | 待 F-T4 |
| 产品起点/模板/向导 | 9 | W3(Studio,消费 F2 契约) | Studio own | 5 个死模板 | 待 §8-6 裁决 |
| MoirAI 资产 | 10 | 新仓 `integrations/assets/moirai`(已裁);Studio=装载投影读者 | 新仓写;宿主装载 | 双 owner 100% 漂移 | 批B′ |
| executor 闭集与解析 | 3 | E2 | 新仓 own | 3 值+空 Port | §5.9 步1 |
| run 终局判定 | 3 | E1b(唯一表达"缺失即成功"默认) | 域3 判;域4/前端只读投影 | 前后端两默认相左 | 待 T-O3 |
| 重启预算常量 | 12 | B3 | 单一定义源;Rust/TS 执行 | 3 手抄+2 放弃线 | 待 T6 |
| 相位身份(rename 全集) | 8 | A3 | 一次事务四落点 | 只同步 3 处 | 待 W5 |

---

## 3. 全局病理(六型)

1. **概念多 owner**:base_url 9、信封 5、index 6、模板 5、parser 4、stale 4、冲突策略 4、事件闭集 4、预算 3+2、golden schema 3、diff 3、frontmatter 3、新建 2、git init 2、序列化器 2——触发条件全是"某个面需要一点知识就地自建一小份"。
2. **吞错**:index 5 份 `except→None`;事件写盘失败只 log;空包体替 provider 定罪;刮不到码就编一个。
3. **门禁名不副实**:import-boundary 不查 private;one-error-exit 漏跨行;CORS 只测预检;MoirAI 指纹只指纹一份;predict 绿≠验过。
4. **接线断裂**:fork/delete、run-from-release、stderr 环、paused_at/auto_commit、媒体 endpoint、RuntimeEvent/EventSink、6 agent 事件、1287 行孤儿。
5. **两仓分叉已发生**:DEFAULT_LLM_ROLE 回归;MoirAI 漂移+KB 撞名;golden_eval fork 钉死;事件基类 fork 38/44。
6. **证据环境≠发货环境**:vendor 无新鲜度戳(三起发货事故同源);仅 windows;两个 Python 世界;发布域零真机 e2e;桌面 app 永远跑 vendor 冻结快照。

---

## 4. 工单 DAG(**provisional**:任一 L3 候选资格审失败,与其相关的节点与边即失效,必须重新生成 DAG,不得沿旧图实施)

```
批A 血止(进行中,主仓) ─┐
批B 交接门(新仓行为正确+分叉可发现+原生语料) ─┬→ 批C 搬迁(前置:113/命名/目标仓门禁) → 批D 新仓五门禁+模块化 → 批E 原子 cutover → 批F 全面收敛
批B′ MoirAI 单 owner(搬迁前置) ──────────────┘
```

### 批A · 血止(★已开工)
M0 protocol_unsupported 永不删 route · M1 补 probed_backend · X0 媒体写锁+chmod+原子写 · M2 `[google]` · T1 兜底中间件(CORS 内侧,形状 A,INTERNAL_ERROR 入册) · T2 判死前查 `/health` · A-8 K7-BOM。judge 判则改写归 M6(引入新枚举需贯通消费面)。

### 批B · 交接门(新仓)
- D-T1 回灌 #1072 ★ · **X-T1a vendor 新鲜度门禁**(content-hash 戳,响亮报错;**不含**依赖重指——那是批E 的 X-T1b)
- **原生 v1 测试语料**(决议 §4.6-3):255 测试中 89 个经 legacy 转换器、原生语料仅 2;补齐原生 corpus,转换器退出测试热路径。范围=覆盖 v1 全语法面(相位三型/子图/iterate/io/artifact),owner=engine,验收=原生语料可独立跑绿且转换器仅存于 migration 测试。与门⑤(转换器实战)互不替代:一个测引擎本体,一个测转换路径。
  - **订正(2026-09-02,#1103)**:上句里的「255 测试中 89 个」是错数,**实测 44/252 ≈ 17%**(#5 之后 shim 引用恒为 44;工单口径 45 = 44 + 1 直接调用);证据链见 [`domain-reports/ac2a0cf93205b9ba4_v2.md`](domain-reports/ac2a0cf93205b9ba4_v2.md)。**原句保留不动**——它是盘点当刻的记录;工单本身(补齐原生语料、转换器退出测试热路径)不受影响。
- F-T1 删不可达校验 · F-T2/F-T8 文档指针 · F-T3 哈希锁→FROZEN · D-T3 doc_link 重钉 · D-T12 聚合化 · D-T13 码词表归属 · import-linter 从零建 · 113 分支落 main。

### 批B′ · MoirAI 单 owner 迁移(搬迁前置;§4.6-2"立即行动")
资产清单+冲突映射 → 编号由目标 owner 分配(稳定 id+旧 id 重定向+语义不变对照;语义需改写才上升)→ 迁移 → 指纹改跨 owner 校验。

### 批C · 搬迁(§4.4 顺序固定):113 落 main → 命名裁决(§8-5)→ 目标仓 CI/分支保护/必过检查生效 → gateway+studio 整体迁入,**旧 engine 冻结随迁**(§4.3:显式迁移带退出条件;五门禁全过后整包删除)→ 主仓归档只读。搬迁不改行为;验收=迁后全门禁绿+打包链可跑。

### 批D · 新仓五门禁 + 模块化

**执行模型主链(§5.9 固定四步,硬边不可绕;每步以完成判据放行)**
0. 前提裁定(G4 addendum 收敛):**ah=同步**(§5.3:受监督进程"建会话→注入任务→收结构化结果→回收";run 级异步是 §5.7 的任务模型,与 executor 交接无关);`AgentTask`/`AgentResult` 存活为 Port 边界类型,不随 handoff 连坐。
1. **T-E1**:executor Port 收口(闭集两成员 {embedded,ah})+参数链(`RunRequest.executor`→`RunPreset.node_overrides[].executor`,相位级覆盖按 §5.2 保留;删 `fallback_executors`)+**缺省改 embedded 必须连带升 `schema_version`**(旧 RunRequest 快照显式硬失败,不静默改判默认、不写迁移垫片)+preflight 上提为 Port 能力(§5.4;**新建**,继承 vendor_cli 的工具面检查形状〔tools/subagents/context_access/迭代与并行 × 执行者支持面〕;host-native 的"等待点可定位"清单随 durable-pause 模型死,真实图形约束按 §7-10 口径编译期重推)。此步只动契约与解析,host-native/cli 机件暂存(仍可跑)。**ModelResolver Port 契约草案在此步内先行**——契约 owner=engine/执行侧(§5.3:engine 只依赖稳定 Port),gateway 只 own adapter 实现;两处先改:返回不携 LangChain 类型、快照生命周期显式。
2. **M9/S4:ModelResolver 可运行对接**。完成判据=**gateway adapter 可运行实现 + 正向 e2e**(embedded 真跑通一个 AGENT 相位:角色经 Port 解析到真实模型并完成一轮 agent 环路)。**硬前置=供给链 M4/M5/M6/M8**(它们改变 Port 实现的边界语义:URL 计划、原因码枚举、role 物化单入口),不允许以"契约已定稿"提前放行。
3. **T-E2**:ah adapter(四件边界:AgentTask 入/AgentResult 出/executor_id/preflight)+**同一变更删净六个直连 vendor CLI adapter**(≈1943 行)。前置=步 2 完成(删直连前 embedded 必须已是可运行的第一路径,不得出现无可用执行者的窗口)。
4. **§5.6 删除清单执行**+ **T-O1 异步 run 任务模型落地**(与实时事件订阅同一 Port,§5.7)。删除面(G4 定稿逐坐标表,总计 **≈3402 行**):vendor_cli 全目录 1943(步3 已删)、host-native 本体两文件 320+410、`agent_handoffs.py` 278(SQLite 表无第二读写方)、runner 内 host-native 区 ≈157(`ExternalPhaseCompletion`/`recover_paused_skill`/`_apply_external_phase_completion`——三件已证**无独立效果**)、**6 个 agent 生命周期事件** ≈86(零生产者,连同闭集 6 值逐值删除→**GSR 事件闭集 44→38 与主仓完全对齐**,前端 38 值表零改动、门禁测试跨仓复用,门②/T-O2 成本直降——收益计入;红线见 §7-14)、`AgentRequired` 与 submit/resume 提交出口 ≈180、`append_run_event_once` 26(零剩余调用者连带死亡,③O2/O3/O4 随之消失)、`FrameworkState.agent_result_hashes` 2(从 state 模型删除+显式声明已落盘检查点不兼容,数据可弃)。§5.6⑤ 的理由获代码自证:`host_native.py:43-46` docstring 原文"rejected instead of silently running an embedded model"。

**供给链(M4 为最高档——G3 订正:与 M0 并列;M0 已在批A 主仓止血,M4 是根治)**
`M4(UrlPlan,最高档,即刻启动)→ M5(证据记 request_url)→ M6(Verdict 闭合枚举+judge 判则改写 url_plan_suspect+删前端回推)→ 分叉 {M7(ProbeChannel), M8(materialize_role 单入口)};M8 →(硬边)主链步 2`。M3(删死码)为独立清扫项,与 M4 并行、不阻塞任何项。
M4 验收=G3 订正(`ac08659a6d5b556a3_v3.md` §4)的四条断言,语义以该原文为准:①∀(endpoint, question):模型列表探测与生成探测由**同一个 `UrlPlan` 实例**派生——`wire.py:342` 与 `factory.py:69` 不得各算各的;②`UrlPlan(raw="https://api.openai.com", proto=openai_compatible).request_url("/chat/completions") == ".../v1/chat/completions"`(openai 案回归);③`UrlPlan(raw="https://api.deepseek.com", proto=anthropic_compatible).request_url(method="deepseek_chat_completions")` 必须**拒绝**(协议与 method 的 wire family 不匹配),而不是产出 `/anthropic/v1/chat/completions`(deepseek 案回归);④四条测试通道(②表)对同一 (endpoint, method) 产出**逐字节相同**的 request_url(收口 factory vs copilot 通道分裂)。

**门②:12 类 engine 内部接口逐项处置**(固定基线=两仓对比报告 `ac2a0cf93205b9ba4_v1.md` §6.3 的原始清单,含各自 import 处数;不得替换凑数。新增发现另列,不占 12 项计数)

| # | 内部接口(import 处数) | 处置 | owner | 验收 |
|---|---|---|---|---|
| 1 | `core.manifest`(8)——GraphManifest/AST 类型 | 公开 typed manifest 契约(新仓已 closed+frozen Pydantic,升公开命名空间;注意形状已改:`name`→`graph_id` 等,Studio 侧同步迁移) | 域1 F1 | Studio 内部 import 归零+类型迁移测试 |
| 2 | `core.adapter_contracts.RunSession`(7) | 并入异步 run 任务模型 Port(主链步4/T-O1) | 域3 | 公开 Port 覆盖全部 7 处消费 |
| 3 | `core.result_contracts`(7)——NodeRunResult/RunResultSnapshot/RunResultsRef/GoldenInputRef | 正式化 versioned public contract | 域3 | 版本化+契约测试 |
| 4 | `io.run_layout`(4) | run/trace 目录布局契约化(T-O5;新仓已 `.workspace/`→`.gskill/`,迁移含路径变更) | 域4 | 三处 `_trace_directory` 各算消失 |
| 5 | `core.topology_projection`(4) | 公开投影 API(画布/前端投影的唯一来源,F-T5 依赖) | 域1 | 前端自建 dataflow 推导退役 |
| 6 | `core.graph_serializer`(3)——**主仓 Studio 画布写路真实消费**(G2 §2.2;新仓另有同名零消费 seam,勿混淆) | 公开 serialize Port 并**接线**(F-T7;**不得以"冻结"过门**——画布写路断路即门②不过) | 域1 | 画布写回经公开 Port 的正向 e2e |
| 7 | `core.result`(4)——RunResult/PathDiff/PhaseRecord | Studio 重写到新公开类型 `domain.models.RunResult`(不同类型,非改名) | 域3 | 旧类型 import 归零 |
| 8 | `core.loader.SkillLoader`(2;另 Studio 6 处绕 facade 直调) | Studio 重写:收敛到公开 compile 出口,继承 `require_skill_resolver` 硬门(D-T14) | 域2 | 直调点归零 |
| 9 | `core.event_contracts.make_event_envelope`(2) | 并入 EventContract/LiveEventStream 公开面(O1/O2) | 域4 | 公开面覆盖 |
| 10 | `core.compiler.compile_skill`(2) | Studio 重写到公开出口 `RuntimeApplication.compile`(与 #8 同批执行,计数保留) | 域2 | 同 #8 |
| 11 | `core.artifacts.ArtifactRef`(2) | 并入 versioned artifact 公开契约(与 #3 同族) | 域3 | 版本化+契约测试 |
| 12 | `core.llm_provider.LLMProviderError`(3) | 错误契约公开化(与 ModelResolver Port 错误族同批定形,投影入两册联合导出) | 域6/域14 | 公开错误族覆盖 |

门②通过定义=**原始 12 项全部闭合**(公开 Port / Studio 重写 / 删除,三选一落地,每项给具体符号+正向消费断言+内部 import 归零证据)。**另列新增项(不占计数,同批处置)**:`_predict_internal` 四条私有穿透(golden_eval.calculate_score/diff_outputs、path_diff.compute_diff、stub.generate_heuristic_stub→E-T1/门②配套)、checkpoint validity Studio 重造(§7-9)、事件 union 手抄(T-O2)、`parse_markdown_parts` 正式公开(W-T2);private 穿透守门测试补 `allow_private:False` 后全绿。

**门③** = 主链步 4 的 T-O1 + T-O2。**门④** = 批C 前置已了断。**门⑤**:converter 真实用户 skill(含嵌套子图)实战。
**D-T2 重推**:并联/iterate 编译期诊断按引擎 AST/reducer 契约在新仓取证重推,不继承 host-native 拒绝清单。

### 批E · 原子 cutover(五门禁全过后)
X-T1b:依赖单点重指 `graph_skill_runtime` + 删旧 engine 包(§4.3 退出条件)+ vendor 重建 + 打包版真机点验 + 回滚预案(保留旧 engine tag,一次 revert 可回)。
**回归对照证据(脱敏)**:cutover 前后各存一份**脱敏结构快照**——endpoint/route/role 的 id、状态、探测结论 + 密钥的不可逆摘要(如 sha256 前 8 位)——**禁止复制含 `api_key` 明文的 `llm_credentials.json` 原件**;skill 快照只含源文件不含 `.workspace` 凭据类内容。

### 批F · 全面收敛(cutover 后,契约叶子先行)
契约基建:T8(唯一 raise 入口)T9(唯一信封形状)T10(文案出口门禁 AST 化)T12-T15(codegen+漂移门禁+迁手抄+接盲区)+两册联合导出 Port(owner/命名空间/投影面已锁定,见 §7-5)。
底座:T3 T4 T5 T6 T7 T11;B8 写闸登记表全量化(E-T6/E-T7 并入)。
创作:W1-W14。工作台:W-T1/2/4/5/6/7/8/9/10。评测:E-T3/4/5/8/10。委托/发布:D1-1/2/3/5/6/7、D2-1/2/3/4/5。发货:D3-2 后两步、D3-1、D3-4/5/6。

---

## 5. 执行与资源(决议 §9)

血止批 Opus(xhigh)≤2 worktree、一单一 PR、TDD、codex 审 diff 后放行——已开工。批B/B′ 随后;批C 搬迁出独立执行方案(结构性变更,先呈)。每模块六步管线+DoD 五锁;真机点验串行占 `cdp-9222`。真机待验:白窗采样、无 CORS 500 打包复现、gemini ImportError、golden 空洞通过实跑、删 route 快照存档(脱敏)。

## 6. 覆盖缺口声明

L3 候选与 owner 矩阵均为拟定,未过三向反事实+膜/原子性分审(立项逐个补);验收清单⑤⑨⑩靠实施期证据;G4 host-native 修订回执未返(其 v1 与 #1075 冲突处以 #1075 为准);端到端旅程图在本文为系统层版本(§1),逐域细化在模块立项第①步。

## 7. 已拍板决定(可由既有原则推导者,自行拍板附依据)

1. **golden 方案甲**(engine own 判决核+sealed-snapshot;顺序 E-T2→E-T1):北极星③+engine baseline §2。
2. **scaffold 两级**:engine=最小合法骨架(F2),Studio=产品起点(W3,消费 F2 契约):SRP,两个变更理由。
3. **两条 501 删**+清过时声明:零消费者+no-backward-compat。
4. **信封删 `http_status`/`retry_strategy`**:零消费。
5. **两册错误码并存,配套先锁**:联合 catalog 导出 owner=域14 B6(聚合 engine registry 投影+studio 册的唯一 Port);命名空间规则=engine `[F-v3-*]`、studio `UPPER_SNAKE`、gateway 点分小写词表随 M6 收敛入 Verdict 后消亡;允许投影面闭集={i18n codes 表、审批卡、RuntimeGate banner、Compile 抽屉、trace}。三件配套与 T8 同批落地,不后置。
6. **handoff 机件全删**(#1075 §5.6),执行位置=主链步 4。补裁定:**ah=同步**(§5.3 流程原文"建会话→注入任务→收结构化结果→回收";run 级异步归 §5.7 任务模型);`_apply_external_phase_completion`/`agent_handoffs.py`/`recover_paused_skill` 三件经 G4 定向核实**无独立效果**(唯一生产者/调用者全在删除面内),全删;`AgentTask`/`AgentResult` 为 ah 的 Port 边界类型,存活不连坐;6 个 agent 事件随零生产者删除(闭集 44→38 两仓对齐)。
7. **schema_drift:compile 非 fatal 已定**(engine baseline §4 权威明文,Studio compile-fatal 是 drift);**predict/golden-eval 行为未决**——E-T5 立项时按 predict/eval/缓存/错误传播做完整 Effect 推导,推得出唯一解即定,推不出上交。
8. **KB-11/12/13 编号由目标 owner 分配**(稳定 id+重定向+语义不变对照;语义改写才上升)。
9. **checkpoint_validity 归 engine**,Studio 重造删除。
10. **D-T2 重推口径**:依据引擎 AST/reducer 契约在新仓取证,不继承 host-native 清单、不引会话记忆。
11. **门②清单以上表 12 项为准**(决议只记总数;证据坐标在域报告,立项逐项复核消费点)。
12. **ah 不桥接 portable 工具面**(G4 须裁 A):ah 初始支持面=无 tools/subagents/subgraphs/context_access 声明的 AGENT 相位,preflight 起跑前以原因码拒绝;缺口只影响显式选 ah 的用户(embedded 全形状支持,§5.6⑤);立独立 backlog"ah 工具面桥接",不并入已注销的 Phase 3b;`subgraph` 纳入 preflight 轴(§5.4 枚举按例示理解,文档措辞随下次修订补齐)。依据:YAGNI+显式缺口优于静默缺口。
13. **两级 executor 解析链叠加于既有 overlay 机制之上**(G4 须裁 B):§5.2 两级链是用户可见语义契约,overlay+`field_origins` 是实现它的解析与溯源机器;不替换(KISS)。工单按实际字段路径落(`RunRequest.profile.profile.executor` 等);§5.2 简写路径作为文档滞后随下次决议修订对齐。
14. **6 个 agent 事件删除的实现红线**:不可按 `agent_` 前缀批量删——`agent_exit_decision`/`agent_loop_iteration` 是引擎内部 Agent 循环事件,两仓 38 值中共有,必须保留;逐值删指定 6 个(G4 定稿列名)。连带收益:`append_run_event_once` 零调用者随删,原 T-O2 相关三缺陷(吞错/O(n²)/进程内锁)自动消失,省三张工单;T-E1 第 4 步(缺省改 embedded+升 schema_version+旧快照硬拒)**必须同一 PR**,否则出现"新默认 × 旧快照"静默改判窗口。

## 8. 待用户裁决(原则/目标级;各附推荐)

1. **XML vs YAML 拓扑载体**(§6 既有)。新增证据:markdown 载体在主仓产生第二 parser 且 `<phase>` 形状知识散在五处,YAML 在新仓消除全部;徒手读写只在 Monaco+agent 两场景且都不依赖 XML 标签;评审只有 git 文本 diff。证据偏 YAML;"人类编辑体验"是你保留意见的原则,由你裁。
2. **副作用轴是否含"计费"**:5 条零审批工具发真实付费请求。推荐:算副作用,处置=会话级预算闸+用量可见,不迁审批档。
3. **媒体 `endpoint` 字段命运**:建生成路径 vs 删字段。推荐先删承诺(现状"字段在、承诺在、能力不在"最坏),立项时按 S1/S2 重建。
4. **updater 立项或明确不做**:推荐本阶段不做,但把升级/卸载/搬家行为写成决议。
5. **新仓命名**(商标冲突;批C 硬前置)。
6. **随仓模板(5 个)去留**:a)删除 b)重写为当代形状。推荐 a;裁决前先落"随仓起点必须能 compile"门禁。
