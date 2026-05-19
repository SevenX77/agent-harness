# Studio V2.1 Multi-file Editor & API (Full Stack) — Requirements

**Spec**: studio-frontend-v21-multifile-editor
**Status**: Requirements (Kiro Step 1, Round 2)
**Date**: 2026-05-16
**Author**: a2 Gemini
**Dependency**: V2.1 backend cutover (PR #45)

## R0. 项目背景与范围声明
随着 V2.1 backend cutover 落地，Skill 物理结构已强制变更为目录树（`GRAPH.md` + `io/*.json` + `phases/*/{LOGIC,SUBGRAPH,SKILL}.md`）。当前 Studio 的 `POST/PUT /api/skills` 接口及前端编辑器仍处于 V2.0 单文件状态，导致保存操作 100% 触发 **422 Unprocessable Entity**。
**本 Spec 核心范围 (EXPANDED)**：端到端（Full Stack）解决多文件作者编写与保存的阻断问题。包含 Backend 接口的 Multi-file 接收与安全写入，以及 Frontend 的目录式编辑器重构。
**基准与原则**：设计与测试基准仅限于 1-2 个 reference V2.1 skill（推荐 `skills/batch-analysis/` 或 `skills/story-deconstruction/`）。其他破损的 V2.1 skill 视为反例 corpus/pending 迁移，不在 must-pass 范围。*（遵循 memory `feedback_prototype_get_right_not_runnable`："所有的策略都指向把事情做对而不是能不能跑...不需要那些skill真的能跑"）*

## R1-R4. Frontend 侧功能需求
**R1. 目录式技能树视图 (File Tree View)**
前端必须提供侧边栏资源管理器（File Tree），精确反映 V2.1 四角色物理结构。
**R2. 多文件编辑与热切换 (Multi-file Tabs)**
支持多 Tab 并在 Monaco Model 级别热切换，保持光标与 Undo 栈。
**R3. 细粒度脏标与多文件合并提交 (Dirty State & Save)**
引入跨文件的全局脏状态（DirtyBar）。`Ctrl+S` 时将虚拟树状态打包为多文件 Dictionary 发往后端。
**R4. Preview API 消费与行号报错联动**
消费 `GET /api/skills/{id}` 的 `graph_topology` / `node_schema_v21` / `io_schema` 进行只读反馈。对编译期返回的 `file:line` FATAL 进行跨文件红标定位。

## R5-R8. Backend 侧功能需求
**R5. Multi-file 更新端点 (`PUT /api/skills/{id}`)**
摒弃单文件 `content` 接收，Req Model 变更为接收 `files: Record<string, string>`。写入时需保证原子性（Atomicity），防部分失败。
**R6. Multi-file 创建端点 (`POST /api/skills`) 与脚手架 (Scaffold)**
解封新建操作。接收带有初始模板的文件映射，或由后端自动推导补齐 `GRAPH.md` + `io/*.json` 骨架。
**R7. 严格路径校验 (Path Validation)**
所有传入的 relative path key 必须经过严格验证，防止目录穿越（`../`）或非法后缀（如非 `.md` / `.json` / `.py` 文件）。
**R8. Pydantic 模型收紧**
更新 `CreateSkillReq` 与 `UpdateSkillReq`，必须配置 `extra="forbid"`，拒绝一切未定义字段。

## R9-R10. 非功能性需求 (NFR)
**R9. 彻底抛弃 V2.0 兼容**
完全移除前后端针对单文件 `SKILL.md` 的兜底与兼容逻辑。*（遵循 memory `feedback_prototype_no_legacy_inertia`："不要过度考虑向后兼容"）*。
**R10. 明确的白名单机制**
无论是前端 UI 拦截还是后端 API 验证，只允许在 `phases/`、`io/`、根目录下创建符合 V2.1 规范的文件名。

## Q-N. Open Questions
**Q-1 (Scaffold 策略)**: 新建 Skill 时，是由前端在 Payload 中组装并发送一份最小合法的 `files` 字典，还是前端仅发 `skill_id` 由后端引擎自动生成 Starter 目录骨架？
*我的推荐*：**后端引擎自动生成 Starter**。保持前端“纯 Dumb”展示器定位，避免在前端硬编码 `GRAPH.md` 模板内容。
