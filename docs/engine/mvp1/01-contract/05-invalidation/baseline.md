---
module: 01-contract/05-invalidation
doc: baseline
status: audited-ready（B 成段:对当前 packages/graph-agent grep 核 2026-06-05 + codex 复审修正;live=compile cache(.md mtime/size)+ golden hash 比对 warn(退役标的);diff_skill/ChangeAxis 未实现;编译期 golden 硬错误码从未落地）
binds_alignment: ./mvp1-alignment.md
binds_code: packages/graph-agent/src/graph_agent/core/cache.py:compute_cache_key · core/compiler.py:compile_skill · core/runner.py:_warn_on_stale_golden_hashes_sdk
---

# 05-invalidation — Baseline(当下代码实现逻辑)

> **Scope**: "源变更 → 派生物失效"的**现状代码**:三类派生物(compile cache / golden / checkpoint)各自当前怎么(不)处理失效。alignment 的统一变更轴 `diff_skill(old,new)->set[ChangeAxis]` 是**目标**,当前**未实现**。
> **现状一句话**:当前只有**两件 live 的失效相关代码**——① **compile cache**:`core/cache.py`(`compute_cache_key`/`load_from_cache`/`save_to_cache`)+ `compiler.py:compile_skill`,key = `GRAPH.md` + `phases/**/*.md` 的 **mtime+size**(非内容 hash);② **golden hash 比对 warn**:`runner.py:_warn_on_stale_golden_hashes_sdk` 比 **`prompt_hash` + `io_outputs_schema_hash` 两个独立哈希**,任一变即 warn(不 block),正是 alignment IV3 的**退役标的**(改 prompt 即误报)。统一 `diff_skill`/`ChangeAxis`、checkpoint 置灰、eval 期 A2a golden 失效**均未实现**;旧 records 说的"编译期硬错误 `[F-v3-golden-stale-fields]`"**从未落地**(`error_registry` 无任何 golden 码)。

## UI/UX
N/A。

## 前端逻辑
N/A —— checkpoint 失效的 `[Resume]` 置灰是 studio 侧消费,engine 只供失效判定(待 `diff_skill`)。

## 后端功能

### 1. compile cache 失效(live)
- `core/cache.py:compute_cache_key`(:25):cache key = `payload` 的 sha256,`payload` = `{format:"v2", root, python 版本, graph-agent package 版本, files}`(:27)。`files` 由 `_skill_file_metadata`(:71)产出,逐文件取 **`(相对路径, st_mtime_ns, st_size)`——即 mtime+size,非内容 hash**;文件集 `_collect_skill_files`(:59)**只收 `GRAPH.md` + `phases/**/*.md`**。
- `load_from_cache`(:38)按 key 读 `<cache_dir>/<key>.json`;`save_to_cache`(:50)写回。
- `core/compiler.py:compile_skill`(:41)消费:`cache: bool=True`(:45);命中 key 则 `load_from_cache` 直接返回(:57),否则编译完 `save_to_cache`(:64)。
- 失效语义:**`GRAPH.md` / `phases/**/*.md` 的 mtime 或 size 变 → key 变 → 透明重编**(无感;消费者矩阵的 "compile cache" 行)。
- ⚠️ **缺口**:action/tool `.py`(编译期经 `core/loader.py:_discover_actions_and_tools`:219 加载)**不在 cache key 文件集**——改 `.py` 不改任何 `.md` 的 mtime,cache 仍命中旧编译产物、不失效。现状漏洞,记 refactor-target。

### 2. golden 失效(现状 = hash 比对 warn,退役标的)
- `core/runner.py:_warn_on_stale_golden_hashes_sdk`(:127,签名 `(strategy, current_hashes) -> None`;`predict_skill` 路径 `runner.py:246` 调用):逐 phase 比对 golden case metadata 的 **`prompt_hash`(:146)与 `io_outputs_schema_hash`(:147)两个独立哈希**(分别来自 `core/_predict_internal/hash.py:prompt_hash`:13 / `schema_hash`:21),**任一不一致**即 `logger.warning`(:152)——**不 block**(:248 继续执行)。
- ⚠️ **这是 alignment IV3 的退役标的**:它比 `prompt_hash` 使**改 prompt(A1)就触发 stale warn**——但 prompt 改不使"已填的期望值"失效,属误报;粒度太粗。mvp1 用"只看 A2a 必填字段、eval 期"取代(归 `06-golden-eval`)。
- ⚠️ **旧"编译期硬错误"模型从未落地**:records §2 称 golden stale = 编译期硬错误 `[F-v3-golden-stale-fields]`,但全包 grep 确认 `error_registry` 中**无此码、也无任何 golden 域码**(未知码会被 `core/exceptions.py:37` 拒)——live 只有上面的 hash 比对 warn。golden→workspace 反转后(IV2),失效校验移到 **eval 期**(`06-golden-eval`),编译期读不到 `.workspace`。

