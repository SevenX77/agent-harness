# 产品重整全局盘点草稿：对抗审计

审计对象为 `inventory-synthesis-draft.md`。本审计只使用上位决议、writer brief 与 `domain-reports/` 中的证据文件；代码静态因果链、报告推断、运行产物和用户裁决分别记账，不互相替代。六个要求维度——树锁、依赖、八条决定、待裁、转述、结构风险——均有发现。

## P0

[严重度 P0]【维度：依赖、结构风险】草稿把 Studio 五门禁与整体搬迁并行，且没有把目标仓等强度 CI、分支保护和必过检查已生效列为搬迁硬前置，直接颠倒了“先搬家、后在最终形状模块化”的上位顺序。依据：草稿 `inventory-synthesis-draft.md:95-103,123-125`；上位决议 `gskill-restructure-decision-2026-08-31.md:176,182-195`。修改建议：把执行序改为“113 个文件落 main → 命名裁决 → 目标仓 CI/分支保护/门禁生效 → 冻结旧 engine 随 gateway、Studio 整体搬迁 → 在新仓实施五门禁与模块化 → 五门禁全过后原子切换并删除旧 engine”，不得再写批 C 与批 D 并行。

[严重度 P0]【维度：依赖、转述、结构风险】X-T1 把“桌面 vendor 新鲜度必须可验证”擅自扩大为“立即把 `build_vendor.py` 的 engine 依赖重指新仓”，既无域报告坐标证明这个立即切换动作，又破坏冻结旧 engine 随迁、五门禁后再 cutover 的安排。依据：草稿 `inventory-synthesis-draft.md:89-93`；上位决议 `gskill-restructure-decision-2026-08-31.md:178,189-195`；G7 `domain-reports/06_a66fac8a014fefd6b.md:229-230,244,302` 只支持 workspace 闭包与 vendor 新鲜度问题。修改建议：把 X-T1 拆成“迁移前即可落地的新鲜度门禁”和“五门禁通过后的原子依赖重指”；后者必须与旧包删除、打包版因果点验及失败回滚条件写在同一个 cutover 工单中。

[严重度 P0]【维度：八条决定、依赖】草稿一面接受 executor 闭集 `{embedded, ah}`，一面又保留 `agent_handoffs` / `_apply_external_phase_completion`，并用无报告依据的“既有记忆”重定 D-T2，正面违反 host-native 及 durable handoff 链同批删除的上位决议。依据：草稿 `inventory-synthesis-draft.md:96,142`；上位决议 `gskill-restructure-decision-2026-08-31.md:229,253-259,269-274`；G4 正文仍是旧闭集并建议保留，见 `domain-reports/line252_aeed340fbc0847f26.md:22-39,154-158`，不能覆盖后来的用户裁决。修改建议：删除上位决议明确列出的 durable handoff store、`submit_agent_result`、`checkpoint_ref` 与 Phase 3b；对 `_apply_external_phase_completion`，先证明它在去掉 durable handoff 后仍有独立公开效果，否则删除，不得以 ah 为由原样保留 host-native 链；把 D-T2 从 AST 状态合并、preflight 能力与 LangGraph reducer 契约重新推导，并按“Port/参数/preflight → ModelResolver → ah adapter → 删除 host-native 与异步 run”重写工单。

[严重度 P0]【维度：依赖、结构风险】七批队列不是有效依赖序：M9 被放在 M4/M6/M8 之前，M4 又被安排在其前置 M3 之前，GoldenVerdict Port 也写在磁盘 schema 统一之前，当前队列按文面执行必然返工。依据：草稿 `inventory-synthesis-draft.md:96-97,105-106`；G3 `domain-reports/07_ac08659a6d5b556a3.md:232-241` 明列 M4 依赖 M3、M9 依赖 M4/M6/M8；G5 `domain-reports/line342_ac68cf30433471aa0.md:233-250` 明列 E-T2 先于 E-T1。修改建议：废弃手写“七批”序，先生成包含每个工单前置、产物、owner、读写权、迁移状态与验收证据的 DAG，再拓扑排序；至少应满足 M3→M4→M6→M8→M9 和 E-T2→E-T1。

