---
doc: gskill-restructure-inventory-2026-08-31
status: drafted(交付物 v5 已经五轮对抗审收敛;域树+批次 DAG 已按用户长期有效指令生效,六项待裁——原列于 inventory-synthesis.md §8——已于 2026-08-31 全部裁定,见决议 §11;批B/批B′ 获准开工,批C 仍须先呈完整方案)
role: workflow-record
---

# gskill 重整 · 全局盘点交付物与证据包(2026-08-31)

> **本目录是什么**:决议 `docs/design/gskill-restructure-decision-2026-08-31.md` §7 要求的全局盘点的完整产出——
> 交付物正本、七路域级对账证据、五轮 codex 对抗审的裁定记录,以及血止批(批A)的真机点验报告。
> **本目录不是什么**:不是进度状态(唯一可变状态在 `docs/development/DELIVERY_LEDGER.md`),
> 也不是裁决正本——**用户对本目录待裁项的裁决落在决议 §11**,本目录保持为裁决当时的历史快照。
>
> **裁决状态(2026-08-31,落盘 2026-09-01)**:域树与七批工单 DAG 按用户长期有效指令生效;
> `inventory-synthesis.md` §8 的六项待裁**已全部裁定**——格式载体维持 `graph.yaml`、副作用轴含计费
> 且治理从宽、媒体 `endpoint` 字段删、updater 不立项、命名定为 gskill、随仓模板收敛为
> `text-segmentation` 与 `story-deconstruction`(复杂版)两个真实业务场景。**逐条正文、用户原话与
> 执行口径见 `../gskill-restructure-decision-2026-08-31.md` §11**;`inventory-synthesis.md` §8 里的
> "推荐"是裁决前的建议,凡与 §11 冲突处**一律以 §11 为准**。批B(交接门)与批B′(MoirAI 单 owner
> 迁移)获准开工;批C(搬迁)仍须先呈完整方案。批A(血止)是用户既有裁决授权下的已确认缺陷
> 小修补,已完成并点验。

## 文件地图

| 文件 | 是什么 | 证据等级 |
|---|---|---|
| `inventory-synthesis.md` | **交付物正本(v5)**:域树 + 七条系统旅程/失败传播 + owner 矩阵(拟归属) + 六型全局病理 + 七批工单 DAG + 门② 12 项处置表 + 已拍板决定与待裁项 | 汇总(每条断言的 file:line 证据在域报告) |
| `adjudication-record.md` | codex(GPT-5.6-sol xhigh)**五轮对抗审**的逐条裁定记录(8+10+5+1+1 条发现,全部裁定并落实或显式收窄,无未处置项) | 裁定记录 |
| `verification-bloodstop.md` | **血止批(批A)真机点验报告**:7 项中 6 项 verified、1 项如实标注无真机观察面;含环境第一手核实与附带发现 | 第一手真机 |
| `domain-reports/` | 七路域级对账报告及订正 + 前期扫描(证据包;导航见其中 `MANIFEST.md`,含各文件版次关系与证据等级标注) | 域级第一手代码对账 |
| `codex-review/` | 五轮对抗审的 prompt 与审计原文(裁定记录引用的原始材料) | 审计原文 |

## 阅读顺序

1. 上位决议:`../gskill-restructure-decision-2026-08-31.md`(用户已批;§5 执行模型按 #1075 修订;
   **§11 = 本目录待裁项的裁决正本**)。
2. 交付物正本 `inventory-synthesis.md` —— 看域树、旅程、DAG;它 §8 的"待用户裁决"六项
   **已在决议 §11 裁定**,该节保持为裁决前的历史快照,读它时对照 §11 的结论。
3. 对断言有疑问时:顺 `domain-reports/MANIFEST.md` 找到对应域报告的 file:line 证据;
   对"为什么这样定"有疑问时:查 `adjudication-record.md` 的对应轮次。

## 血止批(批A)状态

7 个 PR 已全部合并并真机点验:#1076(M0:protocol_unsupported 不销毁 route/角色引用)、
#1077(T1:统一异常信封 + CORS 兜底)、#1078(T2:掉线判定钉在重启动作上)、
#1079(BOM 十处容错)、#1080(M1:`wire_backend_for_method` 公共 API)、
#1081(X0:媒体配置原子写 + 观察作废)、#1082(M2:`[google]` extra + AST 惰性导入闭包门禁)。
vendor 已重建并预热。点验报告见 `verification-bloodstop.md`;
截图证据页:https://claude.ai/code/artifact/d2b213ae-b441-4fae-80ba-26edb67668d5 。
