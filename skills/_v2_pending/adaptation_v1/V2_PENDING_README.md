# adaptation_v1 (V2 pending)

依赖 `tier` + `subagent_enabled` 字段, 在 V1 (Schema 2.0 reset) MVP-0 (T9a)
被砍除. 等 V2 重新引入 subagent 协议后回归.

具体不兼容字段:
- `tier: balanced` (Schema 2.0 移除, 改 llm_role)
- `subagent_enabled: false` (T9a 砍 subagent_enabled 整路径)

参见 `docs/superpowers/specs/2026-04-28-v1-reset-direction.md` Section 6 V2 路线图.
