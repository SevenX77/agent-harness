# Codex 任务：Studio MVP1 文档 retrofit（装 R4–R8 结构机器，批量）

你是文档工程师。给 `docs/studio/mvp1/` 的**轴② 能力/区域/平台模块**文档（`baseline.md` + `mvp1-alignment.md` 对）**装上新规范的结构机器（R4–R8）**：frontmatter、`units:`、测试锚点差异表、§1–§8、`文件:符号名` 证据、双向交叉引用。
**内容已经对齐过最新决策了——你不要重审 / 改内容，只做结构 retrofit + 把已验真的代码 drift 忠实落进 baseline。**

## 0. 黄金参考（最重要：照着这一对的格式抄）

**`docs/studio/mvp1/02_capabilities/predict/baseline.md` + `mvp1-alignment.md`** 是已定稿的样板，**每一档都要长成这个样**。先把这两份 + `docs/development/design-doc-standards/example/{baseline-example,alignment-example}.md` 读熟，格式严格照抄。

## 1. 判据 / 输入（必读）

1. **标准**：`docs/development/design-doc-standards/00-three-axes.md` · `01-writing-standard.md`（§4 baseline 模板 / §5 alignment 模板 = 权威格式）· `02-audit-standard.md`（R4–R8）。
2. **设计单元 INDEX**：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md` —— **每个模块的 `units:` 从这里查**：该模块 **own 哪些单元切面**就列哪些（消费/依赖的单元走交叉引用、**不**进 `units:`）。
3. **scope / 边界**：`docs/studio/mvp1/README.md` 的四层 NON-GOALS —— **③b gateway 公共内核 + engine 契约只引用 SSOT、不在 studio 复制**；`binds_code` 指 studio ③a 代码（`apps/studio/`），③b/engine 部分用交叉引用。
4. **drift 线索**：`docs/design/studio-mvp1-audit-report.md`（结构 + 代码轨）· `docs/design/studio-mvp1-content-audit-report.md`（内容轨）· INDEX 的 `binds_code` ⚠️ 列。

## 2. 范围（轴② 模块，baseline + alignment 对；**predict 已做、跳过**）

- **02_capabilities（13）**：compile-lint, conflict-overwrite, copilot-assist, debug-resume, file-editing, golden-eval, graph-authoring, phase-editing, publish, run-execution, skill-workspace, studio-settings, trace-observability
- **03_regions（12）**：assets, canvas, center-action-bar, copilot, editor, input, local-history, properties, settings, shell-layout, timeline, welcome
- **04_platform（5）**：engine, gateway, llm-copilot-http-api, native-fs, state-engine
- **特例 `04_platform/i18n.md`**（单文件、非 baseline/alignment 对）：只加 frontmatter（`units:`）+ 双向交叉引用，**保留其现有结构**。
- **不碰 `01_workflows/*`**（轴①，另一套 workflow 模板）。

## 3. 每档 retrofit 步骤

1. 读现状 `baseline.md` + `mvp1-alignment.md`。
2. **baseline**（照 predict baseline）：
   - frontmatter：`module` · `doc: baseline` · `status: drafted（现状对齐 pinned 代码 <当前 HEAD short>；<一句话状态>）` · `binds_alignment: ./mvp1-alignment.md` · `binds_code: <文件:符号名 · ...>`（主符号，`·` 分隔）· `units: [<从 INDEX 查>]`（**无 `lock:` 字段**，锁态在 INDEX）。
   - 正文：`> Scope + 现状一句话` → `## UI/UX` → `## 前端逻辑` → `## 后端功能` → `## API` → `## Data Model / State` → `## 当前边界` → `## baseline / alignment 差异（测试锚点）`（表：维度 | 现状 | 目标 + 一行"验是否按目标改了"）→ `## 读代码主路径提示` → `## 交叉引用`。
   - 每条证据挂 **`文件:符号名`**（读对应代码确认符号名，行号作辅）；**已验真的 code↔design drift 标 ⚠️、落进测试锚点的"现状"列**。
3. **alignment**（照 predict alignment）：
   - frontmatter：`module` · `doc: mvp1-alignment` · `status` · `binds_baseline: ./baseline.md` · `units: [...]` · `aligns_with: <workflow 节点>`。
   - 正文 **§1–§8**：`## 1. 定义` · `## 2. 数据流 / 机制`（含设计细节：签名/字段/步骤/错误码，非只方向）· `## 3. 接口契约` · `## 4. 设计决策基础（PM 原话）`（就近写原话）· `## 5. 决策 + 动机`（表）· `## 6. 测试关键点` · `## 7. 涉及 region / platform` · `## 8. gaps / 报警`（🚨；实施细节归 kiro，不进设计文档）· `## 交叉引用`（双向）。
   - **保留现有（已对齐过的）内容**，只重组进 §1–§8 + 补 frontmatter/header/交叉引用 —— **别重新发明内容**。原 F1/F2… 功能段的内容拆进 §2（机制）/§5（决策）/§4（原话）/§6（测试）。
4. **双向交叉引用**：`baseline ↔ alignment` 配对互指；跨模块指到 INDEX 里该单元的 **owner 模块**。
5. **代码轨**：顺 `binds_code` 符号读代码，确认 baseline "现状" 属实（R2）；顺手把 5 维（极简度 / 类型安全 / 死代码 / 测试活性 / 接口依赖清晰度）的明显缺陷记进 baseline 的 drift 列（标 critical/major/minor），**但不改代码**。

## 4. 铁律

- **不改任何代码**（decision-3：drift 只忠实写进 baseline + ⚠️ 警告）。
- `units:` 从 INDEX 查、只列该模块 **own** 的单元切面；**无 `lock:` 字段**（锁态在 INDEX）。
- **四层边界**：③b 内核（model group / 6 态标准投影 / materialize / endpoint 标准化 / draft / 熔断）+ engine 契约（子图 path / golden 落点 / skill 语法 / 错误码 / resolver / checkpoint）**只引用、不复制**；`binds_code` 指 `apps/studio/` 的 ③a 代码。
- 证据 **`文件:符号名` 为主**（读代码确认，别脑补符号名）；拿不准的标"待核"，别瞎写。
- **内容已对齐最新决策，别重审 / 改内容**，只装结构机器。

## 5. 交付

逐档原地编辑；最后产一份简报 `docs/design/studio-mvp1-retrofit-report.md`：① 哪些档已 retrofit；② 每档的 `units:`；③ 遇到的问题（INDEX 缺该单元 / `binds_code` 符号找不到 / 内容疑似仍 stale）。**分批做没问题**（建议 capabilities → regions → platform 三批），每批跑完先报一次。
