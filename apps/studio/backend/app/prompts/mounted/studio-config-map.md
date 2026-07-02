# Studio 配置文件地图（copilot 只读参考）

Studio 的配置根目录（下称 `STUDIO_CONFIG_DIR`）在 Windows 上是
`%APPDATA%/AgentStudio/`（macOS `~/Library/Application Support/AgentStudio/`）。
本文告诉你每个文件/目录是什么、出问题去哪看、以及**哪些绝对不要直接改**。

## 顶层

| 路径 | 是什么 | 能不能手改 |
|---|---|---|
| `app_settings.json` | 应用级设置（主题、窗口等） | 可读；改动应走 Settings UI |
| `skill_index.json` | 已知 skill 的索引缓存 | **不要手改**——由 Studio 维护，删了会重建 |
| `recent_workspaces.json` | 最近打开的 workspace 列表 | 同上 |
| `logs/studio_runtime_activity.jsonl` | 运行时活动日志（endpoint 测试、role 测试、探测结果都记在这） | 只读；诊断"配置到底发生过什么"先看这里 |

## `llm/` —— LLM 配置真相（gateway truth，手改禁区）

这一目录是 credentials / roles / registry 的**唯一真相源**，写入只能经
Studio 后端接口（前端 Settings → FastAPI → gateway），**绝对不要用 Write/Edit
直接改这里的文件**——绕过校验会破坏真相一致性。

| 文件 | 是什么 |
|---|---|
| `llm_credentials.json` | provider endpoints + routes（含能力标注 capabilities） |
| `llm_roles.yaml` | 角色 → model group / fallback_chain 映射（copilot 角色也在这） |
| `llm_probe_catalog.json` | 探测证据库（probe-verified 能力记录） |
| `llm_role_test_results.json` | 最近一次 role / copilot 测试结果 |
| `llm_health.sqlite` | 路由健康/冷却状态 |
| `llm_canonical_rules.yaml` | 模型 ID 归一化规则 |

诊断口径：用户说"模型不可用/角色不见了"→ 先看 `logs/` 里最近的
endpoint_test / role_test 记录，再对照 `llm_credentials.json` 的 route status；
需要改配置时**指引用户去 Settings 操作**，不要代改文件。

## `workspaces/<name>/` —— skill 工作区（你的 cwd 就在这里面）

| 子目录 | 是什么 |
|---|---|
| `skills/<skill>/` | skill 源文件（GRAPH.md / phases/…）——你的主要工作对象 |
| `runs/` | run/predict 的执行产物与 trace |
| `engine_artifacts/` | 编译产物缓存 |
| `blobs/` | 大对象存储（附件等） |
| `ephemeral_run_skills/` | 临时 run 用的 skill 副本，随时可弃 |

## `Skills/`（顶层）

社区/共享 skill 的本地缓存（配 `community_catalog_cache.json` /
`community_upload_queue.json`），不是当前 workspace 的源文件。