[严重度 P0]【维度：树锁、结构风险】“四带”按 engine/gateway/studio/platform 的仓库与部署形状充当域树父层，已经把发布共享域压进 Studio 工作面，并把进程生命周期与 HTTP/API 错误治理塞进同一个运行时底座域，违反按共同不变量分域。依据：草稿 `inventory-synthesis-draft.md:19-51`；上位决议 `gskill-restructure-decision-2026-08-31.md:106,320-350`；发布共享能力可脱离源独立运行，见 G7 `domain-reports/06_a66fac8a014fefd6b.md:131-157`；底座两组候选分别为 B1-B4 与 B5-B6，见 G1 `domain-reports/08_a2b6b29566a8e3097.md:357-471`。修改建议：把“四带”降为只读仓库/部署导航，不赋予归属与依赖语义；对发布共享域和运行时底座域重新执行 split-first、三向反事实、八项义务及膜/原子性分审后再锁树。

[严重度 P0]【维度：树锁、结构风险】owner 图存在三个结构性真空：`workspace-writer` 只归“地基带”却未落到域 12-14 的任何模块，`node-runtime-overrides` 已判迁执行域却未进入执行域模块表，MoirAI 则既没有进入十四域/模块 owner 图，也没有被明确分类为非产品治理资产。依据：草稿 `inventory-synthesis-draft.md:25,49-51,56,110,116-117`；G5 `domain-reports/line342_ac68cf30433471aa0.md:455-458` 只证明 `workspace-writer` 属平台层；G6 `domain-reports/line302_a0f03d30865974364.md:380-389` 明确 L3-6 应迁执行域；G7 `domain-reports/06_a66fac8a014fefd6b.md:81,315` 证明 MoirAI 是双 owner 且碰撞会阻塞迁移。修改建议：在重排前补一张可机械核验的“概念/状态 → 唯一域 → 模块 → Port → 写者/读者 → 当前/目标 owner → 迁移状态”矩阵；MoirAI 若是产品运行能力，应进入相应域/模块，若不是，则必须显式标为非产品治理资产并指定唯一 owner、生命周期与迁移门禁；三个真空未补齐前不得宣称十四域闭合。

[严重度 P0]【维度：依赖、树锁】MoirAI 单 owner 被排到全部收敛后的批 G，既违背上位决议的“立即行动”，也让 KB 编号碰撞持续污染迁移基线。依据：草稿 `inventory-synthesis-draft.md:116-117`；上位决议 `gskill-restructure-decision-2026-08-31.md:197-201`；G7 `domain-reports/06_a66fac8a014fefd6b.md:315` 明确碰撞不先解决会使迁移即回归。修改建议：把 MoirAI 资产清单、冲突映射、目标 owner 和迁移校验移到搬家前置；编号分配由目标 owner 在不删改知识语义的前提下完成，迁移后指纹必须跨旧/新 owner 验证且旧副本退役。

[严重度 P0]【维度：八条决定、树锁】草稿以“新仓已有 `scaffold.py`”这一目录事实和北极星③直接裁定 scaffold 内容归 engine，混淆了 engine 应拥有的“规范合法最小骨架”与 Studio 产品模板/向导内容，会锁错产品内容的权威边界。依据：草稿 `inventory-synthesis-draft.md:41,57,138`；G5 `domain-reports/line342_ac68cf30433471aa0.md:450-453,482` 只提出 Rust 或共享资源二选一；上位决议 `gskill-restructure-decision-2026-08-31.md:328-336` 明令物理形状不作判据。修改建议：拆成两个候选分别过资格审查：engine owner 仅覆盖 serializer、格式和可编译的最小合法构造；产品起点内容、模板选择和向导承诺由 Studio/创作 owner 承担，二者通过公开 scaffold contract 协作。

## P1

[严重度 P1]【维度：转述、结构风险】证据包没有闭合到草稿自称的“七路域报告 + 三份订正”：只能唯一识别六份域报告，G2 文件缺失，G7 有重复副本，G3/G4 的后续订正也没有文件名、版本和替代范围清单，因此 G2 相关树锁和所有“订正后”断言均不足以批准。依据：草稿 `inventory-synthesis-draft.md:3-5`；`domain-reports/line395_unknown.md:45,69,75,78` 记录 G2 当时仍在运行及 G3/G4 会话订正；G3 正文 `domain-reports/07_ac08659a6d5b556a3.md:58-60` 与后续摘要相冲突。修改建议：先生成证据 manifest，逐项列出报告 id、文件、版本、是否权威、被哪份 addendum 替代及替代行范围；补齐 G2 独立报告和 G3/G4 独立 addendum 后，删除草稿中无法回指该 manifest 的断言。

