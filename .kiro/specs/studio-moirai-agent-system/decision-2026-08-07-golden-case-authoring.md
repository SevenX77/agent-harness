# 决议 2026-08-07:golden case 内容可自定义改写(write_golden_case)

状态:已批准(用户 2026-08-07 原话「golden应该是可以自定义改的,不是只有run的结果
才可以当作golden」;本文档为方案落盘。这不是新设计,而是补齐既有冻结设计的实现
落差,设计依据在下)。

## 背景与证据

1. **设计早已如此规定**。golden-eval 设计源
   `docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md`(FROZEN,
   hash-locked)F6:"**golden 本身随时可写**(从 schema 模板 / copilot 设计 /
   手填,**predict 之前也行**)……**Run 的真实输出可作 golden 默认种子**……默认用
   该节点 Run 输出填充、在其上编辑";§4:copilot 依 GRAPH.md 描述设计 golden。
   guard 很窄——只挡「把 predict 的 mock 输出直接提升成 golden」。
2. **实现只有 run 快照一条写路**。
   `apps/studio/backend/app/services/golden_diff.py` 唯一写入口
   `set_golden_baseline_for_run` / `plan_golden_baseline_for_run`,case 内容
   永远取自封存 run 的 `node_outputs`(第 102 行
   `_build_case_file(run_id, target_id, node_outputs[target_id])`)——不存在
   任何「以供给内容写 golden」的入口。F3 记录的手动模板链 2026-07-15 已删,
   `GET /golden/{id}/content` 作为编辑方向的读侧脚手架保留至今,写侧一直缺位。
3. **真实项目坐实缺口**。北极星实验 exp-B round7(`D:\coding\skills\exp-b-round7`)
   现有 golden(12 段版,run2 输出直升)违反该 skill 自己的 P0 不变量
   (SKILL.md:120「A类和C类必须独立分段,绝不与B类合并」——12 段版把 A 类并进
   25-27 的 B 段,A=0);更符合目标的基准是 run3 的 13 段版再修两处边界
   (25 行退出标志应归入 C 段、59 行省略号独立段应并入相邻 B 段)。这个「正确
   基准」不等于任何一次 run 的原样输出,只能人工/copilot 改写得到——正是 F6
   描述的「run 输出作种子、在其上编辑」。
4. **`locked` 标志目前无实效**。`baseline.json` 写入 `locked` 布尔,但没有任何
   写路径检查它(promote 覆写、delete 均不看)。新的编辑路径是第一个让它生效的
   写口。

## 决策

### D-1 服务层编辑路径 `write_golden_case_content`

- `golden_diff.py` 新增
  `write_golden_case_content(skill_id, golden_id, node_id, expected_output) -> GoldenCaseContent`:
  以供给内容改写既有 baseline 中指定节点 case 的 `expected_output`。
- 边界校验(fail fast,与读路径同错误形状):
  - baseline 不存在 → 404 `golden.baseline_not_found`;
  - baseline `locked=true` → 409 `golden.baseline_locked`(锁从声明变实效);
  - 该节点在此 baseline 无 case 记录 → 422 `golden.case_not_found`(本决议是
    「编辑」语义,见「不做什么」);
  - `expected_output` 非非空 dict → 422 `golden.invalid_expected_output`
    (更深的 schema 失效校验按 F4 归 eval 期,不在写口重复)。
- 只重写 `cases/<case_id>.json`,并加来源标记
  `"origin": "authored"` + `"authored_at": <UTC ISO>`;无 `origin` 键 = run
  直升(既有文件不迁移,读方全部 `.get` 式取字段,天然兼容)。`baseline.json`
  的 case 记录只是 ref,不动;`report.json` 是创建期报告,不动。
- `source_run_id` 保留为血统信息:baseline 的容器来自哪次 run 不变,变的是
  case 内容的作者。

### D-2 copilot 写工具 `write_golden_case`

- `copilot_tools.py` 新增 `write_golden_case`
  (`{skill_id, golden_id, node_id, expected_output}`),直调 D-1 服务函数——
  与既有 set/delete golden 工具同一条「写直调服务层」链路
  (copilot_tools.py:753-754 注释即此纪律)。
- 档位:写档,需用户审批。`cli.md` 第 23 行的 "golden writes" 枚举已覆盖,
  不需改;`copilot.py` 的 `_MCP_APPROVAL_WRITE_TOOLS` + `_WRITE_TOOL_ACTION_LABELS`
  注册;CLI 免审批名单(lib.rs `CLAUDE_STUDIO_ALLOWED_TOOLS`)按 D-2(2026-08-07
  前一决议)纪律不收写档工具,零 Rust 变更。
- 工具描述写清 F6 语义:golden 是验收基准,基准的作者是人(或经人确认的判断),
  run 输出只是默认种子;锁定的 baseline 拒绝改写。
- KB-13 工具地图补行;parity toolset 锁测试、assembly 镜像清单同步。

## 不做什么(边界)

- **不加 HTTP 路由**。UI 编辑入口按 F3 仍归 I/O 数据流方向(搁置中),现在没有
  UI 调用方;2026-07-15 删手动模板链的教训正是「无调用方的链路不留」。UI 方向
  启动时再基于同一服务函数加路由。
- **不做「无 run 凭空建 baseline」与「向 baseline 追加新节点 case」**。F6 语义
  上允许,但当前唯一坐实的需求是改写既有 case;baseline 目录以 run_id 为键的
  存储设计也把「无 run 基准」牵连成结构问题,归 I/O 数据流方向一并裁决(YAGNI)。
- **不改冻结设计文档**。golden-eval mvp1-alignment.md 的 F6 已经写着这个能力,
  本次是代码追设计,不是设计变更——不触碰 hash-locked 文档,本决议文档即实现
  与设计的对账记录。
- **不动既有 promote/delete 路径的锁语义**。promote 覆写不查锁是既有行为,是否
  该查归后续裁决;本次只让新写口尊重锁,不顺手扩大爆炸半径。

## 验收判据

1. 服务层测试:改写成功(读回新内容 + `origin=authored`)、404/409/422 四条
   边界、改写单节点不动兄弟节点 case 文件。
2. 工具层测试:成功路径、参数缺失拒绝、服务层错误以 is_error 中继;parity
   toolset 锁、assembly 镜像、审批清单测试全绿。
3. CI 门禁全绿(ruff / mypy×3 / pytest×3 / 前端四件套 / pip-audit)。
4. **真实项目验证**:用新工具把 exp-b-round7 的修正版 golden(13 段版 + 25 行
   归 C + 59 行并段)写入现有 baseline,替换违反 P0 的 12 段版;读回确认内容
   与 `origin=authored` 落盘。
