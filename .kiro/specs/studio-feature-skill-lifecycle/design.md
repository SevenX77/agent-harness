# Specification: studio-feature-skill-lifecycle (Design)

> **状态**: 收敛设计 (2026-06-01)
> **运行环境**: 本地单用户 Tauri 桌面应用(前端 webview + Rust 原生层 + Python sidecar @ `:8787`)
> **关联**: `requirement.md`(本目录) · `research.md` §1 代码审计(仍有效;§2 已被本文件取代) · `review-2026-06-01.md`(评审记录,部分决策已修订)

---

## 1. 概述与语义边界

本特性从原先的"三件杂事捆绑"(哈希自愈 + 多物料上传 + 正则管道)**收敛为单一内聚语义**:

> **技能的「测试输入管理 + 批量运行」** —— 把语料喂进来,然后批量跑这个技能。

| | 内容 | 归属 |
|---|---|---|
| ✅ 范围内 | 测试物料的导入 / 列出 / 删除;单次与批量运行;统一命名序列文件的自动批量 | 本特性 |
| ❌ 移出 | 覆盖白名单哈希 403(原 S1) | 独立本地小修(见 §5,已登记 DEF-011) |
| ❌ 移出 | 文件标准化 / 格式转换工具 | 引擎内置 tools `packages/graph-agent/.../tools/builtin/` |
| ❌ 移出 | 画布渲染 / 节点 / 覆盖检测 | `canvas-topology` |
| ❌ 移出 | 工作区文件树展示 | `asset-explorer` |
| ❌ 不在本次 | 技能创建 / 编译 / 生命周期阶段叙事 | 现有 `skills.py`(稳定) / `docs/studio/01_workflows/` |

**改名建议(开放项,见 §8)**:目录名 `studio-feature-skill-lifecycle` 语义过宽,建议改为 `studio-feature-test-inputs-batch`,让名字 = 语义。

---

## 2. 架构上下文(已核实的事实)