[严重度 P1]【维度：树锁、结构风险】草稿承认 L3 候选尚未完成三向反事实与膜/原子性分审，却称其为“定稿候选”并直接拿来锁十四域和排列七批，不能支撑“95% 不返工”。依据：草稿 `inventory-synthesis-draft.md:21-58,73-117,131`；上位决议 `gskill-restructure-decision-2026-08-31.md:330-350,397-407`。修改建议：把当前表降级为“待资格审查候选”，每个候选补齐八项义务、三向反事实、正向合并证据、膜审和原子性审；只有合格模块才能进入 owner 矩阵与依赖 DAG。

[严重度 P1]【维度：结构风险、依赖】标题承诺“Effect 链”，正文却只有孤立的域级 Effect 表，没有端到端用户旅程、域间因果边、失败传播、原子 cutover/rollback 条件，也没有可复核的 owner/Port/读写权矩阵，因而无法从树推导执行顺序。依据：草稿 `inventory-synthesis-draft.md:1,21-58,62-69,73-125`；上位决议 `gskill-restructure-decision-2026-08-31.md:322-350,405-407`。修改建议：至少补三份生成物：系统旅程→域责任/失败路径图、带 typed edge 的依赖 DAG、owner/Port/状态读写/迁移矩阵；cutover 节点必须写前置观察、原子动作、失败补偿和回滚出口。

[严重度 P1]【维度：八条决定、待裁】删除五个模板是用户可见能力取舍，报告明确要求先裁，草稿却仅凭 no-backward-compat/YAGNI 自决删除，错误地把产品目标层决定降为实现决定。依据：草稿 `inventory-synthesis-draft.md:139`；G5 `domain-reports/line342_ac68cf30433471aa0.md:302-303,331,475-480` 证明模板名仍驱动三个 Copilot 起点按钮且模板去留需先裁。修改建议：把“保留并重写”与“删除并改造三个按钮”的用户可见差异列入待用户裁决；裁决前只允许补“所有随仓起点必须能 compile”的门禁，不得删除能力。

[严重度 P1]【维度：八条决定、树锁、转述】“Studio/engine 两册错误码 + 显式投影 + i18n 门禁”方向可能成立，但缺失 G2 使 engine 编译码册范围不可核，草稿也没有给跨册联合导出、命名空间和投影规则指定唯一 owner。依据：草稿 `inventory-synthesis-draft.md:58,141`；G1 `domain-reports/08_a2b6b29566a8e3097.md:70,172-202,434` 只证明 Studio 码册退化及 engine 码册可作范式；证据 manifest 缺 G2。修改建议：在 G2 补齐前把该项降为候选；由一个明确 owner 定义两命名空间的联合 catalog/export Port、跨册投影允许面和 i18n 覆盖门禁，再决定“两册并存”是否合格。

[严重度 P1]【维度：待裁、八条决定】`schema_drift` 是否阻断 predict 是 G5 明确留下的语义缺口，草稿既没有从 compile 与 golden evaluation 的动作边界推导结论，也没有列入待裁，导致 stale 可能再次冒充 pass 或被错误升级为编译 fatal。依据：G5 `domain-reports/line342_ac68cf30433471aa0.md:243-256`；草稿 `inventory-synthesis-draft.md:135-153` 无此项。修改建议：先由 `GoldenVerdict` 契约分别定义 compile、predict、golden evaluation 对 `schema_drift` 的可观察行为；若北极星和既有动作边界不能唯一推出答案，就新增一条用户待裁并写明两个选项的产品后果。

[严重度 P1]【维度：待裁、依赖】草稿把 KB-11/12/13 新编号上交用户，但单 owner 到新仓已裁定，编号与重定向本应由目标 owner 作为迁移细节处理；只有删除或改写知识语义才需要用户裁决。依据：草稿 `inventory-synthesis-draft.md:117,153`；上位决议 `gskill-restructure-decision-2026-08-31.md:197-201`；G7 `domain-reports/06_a66fac8a014fefd6b.md:315`。修改建议：把该项改为目标 owner 的迁移前置工单，要求无冲突稳定 id、旧 id 重定向和语义不变对照；若工单发现必须合并、删除或改写知识语义，再携差异上交用户。

