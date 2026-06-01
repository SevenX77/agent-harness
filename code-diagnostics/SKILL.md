# SKILL: 卓越工程代码美学与架构诊断规约 (Anti-Laziness Diagnostics Oracle)

本规约旨在约束并协同主控 Agent（orchestrator）执行项目根目录顶级 `code-diagnostics/` 独立体检套件的诊断流程，彻底消解大模型的"注意力稀释"与"脑补敷衍"通病，强制通过注入式报告与主控自调度的多子代理并行走查，完成全仓所有源文件的高密度、高保真代码美学体检。

---

## 📁 产出物路径铁律 (Artifact Path Policy)

本套件的**一切产出物**——报告 `.md`、分批清单 `.txt`、子代理 findings JSON、指令文件——**只允许写入 `code-diagnostics/output/{run_id}/` 下**。该目录已被 `.gitignore` 整体忽略，不入库。

- `{run_id}` 为本轮体检的唯一 UTC 时间戳（如 `20260601_082943`）；一次体检的**全部产物归拢到 `output/{run_id}/` 单一文件夹**。
- 标准布局：
  ```
  code-diagnostics/output/{run_id}/
    diag_report_{run_id}.md      # 报告（build_tree / static / backfill 写）
    manifest_batch_{k}.txt       # 主控分批清单
    findings/batch_{k}.json      # 子代理走查产出（含 severity）
  ```
- **强制执行**：`diag_paths.py` 是唯一路径出口，提供 `OUTPUT_ROOT` 与 `ensure_output_path()`；四个脚本写盘前一律校验，**越界路径直接拒绝退出**。主控派发 subagent 时也必须把落盘路径限定在 `output/{run_id}/findings/` 下。任何产出物都不得散落到 `output/` 之外。

---

## 🛠️ 第一阶段：动态报告创建与硬性扫描 (Setup & Static Audit)

主控接收到体检任务时，必须生成唯一的精确 UTC `{run_id}`（如 `20260601_082943`），并按顺序执行：

1. **运行结构生成器**：
   ```bash
   python3 code-diagnostics/build_tree.py --file code-diagnostics/output/{run_id}/diag_report_{run_id}.md
   ```
   它会生成该次审计的基准清单文件，并将全仓待审文件初始化为待审计状态 `[ ]`。

2. **运行静态硬性卡口**：
   ```bash
   python3 code-diagnostics/run_static_audit.py --file code-diagnostics/output/{run_id}/diag_report_{run_id}.md
   ```
   它会在本地完成 5 维硬性指标扫描（死代码物理残留、mypy ignore 逃避、skip 测试、os.environ 绕过契约耦合等），并将静态扣分证据与得分自动回填到报告中。静态分在第六节只作**纯扣分项**。

---

## 🔍 第二阶段：主控调度子代理微观深度质检 (Orchestrator-Driven Subagent Micro-Audit)

本阶段**不绑定任何固定外部大模型**。微观走查全部由**主控自行调度若干 subagent** 并行完成——主控对「派多少个、如何分批、用哪种 subagent」拥有完全裁量权，依据待审文件的数量与体量自主权衡，使每个 subagent 的上下文负载均衡且彼此不重叠。

### 1. 调度机制（主控自主裁量，禁止硬编码并发数）
- **读取清单**：从第一阶段报告中解析所有 `[ ]` 待审文件，按 package 与子目录归类。
- **以模块为边界分批**：以「子目录/模块」作为天然切分边界。超大模块（如数十文件的 `core/`）必须进一步细分，避免单个 subagent 上下文过载；零散小文件可合批。单批粒度由主控按文件体量临场判断，不设固定数字。
- **并行派发**：在同一条消息中并行派发多个 subagent 以最大化吞吐；仓库规模过大时可分多波次推进。
- **subagent 选型**：选用具备完整文件读取与推理能力的通用型 subagent（而非只读检索型），确保其能逐行精读源码并产出深度架构分析，且有权限将结论写盘。

### 2. 每个 subagent 的下发契约
派发给每个 subagent 的指令必须包含：
1. 其负责的**精确文件清单**：package 名 + 报告内**原样 subpath** + 可直接读取的绝对路径；
2. 下方第 3 节的 **5 维找茬标准** + 第 4 节的严重度判据；
3. 第 5 节的**输出 JSON Schema**；
4. **落盘路径**：`code-diagnostics/output/{run_id}/findings/batch_{k}.json`。

subagent 必须**逐字精读**所负责的每个文件，**严禁凭文件名/目录名脑补内容**；读完即按 Schema 将结论 **写入**指定 JSON 文件（而非仅在回复中陈述）。

### 3. 深度审阅的 5 个健康维度（核心找茬机制）
每个 subagent 围绕以下 5 个美学指标进行最严苛的找茬：
- **极简度（奥卡姆剃刀）**：是否为了向下兼容或历史平滑过渡而层层包裹临时补丁/适配器（Transitional Adaptors / Monkey-patches）？是否存在设计过度的冗余包装？
- **类型安全度**：是否滥用 `cast(Any, ...)`、`type: ignore` 逃避类型检查？是否有函数完全缺乏类型注解、隐式 Any 推断？
- **死代码干净度**：是否存在物理已弃用但残留未清的方法/属性？是否有不可达方法、废弃未用的类定义或被新流程取代的历史包袱逻辑？
- **测试活性度**：若为测试文件，断言是否仅依赖虚假 Mock 而缺乏真实端到端校验？是否有过于脆弱或被局部跳过的用例？
- **接口与依赖清晰度**：是否越权引入私有底层实现（如 `_` 开头模块、`_predict_internal` 内部依赖）？是否绕过统一 `Settings` 而随处 `os.environ`/`os.getenv` 硬编码？是否存在循环导入或过度多层调用？