| 事实 | 证据 |
|---|---|
| 本地 Tauri:webview + Rust 原生层 + Python sidecar(FastAPI @ `:8787`) | `apps/studio/tauri/`;`api/client.ts:22` `API_BASE_URL` |
| 文件 I/O 现状全部经 Python sidecar;Rust 未引入 `tauri-plugin-fs` | `api/client.ts` `writeSkillFile`;`tauri/Cargo.toml` 仅 `tauri-plugin-dialog` |
| **原生文件夹选择已存在并接通** | Rust `select_directory`(`tauri/src/lib.rs:94` `dialog.pick_folder`)+ 前端 `selectSkillDirectory()`(`lib/tauri.ts`) |
| `test_inputs` 写接口是 501 桩;list 仅 glob `*.json` | `routers/test_inputs.py`(create/delete `raise_not_implemented` ~L50;list `*.json` L31;`_preview_json` 已对非 JSON 回退原文 L63-69) |
| 批量装载硬 `json.loads`,非 JSON 抛 ValueError | `services/run_manager.py` `_load_test_input` L554(`json.loads` L566);`start_batch_run` L239 消费 |
| 可复用的安全路径校验 | `services/skills.py` `validate_skill_file_path` L108(拒 `..`/`/`/`\`) |
| 批量 UI / 类型 | `BatchRunner.tsx` · `useBatchRun.ts` · `TestInputMetadata`(`api/types.ts:127`) |
| 引擎已有内置工具(含格式转换) | `packages/graph-agent/.../tools/builtin/` · `tools/md_to_json.py` |

### 决策 D1 — 文件所有权:Rust 只管对话框,Python 独占文件(Q1 结论)

- **采用方案 A**:Rust 负责弹原生对话框、返回路径;**Python 独占 `.workspace` 文件读写**。
- **理由**:Python 引擎必然拥有这些文件(编译 / git 备份 / hash / 原子写 / 运行)。若 Rust 也写同一批文件 → **双写者 = 在本地凭空制造并发冲突**(即原 S1)。单一写者最安全、改动最小。
- 方案 B(Rust 独占裸 FS、Python 纯计算)= 独立的未来大重构,**不在本范围**。

---

## 3. Pillar 1 — 测试输入管理

### 3.1 导入流程(原生路径,非网页 multipart 上传)

本地 app 的自然形态不是浏览器式 multipart 上传,而是"选路径 → 后端读入":

```
用户点"导入"
  → Rust 原生对话框(选文件 / 文件夹)返回本地路径   [前端 invoke select_directory / 新增 select_files]
  → 前端把路径 POST 给 Python sidecar               [非文件流,只传路径]
  → Python 读入/复制进 该技能 .workspace/test_inputs/
  → 返回元数据 → 刷新列表
```

- **后端落地**:把 `routers/test_inputs.py` 的 `create` / `delete` 从 501 桩实现为真实逻辑。`create` 接收**本地路径**(而非 multipart 文件流)。
- **健壮性**:写入目标路径复用 `validate_skill_file_path`,确保落在 `test_inputs/` 内。
  - 定位为**健壮性而非安全防护**(本地单用户,不存在外部攻击者)。
- **拷贝 vs 引用**:默认**拷贝进 `test_inputs/`**,保持 `.workspace` 自包含(开放项,见 §8)。
- **Rust 侧**:目前只有文件夹选择(`pick_folder`)。若需选单/多文件,需新增一个 `select_files` 命令(`pick_file`/`pick_files`)。

### 3.2 列出与类型标注(防崩的基础)

- `list_test_inputs` 的 glob `*.json` → `*`(纳入 `.md`/`.txt`)。
- **但每项标注 `kind`**:`"json"`(结构化输入)/ `"raw"`(原始物料),最简实现按扩展名判定。
- `TestInputMetadata` 增加 `kind` 字段(轻量,不做正式类型契约)。

### 3.3 删除

- 实现 `delete_test_input`:移除文件 + 刷新列表。

---

## 4. Pillar 2 — 批量运行

### 4.1 防崩:raw 物料不进 JSON-only 装载路径

当前 `_load_test_input` 硬 `json.loads`,放宽 glob 后若 `.md` 流入会崩。修法:

- 装载前按 `kind` 分流:**仅 `kind=json` 进入 `_load_test_input`**;`raw` 物料不触发 `json.loads`。
- UI 把"原始物料"与"JSON 输入"分区呈现,raw 不出现在仅接受 JSON 的选择器里。

### 4.2 一输入一运行 + 序列自动批量

- 批量 = 对所选输入**各发起一次运行**(沿用现有 `start_batch_run` 语义:逐项 `start_run`)。
- **序列检测(轻量 UI 便利)**:前端识别"数字后缀的统一命名序列"(如 `chapter1`、`chapter2`…)→ **建议自动开启批量,默认运行数量 = 文件数量**。
  - 仅前端便利,**不改后端运行语义**。
  - (区分:引擎 `parallel_map` 是"单次运行内部对列表 fan-out",与此处"一文件一运行"的外层批量正交。)

### 4.3 假定输入干净(不为脏数据过度设计)

- **默认导入的序列物料格式 / 命名是统一规整的**(像 1000 章规整小说;外部素材本就会归一化;graph agent 批量产出天然命名规范)。
- **不做**正则映射管道 / 强制 dry-run / 类型强转引擎。脏数据由用户上游规整,或经**引擎内置转换工具**(如 `md_to_json`)处理后再导入。
- "测试跑一下就知道问题,有问题再解决"——不为假想边界提前设计。

### 4.4 失败显式上报

- 批量运行中某输入失败 → **显式报告失败项,不静默跳过**(WARNING 级日志 + UI 可见)。

---

## 5. 范围外与移交(关键)

### 原 S1(覆盖白名单哈希 403)—— 移出本特性,降级为独立本地小修

- **最小修法**(本地版):
  - "加入白名单"提供**后端 read-modify-write**(`addSequentialOverwriteField` 的服务端等价,在 `skills.py`),该操作不再经客户端 hash → 不会 403。
  - 通用编辑器保存若撞 403(你在外部也改了同一文件)→ 给一个**"重新加载"按钮**。
- **不做**:平台版本契约 / 三方合并(过度设计,已撤回)。
- 已登记 `docs/deferred-items.md` **DEF-011**;owner 待定。

### 文件标准化 / 格式转换工具 —— 移交引擎

- 归 `packages/graph-agent/.../tools/builtin/`(已有 `md_to_json`)。职责:引擎管可复用工具,Studio 管生命周期 UI。

### 其它

- 画布 / 覆盖检测 → `canvas-topology`;文件树 → `asset-explorer`。

---

## 6. 文档协作(Q2 结论)

- **layout 单一事实源 = `docs/studio/03_platform/system-layout/`(已存在)**。
- 本特性触及的区域(测试输入面板 tab、批量运行入口)在 feature 文档中以**链接引用 system-layout 锚点**的方式描述,**不重述 layout**(引用而非复制,避免漂移)。

---

## 7. 测试策略(TDD,先写失败测试)

- **后端**:`create_test_input`(本地路径 + 路径健壮性)、`delete_test_input`、`list` 含 `kind`、`_load_test_input` 对 `raw` 不崩。
- **批量**:一输入一运行;失败项显式上报;序列检测建议。
- **前端**:导入流程(mock Rust dialog 返回路径)、raw/json 分区、序列自动批量建议。

---

## 8. 开放项(待确认)

1. **改名**:`studio-feature-skill-lifecycle` → `studio-feature-test-inputs-batch`?(语义对齐,但牵动 `INDEX.md` 与交叉引用)。
2. **原 S1 小修**的 owner 与排期(DEF-011)。
3. 导入**拷贝进 `test_inputs` vs 原地引用路径**——当前默认拷贝进(自包含),如需引用模式再议。
