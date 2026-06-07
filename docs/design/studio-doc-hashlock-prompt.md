# Codex 任务:建 studio 设计文档最小哈希锁(防漂移)

## 目标
给 `docs/studio/mvp1/` 的 63 份 **audited-ready** 设计文档建一个**最小哈希锁机器**,防多 session/AI 静默漂移("顺手改一句""对齐实现改一段""格式化带走几行")。**仿 engine 现成实现,不做重型 CI 平台——一个锁表 + 一个 pytest 即可。**

## 输入(已就绪)
- **锁表种子**:`docs/studio/mvp1/_audited-ready-hashes.json` —— 63 档 `relative_path → SHA-256` + `_meta`。这是 EXPECTED 哈希的权威源,**就是从当前 audited 文档算出来的,所以新建的测试对当前文档应全 PASS**。
- **参考实现**:`packages/graph-agent/tests/test_contract_hash_lock.py`(engine 的 `EXPECTED_CONTRACT_HASHES` + drift 测试 + exemption 表)——读它、仿其模式。

## 要建的
1. **一个 pytest**(放合适 tests 目录,参照 engine 测试的位置惯例;studio 相关可考虑 `apps/studio/backend/tests/` 或仿 engine 的 docs-lock 位置):
   - 读 `_audited-ready-hashes.json` 的 `hashes`;
   - 逐档重算 SHA-256 与锁表比;**不符 → FAIL**,报哪个文件漂了 + 可操作指引(revert / owner 批准后更新底账 / 走 exemption);
   - 锁表里的文件**缺失或仓库新增同类文档未入表**也应能报(至少缺失必报)。
2. **exemption 机制**(仿 engine):owner 批准的改动登记到 exemption(文件 + 新 hash + 说明),测试放行该项。
3. 接入默认 pytest 收集(`uv run pytest` 能跑到)。

## 铁律
- **不改那 63 份设计文档**;**不改 `_audited-ready-hashes.json` 里的 `hashes`**(它 = 当前 audited 真相)。
- 只加测试 + 必要的最小 plumbing(import/conftest 之类)。
- 失败信息必须可操作(明确告诉人怎么 revert / 更新底账 / 申请豁免)。

## 不在本任务
- 把文档 `status` 从 `drafted` 改成 `FROZEN` —— 那是机器建成 + 测试绿之后、Claude/owner 的**原子提交**步骤(录 hash + unit `locked` + 文件 `FROZEN`),不在本任务。

## 交付
新增测试文件(+ 如需 exemption 表/小工具);报告:测试路径、怎么跑、当前对 63 档是否全绿。
