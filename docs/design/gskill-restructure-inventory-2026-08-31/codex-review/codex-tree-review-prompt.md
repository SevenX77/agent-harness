你是对抗审计员。审计对象:一份"产品重整全局盘点交付物"草稿(域树 + Effect 链 + 工单总账)。

文件:
- 被审草稿: inventory-synthesis-draft.md(本目录)
- 证据底稿: domain-reports/ 目录下 7 份域级对账报告(草稿的全部事实来源;每条断言带 file:line)
- 上位决议: D:\coding\agent-harness\docs\design\gskill-restructure-decision-2026-08-31.md(北极星五条、验收清单、管线)

背景:双仓库——主仓 D:\coding\agent-harness(三模块:packages/graph-agent 引擎、packages/graph-agent-gateway、apps/studio),独立新引擎仓 D:\coding\graph-skill-runtime。已裁决:engine 唯一 owner 收敛到新仓,gateway+studio 整体搬入新仓 monorepo(搬家先于模块化);AGENT 相位执行器闭集 {embedded, ah},host-native 已删除。

你的任务(按破坏力排序输出,不要复述草稿):
1. **树锁错了吗**——域的划分、四带归类、跨域共享模块的归属判定(UrlPlan/Verdict 归模型域、GoldenVerdict 归 engine、workspace-writer 归地基带、scaffold 归 engine、两册错误码并存)有没有站不住的?有没有该立而漏立的域/模块?有没有两个域实为一个、或一个域藏着两个?
2. **依赖顺序错了吗**——七批工单的先后(血止→交接门→五门禁→搬迁→供给带→工作面/地基→MoirAI)有没有会返工的排序错误?特别检查:搬迁与五门禁的并行是否成立、X-T1(vendor 重指向)的位置。
3. **八条已拍板决定**(§6)每条的推导链是否成立?有没有依据不足、或与决议/北极星冲突的?
4. **待裁清单**(§7)有没有该由执行者自决却被上交的、或该上交却被自决的?
5. 草稿与 7 份域报告之间的**转述失真**:抽查关键断言(空洞通过、删 124 route、杀活 sidecar、DEFAULT_LLM_ROLE 回归、X-T1)是否忠实。
6. 任何你认为会让"95% 概率不需要再改"落空的结构性风险。

输出格式:每条发现 = [严重度 P0/P1/P2] + 一句话结论 + 依据(引用草稿行文或报告坐标) + 修改建议。没有发现的维度明说"未发现"。中文输出。
