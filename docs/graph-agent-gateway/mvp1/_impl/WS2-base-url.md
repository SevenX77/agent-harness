---
ws_id: WS-2-base-url-canonicalization
modules: [03]
depends_on: [WS-1 的 registry/base_url.py(仅 import,已在工作区存在;不改它)]
blocks: []
owns_files:
  - packages/graph-agent-gateway/src/graph_agent_gateway/registry/fingerprint.py   # 改:_normalize_base_url 升级为 per-protocol(调 canonicalize_base_url)
  - apps/studio/backend/app/services/llm_credentials.py                        # 改:upsert_endpoints 保存时归一化(+ v3→v4 migration / draft apply 同规则)
  - packages/graph-agent-gateway/tests/test_registry_base_url.py 或 test_registry_*.py  # 加:fingerprint 用 canonical 的测试
  - apps/studio/backend/tests/（credentials 相关测试文件）                     # 加:upsert 保存时 canonicalize 的测试
spec_ssot:
  - ../03-orch-credentials-endpoints/mvp1-alignment.md §F3 / §F5 / 接口契约「base_url 归一化」/ gaps
status: drafted
---

# WS-2 base_url 保存时归一化 — 任务书

## 1. 目标(intent + why)

把 base_url **在保存 endpoint 时**按 protocol 归一化成 canonical 形态(F3),并让凭证 fingerprint 以 canonical base_url 为输入(F5)。**为什么**:现状 base_url 原样透传(只 strip/rstrip),导致 WaveSpeed anthropic SDK 用 `/v1` → SDK 自加变 `/v1/v1/messages` → 404(实证);保存时固定 canonical,让 resolver / probe / client factory / fingerprint / copilot env 读到**同一份** base_url,杜绝"测试通了运行又错"。规则与 WS-1 已建的 `canonicalize_base_url` 完全一致——**本 WS 只在保存侧调它,不复制规则**。目标机制以 spec_ssot 为准。

## 2. SSOT 指针(grounding,IR2/IR5)

- **目标(怎么做)**:`../03-orch-credentials-endpoints/mvp1-alignment.md` §F3(保存时 per-protocol)、§F5(fingerprint 用 canonical)、接口契约「base_url 归一化(③b 公共,两道)」、gaps #2/#3。
- **现状(起点)**:`../03-orch-credentials-endpoints/baseline.md` §3(base_url 原样透传)、§F5。
- **复用(只 import,不改)**:`packages/graph-agent-gateway/src/graph_agent_gateway/registry/base_url.py:canonicalize_base_url`(WS-1 已建,per-protocol + 幂等)。
- **实现前必读源码(先读并确认)**:
  - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/fingerprint.py:13-42`(`compute_credential_fingerprint` + 现 `_normalize_base_url` 只 `strip().rstrip("/")`)
  - `apps/studio/backend/app/services/llm_credentials.py:107-136`(`upsert_endpoints` 现状保存,不归一)、`:299-326`(`_v3_payload_to_v4`)、`:369-393`(`_stable_endpoint_id`,**不动,F4 延期**)
  - `apps/studio/backend/app/services/llm_import_drafts.py:136-202`(`apply_draft` 写 endpoint,同规则候选)
  - 参考(不抄):`apps/studio/backend/app/services/copilot.py:476-491`(现 deepseek/ark 局部 helper,证明规则之前散在调用侧)

## 3. 文件归属(并发锁,IR1)

- **本 WS owns**:见 frontmatter。
- **禁止触碰**:
  - `registry/base_url.py` → **WS-1 owns**,本 WS **只 import**,不改。
  - `call/chat_model.py`/`call/factory.py`/`call/profiles.py`/`models.py` → WS-1。
  - `registry/resolver.py`/`protocol.py` → WS-5。
  - copilot 调用方式(`copilot.py` 的 `_resolve_route_runtime`)→ ③a 调用层,不在本 WS(只读作参考)。
- **共享文件协调**:无(本 WS 文件与 WS-1/WS-3/WS-4 不重叠;可与它们并发)。
- **⚠️ 注意**:WS-1 尚未提交、工作区有大量预存改动;本 WS **只 stage 自己 owns 的文件 + 自己的测试**,别 `git add .`,别碰 WS-1 staged 集。

## 4. 现状锚点(baseline)

`_normalize_base_url` 只 `strip().rstrip("/")`,无 per-protocol 规则;`upsert_endpoints` 存前不归一;canonical 规则只在 copilot runtime 有局部 deepseek/ark helper(散)。详见 baseline §3/§F5。

## 5. 目标行为(可测的契约)

- **保存时归一化(F3)**:`upsert_endpoints` 把每条 endpoint 的 `base_url` 在写入前替换为 `canonicalize_base_url(base_url, protocol)`。存进文件的就是 canonical。
- **storage 归一化升级(F3+F5)**:`registry/storage.py` 的 `_normalize_base_url` 升级为 per-protocol —— 即改成调用 `canonicalize_base_url(value, protocol)`(需把 protocol 传进来;`compute_credential_fingerprint` 有 endpoint,取 `endpoint.protocol`)。于是 fingerprint **自动**以 canonical base_url 为输入(F5 随之满足)。
- **同一规则覆盖多写入口(F3,gaps #2)**:`upsert_endpoints` 为主;`_v3_payload_to_v4`(migration)、`apply_draft`(draft 写 endpoint)走**同一个** `canonicalize_base_url`。若某入口本轮无法干净接入,**显式延期**(记 deferred + 报告说明),不许静默漏。
- **canonical 规则**:全部来自 WS-1 的 `canonicalize_base_url`(anthropic 去尾 `/v1`、openai 保持、deepseek-anthropic 去 `/v1` 补 `/anthropic`、ark `.../api/v3`)。**本 WS 不新写规则**。
- **不变项**:secret 保留逻辑(`_preserved_secret`)、原子写 + `0600`、endpoint/route 分层删除 —— 都不动。

## 6. 测试要求(Codex 必须覆盖,IR3/IR4)

抽自 03 alignment §F3/§F5 测试点:
- **保存时 per-protocol canonical**:`upsert_endpoints` 存 anthropic endpoint(base_url 带 `/v1`)→ 文件里是去尾 `/v1`;deepseek-anthropic 带 `/v1` → `/anthropic`;ark → `.../api/v3`;openai → 保持(**防回归成"只 strip 尾斜杠"**)。
- **fingerprint 对等价 URL 稳定(F5)**:同一 endpoint 录入 `https://x/v1` 与 `https://x/v1/` → canonical 后 `compute_credential_fingerprint` **相同**(不反复失效)。
- **保存=读取同一路径**:upsert 后,resolver 读到的 `ResolvedRoute.base_url` 与存的 canonical **一致**。
- **migration / draft apply 同规则**(若本轮接入):v3→v4 / apply_draft 写出的 endpoint base_url 也是 canonical。
- **真实**:测试要真调 `canonicalize_base_url`,不许 mock 掉归一化本身。

