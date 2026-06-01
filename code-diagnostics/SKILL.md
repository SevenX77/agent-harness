# SKILL: 卓越工程代码美学与架构诊断规约 (Anti-Laziness Diagnostics Oracle)

本规约旨在约束并协同 AI 助理（大模型）执行项目根目录顶级 `code-diagnostics/` 独立体检套件的诊断流程，彻底消解大模型的“注意力稀释”与“脑补敷衍”通病，强制通过注入式时间戳报告与多线程并行走查，完成全仓所有源文件的高密度、高保真代码美学体检。

---

## 🛠️ 第一阶段：动态报告创建与硬性扫描 (Setup & Static Audit)

AI 助理接收到体检打分任务时，必须生成一个唯一的精确 UTC 时间戳（如 `20260601_082943`），并按顺序执行以下注入式动态操作：

1. **运行结构生成器**：
   ```bash
   python3 code-diagnostics/build_tree.py --file code-diagnostics/reports/diag_report_{timestamp}.md
   ```
   它会在 `reports/` 目录下生成该次审计的基准清单文件，并将全仓待审文件初始化为待审计状态 `[ ]`。

2. **运行静态硬性卡口**：
   ```bash
   python3 code-diagnostics/run_static_audit.py --file code-diagnostics/reports/diag_report_{timestamp}.md
   ```
   它会在本地完成 5 维硬性指标打分（如死代码物理残留、mypy ignore 逃避、skip测试、os.environ绕过契约耦合等），并将静态扣分证据与得分自动回填到当前时间戳报告中。

---

## 🔍 第二阶段：大模型微观深度质检 (LLM Parallel Micro-Audit)

在对各个文件进行“架构与美学打分”时，大模型必须遵守以下**【绝对硬性红线】**：

### 1. 强力防偷懒红线：【就地内嵌微观线索凭证】
- 废除零散证据小节，大模型针对文件的任何代码缺陷（如：冗余向下兼容、层层包裹的临时 Patch、类型系统逃逸）的诊断，**一律作为子节点就地内嵌并缩进悬挂在对应文件条目的正下方**。
- 大模型**必须一字不差地复制**对应有问题的源代码段，并标注出**绝对精准的起始行号**（格式如 `runner.py:L123-145`）。

### 2. 深度审阅的 5 个健康维度
LLM 必须围绕以下 5 个美学指标进行找茬打分：
- **极简度（奥卡姆剃刀）**：代码中是否为了处理废弃逻辑而保留了层层包裹的 Patch 和 Adaptor？
- **类型安全度**：是否存在滥用 `cast(Any, ...)`、`type: ignore` 逃避类型检查的代码？
- **死代码干净度**：代码内部是否依然定义了已宣告废弃的类和不可达方法？
- **测试活性度**：测试是不是跑在虚假的 Mock 预设上，有没有真正的端到端断言？
- **接口与依赖清晰度**：是否绕过标准 `Settings` 等契约接口直接引用系统底层，或存在非标越权私有导入？

### 3. 多线程并发走查提速
由于全仓文件极其庞大，主 Agent 严禁单线程串行操作以防上下文爆仓，必须运行以下并行走查器：
```bash
python3 code-diagnostics/run_llm_audit.py --file code-diagnostics/reports/diag_report_{timestamp}.md --workers 12
```
它会多线程并发读取所有 Python 源文件并调用极速 LLM 质检回填，并完成 final score 折算。

---

## 🛡️ 第三阶段：强力卡口与验收卡点 (Strict Verification Gate)

全仓体检完成后，必须运行验收脚本确保 100% 的覆盖率，防止任何漏检行为：
```bash
python3 code-diagnostics/verify_report.py --file code-diagnostics/reports/diag_report_{timestamp}.md
```

### 验收卡口要求：
- **无缝覆盖**：每一个待审计的 Python 文件必须勾选为 `[x]` 并标注健康分（格式如 `(健康分: X/10)`）。
- **证据就位**：每一项文件条目下方必须缩进悬挂有非空的美学维度微观证据（或显式的 `[体检通过]` 标记）。
- **漏检抛错**：若有任何漏检，卡口工具将打印 **“漏检的文件清单”** 与 **“漏检的索引条目”**，并以 `exit 1` 强力阻断流水线。

---

## 📂 第四阶段：版本控制与 Git 追踪 (Version Control)

每一轮体检均单独生成唯一的 timestamp 文件：
1. **天然归档**：体检文件即为 `reports/diag_report_{timestamp}.md`，无 latest 冗余复制。
2. **Git 版本追踪**：通过 Git 进行提交和管理，在 commit 记录中明确标明 `[code-diagnostics] diag_report_{timestamp} Score: XX/100`。