### 4. 强力防偷懒红线【绝对硬性】
- **就地内嵌微观线索凭证**：subagent 针对任何缺陷，**必须一字不差地复制**对应有问题的源代码段，并标注**绝对精准的起始行号**（格式如 `L123` 或 `L123-145`）。
- **拒绝放水**：即使是极其微小的代码异味（缺 docstring、临时过渡 Patch 注释、`except Exception:` 无回退、静态契约越权、类型收窄失败），也必须立刻记录为缺陷。
- **深度分析**：`description` 必须深入解析该设计的弊端、技术债以及在长线演进中为何"有害"，写出专业、深刻的架构分析，禁止敷衍套话。
- **如实找全**：最终分由"严重度加权缺陷密度"惩罚制折算（见第 6 节），subagent 的首要职责是**把缺陷找全找准**——少报一处就人为抬高了分数。不要因为"整体观感还行"而漏报。
- **逐条标注严重度（severity，必填）**：每条 finding 按其**真实危害**判定 `severity ∈ {critical, major, minor}`（看 description 实质，不要只看 dimension）：
  - **critical**：导致正确性/稳定性/安全问题或核心架构债——静默吞异常、加载期循环导入、竞态、资源泄漏、不可达逻辑、核心边界 `cast(Any)` 使整链类型失效。
  - **major**：明确设计/可维护性缺陷但不直接崩——局部 `cast(Any)`/`type: ignore`、死代码残留、临时适配器、绕过 `Settings` 的 `os.getenv`、公共函数缺类型注解。
  - **minor**：风格/可读性 nitpick——缺 docstring、命名、魔法数、轻微冗余。

### 5. subagent 落盘 JSON Schema
每个 subagent 向 `code-diagnostics/output/{run_id}/findings/batch_{k}.json` 写入且仅写入如下结构（`subpath` 必须与报告清单中的字符串**逐字一致**；每条 finding 的 `severity` 必填）：
```json
{
  "results": [
    {
      "package": "graph-agent",
      "subpath": "core/harness.py",
      "findings": [
        {
          "dimension": "类型安全度",
          "severity": "critical",
          "line_range": "L280",
          "code_snippet": "callbacks=cast(Any, event_sink),",
          "description": "此处使用 cast(Any) 强行规避了 LangGraph 回调事件订阅的类型推导，导致静态类型系统在此处彻底瓦解，后期接口重构时 Mypy 无法感知类型错误，遗留隐患。"
        }
      ]
    }
  ]
}
```

### 6. 回填与加权折算（模型无关引擎）
所有 subagent 落盘完成后，主控运行模型无关的回填引擎，将 findings 就地内嵌回报告并折算总分：
```bash
python3 code-diagnostics/backfill_audit.py \
  --file code-diagnostics/output/{run_id}/diag_report_{run_id}.md \
  --findings code-diagnostics/output/{run_id}/findings/
```
折算口径为**严重度加权缺陷密度惩罚制**（杜绝"平均分"把缺陷数量摊没，常量可在 `backfill_audit.py` 顶部调节）：
- **缺陷赋权**：critical=5 / major=2 / minor=0.5（severity 缺失按 major）。一条 critical 抵 10 条 minor，避免被 docstring 级 nitpick 砸穿。
- **单文件健康分** = `clamp(round(10 − 该文件加权缺陷量), 0, 9)`，零缺陷=10。
- **全仓惩罚分** = `round(100 · e^(−λ · 加权密度))`，加权密度 = `Σ权重 / 已审文件数`，`λ=DECAY_LAMBDA`（默认 0.18，调大更狠）。指数曲线在"很差"区间仍可区分，便于追踪整改进展。
- **最终分** = `max(0, 惩罚分 − 静态扣分)`。静态卡口（第一阶段）只作**纯扣分项**——它发现问题就扣分，绝不正向加权抬分。静态扣分 = `100 − 静态体检得分`。

未被任何 subagent 覆盖的文件将保持 `[ ]`，交由第三阶段卡口拦截，从而强制形成 100% 覆盖率闭环。

---

## 🛡️ 第三阶段：强力卡口与验收卡点 (Strict Verification Gate)

全仓体检完成后，必须运行验收脚本确保 100% 的覆盖率，防止任何漏检行为：
```bash
python3 code-diagnostics/verify_report.py --file code-diagnostics/output/{run_id}/diag_report_{run_id}.md
```

### 验收卡口要求：
- **无缝覆盖**：每一个待审计的 Python 文件必须勾选为 `[x]` 并标注健康分（格式如 `(健康分: X/10)`）。
- **证据就位**：每一项文件条目下方必须缩进悬挂有非空的美学维度微观证据（或显式的 `[体检通过]` 标记）。
- **漏检抛错**：若有任何漏检，卡口工具将打印 **"漏检的文件清单"** 与 **"漏检的索引条目"**，并以 `exit 1` 强力阻断流水线。漏检即说明对应批次的 subagent 落盘缺失或 `subpath` 不一致，需补派 subagent 重新走查该批次后再次回填。

---

## 📂 第四阶段：归档与 Git (Archival)

- **天然归档**：每轮体检的全部产物即 `output/{run_id}/`，按 `run_id` 自然分文件夹，无需 latest 冗余复制。
- **不入库**：`output/` 已被 `.gitignore` 忽略——报告与中间产物是本地诊断快照，不污染仓库历史。
- **Git 追踪得分**：若本轮伴随工具/代码改动需提交，可在 commit 记录中标注 `[code-diagnostics] {run_id} Score: XX/100` 以留痕。