## 7. 内部子步骤顺序

1. `registry/storage.py`:`_normalize_base_url` 升级为 per-protocol(import + 调 `canonicalize_base_url`,签名加 protocol);`compute_credential_fingerprint` 传 `endpoint.protocol`。
2. `llm_credentials.py:upsert_endpoints`:保存前 `canonicalize_base_url(base_url, protocol)`。
3. 同规则接入 `_v3_payload_to_v4` / `apply_draft`(能干净接则接,否则显式延期)。

## 8. 验收标准(硬退出,IR4)

- [ ] §6 测试全绿。
- [ ] `uv run pytest packages/graph-agent-gateway/tests -q` 全绿;`uv run pytest apps/studio/backend/tests -q`(至少 credentials/registry 相关)全绿。
- [ ] `uv run mypy`(改动文件)0 error。
- [ ] fingerprint 对等价 URL 稳定有专测。
- [ ] 未接入的写入口(若有)已记 deferred + 报告列明,无静默漏。

## 9. 不做(范围锁定,IR7)

- **F4 endpoint 标准化拆分 + canonical endpoint_id 下沉 ③b —— 本轮不做**(alignment gaps #1 明列"后续工程,非本轮")。`_stable_endpoint_id` 不动、不退役。→ 记/确认 `docs/deferred-items.md`。
- 不动 secret vault 迁移(F1 #6 仍是明文文件,本轮不碰)。
- 不改 `registry/base_url.py`(WS-1)、不碰 copilot 调用方式、不重构 `llm.py`。
- 范围外问题 → 记 deferred,不顺手改。

## 10. baseline 回写指令(IR6,实现后)

照真实代码改 `../03-orch-credentials-endpoints/baseline.md`:§3「base_url 原样透传」→「保存时 per-protocol canonical(`canonicalize_base_url`)」;§F5「fingerprint 只清尾斜杠」→「以 canonical base_url 为输入」。F4 现状保持"未下沉"(诚实)。

## 11. 评审检查点

- **契约门(Claude 审测试,放实现者前)**:重点查 F3 四条 per-protocol 用例 + F5 等价 URL 稳定是否忠实编码 alignment(尤其 openai「保持」别被写成「去 /v1」、deepseek「补 /anthropic」别漏)。
- **Codex 审查退出** = §8 全满足。
- **Claude 终审**:① 规则确实复用 WS-1 helper(没第二份);② 多写入口是否一致(或延期已披露);③ baseline 回写诚实;④ 无静默 stub / 无死代码遗留。