[严重度 P1]【维度：转述】“空洞通过”只有 schema 与代码路径构成的静态可达链，没有一次实际 golden run 和结果 artifact；草稿用“三种方式暴露”和“engine 读 Studio 基线=0 case=passed”会被读成已经运行复现。依据：草稿 `inventory-synthesis-draft.md:11,27`；G5 `domain-reports/line342_ac68cf30433471aa0.md:109-124`。修改建议：统一改写为“静态因果链证明代码级可达的空洞通过风险”，并把实际 golden run、输入 baseline、stdout/结果文件及 `total_cases=0,status=passed` 作为待补运行证据。

[严重度 P1]【维度：转述】“删 124 条 route”把未经独立前后快照证明的数量、G3 正文已证伪的 URL 根因和只存在于会话摘要的订正混成“真机证实”，证据层级与根因都不稳定。依据：草稿 `inventory-synthesis-draft.md:11,33,80-81`；G3 正文 `domain-reports/07_ac08659a6d5b556a3.md:58-70,232`；后续订正只见 `domain-reports/line395_unknown.md:45,75`。修改建议：把已核部分限定为“`protocol_unsupported` 会删该 endpoint 全部 routes、剥角色引用并跳过 30 天重测”；124 仅标为待前后快照补证，URL 根因在独立 addendum 落盘前不得写成权威结论。

## P2

[严重度 P2]【维度：转述】“杀活 sidecar（7 环链验实）”没有明确“验实”仅指代码静态因果链，且与后文仍列浏览器真机复现为待验相冲突。依据：草稿 `inventory-synthesis-draft.md:11,49,127`；G1 `domain-reports/08_a2b6b29566a8e3097.md:147-158,563-566`。修改建议：改成“七环静态因果链已闭合；浏览器丢弃无 CORS 500 后触发重启的行为尚待打包版真机复现”，运行证据补齐前不得使用“真机验实”或同义措辞。

未发现：`UrlPlan` / `Verdict` / `ProbeChannel` 归模型域且由媒体复用、`GoldenVerdict` 归 engine 的方向有报告支撑；`workspace-writer` 归平台层有支撑，但精确域仍缺。

未发现：待裁清单现有 XML/YAML、计费轴、媒体 endpoint、updater、命名五项的上交层级没有问题；KB 编号见前述发现，漏上交模板见前述发现。

## 五项指定抽查结论

| 抽查点 | 结论 |
|---|---|
| 空洞通过 | 有转述失真：静态可达风险被写成已暴露事实，见 P1。 |
| 删 124 route | 有转述失真：删除机制可核，但数量无独立 artifact，根因订正未正式落盘，见 P1。 |
| 杀活 sidecar | 有证据层级歧义：七环是静态因果链，浏览器行为未真机复现，见 P2。 |
| `DEFAULT_LLM_ROLE` 回归 | 未发现事实转述失真；双仓比较 `domain-reports/04_ac2a0cf93205b9ba4.md:35-38,369,380` 支持主仓删除、新仓复活且缺 `[F-v3-agent-llm-role-missing]`。但它不是草稿声称的七份域报告之一，来源清单问题归入证据 manifest 发现。 |
| X-T1 | 有越证推断且与迁移 cutover 冲突，见 P0。 |

八条自行拍板决定中，删除两条 501、删除错误信封两个冗余字段、`checkpoint_validity` 归 engine 未发现转述失真；GoldenVerdict 方案甲的方向有报告支持，但必须服从 E-T2→E-T1 的落地顺序。其余 scaffold、模板、两册错误码、D-T2 已分别列出发现。

## 总裁决

**rework**。

最小下一步：立即停止把当前域树和七批队列作为实施依据；先补齐 G2 与 G3/G4 独立 addendum 并生成版本化证据 manifest，再按上位决议重建 owner/Port/读写/迁移矩阵、依赖 DAG 及原子 cutover/rollback 条件，完成候选资格审查后重新提交对抗审计。
