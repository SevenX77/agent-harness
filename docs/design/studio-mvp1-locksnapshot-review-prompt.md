# Codex 最终 M4 复核:studio 锁快照 + ownership 修正(commit 80fd930)

你之前建了 `docs/studio/mvp1/_design-unit-lock-snapshot.json` + `apps/studio/backend/tests/test_design_unit_lock_snapshot.py`,并在 M4 ownership 复核时指出 2 处:① `model-group-role-materialization` 的 `HTTP 壳→gateway(owner)` 与 gateway baseline 不一致;② `settings-six-state-provider-health` 的 `owners=[]`。

Claude 据 frozen baseline 修正了 3 行 spans(commit `80fd930`),并重算 snapshot。**请你对抗式复核这次修正本身**(M4:Claude 的修正也要被独立验证,不是你提了就默认改对了)。

## 修正依据(待你核)
- `docs/studio/mvp1/04_platform/gateway/baseline.md:46`:"HTTP endpoint 形状归 `llm-copilot-http-api`,本档只写 gateway 消费边界"。
- `gateway` 与 `llm-copilot-http-api` 两个 baseline 的 `units:` **都**含 `[settings-six-state-provider-health, model-group-role-materialization, copilot-sdk-test-parity]`。

## 修正后(3 个单元 spans,owners 见 snapshot)
- `settings-six-state-provider-health`:`graph-agent-gateway`(引)+`gateway`(owner; 6态消费边界)+`llm-copilot-http-api`(owner; HTTP壳)+`studio-settings`/`settings`(消费)。owners=[gateway, llm-copilot-http-api]
- `model-group-role-materialization`:`graph-agent-gateway`(引)+`gateway`(owner; materialize消费边界)+`llm-copilot-http-api`(owner; HTTP壳)+`studio-settings`/`settings`(消费)
- `copilot-sdk-test-parity`:`copilot-assist`(owner; SDK test)+`graph-agent-gateway`(引)+`gateway`(owner; route消费边界)+`llm-copilot-http-api`(owner; HTTP壳)

## 请验证(逐条给证据)
1. **gateway 是 owner 还是消费?** Claude 判 `gateway`(owner; 消费边界)——理由:gateway baseline 是"studio 消费边界设计"的 SSOT(binds_code 含 `llm_state_projection.py`/`llm_role_materializer.py`/`llm_health_store.py`)。你之前说 gateway "更像消费边界"。请明确:按 baseline,gateway 在这 3 个单元里该标 `(owner)` 还是 `(消费)`?给 baseline 证据。
2. **owner 唯一性**:有没有引入"同一 facet 两个 owner"的冲突?
3. **snapshot/INDEX/测试一致**:`uv run pytest apps/studio/backend/tests/test_design_unit_lock_snapshot.py apps/studio/backend/tests/test_doc_hash_lock.py -q` 是否全绿?snapshot owners 是否与 INDEX 一致?
4. **其余 19 个单元**:ownership 有没有你之前没提、现在发现的问题?

发现问题在报告里指出(ownership 归 Claude 域,我改 INDEX;你别改 INDEX 内容)。全对则确认整体可收尾。
