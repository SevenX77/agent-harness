总裁决：rework

[P0] 结论：批次 DAG 仍违反固定实施顺序，可能提前删除可用执行路径。依据：T-E1 已包含删除 host-native、durable handoff 等闭集修改，但 ModelResolver M9、ah adapter T-E2 和异步 run T-O1 均位于其后或独立链上，不满足上位决议 §5.9 规定的 executor → ModelResolver → ah adapter 与六个直连 adapter 删除 → §5.6 删除清单与异步 run 顺序。建议：拆分 T-E1，并建立不可绕过的跨链硬边：`executor Port/参数链/preflight → M9 → T-E2及六个直连adapter删除 → host-native与handoff全链删除+T-O1`。

[P0] 结论：门禁②仍不是完整闭集，不能据此进入批 E 或 cutover。依据：v2 仅以 E-T2→E-T1 和四条私有穿透公开化代表该门禁；上位决议要求 Studio 消费的 12 类 engine 内部接口全部提升为公开 Port，或由 Studio 完成重写，其余八类尚无逐项处置与验收。建议：列出全部 12 类接口，为每类指定“公开 Port”或“Studio 重写”、owner、依赖与验收证据，并以十二项全部闭合定义门禁通过。

[P0] 结论：批 E 要求保存完整凭据快照，会复制明文秘密，不能作为实施指令。依据：`llm_credentials.json` 的写入路径包含 `api_key.get_secret_value()`，而 v2 未定义脱敏、加密、访问权限、保存期限和销毁规则。建议：禁止保存完整凭据文件，改用脱敏结构快照、不可逆摘要及状态或路由差异证据；将事故复现证据分别归入 M0、M6 工单并明确安全边界。

[P1] 结论：“候选须资格化后才能进入 owner 矩阵和实施 DAG”的要求尚未落实。依据：§1 将 L3 标为待资格审查候选，但 §1 的 owner 矩阵和 §3 的 DAG 已直接用 S1/S2、V1/V2、O1、D2、B5/B6、W1/W2、B8、F2、W3、E2、E1b、B3、A3 等候选锁定 owner 并排批。建议：逐项补齐八项义务、三向反事实、正向合并证据、膜审与原子性审；未通过审查者不得进入锁定 owner 矩阵或可执行 DAG。

[P1] 结论：owner 矩阵仍不满足“每个概念唯一域、唯一目标 owner、明确写者和读者”。依据：MoirAI 的“域”填写为“产品资产”，owner 仅为仓库路径；run 终局判定仍标作“3/4”；“作者文本读取+frontmatter”又把域9解码与域1 parser 两个概念合并在同一行。建议：完成 MoirAI 的域归属与职责契约，裁定 run 终局判定的唯一域，并拆分文本读取、frontmatter 解码和 parser 概念，分别填写唯一 owner、写者与读者。

[P1] 结论：域12把 sidecar 生命周期与本地文件写闸合并，仍缺少资格化的正向合并证据。依据：G5 将写闸识别为跨域同一模块问题并建议单独立项；上位决议要求 split-first，不能仅凭目录邻近或实现便利并域。发布共享域具备独立 Effect、不变量和膜证据，因此保留该域本身可以接受，但这不能反向证明域12的合并成立。建议：先将写闸拆为独立候选，再完成反事实、Effect、膜与原子性审后决定是否合并。

[P1] 结论：将端到端旅程责任图和逐域失败传播押后到模块立项不可接受。依据：上位决议 §7.1、§7.3、§7.6 要求旅程位于系统层、用于确定责任轴，并在对照实现前推导应然旅程和失败路径；缺少这些输入时，当前域间依赖边和 DAG 完整性无法证明。建议：在批准 owner 矩阵和实施 DAG 前，补齐端到端旅程、失败传播、责任交接及其导出的跨域依赖。

[P1] 结论：P1-5 仍是先批准错误码册并存，再将关键约束后置。依据：§6-5 已允许 Studio 与 engine 两册错误码并存，但联合 catalog 的唯一 owner、命名空间和允许投影面仍只是未来模块过审条件；owner 矩阵也缺少 Studio workspace preflight 码册及联合 export Port 的唯一 owner。建议：先定义并锁定联合 catalog owner、命名空间和投影契约，补全两册及 export Port 的写者与读者，再决定是否允许并存。

[P1] 结论：`schema_drift` 对 predict 行为的自行裁定越过现有证据边界，不可接受。依据：G5 只支持 compile 不因 drift 致命，并明确“是否阻断 predict”仍需裁决；v2 却依据旧 baseline 扩展为 predict 仅警示且 golden eval stale，尚未通过日期、原话和第一性 Effect 推导三道检验。建议：保留“compile 非 fatal”，将 predict 行为标为未决并上交裁决；或先补齐对 predict、eval、缓存和错误传播的完整 Effect 推导。

[P1] 结论：v2 遗漏“补齐新仓原生 v1 测试语料”这一立即行动。依据：门禁⑤中的单个真实用户 skill 转换实战只能证明转换路径，不等价于新仓原生 corpus 的覆盖。建议：在迁移前批次增加独立工单，明确语料范围、owner、验收标准及其与门禁⑤的区别。

其余经裁定项未发现残留。