### 3. checkpoint 失效(engine 侧未实现)
- alignment 矩阵:checkpoint 关心 A2/A4/A5,resume 期下游置脏 → studio `[Resume]` 置灰(软)。
- 现状:engine 无 checkpoint 失效判定代码(依赖未实现的 `diff_skill` + 拓扑依赖分析);resume 置灰目前是 studio 侧编排。

### 4. 统一变更检测(未实现)
- alignment 目标 `diff_skill(old,new)->set[ChangeAxis]` + `ChangeAxis` 枚举(A1–A5)**当前不存在**(全包 grep `diff_skill`/`ChangeAxis` 为空)。归 kiro 实施(alignment §8 #1,TDD)。

## API
- compile cache 入口:`core/compiler.py:compile_skill`(`cache` 参数)。
- (统一失效检测 `diff_skill` 待实现,届时为各消费者订阅入口。)

## Data Model / State
- cache key:`core/cache.py:compute_cache_key`(version 信息 + `GRAPH.md`/`phases/**/*.md` 的 mtime+size)。
- golden hash(退役):golden case metadata 的 `prompt_hash` + `io_outputs_schema_hash`(`hash.py`)。
- (`ChangeAxis` 枚举待定义。)

## 当前边界(这个模块现在不是什么)
- **现状非"一套变更轴 + 多消费者"**:只有 compile cache(`.md` mtime/size)+ golden hash 比对 warn 两件孤立逻辑,无统一 `ChangeAxis`/`diff_skill`。
- **golden 失效现状 = warn 非 block**,且比 prompt_hash+schema_hash 两哈希(退役标的);eval 期 A2a 失效未实现。
- checkpoint 失效判定在 engine 侧未落地。

## baseline / alignment 差异(测试锚点)
| 维度 | 现状(baseline) | mvp1 目标(alignment) |
|---|---|---|
| 统一变更轴 | 无 `ChangeAxis`/`diff_skill`;cache 与 golden 各自为政 | 一套 A1–A5 轴 + `diff_skill`,消费者各取子集(IV1) |
| golden 失效粒度 | 比 `prompt_hash` + `io_outputs_schema_hash` 两哈希,任一变即 warn(改 prompt 即误报) | 仅 A2a 必填字段;hash warn 退役(IV3) |
| golden 失效时机 | warn 在 predict 路径(runner);旧 records 设想编译期硬错误(**从未落地**) | **eval 期**(golden 在 `.workspace`,compile 读不到;IV2) |
| checkpoint 失效 | engine 无判定 | A2/A4/A5 → resume 置灰(待 `diff_skill`) |
| compile cache | ✅ live(`GRAPH.md`/`phases/**/*.md` mtime/size 重编;⚠️ action/tool `.py` 不在 key) | ♻️ 沿用 + 补 `.py` 入 key(消缺口) |

> **验"是否按 mvp1 改了"**:① `ChangeAxis`/`diff_skill` 实现且单测 A1–A5;② golden 失效只看 A2a、在 eval 期(非 hash 比对 warn、非编译期);③ `_warn_on_stale_golden_hashes_sdk` 退役;④ checkpoint 置灰按 A2/A4/A5;⑤ action/tool `.py` 纳入 cache key。

## 读代码主路径提示
cache: `core/cache.py`(`compute_cache_key` → `_skill_file_metadata`/`_collect_skill_files`)→ `core/compiler.py:compile_skill`(:57-65)。golden hash 比对(退役):`core/runner.py:_warn_on_stale_golden_hashes_sdk`(:127 → 调用 :246;hash 来自 `_predict_internal/hash.py`)。统一 `diff_skill`:待实施。

## 交叉引用(链接, 不复制)
[mvp1-alignment](./mvp1-alignment.md)(目标:变更轴+消费者矩阵)· `05-run-inner/06-golden-eval`(golden 失效 eval 期落点)· `04-run-outer/03-checkpoint`(checkpoint 失效)· `02-mechanism/01-compile`(cache 实现)· `03-compile-rules`(CR3 golden-stale 码归属)
