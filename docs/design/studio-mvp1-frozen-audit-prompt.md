# Codex 任务:全面审计 studio MVP1 FROZEN 锁定提交(对抗式独立复核)

## 你的角色
你是独立、对抗式的审计者。目标是**找出这次 FROZEN 锁定操作的任何错误 / 疏漏 / 不一致**,不是给它背书。默认怀疑"自报全绿"。遵守 M4 原则:任何自审(含 AI 自审)都必须被独立复核,复核者是对抗的——你不能只凭下面的描述下结论,必须亲自读文件 / 跑命令验证。

## 背景:这次操作做了什么(客观事实,供你核对,**不是结论**)
仓库分支 `docs/mvp1-design-20260604`,提交 `924ff4c`(`docs(studio): FROZEN 63 设计文档 + 22 单元 locked`)。

目标:把 `docs/studio/mvp1/` 下 63 份已审计设计文档从 `drafted` 锁定为 `FROZEN`,并把横切设计单元索引里的 22 个单元标 `locked`。具体五步(均为**待你验证的声称**):
1. 63 档 frontmatter `status: drafted（…）` → `status: FROZEN（…）`(声称只改 status 那一行的 token,括号内描述原样保留)。
2. `docs/studio/mvp1/DESIGN_UNITS_INDEX.md`:22 个 `| drafted |` 单元锁格 → `| locked |`;另改 6 处与"已冻结"矛盾的正文 / frontmatter。
3. 重算 `docs/studio/mvp1/_audited-ready-hashes.json` 的 63 个 SHA-256(因 status 改了字节)+ `_meta` 改为 `frozen`。
4. 跑 `apps/studio/backend/tests/test_doc_hash_lock.py`(哈希锁测试),声称 3 passed。
5. 只暂存 `docs/studio/mvp1/` 下 65 文件提交(仓库另有 60+ 个无关脏文件,声称一个没碰)。

## 审计标准(先读)
- `docs/development/design-doc-standards/01-writing-standard.md` §1(FROZEN 状态机:§1.1 四态、§1.6 单元锁与"文件级 FROZEN = 承载的所有单元切面都 locked"、§1.4"审计后才锁")。
- `docs/development/design-doc-standards/02-audit-standard.md`(R0–R8 硬规则、§六 审计方法论 M1–M8)。

## 必须独立验证的 7 点(逐条给证据 `file:line` 或命令输出,别只说"看起来对")

1. **提交范围完整性**:`git show --stat 924ff4c` —— 是否恰好 65 文件、全部在 `docs/studio/mvp1/` 下?有没有该锁的档漏了、或不该动的被裹进来?提交里的 63 份内容档清单,是否与 `_audited-ready-hashes.json` 的 `hashes` keys **完全一致**(不多不少)?

2. **status 翻转纯净性**:逐档抽查 `git show 924ff4c -- <file>` —— 每档是否**只有 status 那一行**变化(`drafted`→`FROZEN`)?有没有哪档的括号描述被误改、或 frontmatter 其它字段(module/doc/binds_*/units/aligns_with)被动?有没有正文 body 里别处的 `status: drafted` 被误伤?**反向**:有没有本应保持 `drafted` 的档(如纯 target-design 占位、尚未审计完的)被错误冻结?

3. **底账与文件逐字节吻合**:**自己重算**当前 63 档的 SHA-256(`shasum -a 256` 或 python),与 `_audited-ready-hashes.json` 的 `hashes` 全量对比 —— 是否全等?`_meta.count`(应为 63)是否 == `len(hashes)`?底账文件自身是否正确地**不在**被锁的 63 份里(否则改它就死循环)?

4. **哈希锁真的有牙(对抗验证,别信"3 passed")**:
   - 自己跑 `uv run pytest apps/studio/backend/tests/test_doc_hash_lock.py -q`,确认绿。
   - 对抗:临时给某一档追加一个字节 → 重跑 → 确认测试 **FAIL 且报对了是哪个文件 + expected/got** → `git checkout` 还原 → 再跑确认回绿。
   - 查 exemption 机制(`apps/studio/backend/tests/studio-doc-exemptions.yaml`)逻辑:是否只放行**精确的 file + sha256** 配对,不会误放行其它漂移。

5. **INDEX 一致性 + 不引入新错误声明**:
   - 22 格是否全 `locked`、0 `drafted`?
   - 6 处正文改写后有没有**残留自相矛盾**(全文搜:还有没有"0 进 FROZEN""机器未接""所有 unit-lock=drafted""暂留 drafted"之类)?
   - 改写有没有**引入新的不实声明**?重点核:新写的"spans / owner 已审计复核(R8 双射 22=22、owner 唯一性 PASS)"是否**真成立**——自己数一遍单元表行数是否 22、自己扫"切面 × owner"确认每个切面只有一个 owner(R8 去重铁律)。

6. **跨文档一致性(R0 / R1)**:冻结后,`docs/studio/mvp1/` 里**未冻结**的文档(`README.md`、`01_workflows/`、`01_workflows/00_settings-ux-spec.md`)以及引用这些档的其它地方,有没有现在与"63 档已 FROZEN"矛盾的表述(如别处仍写"全部 drafted""待锁""审计未过")?各档 `binds_code` / 交叉引用在冻结后是否仍成立(没被这次操作弄断)?

7. **治理逻辑自洽(§1.6)**:
   - 被冻结的 63 档与"22 单元 locked"是否**互相支持**:对每个标 `locked` 的单元,它的各切面 owner 所在的内容档是否都在被冻结的 63 份里?有没有哪个单元的某个切面 owner 档其实没被冻结、导致该单元不该宣称 `locked`?
   - `DESIGN_UNITS_INDEX.md` 自身**不入哈希锁**却标 units `locked` —— 这个设计是否站得住(单元锁的强制力是否真来自被冻结的内容档,而非 INDEX 自身)?这算不算"软 FROZEN"漏洞?

## 输出格式(按 `02-audit-standard.md` §四)
- 每条 finding:严重级(**FAIL** / ⚠️ / info)+ 证据(`file:line` 或命令输出)+ 具体问题 + 修复建议。
- 没问题的维度也要明说"**PASS** + 用什么方式验证的"。
- 结尾给**总判**:这次 FROZEN 锁定是否干净、可保留;若有 FAIL,列出必须先修的项。
- 铁律:**宁误报不漏报;每条挂证据;不准只凭上面的描述下结论,必须自己读文件 / 跑命令。**
